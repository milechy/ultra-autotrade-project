# backend/app/aave/state_manager.py

"""
Aave システム状態ファイル（state.json）の管理モジュール。

- state.json の読み書き（atomic write）
- 状態の鮮度チェック
- デフォルト状態の生成
"""

import json
import logging
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from app.aave.config import get_aave_settings
from app.aave.schemas import AaveOperationMode, AaveSystemState

logger = logging.getLogger(__name__)


def _model_to_json(model: AaveSystemState) -> str:
    """Pydantic v1/v2 互換の JSON シリアライズ。"""
    if hasattr(model, "model_dump_json"):
        # Pydantic v2
        return model.model_dump_json(indent=2)
    else:
        # Pydantic v1
        return model.json(indent=2)


def get_default_state() -> AaveSystemState:
    """
    デフォルトのシステム状態を生成する。

    初期状態は NORMAL モード、緊急停止なし、Circuit Breaker 閉（動作可）。
    初回起動時（state.json が存在しない場合）に使用。
    """
    settings = get_aave_settings()
    return AaveSystemState(
        emergency_stop=False,
        mode=AaveOperationMode.NORMAL,
        health_factor=None,
        last_update=datetime.now(timezone.utc),
        reason=None,
        circuit_closed=True,
        stale_threshold_seconds=settings.state_stale_threshold_seconds,
    )


def get_safe_default_state() -> AaveSystemState:
    """
    安全側のデフォルト状態を生成する（パースエラー時用）。

    パースエラー = ファイルが壊れている = 情報が不明
    → 安全側に倒して全操作をブロックする（fail-closed）

    - emergency_stop=True: 緊急停止状態
    - mode=HARD_STOP: 全操作をブロック
    - circuit_closed=False: Circuit Breaker も開いた状態
    """
    settings = get_aave_settings()
    return AaveSystemState(
        emergency_stop=True,
        mode=AaveOperationMode.HARD_STOP,
        health_factor=None,
        last_update=datetime.now(timezone.utc),
        reason="state.json parse error - fail-closed for safety",
        circuit_closed=False,
        stale_threshold_seconds=settings.state_stale_threshold_seconds,
    )


class StateFileNotFoundError(Exception):
    """state.json が存在しない場合の例外（初回起動時）。"""


class StateFileParseError(Exception):
    """state.json のパースに失敗した場合の例外。"""


def read_system_state() -> AaveSystemState:
    """
    state.json からシステム状態を読み込む。

    Returns:
        AaveSystemState: 読み込みに成功した場合

    Raises:
        StateFileNotFoundError: ファイルが存在しない場合（初回起動）
        StateFileParseError: パースエラーや読み取りエラーの場合
    """
    settings = get_aave_settings()
    state_path = Path(settings.state_file_path)

    try:
        if not state_path.exists():
            logger.info("State file does not exist: %s (initial startup)", state_path)
            raise StateFileNotFoundError(f"State file not found: {state_path}")

        with state_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return AaveSystemState(**data)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse state file %s: %s", state_path, e)
        raise StateFileParseError(f"JSON decode error: {e}") from e
    except ValidationError as e:
        logger.error("Invalid state file schema %s: %s", state_path, e)
        raise StateFileParseError(f"Schema validation error: {e}") from e
    except OSError as e:
        if isinstance(e, FileNotFoundError):
            logger.info("State file does not exist: %s (initial startup)", state_path)
            raise StateFileNotFoundError(f"State file not found: {state_path}") from e
        logger.error("Failed to read state file %s: %s", state_path, e)
        raise StateFileParseError(f"OS error: {e}") from e


