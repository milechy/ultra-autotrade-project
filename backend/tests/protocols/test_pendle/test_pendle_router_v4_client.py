"""PendleRouterV4Client ユニットテスト（モックを使用、実 API 呼び出しなし）。"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.protocols.pendle.client import PendleRouterV4Client
from app.protocols.pendle.config import PendleConfig
from app.protocols.pendle.schemas import RouterV4AddLiquidityResult, RouterV4SwapResult

MARKET = "0x" + "aa" * 20
TOKEN_IN = "0x" + "bb" * 20
TOKEN_OUT = "0x" + "cc" * 20
RECEIVER = "0x" + "dd" * 20

# SDK が返すモックレスポンス（swap 系）
_MOCK_SWAP_RESPONSE: dict = {
    "data": {
        "tx": {
            "data": "0xdeadbeef",
        },
        "amountOut": str(int(Decimal("0.95") * Decimal(10**18))),
    }
}

# SDK が返すモックレスポンス（add_liquidity 系）
_MOCK_ADD_LIQ_RESPONSE: dict = {
    "data": {
        "tx": {
            "data": "0xcafebabe",
        },
        "amountLpOut": str(int(Decimal("0.98") * Decimal(10**18))),
    }
}


@pytest.fixture
def router_client() -> PendleRouterV4Client:
    config = PendleConfig(sandbox=False)
    return PendleRouterV4Client(config)


class TestPendleRouterV4ClientInit:
    def test_router_address_is_correct(self, router_client: PendleRouterV4Client) -> None:
        """Router アドレスが正しい Pendle V4 アドレスであること。"""
        assert router_client._ROUTER_ADDRESS == "0x888888888889758F76e7103c6CbF23ABbF58F946"

    def test_default_slippage_is_half_percent(self, router_client: PendleRouterV4Client) -> None:
        """デフォルトスリッページが 0.5% (0.005) であること。"""
        assert router_client._DEFAULT_SLIPPAGE == Decimal("0.005")

    def test_chain_id_mapped_for_arbitrum(self) -> None:
        """arbitrum チェーンの場合 chain_id = 42161 であること。"""
        config = PendleConfig(sandbox=False)
        config.chain = "arbitrum"
        client = PendleRouterV4Client(config)
        assert client._chain_id == 42161

    def test_chain_id_mapped_for_sepolia(self) -> None:
        """sepolia チェーンの場合 chain_id = 421614 であること。"""
        config = PendleConfig(sandbox=False)
        config.chain = "sepolia"
        client = PendleRouterV4Client(config)
        assert client._chain_id == 421614


class TestAmountConversion:
    def test_amount_to_wei_1_ether(self, router_client: PendleRouterV4Client) -> None:
        """1 ETH = 1e18 wei の変換が正しいこと。"""
        assert router_client._amount_to_wei(Decimal("1")) == 10**18

    def test_amount_to_wei_decimal_precision(self, router_client: PendleRouterV4Client) -> None:
        """0.5 ETH の変換が正しいこと。"""
        assert router_client._amount_to_wei(Decimal("0.5")) == 5 * 10**17

    def test_wei_to_decimal_roundtrip(self, router_client: PendleRouterV4Client) -> None:
        """_amount_to_wei → _wei_to_decimal のラウンドトリップが正確であること。"""
        original = Decimal("1.23456789")
        wei = router_client._amount_to_wei(original)
        restored = router_client._wei_to_decimal(wei)
        assert restored == original

    def test_amount_to_wei_custom_decimals(self, router_client: PendleRouterV4Client) -> None:
        """カスタム decimals=6 の変換（USDC 等）が正しいこと。"""
        assert router_client._amount_to_wei(Decimal("1"), decimals=6) == 10**6

    def test_amount_types_are_decimal(self, router_client: PendleRouterV4Client) -> None:
        """_wei_to_decimal の戻り値が Decimal であること（float 禁止）。"""
        result = router_client._wei_to_decimal(10**18)
        assert type(result) is Decimal


class TestBuyYt:
    @pytest.mark.asyncio
    async def test_buy_yt_success(self, router_client: PendleRouterV4Client) -> None:
        """buy_yt が成功時に RouterV4SwapResult(success=True) を返すこと。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert isinstance(result, RouterV4SwapResult)
        assert result.success is True
        assert result.calldata == "0xdeadbeef"
        assert result.amount_out is not None

    @pytest.mark.asyncio
    async def test_buy_yt_amount_out_is_decimal(self, router_client: PendleRouterV4Client) -> None:
        """buy_yt の amount_out が Decimal であること（float 禁止）。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.amount_out is not None
        assert type(result.amount_out) is Decimal

    @pytest.mark.asyncio
    async def test_buy_yt_uses_swapExactTokenForYt_endpoint(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """buy_yt が SDK の swapExactTokenForYt エンドポイントを呼ぶこと。"""
        captured_endpoint: list[str] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_endpoint.append(endpoint)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_endpoint[0] == "swapExactTokenForYt"

    @pytest.mark.asyncio
    async def test_buy_yt_default_slippage(self, router_client: PendleRouterV4Client) -> None:
        """buy_yt のデフォルトスリッページが 0.005 であること。"""
        captured_params: list[dict] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_params[0]["slippage"] == "0.005"

    @pytest.mark.asyncio
    async def test_buy_yt_custom_slippage(self, router_client: PendleRouterV4Client) -> None:
        """buy_yt にカスタムスリッページを指定できること。"""
        captured_params: list[dict] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_yt(
                MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER, slippage=Decimal("0.01")
            )
        assert captured_params[0]["slippage"] == "0.01"

    @pytest.mark.asyncio
    async def test_buy_yt_http_error_returns_failure(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """buy_yt が HTTP エラー時に success=False を返すこと（fail-open）。"""
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError("error", request=None, response=mock_response)
            ),  # type: ignore[arg-type]
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_buy_yt_network_error_returns_failure(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """buy_yt がネットワークエラー時に success=False を返すこと（fail-open）。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(side_effect=Exception("connection refused")),
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert "connection refused" in (result.error or "")


