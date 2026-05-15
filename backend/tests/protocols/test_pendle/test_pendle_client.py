"""PendleClient ユニットテスト（DummyPendleClient / PendleWebClient）。"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.protocols.pendle.client import DummyPendleClient, PendleWebClient, get_pendle_client
from app.protocols.pendle.config import PendleConfig
from app.protocols.pendle.schemas import PendleMarketInfo


@pytest.fixture
def dummy_config() -> PendleConfig:
    return PendleConfig(sandbox=True)


@pytest.fixture
def dummy_client(dummy_config: PendleConfig) -> DummyPendleClient:
    return DummyPendleClient(dummy_config)


class TestDummyPendleClientMintSy:
    @pytest.mark.asyncio
    async def test_mint_sy_returns_success(self, dummy_client: DummyPendleClient) -> None:
        result = await dummy_client.mint_sy("0x" + "0" * 40, Decimal("1.0"))
        assert result["success"] is True
        assert result["sy_received"] == Decimal("1.0")
        assert result["tx_hash"] is not None
        assert result["tx_hash"].startswith("0x")

    @pytest.mark.asyncio
    async def test_mint_sy_amount_preserved(self, dummy_client: DummyPendleClient) -> None:
        amount = Decimal("0.5")
        result = await dummy_client.mint_sy("0xstETH", amount)
        assert result["sy_received"] == amount


class TestDummyPendleClientMintPtYt:
    @pytest.mark.asyncio
    async def test_mint_pt_yt_returns_pt_and_yt(self, dummy_client: DummyPendleClient) -> None:
        result = await dummy_client.mint_pt_yt(Decimal("1.0"), "0x" + "0" * 40)
        assert result["success"] is True
        assert "pt_received" in result
        assert "yt_received" in result
        assert result["tx_hash"] is not None

    @pytest.mark.asyncio
    async def test_mint_pt_yt_amounts_are_decimal(self, dummy_client: DummyPendleClient) -> None:
        result = await dummy_client.mint_pt_yt(Decimal("2.0"), "0x" + "0" * 40)
        assert type(result["pt_received"]) is Decimal
        assert type(result["yt_received"]) is Decimal

    @pytest.mark.asyncio
    async def test_mint_pt_yt_pt_amount_calculated_correctly(
        self, dummy_client: DummyPendleClient
    ) -> None:
        """PT 量 = sy_amount / pt_price (0.95) を確認。"""
        sy_amount = Decimal("1.0")
        result = await dummy_client.mint_pt_yt(sy_amount, "0x" + "0" * 40)
        expected_pt = sy_amount / Decimal("0.95")
        assert result["pt_received"] == expected_pt


class TestDummyPendleClientGetMarketInfo:
    @pytest.mark.asyncio
    async def test_get_market_info_returns_valid_info(
        self, dummy_client: DummyPendleClient
    ) -> None:
        market_address = "0x" + "ab" * 20
        info = await dummy_client.get_market_info(market_address)
        assert isinstance(info, PendleMarketInfo)
        assert info.market_address == market_address
        assert info.underlying_asset == "stETH"
        assert info.days_to_maturity == 30

    @pytest.mark.asyncio
    async def test_get_market_info_pt_price_is_095(self, dummy_client: DummyPendleClient) -> None:
        info = await dummy_client.get_market_info("0x" + "0" * 40)
        assert info.pt_price == Decimal("0.95")

    @pytest.mark.asyncio
    async def test_get_market_info_yt_price_is_005(self, dummy_client: DummyPendleClient) -> None:
        info = await dummy_client.get_market_info("0x" + "0" * 40)
        assert info.yt_price == Decimal("0.05")

    @pytest.mark.asyncio
    async def test_get_market_info_implied_apy_is_52(self, dummy_client: DummyPendleClient) -> None:
        info = await dummy_client.get_market_info("0x" + "0" * 40)
        assert info.implied_apy == Decimal("5.2")

    @pytest.mark.asyncio
    async def test_get_market_info_tvl_is_50m(self, dummy_client: DummyPendleClient) -> None:
        info = await dummy_client.get_market_info("0x" + "0" * 40)
        assert info.tvl_usd == Decimal("50000000")

    @pytest.mark.asyncio
    async def test_get_market_info_all_decimal(self, dummy_client: DummyPendleClient) -> None:
        """全ての金額フィールドが Decimal であることを確認（float なし）。"""
        info = await dummy_client.get_market_info("0x" + "0" * 40)
        assert type(info.implied_apy) is Decimal
        assert type(info.pt_price) is Decimal
        assert type(info.yt_price) is Decimal
        assert type(info.tvl_usd) is Decimal


class TestDummyPendleClientPrices:
    @pytest.mark.asyncio
    async def test_get_pt_price_returns_095(self, dummy_client: DummyPendleClient) -> None:
        price = await dummy_client.get_pt_price("0x" + "0" * 40)
        assert price == Decimal("0.95")

    @pytest.mark.asyncio
    async def test_get_yt_price_returns_005(self, dummy_client: DummyPendleClient) -> None:
        price = await dummy_client.get_yt_price("0x" + "0" * 40)
        assert price == Decimal("0.05")

    @pytest.mark.asyncio
    async def test_pt_price_is_decimal(self, dummy_client: DummyPendleClient) -> None:
        price = await dummy_client.get_pt_price("0x" + "0" * 40)
        assert type(price) is Decimal

    @pytest.mark.asyncio
    async def test_yt_price_is_decimal(self, dummy_client: DummyPendleClient) -> None:
        price = await dummy_client.get_yt_price("0x" + "0" * 40)
        assert type(price) is Decimal


class TestGetPendleClient:
    def test_sandbox_returns_dummy_client(self) -> None:
        config = PendleConfig(sandbox=True)
        client = get_pendle_client(config)
        assert isinstance(client, DummyPendleClient)

    def test_non_sandbox_returns_web_client(self) -> None:
        """sandbox=False の場合、PendleWebClient を返す。"""
        config = PendleConfig(sandbox=False)
        client = get_pendle_client(config)
        assert isinstance(client, PendleWebClient)

    def test_production_env_with_sandbox_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """APP_ENV=production + sandbox=True でエラーが発生すること。"""
        monkeypatch.setenv("APP_ENV", "production")
        config = PendleConfig(sandbox=True)
        with pytest.raises(RuntimeError, match="DummyClient cannot be used in production"):
            get_pendle_client(config)

    def test_staging_env_with_sandbox_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Phase 1 期間中、APP_ENV=staging + sandbox=True は DummyClient を返すこと（docs/13 §1.4）。"""
        monkeypatch.setenv("APP_ENV", "staging")
        config = PendleConfig(sandbox=True)
        client = get_pendle_client(config)
        assert isinstance(client, DummyPendleClient)

    def test_development_env_with_sandbox_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """APP_ENV=development + sandbox=True は正常動作すること。"""
        monkeypatch.setenv("APP_ENV", "development")
        config = PendleConfig(sandbox=True)
        client = get_pendle_client(config)
        assert isinstance(client, DummyPendleClient)


