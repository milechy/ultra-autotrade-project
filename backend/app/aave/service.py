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

from app.automation.state import get_monitoring_service
from app.automation.monitoring_service import MonitoringService
from app.automation.schemas import AlertLevel, ComponentType

from .client import AaveClient, AaveClientError, get_default_aave_client
from .config import AaveSettings, get_aave_settings
from .schemas import (
    AaveOperationResult,
    AaveOperationStatus,
    AaveOperationType,
)

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
        monitoring_service: Optional[MonitoringService] | None = None,
    ) -> None:
        self._client: AaveClient = client or get_default_aave_client()
        self._settings: AaveSettings = settings or get_aave_settings()

        # 監視・緊急停止ロジック
        self._monitoring: MonitoringService = monitoring_service or get_monitoring_service()

        # 直近のトレード時刻を記録する（単純なリストで十分）
        self._recent_actions: List[datetime] = []

    # ---- 内部ヘルパー -------------------------------------------------

    def _now(self) -> datetime:
        """テストしやすさのために現在時刻取得をメソッド化。"""
        return datetime.now(timezone.utc)

    def _cleanup_recent_actions(self, now: datetime) -> None:
        """トレードクールダウン期間外の履歴を破棄する。"""
        window_start = now - timedelta(seconds=self._settings.trade_cooldown_seconds)
        self._recent_actions = [
            ts for ts in self._recent_actions if ts >= window_start
        ]

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
        # まず入力バリデーションを行う（負の金額などはここで ValueError）
        normalized_amount = self._normalize_amount(amount)

        token = asset_symbol or self._settings.default_asset_symbol
        now = self._now()

        # 監視ロジック側で緊急停止中の場合は、ポジションを増やさない
        if (
            hasattr(self, "_monitoring")
            and self._monitoring is not None
            and not self._monitoring.is_trading_allowed()
        ):
            logger.warning(
                "Trading is paused by MonitoringService emergency stop. Forcing NOOP."
            )
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
