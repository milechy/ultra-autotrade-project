# backend/app/aave/service.py

"""
Aave 運用ロジックのサービス層。

責務:
- TradeAction(BUY/SELL/HOLD) を AaveOperationType(DEPOSIT/WITHDRAW/NOOP) に変換
- docs/07_aave_operation_logic.md の基本ルールを実装
- docs/08_automation_rules.md / 13_security_design.md のリスク制御を意識
- エラー時は「ポジションを増やさない」ことを最優先
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from app.ai.schemas import TradeAction
from app.automation.monitoring_service import MonitoringService
from app.automation.state import get_monitoring_service

from .client import AaveClient, AaveClientError, get_default_aave_client
from .config import AaveSettings, get_aave_settings
from .schemas import (
    AaveOperationMode,
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)
from .state_manager import AaveStateManager, get_default_state_manager

logger = logging.getLogger(__name__)


class RiskLimitError(Exception):
    """
    リスク制限を超えた操作を行おうとした場合の例外。

    NOTE:
    - 現時点の実装では通常の「スキップ」は例外ではなく NOOP として扱い、
      本例外は「明らかに入力が不正な場合」などに限定して使う想定。
    """


class AaveService:
    """
    Aave への実際の操作をまとめるサービス層。

    - BUY → deposit
    - SELL → withdraw
    - HOLD → 何もしない(NOOP)
    - 10分以内の連続トレードを抑制
    - ヘルスファクターがしきい値未満の場合、BUY を抑制
    """

    def __init__(
        self,
        client: AaveClient | None = None,
        settings: AaveSettings | None = None,
        monitoring_service: Optional[MonitoringService] = None,
        state_manager: Optional[AaveStateManager] = None,
    ) -> None:
        self._client: AaveClient = client or get_default_aave_client()
        self._settings: AaveSettings = settings or get_aave_settings()

        # 監視・緊急停止ロジック
        self._monitoring: MonitoringService = monitoring_service or get_monitoring_service()

        # state.json 管理
        self._state_manager: AaveStateManager = state_manager or get_default_state_manager()

        # 直近のトレード時刻を記録する（単純なリストで十分）
        self._recent_actions: List[datetime] = []

    # ---- 内部ヘルパー -------------------------------------------------

    def _now(self) -> datetime:
        """テストしやすさのために現在時刻取得をメソッド化。"""
        return datetime.now(timezone.utc)

    def _cleanup_recent_actions(self, now: datetime) -> None:
        """トレードクールダウン期間外の履歴を破棄する。"""
        window_start = now - timedelta(seconds=self._settings.trade_cooldown_seconds)
        self._recent_actions = [ts for ts in self._recent_actions if ts >= window_start]

    def _is_in_cooldown(self, now: datetime) -> bool:
        """
        クールダウン時間内にトレードが行われているかどうかを判定する。
        """
        self._cleanup_recent_actions(now)
        return len(self._recent_actions) > 0

    def _normalize_amount(self, amount: Decimal) -> Decimal:
        """
        入力金額を検証・正規化する。

        - 0 以下なら ValueError
        - 上限を超えていれば max_single_trade_usd までにクリップ
        """
        if amount <= 0:
            raise ValueError("amount must be greater than 0")

        if amount > self._settings.max_single_trade_usd:
            return self._settings.max_single_trade_usd

        return amount

    @staticmethod
    def _normalize_action_value(action: TradeAction | str) -> str:
        """
        TradeAction/str のどちらにも対応したアクション文字列の正規化。
        """
        if hasattr(action, "value"):
            return str(getattr(action, "value")).upper()
        return str(action).upper()

    def _decide_operation(
        self,
        action: TradeAction,
        now: datetime,
        health_factor: Optional[Decimal],
    ) -> AaveOperationType:
        """
        BUY/SELL/HOLD と現在の状態から、DEPOSIT/WITHDRAW/NOOP を決定する。
        """
        action_val = self._normalize_action_value(action)

        # HOLD は常に NOOP
        if action_val == "HOLD":
            return AaveOperationType.NOOP

        # 連続トレード制限（10分以内に 1回まで）
        if self._is_in_cooldown(now):
            logger.info("Trade skipped by cooldown rule.")
            return AaveOperationType.NOOP

        # ヘルスファクターがしきい値を下回っているときの BUY 抑制
        if (
            health_factor is not None
            and health_factor < self._settings.min_health_factor
            and action_val == "BUY"
        ):
            logger.warning(
                "Trade skipped because health factor is below threshold: %s", health_factor
            )
            return AaveOperationType.NOOP

        # 基本ルール
        if action_val == "BUY":
            return AaveOperationType.DEPOSIT
        if action_val == "SELL":
            return AaveOperationType.WITHDRAW

        # 想定外の値は NOOP として安全側に倒す
        logger.warning("Unknown action %s; treating as NOOP.", action_val)
        return AaveOperationType.NOOP

    # ---- 公開メソッド -------------------------------------------------

    def execute_rebalance(
        self,
        action: TradeAction,
        amount: Decimal,
        asset_symbol: str | None = None,
        dry_run: bool = False,
    ) -> AaveOperationResult:
        """
        BUY/SELL/HOLD に応じて Aave 上のポジションを調整するメイン処理。

        :param action: AI もしくは OctoBot からのアクション（BUY/SELL/HOLD）
        :param amount: 希望するトレード金額（USD 相当）
        :param asset_symbol: 対象トークン。None の場合は設定値のデフォルトを使用。
        :param dry_run: True の場合は実際のトランザクションを送信しない。
        """
        token = asset_symbol or self._settings.default_asset_symbol

        # 1. state.json の stale チェック（最優先）
        if self._state_manager.is_stale():
            logger.warning("state.json is stale; forcing NOOP for safety")
            return AaveOperationResult(
                operation=AaveOperationType.NOOP,
                status=AaveOperationStatus.SKIPPED,
                asset_symbol=token,
                amount=Decimal("0"),
                tx_hash=None,
                message="state.json is stale; no Aave operation executed.",
                before_health_factor=None,
                after_health_factor=None,
            )

        # 2. state.json からモード取得
        state = self._state_manager.read_state()
        mode = state.mode
        action_val = self._normalize_action_value(action)

        # 3. emergency_stop のチェック（P1対応）
        if state.emergency_stop:
            logger.warning("emergency_stop is True in state.json; forcing NOOP")
            return AaveOperationResult(
                operation=AaveOperationType.NOOP,
                status=AaveOperationStatus.SKIPPED,
                asset_symbol=token,
                amount=Decimal("0"),
                tx_hash=None,
                message="emergency_stop is True; all Aave operations are blocked.",
                before_health_factor=state.health_factor,
                after_health_factor=state.health_factor,
            )

        # 4. circuit_closed のチェック（P1対応）
        if not state.circuit_closed:
            logger.warning("circuit_closed is False in state.json; forcing NOOP")
            return AaveOperationResult(
                operation=AaveOperationType.NOOP,
                status=AaveOperationStatus.SKIPPED,
                asset_symbol=token,
                amount=Decimal("0"),
                tx_hash=None,
                message="circuit_closed is False; all Aave operations are blocked.",
                before_health_factor=state.health_factor,
                after_health_factor=state.health_factor,
            )

        # 5. モード別の制御
        if mode == AaveOperationMode.HARD_STOP:
            logger.warning("Mode=%s: all operations are blocked", mode.value)
            return AaveOperationResult(
                operation=AaveOperationType.NOOP,
                status=AaveOperationStatus.SKIPPED,
                asset_symbol=token,
                amount=Decimal("0"),
                tx_hash=None,
                message=f"Mode={mode.value}: all Aave operations are blocked.",
                before_health_factor=state.health_factor,
                after_health_factor=state.health_factor,
            )

        if mode == AaveOperationMode.SAFE_MODE and action_val == "BUY":
            logger.warning("Mode=%s: BUY is blocked", mode.value)
            return AaveOperationResult(
                operation=AaveOperationType.NOOP,
                status=AaveOperationStatus.SKIPPED,
                asset_symbol=token,
                amount=Decimal("0"),
                tx_hash=None,
                message=f"Mode={mode.value}: BUY is blocked; only SELL/HOLD allowed.",
                before_health_factor=state.health_factor,
                after_health_factor=state.health_factor,
            )

        # まず入力バリデーションを行う（負の金額などはここで ValueError）
        normalized_amount = self._normalize_amount(amount)

        now = self._now()

        # 監視ロジック側で緊急停止中の場合は、ポジションを増やさない
        if (
            hasattr(self, "_monitoring")
            and self._monitoring is not None
            and not self._monitoring.is_trading_allowed()
        ):
            logger.warning("Trading is paused by MonitoringService emergency stop. Forcing NOOP.")
            return AaveOperationResult(
                operation=AaveOperationType.NOOP,
                status=AaveOperationStatus.SKIPPED,
                asset_symbol=token,
                amount=Decimal("0"),
                tx_hash=None,
                message="Trading is paused by emergency mode. No Aave operation executed.",
                before_health_factor=None,
                after_health_factor=None,
            )

        # ヘルスファクター取得（失敗してもエラーにはせず、None として扱う）
        before_hf: Optional[Decimal]
        try:
            before_hf = self._client.get_health_factor()
        except AaveClientError as exc:
            logger.error("Failed to fetch health factor: %s", exc)
            before_hf = None

        # 取得したヘルスファクターを監視ロジックへ連携
        if hasattr(self, "_monitoring") and self._monitoring is not None:
            hf_status = self._monitoring.record_health_factor(before_hf, at=now)
            # 緊急停止レベルまで悪化している場合、BUY は NOOP として扱う
            if hf_status.is_emergency and action == TradeAction.BUY:
                logger.warning(
                    "Emergency stop triggered by health factor. Skipping BUY and returning NOOP."
                )
                return AaveOperationResult(
                    operation=AaveOperationType.NOOP,
                    status=AaveOperationStatus.SKIPPED,
                    asset_symbol=token,
                    amount=Decimal("0"),
                    tx_hash=None,
                    message="Emergency stop: BUY skipped because health factor is too low.",
                    before_health_factor=before_hf,
                    after_health_factor=before_hf,
                )

        operation = self._decide_operation(action, now, before_hf)

        # NOOP の場合は一切トランザクションを送らずに終了
        if operation is AaveOperationType.NOOP:
            return AaveOperationResult(
                operation=operation,
                status=AaveOperationStatus.SKIPPED,
                asset_symbol=token,
                amount=Decimal("0"),
                tx_hash=None,
                message="Operation was skipped by safety rules (HOLD / cooldown / health factor).",
                before_health_factor=before_hf,
                after_health_factor=before_hf,
            )

        # dry_run の場合は tx_hash を None とした成功扱い
        if dry_run:
            return AaveOperationResult(
                operation=operation,
                status=AaveOperationStatus.SUCCESS,
                asset_symbol=token,
                amount=normalized_amount,
                tx_hash=None,
                message="Dry-run: no transaction was sent to Aave.",
                before_health_factor=before_hf,
                after_health_factor=before_hf,
            )

        # 実際の deposit / withdraw 呼び出し
        try:
            if operation is AaveOperationType.DEPOSIT:
                tx_hash = self._client.deposit(token, normalized_amount)
            elif operation is AaveOperationType.WITHDRAW:
                tx_hash = self._client.withdraw(token, normalized_amount)
            else:
                # ここに来ることは想定していないが、安全側で NOOP とする
                logger.warning("Unexpected operation %s; treating as NOOP.", operation)
                return AaveOperationResult(
                    operation=AaveOperationType.NOOP,
                    status=AaveOperationStatus.SKIPPED,
                    asset_symbol=token,
                    amount=Decimal("0"),
                    tx_hash=None,
                    message="Unexpected operation type; treated as NOOP.",
                    before_health_factor=before_hf,
                    after_health_factor=before_hf,
                )
        except AaveClientError as exc:
            logger.error("Aave client error during %s: %s", operation, exc)
            # 失敗時は「ポジションを増やさない」ことを保証する。
            return AaveOperationResult(
                operation=operation,
                status=AaveOperationStatus.ERROR,
                asset_symbol=token,
                amount=Decimal("0"),
                tx_hash=None,
                message="Aave client error; no position was changed.",
                before_health_factor=before_hf,
                after_health_factor=before_hf,
            )

        # 正常終了：クールダウン用に履歴を記録
        self._recent_actions.append(now)

        return AaveOperationResult(
            operation=operation,
            status=AaveOperationStatus.SUCCESS,
            asset_symbol=token,
            amount=normalized_amount,
            tx_hash=tx_hash,
            message="Aave operation executed successfully.",
            before_health_factor=before_hf,
            after_health_factor=before_hf,
        )


class MultiChainAaveService:
    """
    チェーンごとに独立した AaveService を管理するマルチチェーンサービス。

    各チェーンの Health Factor は独立して管理され、
    1 つのチェーンの HARD_STOP が他チェーンに影響しない。
    """

    def __init__(
        self,
        services: dict[str, AaveService] | None = None,
    ) -> None:
        # services が明示的に渡された場合はそのまま使用する。
        # None の場合は初回アクセス時に遅延初期化する（lazy init）。
        # これにより、RPC URL 未設定環境でも __init__ 時点では ValueError が発生しない。
        self._services: dict[str, AaveService] | None = services

    def _get_services(self) -> dict[str, AaveService]:
        """チェーンサービスマップを遅延初期化して返す。"""
        if self._services is None:
            from .client import make_multi_chain_clients
            from .config import get_multi_chain_settings

            clients = make_multi_chain_clients()
            settings_map = get_multi_chain_settings()
            self._services = {
                name: AaveService(client=client, settings=settings_map[name])  # type: ignore[arg-type]
                for name, client in clients.items()
            }
        return self._services

    def get_chain_names(self) -> list[str]:
        """アクティブなチェーン名の一覧を返す。"""
        return list(self._get_services().keys())

    def get_service(self, chain_name: str) -> AaveService:
        """
        指定チェーンの AaveService を取得する。

        :raises KeyError: 存在しないチェーン名の場合
        """
        services = self._get_services()
        if chain_name not in services:
            available = ", ".join(sorted(services.keys()))
            raise KeyError(f"チェーン {chain_name!r} は存在しません。利用可能: {available}")
        return services[chain_name]

    def execute_rebalance(
        self,
        chain_name: str,
        action: TradeAction,
        amount: Decimal,
        asset_symbol: str | None = None,
        dry_run: bool = False,
    ) -> AaveOperationResult:
        """
        指定チェーンでリバランスを実行する。

        :param chain_name: 対象チェーン名
        """
        service = self.get_service(chain_name)
        return service.execute_rebalance(
            action=action,
            amount=amount,
            asset_symbol=asset_symbol,
            dry_run=dry_run,
        )

    def get_all_health_factors(self) -> dict[str, Optional[Decimal]]:
        """
        全アクティブチェーンの Health Factor を取得する。

        各チェーンは独立して問い合わせ、1 つのチェーンの失敗が
        他のチェーンに影響しない。失敗したチェーンの値は None。
        """
        result: dict[str, Optional[Decimal]] = {}
        for name, service in self._get_services().items():
            try:
                hf = service._client.get_health_factor()
                result[name] = hf
            except Exception:
                logger.error("Failed to get health factor for chain %s", name, exc_info=True)
                result[name] = None
        return result
