"""PendleRouterV4Client ユニットテスト（モックを使用、実 API 呼び出しなし）。"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.protocols.pendle.client import PendleRouterV4Client
from app.protocols.pendle.config import PendleConfig
from app.protocols.pendle.schemas import RouterV4AddLiquidityResult, RouterV4SwapResult

from .convert_api_fixtures import convert_response, output

MARKET = "0x" + "aa" * 20
TOKEN_IN = "0x" + "bb" * 20
TOKEN_OUT = "0x" + "cc" * 20
RECEIVER = "0x" + "dd" * 20

# Convert API が返すモックレスポンス（swap 系）。tx.to は Router アドレス（C2 照合をパスする）。
# 応答形の定義は convert_api_fixtures に集約する（各ファイルで手書きしない）。
_MOCK_SWAP_RESPONSE: dict = convert_response(
    outputs=[output(TOKEN_OUT, int(Decimal("0.95") * Decimal(10**18)))],
)

# add_liquidity 系。LP 受取量は outputs の token=market(LP) アドレスから 18 桁で復元される。
_MOCK_ADD_LIQ_RESPONSE: dict = convert_response(
    data="0xcafebabe",
    action="add-liquidity",
    outputs=[output(MARKET, int(Decimal("0.98") * Decimal(10**18)))],
)


@pytest.fixture
def router_client() -> PendleRouterV4Client:
    config = PendleConfig(sandbox=False)
    # テスト用に enable_onchain_write=True（ガードを通過させる）
    config.enable_onchain_write = True
    return PendleRouterV4Client(config)


class TestPendleRouterV4ClientInit:
    def test_router_address_is_correct(self, router_client: PendleRouterV4Client) -> None:
        """Router アドレスが正しい Pendle V4 アドレスであること。"""
        assert router_client._config.router_address == "0x888888888889758F76e7103c6CbF23ABbF58F946"

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
    async def test_buy_yt_requests_yt_as_tokens_out(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """buy_yt が Convert API に tokensIn=入力トークン / tokensOut=YT を渡すこと。

        旧テストは「SDK の swapExactTokenForYt エンドポイントを呼ぶこと」を検証していたが、
        その個別エンドポイントは実在せず（Convert API に統合済み）、URL からは消えた。
        動作は tokensIn/tokensOut の組み合わせで API 側が決めるため、等価な不変条件として
        「渡すトークンの向き」を検証する。
        """
        captured_params: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_params[0]["tokensIn"] == TOKEN_IN
        assert captured_params[0]["tokensOut"] == "YT"
        assert captured_params[0]["receiver"] == RECEIVER

    @pytest.mark.asyncio
    async def test_buy_yt_default_slippage(self, router_client: PendleRouterV4Client) -> None:
        """buy_yt のデフォルトスリッページが 0.005 であること。"""
        captured_params: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_params[0]["slippage"] == "0.005"

    @pytest.mark.asyncio
    async def test_buy_yt_custom_slippage(self, router_client: PendleRouterV4Client) -> None:
        """buy_yt にカスタムスリッページを指定できること。"""
        captured_params: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
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
    async def test_sell_yt_requests_yt_as_tokens_in(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """sell_yt が Convert API に tokensIn=YT / tokensOut=出力トークンを渡すこと（売り方向）。

        旧テストの swapExactYtForToken エンドポイントは実在しないため、等価な不変条件
        （トークンの向きが売り方向であること）に置き換えた。
        """
        captured_params: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.sell_yt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert captured_params[0]["tokensIn"] == "YT"
        assert captured_params[0]["tokensOut"] == TOKEN_OUT

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
    async def test_buy_pt_requests_pt_as_tokens_out(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """buy_pt が tokensIn=入力トークン / tokensOut=**PT の実アドレス** を渡すこと（買い方向）。

        旧テストの swapExactTokenForPt エンドポイントは実在しないため、等価な不変条件
        （トークンの向きが買い方向であること）に置き換えた。さらに Convert API は
        tokensOut に実アドレスを要求するため、旧 SDK 規約のリテラル "PT" では通らない。
        """
        captured_params: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_pt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_params[0]["tokensIn"] == TOKEN_IN
        assert captured_params[0]["tokensOut"] == router_client._config.pt_token_address

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

        async def mock_call_sdk(params: dict) -> dict:
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
    async def test_sell_pt_requests_pt_as_tokens_in(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """sell_pt が Convert API に tokensIn=PT / tokensOut=出力トークンを渡すこと（売り方向）。

        旧テストの swapExactPtForToken エンドポイントは実在しないため、等価な不変条件
        （トークンの向きが売り方向であること）に置き換えた。
        """
        captured_params: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_SWAP_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.sell_pt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert captured_params[0]["tokensIn"] == router_client._config.pt_token_address
        assert captured_params[0]["tokensOut"] == TOKEN_OUT

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
    async def test_add_liquidity_requests_market_as_tokens_out(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """add_liquidity が Convert API に tokensOut=market(LP) アドレスを渡すこと。

        旧テストの addLiquiditySingleToken エンドポイントは実在しない。Convert API は swap と
        同一エンドポイントで、tokensOut に market(LP) アドレスを渡すと action="add-liquidity"
        になる。等価な不変条件として「LP を要求する向きで渡していること」を検証する。
        """
        captured_params: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_ADD_LIQ_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_params[0]["tokensIn"] == TOKEN_IN
        assert captured_params[0]["tokensOut"] == MARKET

    @pytest.mark.asyncio
    async def test_add_liquidity_default_slippage(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """add_liquidity のデフォルトスリッページが 0.005 であること。"""
        captured_params: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_ADD_LIQ_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured_params[0]["slippage"] == "0.005"

    @pytest.mark.asyncio
    async def test_add_liquidity_custom_slippage(self, router_client: PendleRouterV4Client) -> None:
        """add_liquidity にカスタムスリッページを指定できること。"""
        captured_params: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
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
        """add_liquidity が Convert API に正しいパラメータを渡すこと。

        Convert API のパラメータ名は複数形（tokensIn / tokensOut / amountsIn）で、
        market は独立キーでは渡さない（対象 market は tokensOut 側で一意に決まる）。
        """
        captured_params: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured_params.append(params)
            return _MOCK_ADD_LIQ_RESPONSE

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)

        p = captured_params[0]
        assert p["tokensIn"] == TOKEN_IN
        assert p["tokensOut"] == MARKET
        assert p["receiver"] == RECEIVER
        assert p["amountsIn"] == str(10**18)
        assert "market" not in p


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
