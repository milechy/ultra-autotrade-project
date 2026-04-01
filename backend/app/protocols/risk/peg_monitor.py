# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""stETH/ETH ペグ乖離監視モジュール。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .schemas import PegStatus, RiskLevel

logger = logging.getLogger(__name__)


class PegMonitor:
    """stETH/ETH ペグ乖離を監視するクラス。"""

    def __init__(self, lido_client: Any = None) -> None:
        """初期化。

        Args:
            lido_client: Lido クライアント（None の場合は DummyLidoClient を使用）
        """
        if lido_client is None:
            from app.protocols.lido.client import DummyLidoClient
            from app.protocols.lido.config import get_lido_config

            lido_client = DummyLidoClient(get_lido_config())
        self._lido_client = lido_client

    async def get_peg_status(self) -> PegStatus:
        """Lido クライアントから現在のペグ状態を取得する。"""
        logger.info("get_peg_status: stETH/ETH ペグ状態取得")
        ratio = await self._lido_client.get_steth_eth_ratio()
        deviation_pct = abs(Decimal("1") - ratio) * Decimal("100")
        risk_level = self.classify_risk(deviation_pct)
        return PegStatus(
            current_ratio=ratio,
            deviation_pct=deviation_pct,
            risk_level=risk_level,
            last_checked=datetime.now(tz=timezone.utc),
        )

    def classify_risk(self, deviation_pct: Decimal) -> RiskLevel:
        """ペグ乖離率をリスクレベルに分類する。

        Args:
            deviation_pct: 乖離率（%）

        Returns:
            RiskLevel:
                - < 0.5% → LOW
                - 0.5% 以上 1.0% 未満 → MEDIUM
                - 1.0% 以上 2.0% 未満 → HIGH
                - 2.0% 以上 → CRITICAL

        閾値比較はすべて Decimal を使用。
        """
        if deviation_pct < Decimal("0.5"):
            return RiskLevel.LOW
        if deviation_pct < Decimal("1.0"):
            return RiskLevel.MEDIUM
        if deviation_pct < Decimal("2.0"):
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    async def should_trigger_evacuation(self) -> bool:
        """ペグ乖離が CRITICAL の場合に True を返す。"""
        peg_status = await self.get_peg_status()
        result = peg_status.risk_level == RiskLevel.CRITICAL
        if result:
            logger.warning(
                "should_trigger_evacuation: CRITICAL ペグ乖離検知（%.4f%%）",
                float(peg_status.deviation_pct),
            )
        return result
