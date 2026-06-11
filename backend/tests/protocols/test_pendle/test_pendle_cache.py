# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Pendle market address キャッシュ層のユニットテスト。

実 API 呼び出しは httpx.AsyncClient をモックして行わない。
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.protocols.pendle.cache import CacheEntry, CacheMetrics, PendleMarketCache
from app.protocols.pendle.client import PendleRouterV4Client
from app.protocols.pendle.config import PendleConfig

# ---------------------------------------------------------------------------
# CacheEntry テスト
# ---------------------------------------------------------------------------


class TestCacheEntry:
    def test_not_expired_immediately(self) -> None:
        entry = CacheEntry(value="0xABC", stored_at=time.monotonic(), ttl_seconds=300.0)
        assert not entry.is_expired()

    def test_expired_when_ttl_zero(self) -> None:
        # stored_at を過去にセットして即期限切れにする
        entry = CacheEntry(value="0xABC", stored_at=time.monotonic() - 1.0, ttl_seconds=0.5)
        assert entry.is_expired()

    def test_not_expired_within_ttl(self) -> None:
        entry = CacheEntry(value="0xDEF", stored_at=time.monotonic(), ttl_seconds=60.0)
        assert not entry.is_expired()

    def test_expired_past_ttl(self) -> None:
        entry = CacheEntry(
            value="0xGHI",
            stored_at=time.monotonic() - 100.0,
            ttl_seconds=10.0,
        )
        assert entry.is_expired()


# ---------------------------------------------------------------------------
# CacheMetrics テスト
# ---------------------------------------------------------------------------


class TestCacheMetrics:
    def test_initial_state(self) -> None:
        m = CacheMetrics()
        assert m.hits == 0
        assert m.misses == 0
        assert m.total == 0
        assert m.hit_rate == Decimal("0")

    def test_hit_rate_calculation(self) -> None:
        m = CacheMetrics()
        m.record_hit()
        m.record_hit()
        m.record_miss()
        # 2 hits / 3 total = 0.666...
        assert m.total == 3
        expected = Decimal("2") / Decimal("3")
        assert m.hit_rate == expected

    def test_hit_rate_all_hits(self) -> None:
        m = CacheMetrics()
        for _ in range(5):
            m.record_hit()
        assert m.hit_rate == Decimal("1")

    def test_hit_rate_all_misses(self) -> None:
        m = CacheMetrics()
        for _ in range(5):
            m.record_miss()
        assert m.hit_rate == Decimal("0")

    def test_reset(self) -> None:
        m = CacheMetrics()
        m.record_hit()
        m.record_miss()
        m.reset()
        assert m.hits == 0
        assert m.misses == 0

    def test_to_dict(self) -> None:
        m = CacheMetrics()
        m.record_hit()
        m.record_miss()
        d = m.to_dict()
        assert d["hits"] == 1
        assert d["misses"] == 1
        assert d["total"] == 2
        assert "hit_rate" in d


# ---------------------------------------------------------------------------
# PendleMarketCache テスト
# ---------------------------------------------------------------------------

MOCK_MARKETS_RESPONSE: dict[str, Any] = {
    "results": [
        {
            "address": "0x1234567890abcdef1234567890abcdef12345678",
            "underlyingAsset": {"symbol": "stETH"},
        },
        {
            "address": "0xabcdef1234567890abcdef1234567890abcdef12",
            "underlyingAsset": {"symbol": "wstETH"},
        },
        {
            "address": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "underlyingAsset": {"symbol": "USDC"},
        },
    ]
}


def _make_mock_response(data: dict[str, Any], status_code: int = 200) -> MagicMock:
    """httpx.Response モックを生成する。"""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = data
    if status_code >= 400:
        import httpx  # noqa: PLC0415

        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP Error {status_code}",
            request=MagicMock(),
            response=mock_resp,
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


@pytest.fixture()
def cache() -> PendleMarketCache:
    """テスト用 PendleMarketCache（TTL 300s）。"""
    return PendleMarketCache(chain_id=42161, ttl_seconds=300.0)


@pytest.fixture()
def short_ttl_cache() -> PendleMarketCache:
    """TTL 0.1 秒の短命キャッシュ（TTL 切れテスト用）。"""
    return PendleMarketCache(chain_id=42161, ttl_seconds=0.1)


