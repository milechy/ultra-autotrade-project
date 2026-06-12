"""PendleRouterV4Client P1 安全装置テスト。

対象:
- PENDLE_ENABLE_ONCHAIN_WRITE 二段ガード (Q1)
- dry_run 明示 (Q2)
- 単一トレード 10%上限 (Q3)
- SDK timeout/HTTPStatusError fail-open
- approvals 抽出
- get_pendle_router_v4_client ファクトリ関数
"""

from __future__ import annotations

import logging
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.protocols.pendle.client import PendleRouterV4Client, get_pendle_router_v4_client
from app.protocols.pendle.config import PendleConfig
from app.protocols.pendle.schemas import (
    RouterV4AddLiquidityResult,
    RouterV4Approval,
)

MARKET = "0x" + "aa" * 20
TOKEN_IN = "0x" + "bb" * 20
TOKEN_OUT = "0x" + "cc" * 20
RECEIVER = "0x" + "dd" * 20

_ROUTER_ADDRESS = "0x888888888889758F76e7103c6CbF23ABbF58F946"

_MOCK_SWAP_RESPONSE: dict = {
    "data": {
        "tx": {"to": _ROUTER_ADDRESS, "data": "0xdeadbeef"},
        "amountOut": str(int(Decimal("0.95") * Decimal(10**18))),
        "approvals": [{"spender": _ROUTER_ADDRESS, "token": TOKEN_IN}],
    }
}

_MOCK_ADD_LIQ_RESPONSE: dict = {
    "data": {
        "tx": {"to": _ROUTER_ADDRESS, "data": "0xcafebabe"},
        "amountLpOut": str(int(Decimal("0.98") * Decimal(10**18))),
        "approvals": [{"spender": _ROUTER_ADDRESS, "token": TOKEN_IN}],
    }
}


@pytest.fixture
def disabled_client() -> PendleRouterV4Client:
    """enable_onchain_write=False（デフォルト）のクライアント。"""
    config = PendleConfig(sandbox=False)
    assert config.enable_onchain_write is False
    return PendleRouterV4Client(config)


@pytest.fixture
def enabled_client() -> PendleRouterV4Client:
    """enable_onchain_write=True のクライアント（テスト専用）。"""
    config = PendleConfig(sandbox=False)
    config.enable_onchain_write = True
    return PendleRouterV4Client(config)


# ---------------------------------------------------------------------------
# Q1: enable_onchain_write=False のガードテスト
# ---------------------------------------------------------------------------