@pytest.fixture
def web_client() -> PendleWebClient:
    return PendleWebClient(PendleConfig(sandbox=False))


_MOCK_MARKET_DATA = {
    "expiry": "1714521600",
    "impliedApy": 0.052,
    "pt": {"price": {"usd": 0.95}},
    "yt": {"price": {"usd": 0.05}},
    "liquidity": {"usd": 50000000},
    "underlyingAsset": {"symbol": "stETH"},
}


class TestPendleWebClientGetMarketInfo:
    @pytest.mark.asyncio
    async def test_get_market_info_success(self, web_client: PendleWebClient) -> None:
        """API 成功時に PendleMarketInfo を返すこと。"""
        with patch.object(
            web_client, "_fetch_market_data", new=AsyncMock(return_value=_MOCK_MARKET_DATA)
        ):
            info = await web_client.get_market_info("0x" + "0" * 40)
        assert isinstance(info, PendleMarketInfo)
        assert info.implied_apy == Decimal("5.2")
        assert info.pt_price == Decimal("0.95")
        assert info.yt_price == Decimal("0.05")
        assert info.tvl_usd == Decimal("50000000")
        assert info.underlying_asset == "stETH"

    @pytest.mark.asyncio
    async def test_get_market_info_implied_apy_is_decimal(
        self, web_client: PendleWebClient
    ) -> None:
        """implied_apy が Decimal であること。"""
        with patch.object(
            web_client, "_fetch_market_data", new=AsyncMock(return_value=_MOCK_MARKET_DATA)
        ):
            info = await web_client.get_market_info("0x" + "0" * 40)
        assert type(info.implied_apy) is Decimal

    @pytest.mark.asyncio
    async def test_get_market_info_fallback_on_api_error(self, web_client: PendleWebClient) -> None:
        """API 失敗時にフォールバック値（implied_apy=5.2, tvl=0）を返すこと。"""
        with patch.object(
            web_client,
            "_fetch_market_data",
            new=AsyncMock(side_effect=Exception("connection error")),
        ):
            info = await web_client.get_market_info("0x" + "0" * 40)
        assert isinstance(info, PendleMarketInfo)
        assert info.implied_apy == Decimal("5.2")
        assert info.tvl_usd == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_pt_price_from_api(self, web_client: PendleWebClient) -> None:
        """PT 価格が API から取得されること。"""
        with patch.object(
            web_client, "_fetch_market_data", new=AsyncMock(return_value=_MOCK_MARKET_DATA)
        ):
            price = await web_client.get_pt_price("0x" + "0" * 40)
        assert price == Decimal("0.95")
        assert type(price) is Decimal

    @pytest.mark.asyncio
    async def test_get_yt_price_from_api(self, web_client: PendleWebClient) -> None:
        """YT 価格が API から取得されること。"""
        with patch.object(
            web_client, "_fetch_market_data", new=AsyncMock(return_value=_MOCK_MARKET_DATA)
        ):
            price = await web_client.get_yt_price("0x" + "0" * 40)
        assert price == Decimal("0.05")
        assert type(price) is Decimal


