# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle market address キャッシュ層。

Pendle Hosted SDK の /markets エンドポイントから market address を取得し、
TTL ベースでインメモリキャッシュする。

設計方針:
- TTL デフォルト 300 秒（config 経由で変更可能）
- hit/miss カウンタでキャッシュヒット率を計測
- API 失敗時は None を返す（fail-open 設計）
- 秘密鍵・機密情報は一切扱わない
- 金額/数値は Decimal 型（float 禁止）
- TTL 計算は time.monotonic() を使用
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """キャッシュエントリ（market address + TTL 情報）。"""

    value: str
    """キャッシュされた market address。"""
    stored_at: float
    """格納時刻 (time.monotonic())。"""
    ttl_seconds: float
    """有効期限（秒）。"""

    def is_expired(self) -> bool:
        """TTL が切れているか確認する。"""
        return (time.monotonic() - self.stored_at) >= self.ttl_seconds


@dataclass
class CacheMetrics:
    """キャッシュヒット率メトリクス。"""

    hits: int = 0
    misses: int = 0

    @property
    def total(self) -> int:
        """総アクセス数。"""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> Decimal:
        """ヒット率（0〜1 の Decimal）。total が 0 の場合は Decimal("0")。"""
        if self.total == 0:
            return Decimal("0")
        return Decimal(str(self.hits)) / Decimal(str(self.total))

    def record_hit(self) -> None:
        """キャッシュヒットを記録する。"""
        self.hits += 1

    def record_miss(self) -> None:
        """キャッシュミスを記録する。"""
        self.misses += 1

    def reset(self) -> None:
        """カウンタをリセットする。"""
        self.hits = 0
        self.misses = 0

    def to_dict(self) -> dict[str, Any]:
        """メトリクスを辞書形式で返す。"""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total": self.total,
            "hit_rate": str(self.hit_rate),
        }


class PendleMarketCache:
    """Pendle market address インメモリキャッシュ。

    Pendle SDK /markets エンドポイントから market address を取得し、
    TTL ベースでキャッシュする。

    Args:
        chain_id: Pendle SDK が使用するチェーン ID（例: 42161 = Arbitrum）
        ttl_seconds: キャッシュ有効期限（秒）。デフォルト 300 秒。
        api_base: Pendle SDK API ベース URL。
        request_timeout: HTTP リクエストタイムアウト（秒）。

    使用例::

        cache = PendleMarketCache(chain_id=42161)
        market_address = await cache.get_market_address(underlying_asset="stETH")
        metrics = cache.get_metrics()
    """

    _DEFAULT_API_BASE = "https://api-v2.pendle.finance/core/v1"
    _DEFAULT_REQUEST_TIMEOUT = 10.0
    _DEFAULT_TTL_SECONDS = 300.0

    def __init__(
        self,
        chain_id: int,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        api_base: str = _DEFAULT_API_BASE,
        request_timeout: float = _DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self._chain_id = chain_id
        self._ttl_seconds = ttl_seconds
        self._api_base = api_base
        self._request_timeout = request_timeout
        # キー: 小文字の underlying_asset 識別子（例: "steth"）
        # 値: CacheEntry
        self._cache: dict[str, CacheEntry] = {}
        self._metrics = CacheMetrics()
        logger.info(
            "PendleMarketCache initialized (chain_id=%d, ttl=%ss)",
            chain_id,
            ttl_seconds,
        )

    # -------------------------------------------------------------------
    # 公開 API
    # -------------------------------------------------------------------

    async def get_market_address(
        self,
        underlying_asset: str,
    ) -> str | None:
        """underlying_asset に対応する market address を取得する。

        キャッシュヒット時はキャッシュを返す。
        キャッシュミス or TTL 切れ時は /markets エンドポイントを呼び出して更新。
        API 失敗時は None を返す（fail-open 設計）。

        Args:
            underlying_asset: 原資産識別子（例: "stETH", "wstETH"）

        Returns:
            market address 文字列、または None（失敗時）
        """
        cache_key = underlying_asset.lower()
        entry = self._cache.get(cache_key)

        if entry is not None and not entry.is_expired():
            self._metrics.record_hit()
            logger.debug(
                "PendleMarketCache HIT: asset=%s, address=%s",
                underlying_asset,
                entry.value[:10] + "...",
            )
            return entry.value

        # キャッシュミス or TTL 切れ
        self._metrics.record_miss()
        logger.debug("PendleMarketCache MISS: asset=%s", underlying_asset)

        market_address = await self._fetch_market_address(underlying_asset)
        if market_address is not None:
            self._cache[cache_key] = CacheEntry(
                value=market_address,
                stored_at=time.monotonic(),
                ttl_seconds=self._ttl_seconds,
            )
        return market_address

    async def get_all_markets(self) -> list[dict[str, Any]]:
        """チェーン上の全マーケット一覧を取得する（キャッシュなし）。

        Returns:
            マーケット情報のリスト。API 失敗時は空リスト。
        """
        url = f"{self._api_base}/{self._chain_id}/markets"
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                markets: list[dict[str, Any]] = data.get("results", [])
                logger.info(
                    "PendleMarketCache.get_all_markets: %d markets fetched",
                    len(markets),
                )
                return markets
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "PendleMarketCache.get_all_markets HTTP エラー: status=%d",
                exc.response.status_code,
            )
            return []
        except Exception as exc:
            logger.warning("PendleMarketCache.get_all_markets 失敗: %s", exc)
            return []

    def invalidate(self, underlying_asset: str) -> None:
        """特定 asset のキャッシュを手動で無効化する。"""
        cache_key = underlying_asset.lower()
        removed = self._cache.pop(cache_key, None)
        if removed is not None:
            logger.info("PendleMarketCache: cache invalidated for asset=%s", underlying_asset)

    def invalidate_all(self) -> None:
        """全キャッシュを手動でクリアする。"""
        count = len(self._cache)
        self._cache.clear()
        logger.info("PendleMarketCache: all %d entries cleared", count)

    def get_metrics(self) -> CacheMetrics:
        """現在のキャッシュメトリクスを返す。"""
        return self._metrics

    def reset_metrics(self) -> None:
        """メトリクスカウンタをリセットする。"""
        self._metrics.reset()

    # -------------------------------------------------------------------
    # 内部ヘルパー
    # -------------------------------------------------------------------

    async def _fetch_market_address(self, underlying_asset: str) -> str | None:
        """Pendle /markets エンドポイントから underlying_asset に一致する address を取得。

        Args:
            underlying_asset: 原資産識別子（大文字小文字不問）

        Returns:
            market address 文字列、または None（失敗時 / 見つからない時）
        """
        markets = await self.get_all_markets()
        if not markets:
            return None

        asset_lower = underlying_asset.lower()
        for market in markets:
            # Pendle API の market オブジェクト構造:
            # { "address": "0x...", "underlyingAsset": { "symbol": "stETH", ... }, ... }
            symbol: str = (market.get("underlyingAsset", {}).get("symbol", "") or "").lower()
            address: str = market.get("address", "") or ""
            if symbol == asset_lower and address:
                logger.info(
                    "PendleMarketCache: asset=%s -> address=%s",
                    underlying_asset,
                    address[:10] + "...",
                )
                return address

        logger.warning(
            "PendleMarketCache: market not found for asset=%s (searched %d markets)",
            underlying_asset,
            len(markets),
        )
        return None