class TestSellYt:
    @pytest.mark.asyncio
    async def test_sell_yt_success(self, router_client: PendleRouterV4Client) -> None:
        """sell_yt が成功時に RouterV4SwapResult(success=True) を返すこと。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await router_client.sell_yt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert result.success is True
        assert result.calldata == "0xdeadbeef"

    @pytest.mark.asyncio
    async def test_sell_yt_uses_swapExactYtForToken_endpoint(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """sell_yt が SDK の swapExactYtForToken エンドポイントを呼ぶこと。"""
        captured_endpoint: list[str] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_endpoint.append(endpoint)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.sell_yt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert captured_endpoint[0] == "swapExactYtForToken"

    @pytest.mark.asyncio
    async def test_sell_yt_error_returns_failure(self, router_client: PendleRouterV4Client) -> None:
        """sell_yt がエラー時に success=False を返すこと。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(side_effect=Exception("timeout")),
        ):
            result = await router_client.sell_yt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_sell_yt_amount_out_decimal(self, router_client: PendleRouterV4Client) -> None:
        """sell_yt の amount_out が Decimal であること。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await router_client.sell_yt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert result.amount_out is not None
        assert type(result.amount_out) is Decimal


class TestBuyPt:
    @pytest.mark.asyncio
    async def test_buy_pt_success(self, router_client: PendleRouterV4Client) -> None:
        """buy_pt が成功時に RouterV4SwapResult(success=True) を返すこと。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await router_client.buy_pt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is True
        assert result.calldata == "0xdeadbeef"

    @pytest.mark.asyncio
    async def test_buy_pt_uses_swapExactTokenForPt_endpoint(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """buy_pt が SDK の swapExactTokenForPt エンドポイントを呼ぶこと。"""
        captured_endpoint: list[str] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_endpoint.append(endpoint)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_pt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_endpoint[0] == "swapExactTokenForPt"

    @pytest.mark.asyncio
    async def test_buy_pt_error_returns_failure(self, router_client: PendleRouterV4Client) -> None:
        """buy_pt がエラー時に success=False を返すこと。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(side_effect=Exception("network error")),
        ):
            result = await router_client.buy_pt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_buy_pt_amount_out_decimal(self, router_client: PendleRouterV4Client) -> None:
        """buy_pt の amount_out が Decimal であること。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await router_client.buy_pt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.amount_out is not None
        assert type(result.amount_out) is Decimal

    @pytest.mark.asyncio
    async def test_buy_pt_default_slippage(self, router_client: PendleRouterV4Client) -> None:
        """buy_pt のデフォルトスリッページが 0.005 であること。"""
        captured_params: list[dict] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_pt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_params[0]["slippage"] == "0.005"


class TestSellPt:
    @pytest.mark.asyncio
    async def test_sell_pt_success(self, router_client: PendleRouterV4Client) -> None:
        """sell_pt が成功時に RouterV4SwapResult(success=True) を返すこと。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await router_client.sell_pt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert result.success is True
        assert result.calldata == "0xdeadbeef"

    @pytest.mark.asyncio
    async def test_sell_pt_uses_swapExactPtForToken_endpoint(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """sell_pt が SDK の swapExactPtForToken エンドポイントを呼ぶこと。"""
        captured_endpoint: list[str] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_endpoint.append(endpoint)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.sell_pt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert captured_endpoint[0] == "swapExactPtForToken"

    @pytest.mark.asyncio
    async def test_sell_pt_error_returns_failure(self, router_client: PendleRouterV4Client) -> None:
        """sell_pt がエラー時に success=False を返すこと。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(side_effect=Exception("sdk error")),
        ):
            result = await router_client.sell_pt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_sell_pt_http_error_returns_failure(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """sell_pt が HTTP エラー時に success=False を返すこと（fail-open）。"""
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "error",
                    request=None,
                    response=mock_response,  # type: ignore[arg-type]
                )
            ),
        ):
            result = await router_client.sell_pt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error is not None