class TestPendleWebClientTransactions:
    @pytest.mark.asyncio
    async def test_mint_sy_returns_failure(self, web_client: PendleWebClient) -> None:
        """mint_sy は Phase 2 では失敗を返すこと。"""
        result = await web_client.mint_sy("0x" + "0" * 40, Decimal("1.0"))
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mint_pt_yt_returns_failure(self, web_client: PendleWebClient) -> None:
        """mint_pt_yt は Phase 2 では失敗を返すこと。"""
        result = await web_client.mint_pt_yt(Decimal("1.0"), "0x" + "0" * 40)
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_redeem_pt_returns_failure(self, web_client: PendleWebClient) -> None:
        """redeem_pt は Phase 2 では失敗を返すこと。"""
        result = await web_client.redeem_pt(Decimal("1.0"), "0x" + "0" * 40)
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_redeem_yt_returns_failure(self, web_client: PendleWebClient) -> None:
        """redeem_yt は Phase 2 では失敗を返すこと。"""
        result = await web_client.redeem_yt(Decimal("1.0"), "0x" + "0" * 40)
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_supply_via_base_returns_failure(self, web_client: PendleWebClient) -> None:
        """BaseProtocolClient.supply() は mint_sy を通じて失敗を返すこと。"""
        result = await web_client.supply(Decimal("1.0"), "stETH")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_withdraw_via_base_returns_failure(self, web_client: PendleWebClient) -> None:
        """BaseProtocolClient.withdraw() は redeem_pt を通じて失敗を返すこと。"""
        with patch.object(
            web_client,
            "_fetch_market_data",
            new=AsyncMock(side_effect=Exception("api error")),
        ):
            result = await web_client.withdraw(Decimal("1.0"), "PT")
        assert result.success is False