class TestOnchainWriteGuardDisabled:
    """enable_onchain_write=False のとき全 swap 操作が拒否されること。"""

    @pytest.mark.asyncio
    async def test_buy_yt_disabled(self, disabled_client: PendleRouterV4Client) -> None:
        result = await disabled_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error is not None
        assert "PENDLE_ENABLE_ONCHAIN_WRITE=false" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sell_yt_disabled(self, disabled_client: PendleRouterV4Client) -> None:
        result = await disabled_client.sell_yt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert "PENDLE_ENABLE_ONCHAIN_WRITE=false" in (result.error or "")

    @pytest.mark.asyncio
    async def test_buy_pt_disabled(self, disabled_client: PendleRouterV4Client) -> None:
        result = await disabled_client.buy_pt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert "PENDLE_ENABLE_ONCHAIN_WRITE=false" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sell_pt_disabled(self, disabled_client: PendleRouterV4Client) -> None:
        result = await disabled_client.sell_pt(MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert "PENDLE_ENABLE_ONCHAIN_WRITE=false" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_liquidity_disabled(self, disabled_client: PendleRouterV4Client) -> None:
        result = await disabled_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert isinstance(result, RouterV4AddLiquidityResult)
        assert result.success is False
        assert "PENDLE_ENABLE_ONCHAIN_WRITE=false" in (result.error or "")

    @pytest.mark.asyncio
    async def test_disabled_does_not_call_sdk(self, disabled_client: PendleRouterV4Client) -> None:
        """ガード拒否時は SDK を呼ばないこと。"""
        with patch.object(
            disabled_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ) as mock_sdk:
            await disabled_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        mock_sdk.assert_not_called()


# ---------------------------------------------------------------------------
# Q2: dry_run=True で calldata 取得 + tx 送信なし
# ---------------------------------------------------------------------------


class TestDryRunEnabled:
    """enable_onchain_write=True + dry_run=True で calldata が取得できること。"""

    @pytest.mark.asyncio
    async def test_buy_yt_dry_run_gets_calldata(self, enabled_client: PendleRouterV4Client) -> None:
        with patch.object(
            enabled_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await enabled_client.buy_yt(
                MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER, dry_run=True
            )
        assert result.success is True
        assert result.calldata == "0xdeadbeef"
        # tx_hash は dry_run 中は None（tx 送信しない）
        assert result.tx_hash is None

    @pytest.mark.asyncio
    async def test_sell_yt_dry_run_gets_calldata(
        self, enabled_client: PendleRouterV4Client
    ) -> None:
        with patch.object(
            enabled_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await enabled_client.sell_yt(
                MARKET, TOKEN_OUT, Decimal("1.0"), RECEIVER, dry_run=True
            )
        assert result.success is True
        assert result.calldata == "0xdeadbeef"
        assert result.tx_hash is None

    @pytest.mark.asyncio
    async def test_add_liquidity_dry_run_gets_calldata(
        self, enabled_client: PendleRouterV4Client
    ) -> None:
        with patch.object(
            enabled_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_ADD_LIQ_RESPONSE)
        ):
            result = await enabled_client.add_liquidity(
                MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER, dry_run=True
            )
        assert result.success is True
        assert result.calldata == "0xcafebabe"
        assert result.tx_hash is None


# ---------------------------------------------------------------------------
# Q3: 10%上限チェック
# ---------------------------------------------------------------------------


class TestMaxSingleTradeGuard:
    """portfolio_value_usd × 10% を超えたら拒否されること。"""

    @pytest.mark.asyncio
    async def test_exceeds_10pct_is_rejected(self, enabled_client: PendleRouterV4Client) -> None:
        """amount_in > portfolio × 10% は拒否。"""
        portfolio = Decimal("100")
        amount_in = Decimal("11")  # 11% > 10%
        result = await enabled_client.buy_yt(
            MARKET, TOKEN_IN, amount_in, RECEIVER, portfolio_value_usd=portfolio
        )
        assert result.success is False
        assert "exceeds max single trade" in (result.error or "")

    @pytest.mark.asyncio
    async def test_exactly_10pct_is_allowed(self, enabled_client: PendleRouterV4Client) -> None:
        """amount_in = portfolio × 10% は通過。"""
        portfolio = Decimal("100")
        amount_in = Decimal("10")  # 10% = 上限ちょうど
        with patch.object(
            enabled_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await enabled_client.buy_yt(
                MARKET, TOKEN_IN, amount_in, RECEIVER, portfolio_value_usd=portfolio
            )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_within_10pct_is_allowed(self, enabled_client: PendleRouterV4Client) -> None:
        """amount_in < portfolio × 10% は通過。"""
        portfolio = Decimal("100")
        amount_in = Decimal("5")  # 5% < 10%
        with patch.object(
            enabled_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await enabled_client.buy_yt(
                MARKET, TOKEN_IN, amount_in, RECEIVER, portfolio_value_usd=portfolio
            )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_none_portfolio_skips_check_with_warning(
        self, enabled_client: PendleRouterV4Client, caplog: pytest.LogCaptureFixture
    ) -> None:
        """portfolio_value_usd=None はチェックをスキップし warning ログを出すこと。"""
        with caplog.at_level(logging.WARNING, logger="app.protocols.pendle.client"):
            with patch.object(
                enabled_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
            ):
                result = await enabled_client.buy_yt(
                    MARKET, TOKEN_IN, Decimal("999"), RECEIVER, portfolio_value_usd=None
                )
        assert result.success is True
        assert any("10%上限チェックをスキップ" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_add_liquidity_10pct_rejected(self, enabled_client: PendleRouterV4Client) -> None:
        """add_liquidity でも 10%上限が機能すること。"""
        portfolio = Decimal("100")
        amount_in = Decimal("20")  # 20% > 10%
        result = await enabled_client.add_liquidity(
            MARKET, TOKEN_IN, amount_in, RECEIVER, portfolio_value_usd=portfolio
        )
        assert result.success is False
        assert "exceeds max single trade" in (result.error or "")

    def test_10pct_uses_decimal_not_float(self, enabled_client: PendleRouterV4Client) -> None:
        """max_single_trade_pct が Decimal であること（float 禁止）。"""
        assert isinstance(enabled_client._config.max_single_trade_pct, Decimal)


# ---------------------------------------------------------------------------
# fail-open: SDK タイムアウト / HTTPStatusError
# ---------------------------------------------------------------------------


class TestFailOpen:
    """外部 HTTP 失敗時に success=False を返すこと（例外を伝播しない）。"""

    @pytest.mark.asyncio
    async def test_sdk_timeout_returns_failure(self, enabled_client: PendleRouterV4Client) -> None:
        with patch.object(
            enabled_client,
            "_call_sdk",
            new=AsyncMock(side_effect=Exception("connection timeout")),
        ):
            result = await enabled_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert "connection timeout" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sdk_http_status_error_returns_failure(
        self, enabled_client: PendleRouterV4Client
    ) -> None:
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        with patch.object(
            enabled_client,
            "_call_sdk",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "error",
                    request=None,
                    response=mock_response,  # type: ignore[arg-type]
                )
            ),
        ):
            result = await enabled_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False
        assert result.error is not None
        assert "SDK HTTP 500" in (result.error or "")

    @pytest.mark.asyncio
    async def test_add_liquidity_timeout_returns_failure(
        self, enabled_client: PendleRouterV4Client
    ) -> None:
        with patch.object(
            enabled_client,
            "_call_sdk",
            new=AsyncMock(side_effect=Exception("network error")),
        ):
            result = await enabled_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.success is False


# ---------------------------------------------------------------------------
# approvals 抽出
# ---------------------------------------------------------------------------


class TestApprovalsExtraction:
    """SDK レスポンスの approvals が RouterV4SwapResult に格納されること。"""

    @pytest.mark.asyncio
    async def test_approvals_extracted_from_swap(
        self, enabled_client: PendleRouterV4Client
    ) -> None:
        with patch.object(
            enabled_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await enabled_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.approvals is not None
        assert len(result.approvals) == 1
        approval = result.approvals[0]
        assert isinstance(approval, RouterV4Approval)
        assert approval.spender == "0x888888888889758F76e7103c6CbF23ABbF58F946"
        assert approval.token == TOKEN_IN

    @pytest.mark.asyncio
    async def test_approvals_extracted_from_add_liquidity(
        self, enabled_client: PendleRouterV4Client
    ) -> None:
        with patch.object(
            enabled_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_ADD_LIQ_RESPONSE)
        ):
            result = await enabled_client.add_liquidity(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.approvals is not None
        assert len(result.approvals) == 1

    @pytest.mark.asyncio
    async def test_approvals_empty_when_not_in_response(
        self, enabled_client: PendleRouterV4Client
    ) -> None:
        """SDK レスポンスに approvals がない場合は空リストが返ること。"""
        response_no_approvals: dict = {
            "data": {
                "tx": {"to": _ROUTER_ADDRESS, "data": "0xdeadbeef"},
                "amountOut": str(int(Decimal("0.95") * Decimal(10**18))),
            }
        }
        with patch.object(
            enabled_client, "_call_sdk", new=AsyncMock(return_value=response_no_approvals)
        ):
            result = await enabled_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        assert result.approvals is not None
        assert len(result.approvals) == 0

    @pytest.mark.asyncio
    async def test_approvals_not_sent_as_tx(self, enabled_client: PendleRouterV4Client) -> None:
        """approvals は保持のみ。approve tx 送信が起きないこと（sign/send_raw 呼び出しなし）。"""
        with patch.object(
            enabled_client, "_call_sdk", new=AsyncMock(return_value=_MOCK_SWAP_RESPONSE)
        ):
            result = await enabled_client.buy_yt(MARKET, TOKEN_IN, Decimal("1.0"), RECEIVER)
        # tx_hash がない = on-chain tx 送信がない
        assert result.tx_hash is None


# ---------------------------------------------------------------------------
# ファクトリ関数
# ---------------------------------------------------------------------------


class TestFactory:
    """get_pendle_router_v4_client ファクトリ関数のテスト。"""

    def test_factory_returns_router_v4_client(self) -> None:
        config = PendleConfig(sandbox=False)
        client = get_pendle_router_v4_client(config)
        assert isinstance(client, PendleRouterV4Client)

    def test_factory_uses_correct_router_address(self) -> None:
        config = PendleConfig(sandbox=False)
        client = get_pendle_router_v4_client(config)
        assert client._config.router_address == "0x888888888889758F76e7103c6CbF23ABbF58F946"

    def test_factory_inherits_config_enable_flag(self) -> None:
        """ファクトリから生成したクライアントが config の enable_onchain_write を引き継ぐこと。"""
        config = PendleConfig(sandbox=False)
        config.enable_onchain_write = True
        client = get_pendle_router_v4_client(config)
        assert client._config.enable_onchain_write is True

    def test_factory_default_write_disabled(self) -> None:
        """デフォルト config では enable_onchain_write=False であること。"""
        config = PendleConfig(sandbox=False)
        client = get_pendle_router_v4_client(config)
        assert client._config.enable_onchain_write is False


# ---------------------------------------------------------------------------
# 設定デフォルト値
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    """PendleConfig のデフォルト値テスト。"""

    def test_enable_onchain_write_default_false(self) -> None:
        config = PendleConfig()
        assert config.enable_onchain_write is False

    def test_max_single_trade_pct_default_10pct(self) -> None:
        config = PendleConfig()
        assert config.max_single_trade_pct == Decimal("0.10")

    def test_router_address_default_is_correct(self) -> None:
        """config デフォルトの router_address が正式アドレスであること。"""
        config = PendleConfig()
        assert config.router_address == "0x888888888889758F76e7103c6CbF23ABbF58F946"
