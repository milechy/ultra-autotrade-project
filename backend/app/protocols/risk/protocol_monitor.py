# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""プロトコルヘルス監視モジュール。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .schemas import ProtocolHealth, RiskLevel

logger = logging.getLogger(__name__)


class ProtocolMonitor:
    """各プロトコルのヘルス状態を監視するクラス。"""

    def __init__(
        self,
        lido_client: Any = None,
        pendle_client: Any = None,
        monitoring_service: Any = None,
        aave_client: Any = None,
    ) -> None:
        """初期化。

        Args:
            lido_client: Lido クライアント（None の場合はデフォルト設定から生成）
            pendle_client: Pendle クライアント（None の場合はデフォルト設定から生成）
            monitoring_service: MonitoringService（None の場合は check_aave_health
                初回呼出時に app.automation.state.get_monitoring_service() で遅延解決）
            aave_client: Aave クライアント（None の場合は check_aave_health
                初回呼出時に app.aave.client.get_default_aave_client() で遅延解決）
        """
        if lido_client is None:
            from app.protocols.lido.client import get_lido_client
            from app.protocols.lido.config import get_lido_config

            lido_client = get_lido_client(get_lido_config())
        if pendle_client is None:
            from app.protocols.pendle.client import get_pendle_client
            from app.protocols.pendle.config import get_pendle_config

            pendle_client = get_pendle_client(get_pendle_config())

        self._lido_client = lido_client
        self._pendle_client = pendle_client
        # Aave 依存は import 時の副作用 (web3 / 環境変数) を避けるため遅延解決する
        self._monitoring_service = monitoring_service
        self._aave_client = aave_client

    async def check_aave_health(self) -> ProtocolHealth:
        """Aave V3 ヘルスチェック。

        MonitoringService の最新 Health Factor (HF) と Aave クライアントの
        アカウントデータから判定する。HF が未観測 (None) の場合は
        AccountData.health_factor をフォールバックとして使用する。

        リスク判定閾値（出典: docs/08_automation_rules.md — 閾値を変更する場合は
        本 docstring とドキュメント側の二重管理に注意し、同時に更新すること）:
        - HF が None または inf（ポジションなし）→ LOW
        - HF < 1.6（緊急停止水準）→ CRITICAL + アラート
        - HF < 1.8（警告水準）→ HIGH + アラート
        - それ以外 → LOW

        TVL は AccountData.total_collateral_usd（運用ポジションの担保 USD）を
        採用する。プロトコル全体 TVL ではなく、自ポジションのエクスポージャー
        を表す値である点に注意。tvl_change_24h_pct は履歴データを保持しない
        ため Decimal("0") 固定とする。

        is_operational は MonitoringService.is_trading_allowed()（緊急停止
        フラグの OR ロジック）を反映する。

        fail-open: 依存サービスの例外時は raise せず CRITICAL /
        tvl_usd=Decimal("0") / is_operational=False / 日本語アラートで返す
        （check_lido_health のエラーハンドリングと同型）。
        """
        logger.info("check_aave_health: Aave ヘルスチェック実行")
        alerts: list[str] = []

        try:
            if self._monitoring_service is None:
                from app.automation.state import get_monitoring_service

                self._monitoring_service = get_monitoring_service()
            if self._aave_client is None:
                from app.aave.client import get_default_aave_client

                self._aave_client = get_default_aave_client()

            status = self._monitoring_service.get_status()
            hf = status.last_health_factor

            # get_account_data は同期 (web3 RPC) のため event loop をブロックしない
            account = await asyncio.to_thread(self._aave_client.get_account_data, "")
            tvl = account.total_collateral_usd

            if hf is None:
                hf = account.health_factor

            risk_level = RiskLevel.LOW
            if hf is None or hf == Decimal("inf"):
                risk_level = RiskLevel.LOW
            elif hf < Decimal("1.6"):
                risk_level = RiskLevel.CRITICAL
                alerts.append(
                    f"ヘルスファクターが緊急停止水準（1.6）を下回っています（HF: {float(hf):.2f}）"
                )
            elif hf < Decimal("1.8"):
                risk_level = RiskLevel.HIGH
                alerts.append(
                    f"ヘルスファクターが警告水準（1.8）を下回っています（HF: {float(hf):.2f}）"
                )

            is_operational = bool(self._monitoring_service.is_trading_allowed())
        except Exception as exc:
            logger.exception("Aave ヘルスチェック失敗")
            return ProtocolHealth(
                protocol="aave",
                risk_level=RiskLevel.CRITICAL,
                tvl_usd=Decimal("0"),
                tvl_change_24h_pct=Decimal("0"),
                is_operational=False,
                last_checked=datetime.now(tz=timezone.utc),
                alerts=[f"Aave ヘルスチェックエラー: {exc}"],
            )

        return ProtocolHealth(
            protocol="aave",
            risk_level=risk_level,
            tvl_usd=tvl,
            tvl_change_24h_pct=Decimal("0"),
            is_operational=is_operational,
            last_checked=datetime.now(tz=timezone.utc),
            alerts=alerts,
        )

    async def check_lido_health(self) -> ProtocolHealth:
        """Lido ヘルスチェック。

        - lido_client から staking APR および stETH/ETH レートを取得
        - APR < 0% または > 20% → CRITICAL
        - ペグ乖離 > 2% → HIGH
        - TVL 推定: $15B
        """
        logger.info("check_lido_health: Lido ヘルスチェック実行")
        alerts: list[str] = []
        risk_level = RiskLevel.LOW

        try:
            apr = await self._lido_client.get_staking_apr()
            ratio = await self._lido_client.get_steth_eth_ratio()
        except Exception as exc:
            logger.exception("Lido クライアント呼び出し失敗")
            return ProtocolHealth(
                protocol="lido",
                risk_level=RiskLevel.CRITICAL,
                tvl_usd=Decimal("0"),
                tvl_change_24h_pct=Decimal("0"),
                is_operational=False,
                last_checked=datetime.now(tz=timezone.utc),
                alerts=[f"Lido クライアントエラー: {exc}"],
            )

        # APR チェック
        if apr < Decimal("0") or apr > Decimal("20"):
            risk_level = RiskLevel.CRITICAL
            alerts.append(f"ステーキング報酬率が異常値です（{float(apr):.2f}%）")
        # ペグ乖離チェック
        deviation_pct = abs(Decimal("1") - ratio) * Decimal("100")
        if deviation_pct > Decimal("2"):
            if risk_level != RiskLevel.CRITICAL:
                risk_level = RiskLevel.HIGH
            alerts.append(f"価格連動性に乖離があります（{float(deviation_pct):.2f}%）")

        return ProtocolHealth(
            protocol="lido",
            risk_level=risk_level,
            tvl_usd=Decimal("15000000000"),  # $15B 推定
            tvl_change_24h_pct=Decimal("0"),
            is_operational=True,
            last_checked=datetime.now(tz=timezone.utc),
            alerts=alerts,
        )

    async def check_pendle_health(self) -> ProtocolHealth:
        """Pendle ヘルスチェック。

        - pendle_client からマーケット情報を取得
        - TVL はマーケット情報から取得
        - implied APY > 50% → MEDIUM（疑わしい値）
        - implied APY > 100% → HIGH
        - TVL < $1M → HIGH（流動性不足）
        """
        from app.protocols.pendle.config import get_pendle_config

        logger.info("check_pendle_health: Pendle ヘルスチェック実行")
        alerts: list[str] = []
        risk_level = RiskLevel.LOW

        config = get_pendle_config()
        market_address = config.market_address

        try:
            market_info = await self._pendle_client.get_market_info(market_address)
        except Exception as exc:
            logger.exception("Pendle クライアント呼び出し失敗")
            return ProtocolHealth(
                protocol="pendle",
                risk_level=RiskLevel.CRITICAL,
                tvl_usd=Decimal("0"),
                tvl_change_24h_pct=Decimal("0"),
                is_operational=False,
                last_checked=datetime.now(tz=timezone.utc),
                alerts=[f"Pendle クライアントエラー: {exc}"],
            )

        tvl = market_info.tvl_usd
        implied_apy = market_info.implied_apy

        # TVL チェック
        if tvl < Decimal("1000000"):  # $1M 未満
            risk_level = RiskLevel.HIGH
            alerts.append(
                f"取引量が非常に少なく、換金が難しい可能性があります（TVL: ${float(tvl):,.0f}）"
            )

        # implied APY チェック
        if implied_apy > Decimal("100"):
            if risk_level not in (RiskLevel.CRITICAL,):
                risk_level = RiskLevel.HIGH
            alerts.append(
                f"期待利回りが異常に高く、リスクが懸念されます（{float(implied_apy):.1f}%）"
            )
        elif implied_apy > Decimal("50"):
            if risk_level == RiskLevel.LOW:
                risk_level = RiskLevel.MEDIUM
            alerts.append(f"期待利回りが通常より高めです（{float(implied_apy):.1f}%）")

        return ProtocolHealth(
            protocol="pendle",
            risk_level=risk_level,
            tvl_usd=tvl,
            tvl_change_24h_pct=Decimal("0"),
            is_operational=True,
            last_checked=datetime.now(tz=timezone.utc),
            alerts=alerts,
        )

    async def check_all(self) -> list[ProtocolHealth]:
        """全プロトコルをチェックしてリストで返す。"""
        logger.info("check_all: 全プロトコルヘルスチェック開始")
        results = []
        for check_fn in (self.check_aave_health, self.check_lido_health, self.check_pendle_health):
            result = await check_fn()
            results.append(result)
        logger.info(
            "check_all 完了: %d プロトコル確認済み",
            len(results),
        )
        return results