class TestPendleMarketCache:
    @pytest.mark.asyncio
    async def test_cache_miss_fetches_api(self, cache: PendleMarketCache) -> None:
        """キャッシュミス時に API を呼び出して address を返す。"""
        mock_resp = _make_mock_response(MOCK_MARKETS_RESPONSE)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await cache.get_market_address("stETH")

        assert result == "0x1234567890abcdef1234567890abcdef12345678"

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_call_api(self, cache: PendleMarketCache) -> None:
        """キャッシュヒット時は API を呼び出さない。"""
        mock_resp = _make_mock_response(MOCK_MARKETS_RESPONSE)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # 1回目: miss → API 呼び出し
            result1 = await cache.get_market_address("stETH")
            api_call_count_after_miss = mock_client.get.call_count

            # 2回目: hit → API 呼び出しなし
            result2 = await cache.get_market_address("stETH")
            api_call_count_after_hit = mock_client.get.call_count

        assert result1 == result2
        assert api_call_count_after_hit == api_call_count_after_miss

    @pytest.mark.asyncio
    async def test_cache_metrics_hit_miss(self, cache: PendleMarketCache) -> None:
        """hit/miss カウンタが正しく更新される。"""
        mock_resp = _make_mock_response(MOCK_MARKETS_RESPONSE)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # miss
            await cache.get_market_address("stETH")
            # hit
            await cache.get_market_address("stETH")
            # hit
            await cache.get_market_address("stETH")

        metrics = cache.get_metrics()
        assert metrics.misses == 1
        assert metrics.hits == 2
        assert metrics.total == 3

    @pytest.mark.asyncio
    async def test_cache_expired_refetches(self, short_ttl_cache: PendleMarketCache) -> None:
        """TTL 切れ後は再度 API を呼び出す。"""
        mock_resp = _make_mock_response(MOCK_MARKETS_RESPONSE)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # 1回目: miss → API 呼び出し
            await short_ttl_cache.get_market_address("stETH")
            count_1 = mock_client.get.call_count

            # TTL 切れ待ち（0.15 秒 > TTL 0.1 秒）
            time.sleep(0.15)

            # 2回目: TTL 切れ → miss → API 呼び出し
            await short_ttl_cache.get_market_address("stETH")
            count_2 = mock_client.get.call_count

        assert count_2 > count_1

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_asset(self, cache: PendleMarketCache) -> None:
        """存在しないアセットは None を返す（fail-open）。"""
        mock_resp = _make_mock_response(MOCK_MARKETS_RESPONSE)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await cache.get_market_address("NONEXISTENT_TOKEN")

        assert result is None

    @pytest.mark.asyncio
    async def test_api_failure_returns_none(self, cache: PendleMarketCache) -> None:
        """API 障害時は None を返す（fail-open）。"""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=Exception("network error"))
            mock_client_cls.return_value = mock_client

            result = await cache.get_market_address("stETH")

        assert result is None

    @pytest.mark.asyncio
    async def test_http_status_error_returns_none(self, cache: PendleMarketCache) -> None:
        """HTTP 4xx/5xx エラー時は None を返す（fail-open）。"""
        import httpx  # noqa: PLC0415

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            error_resp = MagicMock()
            error_resp.status_code = 503
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    message="Service Unavailable",
                    request=MagicMock(),
                    response=error_resp,
                )
            )
            mock_client_cls.return_value = mock_client

            result = await cache.get_market_address("stETH")

        assert result is None

    @pytest.mark.asyncio
    async def test_case_insensitive_lookup(self, cache: PendleMarketCache) -> None:
        """大文字小文字を区別しない（stETH / STETH / Steth は同じキー）。"""
        mock_resp = _make_mock_response(MOCK_MARKETS_RESPONSE)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result_lower = await cache.get_market_address("steth")
            # 2回目はキャッシュに入っているので API 呼び出しなし
            result_upper = await cache.get_market_address("STETH")

        assert result_lower == result_upper
        assert cache.get_metrics().hits >= 1

    @pytest.mark.asyncio
    async def test_invalidate_forces_refetch(self, cache: PendleMarketCache) -> None:
        """invalidate 後は次回アクセスで再フェッチする。"""
        mock_resp = _make_mock_response(MOCK_MARKETS_RESPONSE)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # 初回 miss → キャッシュ格納
            await cache.get_market_address("stETH")
            count_before = mock_client.get.call_count

            # invalidate
            cache.invalidate("stETH")

            # 再アクセス → miss → 再フェッチ
            await cache.get_market_address("stETH")
            count_after = mock_client.get.call_count

        assert count_after > count_before

    @pytest.mark.asyncio
    async def test_invalidate_all_clears_cache(self, cache: PendleMarketCache) -> None:
        """invalidate_all 後は全エントリが消える。"""
        mock_resp = _make_mock_response(MOCK_MARKETS_RESPONSE)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            # 複数アセットをキャッシュ
            await cache.get_market_address("stETH")
            await cache.get_market_address("wstETH")

            # 全クリア
            cache.invalidate_all()
            cache.reset_metrics()

            # 再アクセス → 両方 miss
            await cache.get_market_address("stETH")
            await cache.get_market_address("wstETH")

        metrics = cache.get_metrics()
        assert metrics.misses == 2
        assert metrics.hits == 0

    @pytest.mark.asyncio
    async def test_get_all_markets_returns_list(self, cache: PendleMarketCache) -> None:
        """get_all_markets は市場リストを返す。"""
        mock_resp = _make_mock_response(MOCK_MARKETS_RESPONSE)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            markets = await cache.get_all_markets()

        assert len(markets) == 3
        assert markets[0]["address"] == "0x1234567890abcdef1234567890abcdef12345678"

    @pytest.mark.asyncio
    async def test_get_all_markets_api_failure_returns_empty(
        self, cache: PendleMarketCache
    ) -> None:
        """get_all_markets が API 失敗時に空リストを返す（fail-open）。"""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=Exception("network error"))
            mock_client_cls.return_value = mock_client

            markets = await cache.get_all_markets()

        assert markets == []

    def test_reset_metrics(self, cache: PendleMarketCache) -> None:
        """reset_metrics でカウンタがゼロに戻る。"""
        cache._metrics.record_hit()
        cache._metrics.record_miss()
        cache.reset_metrics()
        metrics = cache.get_metrics()
        assert metrics.hits == 0
        assert metrics.misses == 0


