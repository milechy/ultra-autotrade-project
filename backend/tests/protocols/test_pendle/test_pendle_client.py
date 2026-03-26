"""DummyPendleClient のユニットテスト。"""

from decimal import Decimal

import pytest

from app.protocols.pendle.client import DummyPendleClient, get_pendle_client
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

    def test_non_sandbox_also_returns_dummy_client_in_poc(self) -> None:
        """PoC フェーズでは sandbox=False でも DummyPendleClient を返す。"""
        config = PendleConfig(sandbox=False)
        client = get_pendle_client(config)
        assert isinstance(client, DummyPendleClient)
