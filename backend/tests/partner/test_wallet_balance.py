# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/partner/test_wallet_balance.py
"""Partner wallet balance service / router の unit test。

Web3 / Chainlink を mock し、cache hit / fallback / 404 を検証する。
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-wallet-balance")

from app.aave.gas_estimator import ETH_USD_FALLBACK_PRICE  # noqa: E402
from app.partner import wallet_balance_service  # noqa: E402

# --- Test constants ---
_TEST_WALLET = "0x1234567890abcdef1234567890abcdef12345678"
_TEST_WALLET_CHECKSUM = "0x1234567890AbcdEF1234567890aBcdef12345678"


def _make_mock_w3(
    *,
    eth_wei: int = 2 * 10**18,
    usdc_raw: int = 100 * 10**6,
    eth_usd_answer: int = 3000 * 10**8,
    eth_raises: bool = False,
    usdc_raises: bool = False,
    price_raises: bool = False,
) -> MagicMock:
    """Web3 mock を生成する。"""
    w3 = MagicMock()

    # to_checksum_address: 入力をそのまま返す (テストでは checksum 化不要)
    w3.to_checksum_address = lambda addr: _TEST_WALLET_CHECKSUM

    # eth.get_balance
    if eth_raises:
        w3.eth.get_balance.side_effect = Exception("RPC eth balance error")
    else:
        w3.eth.get_balance.return_value = eth_wei

    # contract().functions.balanceOf().call() / latestRoundData().call()
    def _contract_factory(address: str, abi: list) -> MagicMock:
        contract = MagicMock()
        # USDC balanceOf
        balance_call = MagicMock()
        if usdc_raises:
            balance_call.call.side_effect = Exception("RPC usdc balance error")
        else:
            balance_call.call.return_value = usdc_raw
        contract.functions.balanceOf = MagicMock(return_value=balance_call)

        # Chainlink latestRoundData
        round_call = MagicMock()
        if price_raises:
            round_call.call.side_effect = Exception("RPC price error")
        else:
            round_call.call.return_value = (0, eth_usd_answer, 0, 0, 0)
        contract.functions.latestRoundData = MagicMock(return_value=round_call)

        return contract

    w3.eth.contract.side_effect = _contract_factory
    return w3


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    wallet_balance_service.clear_cache()
    yield
    wallet_balance_service.clear_cache()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestWalletBalanceServiceHappyPath:
    def test_returns_eth_and_usdc_values(self) -> None:
        """ETH + USDC を Chainlink price で USD 換算して返す"""
        w3 = _make_mock_w3(
            eth_wei=2 * 10**18,
            usdc_raw=100 * 10**6,
            eth_usd_answer=3000 * 10**8,
        )
        resp = _run(wallet_balance_service.fetch(_TEST_WALLET, web3=w3))

        assert resp.eth_balance == Decimal("2")
        assert resp.eth_usd_price == Decimal("3000")
        assert resp.eth_usd_value == Decimal("6000")
        assert resp.usdc_balance == Decimal("100")
        assert resp.usdc_usd_value == Decimal("100")
        assert resp.total_usd == Decimal("6100")
        assert resp.fallback_used is False
        assert resp.chain == "base"
        assert resp.cache_age_seconds == 0


class TestWalletBalanceCache:
    def test_cache_hit_returns_same_response(self) -> None:
        """2 回目の fetch は cache hit して RPC を呼ばないこと"""
        w3 = _make_mock_w3(eth_wei=1 * 10**18, usdc_raw=50 * 10**6)
        first = _run(wallet_balance_service.fetch(_TEST_WALLET, web3=w3))
        # 2 回目は別の web3 を渡しても cache が優先される
        w3_other = _make_mock_w3(eth_wei=999 * 10**18, usdc_raw=999 * 10**6)
        second = _run(wallet_balance_service.fetch(_TEST_WALLET, web3=w3_other))
        # 値が初回と一致 (= cache から返った)
        assert second.eth_balance == first.eth_balance
        assert second.usdc_balance == first.usdc_balance
        # cache_age_seconds は更新後の経過秒
        assert second.cache_age_seconds >= 0


class TestWalletBalanceFallback:
    def test_eth_rpc_failure_returns_zero_with_fallback_flag(self) -> None:
        """ETH RPC 失敗時は ETH 残高 0、fallback_used=true"""
        w3 = _make_mock_w3(
            eth_raises=True,
            usdc_raw=50 * 10**6,
            eth_usd_answer=2000 * 10**8,
        )
        resp = _run(wallet_balance_service.fetch(_TEST_WALLET, web3=w3))
        assert resp.eth_balance == Decimal("0")
        assert resp.usdc_balance == Decimal("50")
        assert resp.fallback_used is True

    def test_price_rpc_failure_uses_fallback_price(self) -> None:
        """Chainlink 失敗時は ETH_USD_FALLBACK_PRICE を使い fallback_used=true"""
        w3 = _make_mock_w3(
            eth_wei=1 * 10**18,
            usdc_raw=0,
            price_raises=True,
        )
        resp = _run(wallet_balance_service.fetch(_TEST_WALLET, web3=w3))
        assert resp.eth_usd_price == ETH_USD_FALLBACK_PRICE
        assert resp.eth_usd_value == ETH_USD_FALLBACK_PRICE  # 1 ETH * fallback
        assert resp.fallback_used is True

    def test_no_web3_returns_full_fallback(self) -> None:
        """Web3 取得不可なら全部 0 + fallback price"""
        # web3=None で _get_web3() に進むが RPC URL も未設定なので None になる
        # 直接 web3=None のままだと _get_web3() が呼ばれるので、env を未設定にして検証
        old_envs = {
            k: os.environ.pop(k, None)
            for k in ("AAVE_RPC_URL_BASE", "BASE_RPC_URL", "WEB3_RPC_URL")
        }
        try:
            resp = _run(wallet_balance_service.fetch(_TEST_WALLET))
            assert resp.eth_balance == Decimal("0")
            assert resp.usdc_balance == Decimal("0")
            assert resp.eth_usd_price == ETH_USD_FALLBACK_PRICE
            assert resp.fallback_used is True
        finally:
            for k, v in old_envs.items():
                if v is not None:
                    os.environ[k] = v


class TestWalletBalanceRouter:
    """Router レイヤの 404 (wallet_address 未設定) 動作。"""

    def test_router_returns_404_when_wallet_address_missing(self) -> None:
        from fastapi import HTTPException

        from app.partner.wallet_balance_router import get_wallet_balance

        # current_user.wallet_address = None
        mock_user = MagicMock()
        mock_user.wallet_address = None

        with pytest.raises(HTTPException) as excinfo:
            _run(get_wallet_balance(current_user=mock_user))
        assert excinfo.value.status_code == 404