def write_system_state(state: AaveSystemState) -> None:
    """
    state.json にシステム状態を書き込む（atomic write）。

    - 一時ファイルに書いてから rename することで原子性を保証
    - ファイル権限は 600（owner のみ読み書き可能）
    - ディレクトリが存在しない場合は自動作成

    Raises:
        OSError: 書き込みに失敗した場合
    """
    settings = get_aave_settings()
    state_path = Path(settings.state_file_path)

    # ディレクトリが存在しない場合は作成
    state_dir = state_path.parent
    if not state_dir.exists():
        logger.info("Creating state directory: %s", state_dir)
        state_dir.mkdir(parents=True, mode=0o755, exist_ok=True)

    # JSON シリアライズ（Pydantic v1/v2 互換）
    state_json = _model_to_json(state)

    # 同一ディレクトリ内に一時ファイルを作成（rename の原子性のため）
    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix="state_",
            dir=str(state_dir),
        )

        # 一時ファイルに書き込み
        os.write(fd, state_json.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        fd = None

        # 権限を 600 に設定
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)

        # atomic rename
        os.rename(tmp_path, state_path)
        tmp_path = None

        logger.debug("Successfully wrote state file: %s", state_path)

    except OSError as e:
        logger.error("Failed to write state file %s: %s", state_path, e)
        raise

    finally:
        # クリーンアップ
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path is not None and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def is_state_stale(state: AaveSystemState) -> bool:
    """
    状態が古い（stale）かどうかを判定する。

    last_update から stale_threshold_seconds 以上経過している場合は True。

    Args:
        state: チェック対象のシステム状態

    Returns:
        bool: 状態が古い場合は True
    """
    now = datetime.now(timezone.utc)

    # last_update が timezone-aware でない場合は UTC として扱う
    last_update = state.last_update
    if last_update.tzinfo is None:
        last_update = last_update.replace(tzinfo=timezone.utc)

    elapsed_seconds = (now - last_update).total_seconds()
    return elapsed_seconds > state.stale_threshold_seconds