class TestAddLiquidity:
    @pytest.mark.asyncio
    async def test_add_liquidity_success(self, router_client: PendleRouterV4Client) -> None:
        """add_liquidity が成功時に RouterV4AddLiquidityResult(success=True) を返すこと。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_ADD_LIQ_RESPONSE)
        ):
            result = await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert isinstance(result, RouterV4AddLiquidityResult)
        assert result.success is True
        assert result.calldata == "0xcafebabe"
        assert result.lp_amount is not None

    @pytest.mark.asyncio
    async def test_add_liquidity_lp_amount_is_decimal(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """add_liquidity の lp_amount が Decimal であること（float 禁止）。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_ADD_LIQ_RESPONSE)
        ):
            result = await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.lp_amount is not None
        assert type(result.lp_amount) is Decimal

    @pytest.mark.asyncio
    async def test_add_liquidity_uses_addLiquiditySingleToken_endpoint(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """add_liquidity が SDK の addLiquiditySingleToken エンドポイントを呼ぶこと。"""
        captured_endpoint: list[str] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_endpoint.append(endpoint)
            return _MOCK_ADD_LIQ_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_endpoint[0] == "addLiquiditySingleToken"

    @pytest.mark.asyncio
    async def test_add_liquidity_default_slippage(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """add_liquidity のデフォルトスリッページが 0.005 であること。"""
        captured_params: list[dict] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_ADD_LIQ_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_params[0]["slippage"] == "0.005"

    @pytest.mark.asyncio
    async def test_add_liquidity_custom_slippage(self, router_client: PendleRouterV4Client) -> None:
        """add_liquidity にカスタムスリッページを指定できること。"""
        captured_params: list[dict] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_ADD_LIQ_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.add_liquidity(
                MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER, slippage=Decimal("0.02")
            )
        assert captured_params[0]["slippage"] == "0.02"

    @pytest.mark.asyncio
    async def test_add_liquidity_http_error_returns_failure(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """add_liquidity が HTTP エラー時に success=False を返すこと（fail-open）。"""
        mock_response = AsyncMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "error",
                    request=None,
                    response=mock_response,  # type: ignore[arg-type]
                )
            ),
        ):
            result = await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_add_liquidity_network_error_returns_failure(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """add_liquidity がネットワークエラー時に success=False を返すこと（fail-open）。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(side_effect=Exception("connection timeout")),
        ):
            result = await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert "connection timeout" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_liquidity_passes_correct_params(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """add_liquidity が SDK に正しいパラメータを渡すこと。"""
        captured_params: list[dict] = []

        async def mock_call_sdk(endpoint: str, params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_ADD_LIQ_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)

        p = captured_params[0]
        assert p["market"] == MARKET
        assert p["tokenIn"] == TOKEN_IN
        assert p["receiver"] == RECEIVER
        assert "amountIn" in p


class TestSecurityConstraints:
    """セキュリティ制約のテスト。"""

    @pytest.mark.asyncio
    async def test_no_private_key_in_logs(
        self, router_client: PendleRouterV4Client, caplog: pytest.LogCaptureFixture
    ) -> None:
        """ログに秘密鍵が出力されないこと。"""
        import logging

        config = PendleConfig(sandbox=False)
        config.wallet_private_key = "0xsecretprivatekey12345"
        client = PendleRouterV4Client(config)

        with caplog.at_level(logging.INFO):
            with patch.object(client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)):
                await client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)

        for record in caplog.records:
            assert "secretprivatekey" not in record.message

    @pytest.mark.asyncio
    async def test_amount_out_no_float(self, router_client: PendleRouterV4Client) -> None:
        """全ての金額フィールドで float が使用されていないこと。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.5"), RECEIVER)
        # amount_out が float でないこと
        if result.amount_out is not None:
            assert not isinstance(result.amount_out, float)
            assert isinstance(result.amount_out, Decimal)
