# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle market address キャッシュ層。

Pendle Hosted SDK の /markets/active エンドポイントから market address を取得し、
TTL ベースでインメモリキャッシュする。

設計方針:
- TTL デフォルト 300 秒（config 経由で変更可能）
- hit/miss カウンタでキャッシュヒット率を計測
- API 失敗時は None を返す（fail-open 設計）
- 満期フィルタは fail-closed（min_days_to_maturity 未満 / 不正アドレスは除外し、
  満たす market が無ければ None）
- 秘密鍵・機密情報は一切扱わない
- 金額/数値は Decimal 型（float 禁止）
- TTL 計算は time.monotonic() を使用
- 同一キー並行 miss の double-fetch は asyncio.Lock + double-checked locking で防止

実 API レスポンス構造（2026-06-12 curl 実測 / VERIFIED）::

    GET https://api-v2.pendle.finance/core/v1/42161/markets/active
    {
      "markets": [
        {
          "name": "wstETH",                       # 人間可読シンボル（symbol 相当）
          "address": "0xf78452...b8cd1e06e53fa25b",
          "expiry": "2026-06-25T00:00:00.000Z",   # ISO 8601 満期日時
          "underlyingAsset": "42161-0x5979d7...",  # chainId-prefixed address 文字列
          ...
        },
        ...
      ]
    }

  注意: トップキーは `markets`（`results` ではない）。
  シンボルは `name` フィールド（`underlyingAsset` は object ではなく
  chainId-prefixed の address 文字列のため `.symbol` は存在しない）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import httpx
from web3 import Web3