# ---------------------------------------------------------------------------
# PendleRouterV4Client.resolve_market_address テスト
# ---------------------------------------------------------------------------


@pytest.fixture()
def router_client_with_mock_cache() -> tuple[PendleRouterV4Client, MagicMock]:
    """PendleMarketCache をモック注入した PendleRouterV4Client を返す。"""
    config = PendleConfig()
    mock_cache = MagicMock(spec=PendleMarketCache)
    client = PendleRouterV4Client(config=config, market_cache=mock_cache)  # type: ignore[arg-type]
    return client, mock_cache


class TestPendleRouterV4ClientResolveMarketAddress:
    @pytest.mark.asyncio
    async def test_resolve_delegates_to_cache(
        self,
        router_client_with_mock_cache: tuple[PendleRouterV4Client, MagicMock],
    ) -> None:
        """resolve_market_address はキャッシュの get_market_address に委譲する。"""
        client, mock_cache = router_client_with_mock_cache
        expected_address = "0x1234567890abcdef1234567890abcdef12345678"
        mock_cache.get_market_address = AsyncMock(return_value=expected_address)

        result = await client.resolve_market_address("stETH")

        assert result == expected_address
        mock_cache.get_market_address.assert_called_once_with("stETH")

    @pytest.mark.asyncio
    async def test_resolve_returns_none_on_failure(
        self,
        router_client_with_mock_cache: tuple[PendleRouterV4Client, MagicMock],
    ) -> None:
        """resolve_market_address は None 返却を透過する（fail-open）。"""
        client, mock_cache = router_client_with_mock_cache
        mock_cache.get_market_address = AsyncMock(return_value=None)

        result = await client.resolve_market_address("NONEXISTENT")

        assert result is None

    def test_get_market_cache_returns_cache_instance(
        self,
        router_client_with_mock_cache: tuple[PendleRouterV4Client, MagicMock],
    ) -> None:
        """get_market_cache はキャッシュインスタンスを返す。"""
        client, mock_cache = router_client_with_mock_cache
        assert client.get_market_cache() is mock_cache

    def test_default_cache_created_when_not_injected(self) -> None:
        """market_cache を注入しない場合、PendleMarketCache が自動生成される。"""
        config = PendleConfig()
        client = PendleRouterV4Client(config=config)
        cache = client.get_market_cache()
        assert isinstance(cache, PendleMarketCache)

    def test_default_cache_uses_correct_chain_id(self) -> None:
        """自動生成されたキャッシュは config の chain に対応する chain_id を使う。"""
        config = PendleConfig()
        config.chain = "ethereum"
        client = PendleRouterV4Client(config=config)
        cache = client.get_market_cache()
        # PendleMarketCache の内部 chain_id を確認
        assert cache._chain_id == 1  # ethereum = 1
