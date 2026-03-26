# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle マーケット満期管理モジュール。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .schemas import MaturityAlert, RiskLevel

logger = logging.getLogger(__name__)


class MaturityManager:
    """Pendle マーケットの満期状況を管理するクラス。"""

    def __init__(self, pendle_client: Any = None) -> None:
        """初期化。

        Args:
            pendle_client: Pendle クライアント（None の場合はデフォルト設定から生成）
        """
        if pendle_client is None:
            from app.protocols.pendle.client import get_pendle_client
            from app.protocols.pendle.config import get_pendle_config

            pendle_client = get_pendle_client(get_pendle_config())
        self._pendle_client = pendle_client

    async def check_maturities(
        self, market_addresses: list[str] | None = None
    ) -> list[MaturityAlert]:
        """指定されたマーケットの満期状況を確認する。

        Args:
            market_addresses: 確認するマーケットアドレスのリスト。
                None の場合は PendleConfig のデフォルトマーケットを使用。

        Returns:
            MaturityAlert のリスト。
        """
        if market_addresses is None:
            from app.protocols.pendle.config import get_pendle_config

            config = get_pendle_config()
            market_addresses = [config.market_address]

        logger.info("check_maturities: %d マーケットの満期確認", len(market_addresses))
        alerts: list[MaturityAlert] = []

        for address in market_addresses:
            try:
                market_info = await self._pendle_client.get_market_info(address)
                now = datetime.now(tz=timezone.utc)
                maturity = market_info.maturity
                # timezone-aware 比較のため UTC に統一
                if maturity.tzinfo is None:
                    maturity = maturity.replace(tzinfo=timezone.utc)
                delta = maturity - now
                # delta.seconds が正の場合は切り上げ（例: 29日 23時間 → 30日）
                days_remaining = max(0, delta.days + (1 if delta.seconds > 0 else 0))
                risk_level, action_required = self.classify_maturity_risk(days_remaining)

                alert = MaturityAlert(
                    market_address=address,
                    asset=market_info.underlying_asset,
                    maturity_date=maturity,
                    days_remaining=days_remaining,
                    risk_level=risk_level,
                    action_required=action_required,
                )
                alerts.append(alert)
                logger.info(
                    "マーケット満期確認: address=%s, days_remaining=%d, risk=%s",
                    address[:10] if len(address) > 10 else address,
                    days_remaining,
                    risk_level.value,
                )
            except Exception as exc:
                logger.exception("マーケット情報取得失敗: address=%s", address)
                # エラーの場合は CRITICAL アラートを追加
                alerts.append(
                    MaturityAlert(
                        market_address=address,
                        asset="unknown",
                        maturity_date=datetime.now(tz=timezone.utc),
                        days_remaining=0,
                        risk_level=RiskLevel.CRITICAL,
                        action_required="exit_now",
                    )
                )
                logger.error("マーケット情報取得失敗のため CRITICAL アラートを追加: %s", exc)

        return alerts

    def classify_maturity_risk(self, days_remaining: int) -> tuple[RiskLevel, str]:
        """残り日数をリスクレベルとアクションに分類する。

        Args:
            days_remaining: 満期までの残り日数。

        Returns:
            (RiskLevel, action_required) のタプル:
                - 30日以上 → (LOW, "none")
                - 14〜29日 → (MEDIUM, "monitor")
                - 7〜13日 → (HIGH, "prepare_exit")
                - 7日未満 → (CRITICAL, "exit_now")
        """
        if days_remaining >= 30:
            return RiskLevel.LOW, "none"
        if days_remaining >= 14:
            return RiskLevel.MEDIUM, "monitor"
        if days_remaining >= 7:
            return RiskLevel.HIGH, "prepare_exit"
        return RiskLevel.CRITICAL, "exit_now"

    async def get_expiring_positions(self, within_days: int = 14) -> list[MaturityAlert]:
        """N 日以内に満期を迎えるポジションを取得する。

        Args:
            within_days: この日数以内に満期を迎えるポジションをフィルタリング。

        Returns:
            フィルタリングされた MaturityAlert のリスト。
        """
        all_alerts = await self.check_maturities()
        expiring = [a for a in all_alerts if a.days_remaining <= within_days]
        logger.info(
            "get_expiring_positions: %d 日以内 → %d 件",
            within_days,
            len(expiring),
        )
        return expiring