if TYPE_CHECKING:
    from .config import PendleConfig

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """キャッシュエントリ（market address + TTL 情報）。"""

    value: str
    """キャッシュされた market address（checksum 正規化済み）。"""
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

    Pendle SDK /markets/active エンドポイントから market address を取得し、
    TTL ベースでキャッシュする。

    返却前に以下のガードを適用する（on-chain 書込経路の入力源のため）:

    - 満期フィルタ (fail-closed): expiry から days_to_maturity を計算し、
      ``config.min_days_to_maturity`` 未満の market は除外。満たす market が
      無ければ ``None`` を返す。
    - アドレス検証: ``Web3.is_address`` で検証し ``Web3.to_checksum_address``
      で正規化。不正なアドレスは除外。
    - 決定的選択 (M3): 同一シンボルに複数 market がある場合、min_days_to_maturity
      を満たす候補のうち**最も満期が遠いもの**を選択する（TTL 中の安定性確保）。

    Args:
        chain_id: Pendle SDK が使用するチェーン ID（例: 42161 = Arbitrum）
        ttl_seconds: キャッシュ有効期限（秒）。デフォルト 300 秒。
        api_base: Pendle SDK API ベース URL。
        request_timeout: HTTP リクエストタイムアウト（秒）。
        config: PendleConfig。``min_days_to_maturity`` を満期フィルタに使用する。
            None の場合はデフォルト（7 日）を使用。

    使用例::

        cache = PendleMarketCache(chain_id=42161, config=get_pendle_config())
        market_address = await cache.get_market_address(underlying_asset="wstETH")
        metrics = cache.get_metrics()
    """

    _DEFAULT_API_BASE = "https://api-v2.pendle.finance/core/v1"
    _DEFAULT_REQUEST_TIMEOUT = 10.0
    _DEFAULT_TTL_SECONDS = 300.0
    _DEFAULT_MIN_DAYS_TO_MATURITY = 7

    def __init__(
        self,
        chain_id: int,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        api_base: str = _DEFAULT_API_BASE,
        request_timeout: float = _DEFAULT_REQUEST_TIMEOUT,
        config: PendleConfig | None = None,
    ) -> None:
        self._chain_id = chain_id
        self._ttl_seconds = ttl_seconds
        self._api_base = api_base
        self._request_timeout = request_timeout
        self._config = config
        # キー: 小文字の underlying_asset 識別子（例: "wsteth"）
        # 値: CacheEntry
        self._cache: dict[str, CacheEntry] = {}
        self._metrics = CacheMetrics()
        # 同一キー並行 miss の double-fetch 防止（double-checked locking 用）
        self._locks: dict[str, asyncio.Lock] = {}
        logger.info(
            "PendleMarketCache initialized (chain_id=%d, ttl=%ss, min_days_to_maturity=%d)",
            chain_id,
            ttl_seconds,
            self._min_days_to_maturity,
        )

    @property
    def _min_days_to_maturity(self) -> int:
        """満期フィルタの最低日数（config 未注入時はデフォルト 7 日）。"""
        if self._config is not None:
            return self._config.min_days_to_maturity
        return self._DEFAULT_MIN_DAYS_TO_MATURITY

    # -------------------------------------------------------------------
    # 公開 API
    # -------------------------------------------------------------------

    async def get_market_address(
        self,
        underlying_asset: str,
    ) -> str | None:
        """underlying_asset に対応する market address を取得する。

        キャッシュヒット時はキャッシュを返す。
        キャッシュミス or TTL 切れ時は /markets/active エンドポイントを呼び出して更新。
        満期フィルタ・アドレス検証を満たす market が無ければ None（fail-closed）。
        API 失敗時も None を返す（fail-open）。

        並行アクセス時は asyncio.Lock + double-checked locking により、
        同一キーに対する fetch は 1 回のみ実行される。

        Args:
            underlying_asset: 原資産識別子（例: "wstETH", "weETH"）

        Returns:
            market address 文字列（checksum 正規化済み）、または None
        """
        cache_key = underlying_asset.lower()

        # 1st check (ロック外): ヒットすれば即返す
        entry = self._cache.get(cache_key)
        if entry is not None and not entry.is_expired():
            self._metrics.record_hit()
            logger.debug(
                "PendleMarketCache HIT: asset=%s, address=%s",
                underlying_asset,
                entry.value[:10] + "...",
            )
            return entry.value

        # miss / 期限切れ → ロックを取得して double-checked locking
        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            # 2nd check (ロック内): 先行 coroutine が埋めていればヒット
            entry = self._cache.get(cache_key)
            if entry is not None and not entry.is_expired():
                self._metrics.record_hit()
                logger.debug(
                    "PendleMarketCache HIT (post-lock): asset=%s",
                    underlying_asset,
                )
                return entry.value

            # 確定 miss
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
        """チェーン上のアクティブな market 一覧を取得する（キャッシュなし）。

        満期切れ market を除外するため ``/markets/active`` を使用する。

        Returns:
            market 情報のリスト。API 失敗時は空リスト。
        """
        url = f"{self._api_base}/{self._chain_id}/markets/active"
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                # 実 API のトップキーは "markets"（"results" ではない / VERIFIED 2026-06-12）
                markets: list[dict[str, Any]] = data.get("markets", [])
                logger.info(
                    "PendleMarketCache.get_all_markets: %d active markets fetched",
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

    @staticmethod
    def _parse_expiry(expiry_raw: str) -> datetime | None:
        """ISO 8601 expiry 文字列を tz-aware datetime にパースする。

        実 API は ``"2026-06-25T00:00:00.000Z"`` 形式（末尾 Z）。
        パース失敗時は None。
        """
        if not expiry_raw:
            return None
        try:
            # 末尾 "Z" を UTC offset に変換（Python 3.11 は Z 直接非対応のケースあり）
            normalized = expiry_raw.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, TypeError):
            return None

    def _days_to_maturity(self, expiry_raw: str, now: datetime) -> Decimal | None:
        """expiry までの残日数を Decimal で返す。パース不能なら None。"""
        expiry = self._parse_expiry(expiry_raw)
        if expiry is None:
            return None
        delta_seconds = Decimal(str((expiry - now).total_seconds()))
        return delta_seconds / Decimal("86400")

    async def _fetch_market_address(self, underlying_asset: str) -> str | None:
        """/markets/active から underlying_asset に一致する address を解決する。

        ガード（すべて適用）:
        1. シンボル一致: market の ``name`` フィールドが underlying_asset と一致
           （case-insensitive）。実 API は ``underlyingAsset`` が address 文字列の
           ため ``name`` を人間可読シンボルとして使用する。
        2. 満期フィルタ (fail-closed): days_to_maturity >= min_days_to_maturity。
        3. アドレス検証: Web3.is_address で検証し、不正なら除外。
        4. 決定的選択 (M3): 候補のうち最も満期が遠いものを選び、
           checksum 正規化して返す。

        Returns:
            checksum 正規化済み market address、または None（該当なし / 失敗）
        """
        markets = await self.get_all_markets()
        if not markets:
            return None

        asset_lower = underlying_asset.lower()
        now = datetime.now(timezone.utc)
        min_days = Decimal(str(self._min_days_to_maturity))

        # (days_to_maturity, checksum_address) の候補を集める
        candidates: list[tuple[Decimal, str]] = []
        for market in markets:
            name: str = (market.get("name", "") or "").lower()
            if name != asset_lower:
                continue

            address_raw: str = market.get("address", "") or ""
            # [C3] アドレス検証
            if not address_raw or not Web3.is_address(address_raw):
                logger.warning(
                    "PendleMarketCache: invalid address for asset=%s (rejected)",
                    underlying_asset,
                )
                continue

            # [C1] 満期フィルタ (fail-closed)
            days = self._days_to_maturity(market.get("expiry", "") or "", now)
            if days is None:
                logger.warning(
                    "PendleMarketCache: unparseable expiry for asset=%s (rejected)",
                    underlying_asset,
                )
                continue
            if days < min_days:
                logger.info(
                    "PendleMarketCache: asset=%s market too close to maturity "
                    "(days=%s < min=%s, rejected)",
                    underlying_asset,
                    str(days.quantize(Decimal("0.01"))),
                    str(min_days),
                )
                continue

            checksum_address = Web3.to_checksum_address(address_raw)
            candidates.append((days, checksum_address))

        if not candidates:
            logger.warning(
                "PendleMarketCache: no valid market for asset=%s "
                "(searched %d markets, min_days_to_maturity=%s)",
                underlying_asset,
                len(markets),
                str(min_days),
            )
            return None

        # [M3] 決定的選択: 最も満期が遠い候補を採用
        candidates.sort(key=lambda c: c[0], reverse=True)
        selected_address = candidates[0][1]
        logger.info(
            "PendleMarketCache: asset=%s -> address=%s (days_to_maturity=%s, %d candidate(s))",
            underlying_asset,
            selected_address[:10] + "...",
            str(candidates[0][0].quantize(Decimal("0.01"))),
            len(candidates),
        )
        return selected_address
