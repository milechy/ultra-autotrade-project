# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""プロトコルヘルス監視モジュール。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .schemas import ProtocolHealth, RiskLevel

logger = logging.getLogger(__name__)


class ProtocolMonitor:
    """各プロトコルのヘルス状態を監視するクラス。"""

    def __init__(self, lido_client: Any = None, pendle_client: Any = None) -> None:
        """初期化。

        Args:
            lido_client: Lido クライアント（None の場合はデフォルト設定から生成）
            pendle_client: Pendle クライアント（None の場合はデフォルト設定から生成）
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

    async def check_aave_health(self) -> ProtocolHealth:
        """Aave V3 ヘルスチェック。

        PoC 実装: 健全なダミーステータスを返す。
        本番では MonitoringService から HF データを取得する。
        TVL 推定: $10B、is_operational=True、risk=LOW
        """
        logger.info("check_aave_health: Aave ヘルスチェック実行")
        return ProtocolHealth(
            protocol="aave",
            risk_level=RiskLevel.LOW,
            tvl_usd=Decimal("10000000000"),  # $10B 推定
            tvl_change_24h_pct=Decimal("0"),
            is_operational=True,
            last_checked=datetime.now(tz=timezone.utc),
            alerts=[],
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
