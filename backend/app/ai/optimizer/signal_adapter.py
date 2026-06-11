# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Signal Adapter モジュール。

Pendle / Lido の実クライアントから APY・価格・リスク情報を取得し、
StrategyScorer が使える形に変換する。

設計方針:
- クライアントは Optional。None の場合はフォールバック定数を返す（fail-open）。
- 外部呼び出し失敗時も例外を握りつぶさず、ログ出力の上でフォールバック値を返す。
- 金額・利率は全て Decimal 型。float 禁止。
- 秘密鍵を要するメソッドは呼ばない（read-only な APY / 価格取得のみ）。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.protocols.lido.client import AbstractLidoClient
    from app.protocols.pendle.client import AbstractPendleClient

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# フォールバック定数（StrategyScorer のダミー定数と同値を使用）
# --------------------------------------------------------------------------- #
_FALLBACK_LIDO_APY: Decimal = Decimal("3.5")
_FALLBACK_PEG_DEVIATION: Decimal = Decimal("0")
_FALLBACK_PENDLE_PT_APY: Decimal = Decimal("5.2")
_FALLBACK_PENDLE_YT_APY: Decimal = Decimal("8.0")
_FALLBACK_PENDLE_MATURITY_DAYS: int = 30


class LidoSignalAdapter:
    """Lido クライアントから APY・ペグ乖離率を取得するアダプター。

    クライアントが None か取得失敗時はフォールバック定数を返す（fail-open 設計）。
    """

    def __init__(self, client: Optional["AbstractLidoClient"] = None) -> None:
        self._client = client

    async def get_staking_apy(self) -> Decimal:
        """Lido staking APY（%）を返す。失敗時はフォールバック値。"""
        if self._client is None:
            logger.debug(
                "LidoSignalAdapter: client=None, フォールバック APY=%s", _FALLBACK_LIDO_APY
            )
            return _FALLBACK_LIDO_APY
        try:
            apy = await self._client.get_staking_apr()
            logger.debug("LidoSignalAdapter.get_staking_apy: apy=%s", apy)
            return apy
        except Exception as exc:
            logger.warning("LidoSignalAdapter.get_staking_apy 失敗、フォールバック: %s", exc)
            return _FALLBACK_LIDO_APY

    async def get_peg_deviation(self) -> Decimal:
        """stETH/ETH ペグ乖離率（%）を返す。0 = 完全ペグ。失敗時は 0。"""
        if self._client is None:
            logger.debug(
                "LidoSignalAdapter: client=None, フォールバック peg_deviation=%s",
                _FALLBACK_PEG_DEVIATION,
            )
            return _FALLBACK_PEG_DEVIATION
        try:
            ratio = await self._client.get_steth_eth_ratio()
            deviation = abs(Decimal("1") - ratio) * Decimal("100")
            logger.debug(
                "LidoSignalAdapter.get_peg_deviation: ratio=%s, deviation=%s", ratio, deviation
            )
            return deviation
        except Exception as exc:
            logger.warning("LidoSignalAdapter.get_peg_deviation 失敗、フォールバック: %s", exc)
            return _FALLBACK_PEG_DEVIATION


class PendleSignalAdapter:
    """Pendle クライアントから implied APY・PT/YT 価格・満期情報を取得するアダプター。

    クライアントが None か取得失敗時はフォールバック定数を返す（fail-open 設計）。
    market_address が None の場合は config から取得を試みる。
    """

    def __init__(
        self,
        client: Optional["AbstractPendleClient"] = None,
        market_address: Optional[str] = None,
    ) -> None:
        self._client = client
        self._market_address = market_address

    def _resolve_market_address(self) -> str:
        """market_address を解決する。未設定時は config から取得を試みる。"""
        if self._market_address:
            return self._market_address
        try:
            from app.protocols.pendle.config import get_pendle_config  # noqa: PLC0415

            return get_pendle_config().market_address
        except Exception:
            return "0x_dummy_market"

    async def get_pt_apy(self) -> Decimal:
        """Pendle PT implied APY（%）を返す。失敗時はフォールバック値。"""
        if self._client is None:
            logger.debug(
                "PendleSignalAdapter: client=None, フォールバック PT APY=%s",
                _FALLBACK_PENDLE_PT_APY,
            )
            return _FALLBACK_PENDLE_PT_APY
        try:
            market_address = self._resolve_market_address()
            info = await self._client.get_market_info(market_address)
            logger.debug(
                "PendleSignalAdapter.get_pt_apy: implied_apy=%s (market=%s)",
                info.implied_apy,
                market_address[:10] if len(market_address) > 10 else market_address,
            )
            return info.implied_apy
        except Exception as exc:
            logger.warning("PendleSignalAdapter.get_pt_apy 失敗、フォールバック: %s", exc)
            return _FALLBACK_PENDLE_PT_APY

    async def get_yt_apy(self) -> Decimal:
        """Pendle YT 期待 APY（%）を返す。

        YT の期待 APY は PT implied APY を基準に推定する（投機的）。
        外部データが取れない場合はフォールバック値を使用。
        """
        if self._client is None:
            logger.debug(
                "PendleSignalAdapter: client=None, フォールバック YT APY=%s",
                _FALLBACK_PENDLE_YT_APY,
            )
            return _FALLBACK_PENDLE_YT_APY
        try:
            market_address = self._resolve_market_address()
            info = await self._client.get_market_info(market_address)
            # YT の期待 APY = implied APY * レバレッジ推定（yt_price ベース）
            # YT price が低いほどレバレッジが高い（高リスク高リターン）
            # 推定式: yt_apy ≒ implied_apy * (1 / yt_price) ただし上限 20%
            if info.yt_price > Decimal("0"):
                leverage_factor = Decimal("1") / info.yt_price
                yt_apy = info.implied_apy * leverage_factor
                # 上限 20% で cap
                yt_apy = min(yt_apy, Decimal("20"))
            else:
                yt_apy = _FALLBACK_PENDLE_YT_APY
            logger.debug(
                "PendleSignalAdapter.get_yt_apy: yt_price=%s, yt_apy=%s",
                info.yt_price,
                yt_apy,
            )
            return yt_apy
        except Exception as exc:
            logger.warning("PendleSignalAdapter.get_yt_apy 失敗、フォールバック: %s", exc)
            return _FALLBACK_PENDLE_YT_APY

    async def get_maturity_days(self) -> int:
        """Pendle PT/YT の残り満期日数を返す。失敗時はフォールバック値（30日）。"""
        if self._client is None:
            logger.debug(
                "PendleSignalAdapter: client=None, フォールバック maturity=%d",
                _FALLBACK_PENDLE_MATURITY_DAYS,
            )
            return _FALLBACK_PENDLE_MATURITY_DAYS
        try:
            market_address = self._resolve_market_address()
            info = await self._client.get_market_info(market_address)
            logger.debug(
                "PendleSignalAdapter.get_maturity_days: days_to_maturity=%d",
                info.days_to_maturity,
            )
            return info.days_to_maturity
        except Exception as exc:
            logger.warning("PendleSignalAdapter.get_maturity_days 失敗、フォールバック: %s", exc)
            return _FALLBACK_PENDLE_MATURITY_DAYS
