"""PendleRouterV4Client セキュリティレビュー指摘の回帰テスト（C2/C3/M1/m1）。

- C2: routes[0].tx.to を Router アドレスと照合し不一致を拒否。approve の spender は
  **API の返り値に依存せず**照合済み Router で補完する（Convert API は spender を返さない）
- C3: 非18桁トークン（USDC=6）の amountsIn 桁ズレを防ぐ decimals 解決
- M1: slippage 境界（0 / 0.05 / 0.051 / 負値）の Pydantic 制約
- m1: calldata 欠損/空文字を success=False で拒否

モックする応答形は `convert_api_fixtures.convert_response()`（実 API 準拠）に集約する。
各ファイルで手書きすると、かつてのように架空の契約を固定してしまう。
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.protocols.pendle.client import PendleRouterV4Client
from app.protocols.pendle.config import PendleConfig
from app.protocols.pendle.schemas import RouterV4SwapRequest

from .convert_api_fixtures import ROUTER, approval, convert_response, output

MARKET = "0x" + "aa" * 20
TOKEN_IN = "0x" + "bb" * 20
TOKEN_OUT = "0x" + "cc" * 20
RECEIVER = "0x" + "dd" * 20
EVIL_CONTRACT = "0x" + "ee" * 20


@pytest.fixture
def router_client() -> PendleRouterV4Client:
    """C2/C3/m1 セキュリティ照合テスト用クライアント。

    enable_onchain_write=True を設定し、Q1 ガードをバイパスする。
    これにより C2（Router 照合）/ C3（decimals）/ m1（calldata）の照合ロジック自体をテストできる。
    enable_onchain_write=False のガード動作は test_pendle_router_v4_guard.py で検証する。
    """
    config = PendleConfig(sandbox=False)
    config.enable_onchain_write = True
    return PendleRouterV4Client(config)


# --- C2: Router アドレス照合 ---


class TestRouterAddressVerification:
    @pytest.mark.asyncio
    async def test_buy_yt_rejects_wrong_tx_to(self, router_client: PendleRouterV4Client) -> None:
        """tx.to が Router 以外なら success=False, error='router address mismatch'。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(return_value=convert_response(to=EVIL_CONTRACT)),
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error == "router address mismatch"
        assert result.calldata is None

    @pytest.mark.asyncio
    async def test_buy_yt_accepts_checksum_case_mismatch(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """tx.to が小文字（checksum 違い）でも Router なら受理する。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(return_value=convert_response(to=ROUTER.lower())),
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is True
        assert result.to is not None
        assert result.to.lower() == ROUTER.lower()

    @pytest.mark.asyncio
    async def test_buy_yt_rejects_missing_tx_to(self, router_client: PendleRouterV4Client) -> None:
        """tx.to 欠損は照合不能 → 拒否。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(return_value=convert_response(include_tx=False)),
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error == "router address mismatch"

    @pytest.mark.asyncio
    async def test_buy_yt_rejects_missing_route(self, router_client: PendleRouterV4Client) -> None:
        """routes が空なら照合対象が存在しない → 拒否（fail-closed）。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(return_value=convert_response(include_routes=False)),
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error == "router address mismatch"

    @pytest.mark.asyncio
    async def test_approval_spender_ignores_api_supplied_spender(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """API が spender を混入させても無視し、照合済み Router を spender にすること。

        旧テストは「API が返した spender が Router 以外なら拒否する」を検証していたが、
        その挙動は既に存在しない（実 Convert API は spender を返さないため、client は
        API 由来の spender を一切読まず、`_verify_router` で照合済みの宛先だけを使う）。
        ここではより強い不変条件を検証する: **API が何を返そうと approve 先は照合済み
        Router 以外にならない**（悪意ある spender の注入経路が存在しない）。
        """
        rogue = [{"token": TOKEN_IN, "spender": EVIL_CONTRACT, "amount": "100"}]
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(return_value=convert_response(required_approvals=rogue)),
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is True
        assert len(result.approvals) == 1
        # EVIL_CONTRACT は素通りせず、照合済み Router に置き換わる
        assert result.approvals[0].spender == ROUTER
        assert result.approvals[0].token == TOKEN_IN

    @pytest.mark.asyncio
    async def test_approval_spender_filled_from_verified_router(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """実 API 通り spender 無しで返っても、照合済み Router が補完されること。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(
                return_value=convert_response(required_approvals=[approval(TOKEN_IN, 100)])
            ),
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is True
        assert len(result.approvals) == 1
        assert result.approvals[0].spender == ROUTER
        assert result.approvals[0].amount == "100"

    @pytest.mark.asyncio
    async def test_wrong_tx_to_yields_no_approvals(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """tx.to が Router 以外なら approvals ごと破棄されること（approve 先が漏れない）。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(
                return_value=convert_response(
                    to=EVIL_CONTRACT, required_approvals=[approval(TOKEN_IN, 100)]
                )
            ),
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error == "router address mismatch"
        assert result.approvals == []

    @pytest.mark.asyncio
    async def test_add_liquidity_rejects_wrong_tx_to(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """add_liquidity も tx.to を照合する。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(return_value=convert_response(to=EVIL_CONTRACT, data="0xcafebabe")),
        ):
            result = await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error == "router address mismatch"


# --- C3: token decimals 解決 ---


class TestTokenDecimals:
    @pytest.mark.asyncio
    async def test_buy_yt_usdc_uses_6_decimals(self, router_client: PendleRouterV4Client) -> None:
        """token_in_decimals=6（USDC）で amountsIn が 10^6 単位になること。"""
        captured: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured.append(params)
            return convert_response()

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_yt(
                MARKET, "USDC", Decimal("100"), RECEIVER, token_in_decimals=6
            )
        # 100 USDC * 10^6 = 100_000_000（18 桁なら 10^20 になってしまう）
        assert captured[0]["amountsIn"] == str(100 * 10**6)

    @pytest.mark.asyncio
    async def test_buy_yt_usdc_resolved_from_config_map(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """token_in_decimals 未指定でもシンボル 'USDC' から 6 桁を解決すること。"""
        captured: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured.append(params)
            return convert_response()

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_yt(MARKET, "usdc", Decimal("100"), RECEIVER)
        assert captured[0]["amountsIn"] == str(100 * 10**6)

    @pytest.mark.asyncio
    async def test_buy_yt_unknown_token_defaults_18(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """未知トークンは 18 桁にフォールバックすること（後方互換）。"""
        captured: list[dict] = []

        async def mock_call_sdk(params: dict) -> dict:
            captured.append(params)
            return convert_response()

        with patch.object(router_client, "_call_sdk", side_effect=mock_call_sdk):
            await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert captured[0]["amountsIn"] == str(10**18)

    @pytest.mark.asyncio
    async def test_sell_yt_usdc_out_amount_uses_6_decimals(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """sell_yt の出力 USDC で amount_out が 6 桁前提で復元されること。

        amount_out は routes[0].outputs のうち token_out に一致するものから復元されるため、
        outputs は client が要求した token_out（ここでは "USDC"）に紐づけて置く。
        """
        with patch.object(
            router_client,
            "_call_sdk",
            # 100 USDC (6 decimals)
            new=AsyncMock(return_value=convert_response(outputs=[output("USDC", 100 * 10**6)])),
        ):
            result = await router_client.sell_yt(
                MARKET, "USDC", Decimal("1.0"), RECEIVER, token_out_decimals=6
            )
        assert result.success is True
        assert result.amount_out == Decimal("100")

    @pytest.mark.asyncio
    async def test_amount_out_picks_matching_token_not_first(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """outputs が複数あるとき token_out に一致するものを選ぶこと（先頭決め打ちでない）。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(
                return_value=convert_response(
                    outputs=[
                        output(TOKEN_IN, 999 * 10**6),  # 別トークン（選ばれてはいけない）
                        output("USDC", 100 * 10**6),
                    ]
                )
            ),
        ):
            result = await router_client.sell_yt(
                MARKET, "USDC", Decimal("1.0"), RECEIVER, token_out_decimals=6
            )
        assert result.success is True
        assert result.amount_out == Decimal("100")

    def test_config_token_decimals_map(self) -> None:
        """config の token_decimals が USDC=6, WBTC=8, default=18 を返すこと。"""
        config = PendleConfig(sandbox=False)
        assert config.token_decimals("USDC") == 6
        assert config.token_decimals("usdt") == 6
        assert config.token_decimals("WBTC") == 8
        assert config.token_decimals("WETH") == 18


# --- M1: slippage 境界 ---


class TestSlippageBounds:
    def test_slippage_zero_rejected(self) -> None:
        """slippage=0 は gt=0 制約で拒否される。"""
        with pytest.raises(ValidationError):
            RouterV4SwapRequest(
                market_address=MARKET,
                token_in=TOKEN_IN,
                token_out="YT",  # noqa: S106
                amount_in=Decimal("1"),
                slippage=Decimal("0"),
                receiver=RECEIVER,
            )

    def test_slippage_negative_rejected(self) -> None:
        """負の slippage は拒否される。"""
        with pytest.raises(ValidationError):
            RouterV4SwapRequest(
                market_address=MARKET,
                token_in=TOKEN_IN,
                token_out="YT",  # noqa: S106
                amount_in=Decimal("1"),
                slippage=Decimal("-0.01"),
                receiver=RECEIVER,
            )

    def test_slippage_upper_bound_accepted(self) -> None:
        """slippage=0.05（5%）は le 制約の境界で許容される。"""
        req = RouterV4SwapRequest(
            market_address=MARKET,
            token_in=TOKEN_IN,
            token_out="YT",  # noqa: S106
            amount_in=Decimal("1"),
            slippage=Decimal("0.05"),
            receiver=RECEIVER,
        )
        assert req.slippage == Decimal("0.05")

    def test_slippage_above_upper_bound_rejected(self) -> None:
        """slippage=0.051（>5%）は拒否される。"""
        with pytest.raises(ValidationError):
            RouterV4SwapRequest(
                market_address=MARKET,
                token_in=TOKEN_IN,
                token_out="YT",  # noqa: S106
                amount_in=Decimal("1"),
                slippage=Decimal("0.051"),
                receiver=RECEIVER,
            )

    def test_slippage_100pct_rejected(self) -> None:
        """slippage=1.0（=100%）は拒否される（レビュー指摘の具体例）。"""
        with pytest.raises(ValidationError):
            RouterV4SwapRequest(
                market_address=MARKET,
                token_in=TOKEN_IN,
                token_out="YT",  # noqa: S106
                amount_in=Decimal("1"),
                slippage=Decimal("1.0"),
                receiver=RECEIVER,
            )


# --- m1: calldata 欠損 ---


class TestEmptyCalldata:
    @pytest.mark.asyncio
    async def test_buy_yt_empty_calldata_rejected(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """calldata が空文字なら success=False（空 tx 送信防止）。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(return_value=convert_response(data="")),
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error == "empty calldata"

    @pytest.mark.asyncio
    async def test_buy_yt_missing_calldata_rejected(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """tx.data 欠損なら success=False。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(return_value=convert_response(data=None)),
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error == "empty calldata"

    @pytest.mark.asyncio
    async def test_add_liquidity_empty_calldata_rejected(
        self, router_client: PendleRouterV4Client
    ) -> None:
        """add_liquidity の calldata 空でも拒否する。"""
        with patch.object(
            router_client,
            "_call_sdk",
            new=AsyncMock(return_value=convert_response(data="")),
        ):
            result = await router_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error == "empty calldata"


# --- C1: ガード土台（フラグ存在確認） ---


class TestOnchainWriteGuard:
    def test_enable_onchain_write_default_false(self) -> None:
        """PENDLE_ENABLE_ONCHAIN_WRITE 未設定時は enable_onchain_write=False。"""
        config = PendleConfig(sandbox=False)
        assert config.enable_onchain_write is False

    @pytest.mark.asyncio
    async def test_tx_hash_always_none_in_phase1(self, router_client: PendleRouterV4Client) -> None:
        """Phase 1 は calldata 取得まで。成功時も tx_hash は None（送信していない）。"""
        with patch.object(
            router_client, "_call_sdk", new=AsyncMock(return_value=convert_response())
        ):
            result = await router_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is True
        assert result.tx_hash is None
