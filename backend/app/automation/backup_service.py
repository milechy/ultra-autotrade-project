# backend/app/automation/backup_service.py
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class BackupTargetType(str, Enum):
    """
    バックアップ対象の種別。

    Phase6 時点では:
    - NOTION: Notion 側のニュースデータやメタ情報
    - AI_ANALYSIS: AI 判定結果
    - TRADES: 取引履歴やポジション情報

    実際にどのようなストレージに書き出すかは、呼び出し側から注入される
    バックアップ関数に委ねる。
    """

    NOTION = "notion"
    AI_ANALYSIS = "ai_analysis"
    TRADES = "trades"


class BackupStatus(str, Enum):
    """
    バックアップ全体のステータス。
    """

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


class BackupItemResult(BaseModel):
    """
    各バックアップ対象ごとの結果。
    """

    target: BackupTargetType = Field(..., description="バックアップ対象の種別")
    items_backed_up: int = Field(
        0,
        ge=0,
        description="バックアップされたレコード件数。失敗した場合は 0。",
    )
    error: Optional[str] = Field(
        None,
        description="失敗した場合のエラーメッセージ（成功時は None）。",
    )


class BackupResult(BaseModel):
    """
    バックアップ全体の結果。
    """

    started_at: datetime = Field(..., description="バックアップ開始時刻（UTC 推奨）")
    finished_at: datetime = Field(..., description="バックアップ終了時刻（UTC 推奨）")
    status: BackupStatus = Field(..., description="全体のステータス")
    items: List[BackupItemResult] = Field(
        default_factory=list,
        description="各バックアップ対象の結果一覧。",
    )
    message: str = Field(
        ...,
        description="人間向けのサマリーメッセージ。",
    )


BackupHandler = Callable[[], int]
"""バックアップを実行し、バックアップした件数を返すコールバック型。"""


class BackupService:
    """
    自動バックアップ処理を統括するサービス。

    実際の I/O（ファイル出力・外部ストレージ・Notion API など）は行わず、
    呼び出し側から渡されたコールバックを順に実行して結果を集約する。

    これにより:
    - ユニットテストでは純粋に件数を返すダミー関数を渡せる
    - 本番コードでは Notion / DB / ファイル書き込みの実処理を注入できる
    """

    def __init__(
        self,
        backup_notion: Optional[BackupHandler] = None,
        backup_ai_analysis: Optional[BackupHandler] = None,
        backup_trades: Optional[BackupHandler] = None,
    ) -> None:
        self._handlers: Dict[BackupTargetType, BackupHandler] = {}
        if backup_notion is not None:
            self._handlers[BackupTargetType.NOTION] = backup_notion
        if backup_ai_analysis is not None:
            self._handlers[BackupTargetType.AI_ANALYSIS] = backup_ai_analysis
        if backup_trades is not None:
            self._handlers[BackupTargetType.TRADES] = backup_trades

    @property
    def has_handlers(self) -> bool:
        """
        1つ以上のバックアップハンドラが登録されているかどうか。
        """
        return bool(self._handlers)

    def run_backup(self) -> BackupResult:
        """
        登録された全バックアップ処理を順に実行し、結果をまとめて返す。

        例外が発生した場合は:
        - その対象の BackupItemResult.error にエラーメッセージを格納
        - 他の対象のバックアップは継続する
        """
        started_at = datetime.now(timezone.utc)

        item_results: List[BackupItemResult] = []

        for target, handler in self._handlers.items():
            try:
                count = int(handler() or 0)
                item_results.append(
                    BackupItemResult(
                        target=target,
                        items_backed_up=count,
                        error=None,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - バックアップ失敗しても他は続行
                item_results.append(
                    BackupItemResult(
                        target=target,
                        items_backed_up=0,
                        error=str(exc),
                    )
                )

        finished_at = datetime.now(timezone.utc)

        if not item_results:
            status = BackupStatus.FAILURE
            message = "No backup handlers configured. Nothing was backed up."
        else:
            any_error = any(item.error for item in item_results)
            all_error = all(item.error for item in item_results)

            if all_error:
                status = BackupStatus.FAILURE
            elif any_error:
                status = BackupStatus.PARTIAL
            else:
                status = BackupStatus.SUCCESS

            parts: List[str] = []
            for item in item_results:
                if item.error:
                    parts.append(f"{item.target.value}: failed ({item.error})")
                else:
                    parts.append(f"{item.target.value}: ok ({item.items_backed_up} items)")
            message = "; ".join(parts)

        return BackupResult(
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            items=item_results,
            message=message,
        )