class AaveStateManager:
    """
    state.json の読み書きを行うマネージャクラス。

    AaveService への依存性注入用。テスト時にモックを渡しやすくする。

    自動回復機能:
    - 一時的なパースエラーから自動回復を試みる
    - 連続エラーが閾値を超えた場合は fail-closed モードに移行
    - 閾値超過後は RETRY_INTERVAL_SECONDS ごとに再読み取りを試みる
    """

    MAX_CONSECUTIVE_ERRORS = 3  # 連続エラー回数の閾値
    RETRY_INTERVAL_SECONDS = 60  # 閾値超過後のリトライ間隔（秒）

    def __init__(self) -> None:
        self._last_read_error: Optional[Exception] = None
        self._consecutive_errors: int = 0
        self._last_retry_attempt: Optional[datetime] = None

    def _now(self) -> datetime:
        """テストしやすさのために現在時刻取得をメソッド化。"""
        return datetime.now(timezone.utc)

    def read_state(self) -> AaveSystemState:
        """
        state.json を読み込み、AaveSystemState を返す。

        ファイルが存在しない場合はデフォルト状態を返す（初回起動）。
        パースエラー時もデフォルト状態を返すが、_last_read_error を記録。
        """
        try:
            state = read_system_state()
            # 成功時はエラーフラグをクリア
            self._last_read_error = None
            self._consecutive_errors = 0
            return state
        except StateFileNotFoundError:
            # 初回起動：エラーではない
            self._last_read_error = None
            self._consecutive_errors = 0
            return get_default_state()
        except StateFileParseError as e:
            # パースエラー：fail-closed のため安全側デフォルトを使用
            self._last_read_error = e
            self._consecutive_errors += 1
            logger.warning(
                "State file parse error (consecutive=%d), using SAFE default (fail-closed): %s",
                self._consecutive_errors,
                e,
            )
            return get_safe_default_state()

    def is_stale(self) -> bool:
        """
        現在の state.json が古い（stale）かどうかを判定する。

        判定ルール:
        1. 前回パースエラーがあった場合:
           a. 連続エラー回数が閾値未満 → 再読み取りを試みて回復を試行
           b. 連続エラー回数が閾値以上 → stale として扱う（fail-closed）
        2. ファイルが存在しない → NOT stale（初回起動は正常）
        3. ファイルは存在するが古い → stale
        """
        # 1. 前回のパースエラーチェック
        if self._last_read_error is not None:
            now = self._now()

            # 連続エラーが閾値を超えている場合
            if self._consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                # リトライ間隔をチェック
                if self._last_retry_attempt is not None:
                    elapsed = (now - self._last_retry_attempt).total_seconds()
                    if elapsed < self.RETRY_INTERVAL_SECONDS:
                        # まだ間隔内 → 再読み取りせずに stale 返却
                        logger.debug(
                            "state.json retry throttled: %d consecutive errors, "
                            "%.1f seconds since last retry (interval=%d)",
                            self._consecutive_errors,
                            elapsed,
                            self.RETRY_INTERVAL_SECONDS,
                        )
                        return True

                # 間隔経過 or 初回リトライ → 再読み取りを試みる
                logger.info(
                    "state.json retry interval elapsed (%d consecutive errors); "
                    "attempting recovery",
                    self._consecutive_errors,
                )
                self._last_retry_attempt = now

                try:
                    state = read_system_state()
                    # 成功 → エラーフラグをクリア
                    self._last_read_error = None
                    self._consecutive_errors = 0
                    self._last_retry_attempt = None
                    logger.info(
                        "state.json successfully recovered from persistent error"
                    )
                    return is_state_stale(state)
                except StateFileNotFoundError:
                    # ファイルが削除された → 初回起動扱い
                    logger.info(
                        "state.json was deleted; treating as NOT stale "
                        "(reset to initial state)"
                    )
                    self._last_read_error = None
                    self._consecutive_errors = 0
                    self._last_retry_attempt = None
                    return False
                except StateFileParseError as e:
                    # まだ壊れている → stale
                    self._last_read_error = e
                    # 閾値超過後はカウントを増やさない（既に上限）
                    logger.warning(
                        "state.json still has parse error on throttled retry: %s; "
                        "treating as stale",
                        e,
                    )
                    return True

            # 連続エラーが閾値未満 → 即座に再読み取りを試みる（自動回復）
            logger.info(
                "Previous read error detected (consecutive=%d); "
                "attempting recovery by re-reading state.json",
                self._consecutive_errors,
            )
            try:
                state = read_system_state()
                # 成功 → エラーフラグをクリア
                self._last_read_error = None
                self._consecutive_errors = 0
                logger.info("state.json successfully recovered from previous error")
                # タイムスタンプチェックへ進む
                return is_state_stale(state)
            except StateFileNotFoundError:
                # ファイルが削除された → 初回起動扱い
                logger.info(
                    "state.json was deleted; treating as NOT stale (reset to initial state)"
                )
                self._last_read_error = None
                self._consecutive_errors = 0
                return False
            except StateFileParseError as e:
                # まだ壊れている → stale
                self._last_read_error = e
                self._consecutive_errors += 1
                logger.warning(
                    "state.json still has parse error on retry (consecutive=%d): %s; "
                    "treating as stale",
                    self._consecutive_errors,
                    e,
                )
                return True

        # 2. エラーフラグなし → 通常の読み取り
        try:
            state = read_system_state()
        except StateFileNotFoundError:
            # ファイルが存在しない = 初回起動 → NOT stale
            logger.info("state.json not found; treating as NOT stale (initial startup)")
            return False
        except StateFileParseError as e:
            # パースエラー = 壊れている → stale (fail-closed)
            self._last_read_error = e
            self._consecutive_errors = 1
            logger.warning(
                "state.json parse error in is_stale(): %s; treating as stale", e
            )
            return True

        # 3. タイムスタンプチェック
        return is_state_stale(state)


# シングルトンインスタンス
_default_state_manager: Optional[AaveStateManager] = None


def get_default_state_manager() -> AaveStateManager:
    """
    デフォルトの AaveStateManager インスタンスを返す。

    シングルトンとして動作。
    """
    global _default_state_manager
    if _default_state_manager is None:
        _default_state_manager = AaveStateManager()
    return _default_state_manager
