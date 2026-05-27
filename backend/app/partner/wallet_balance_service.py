# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/partner/wallet_balance_service.py
"""Partner wallet balance service.

責務:
- partner の wallet_address から Base mainnet 上の USDC + ETH 残高取得
- Chainlink ETH/USD で ETH 残高を USD 換算
- USDC は 1:1 で USD 換算 (簡略化)
- 60 秒 in-memory cache (wallet_address ごと)
- 失敗時は fallback (RPC エラー時 0 + warning、price エラー時は ETH_USD_FALLBACK_PRICE)

NOTE: Aave supply 分は **含まない**。ウォレットに「入っている」分のみ。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from app.aave.gas_estimator import ETH_USD_FALLBACK_PRICE
from app.partner.wallet_balance_schemas import WalletBalanceResponse

logger = logging.getLogger(__name__)

# --- Base mainnet token / oracle addresses ---
# USDC on Base mainnet (6 decimals)
USDC_CONTRACT_ADDRESS_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_DECIMALS = 6

# Chainlink ETH/USD aggregator on Base mainnet (8 decimals)
ETH_USD_FEED_ADDRESS_BASE = "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70"
CHAINLINK_DECIMALS = 8

# Cache TTL
CACHE_TTL_SECONDS = 60

# ERC20 balanceOf ABI (minimal)
_ERC20_ABI: list[dict[str, Any]] = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

# Chainlink AggregatorV3 latestRoundData ABI (minimal)
_AGGREGATOR_ABI: list[dict[str, Any]] = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"internalType": "uint80", "name": "roundId", "type": "uint80"},
            {"internalType": "int256", "name": "answer", "type": "int256"},
            {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
            {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
            {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


@dataclass
class _CacheEntry:
    response: WalletBalanceResponse
    fetched_at_monotonic: float


# in-memory cache (wallet_address (checksum) → _CacheEntry)
_CACHE: dict[str, _CacheEntry] = {}


def _get_base_rpc_url() -> Optional[str]:
    """Base mainnet RPC URL を環境変数から取得する。

    優先順:
      1. AAVE_RPC_URL_BASE (Aave 用と共有)
      2. BASE_RPC_URL (汎用)
      3. WEB3_RPC_URL (legacy)
    """
    return (
        os.getenv("AAVE_RPC_URL_BASE")
        or os.getenv("BASE_RPC_URL")
        or os.getenv("WEB3_RPC_URL")
    )


def _get_web3() -> Optional[Any]:
    """Web3 client を返す。web3 未インストール / RPC URL 未設定なら None。"""
    rpc_url = _get_base_rpc_url()
    if not rpc_url:
        logger.warning("[wallet_balance] Base RPC URL not configured (AAVE_RPC_URL_BASE / BASE_RPC_URL)")
        return None

    try:
        from web3 import Web3  # noqa: PLC0415
    except ImportError:
        logger.warning("[wallet_balance] web3 package not installed; cannot fetch balance")
        return None

    try:
        return Web3(Web3.HTTPProvider(rpc_url))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[wallet_balance] Web3 init failed: %s", exc)
        return None


def _fetch_eth_balance(w3: Any, wallet_address: str) -> tuple[Decimal, bool]:
    """ETH (native) 残高を返す (ether 単位)。エラー時は (0, True)。"""
    try:
        checksum = w3.to_checksum_address(wallet_address)
        wei_balance = w3.eth.get_balance(checksum)
        eth_balance = Decimal(wei_balance) / Decimal(10**18)
        return eth_balance, False
    except Exception as exc:  # noqa: BLE001
        logger.warning("[wallet_balance] ETH balance fetch failed: %s", exc)
        return Decimal("0"), True


def _fetch_usdc_balance(w3: Any, wallet_address: str) -> tuple[Decimal, bool]:
    """USDC 残高を返す (USDC 単位)。エラー時は (0, True)。"""
    try:
        checksum_wallet = w3.to_checksum_address(wallet_address)
        checksum_token = w3.to_checksum_address(USDC_CONTRACT_ADDRESS_BASE)
        contract = w3.eth.contract(address=checksum_token, abi=_ERC20_ABI)
        raw_balance = contract.functions.balanceOf(checksum_wallet).call()
        usdc_balance = Decimal(raw_balance) / Decimal(10**USDC_DECIMALS)
        return usdc_balance, False
    except Exception as exc:  # noqa: BLE001
        logger.warning("[wallet_balance] USDC balance fetch failed: %s", exc)
        return Decimal("0"), True


def _fetch_eth_usd_price(w3: Any) -> tuple[Decimal, bool]:
    """Chainlink ETH/USD price を返す。エラー時は (ETH_USD_FALLBACK_PRICE, True)。"""
    try:
        checksum_feed = w3.to_checksum_address(ETH_USD_FEED_ADDRESS_BASE)
        feed = w3.eth.contract(address=checksum_feed, abi=_AGGREGATOR_ABI)
        round_data = feed.functions.latestRoundData().call()
        _round_id, answer, _started_at, _updated_at, _answered_in_round = round_data
        if answer <= 0:
            logger.warning("[wallet_balance] Chainlink ETH/USD returned non-positive answer: %s", answer)
            return ETH_USD_FALLBACK_PRICE, True
        price = Decimal(answer) / Decimal(10**CHAINLINK_DECIMALS)
        return price, False
    except Exception as exc:  # noqa: BLE001
        logger.warning("[wallet_balance] ETH/USD price fetch failed: %s; using fallback", exc)
        return ETH_USD_FALLBACK_PRICE, True


def _normalize_wallet_address(wallet_address: str) -> str:
    """checksum 化を試みる。web3 が無い場合は lower-case で代用 (cache key 一貫性)。"""
    try:
        from web3 import Web3  # noqa: PLC0415

        return Web3.to_checksum_address(wallet_address)
    except Exception:  # noqa: BLE001
        return wallet_address.lower()


def _build_response(
    wallet_address: str,
    eth_balance: Decimal,
    eth_usd_price: Decimal,
    usdc_balance: Decimal,
    fallback_used: bool,
    fetched_at: datetime,
    cache_age_seconds: int,
) -> WalletBalanceResponse:
    eth_usd_value = eth_balance * eth_usd_price
    usdc_usd_value = usdc_balance  # 1:1
    total_usd = eth_usd_value + usdc_usd_value
    return WalletBalanceResponse(
        wallet_address=wallet_address,
        chain="base",
        eth_balance=eth_balance,
        eth_usd_value=eth_usd_value,
        eth_usd_price=eth_usd_price,
        usdc_balance=usdc_balance,
        usdc_usd_value=usdc_usd_value,
        total_usd=total_usd,
        fetched_at=fetched_at,
        cache_age_seconds=cache_age_seconds,
        fallback_used=fallback_used,
    )


def _all_fallback_response(wallet_address: str) -> WalletBalanceResponse:
    """RPC が一切利用できないときの安全なフォールバック (balance=0, price=fallback)。"""
    now = datetime.now(timezone.utc)
    return _build_response(
        wallet_address=wallet_address,
        eth_balance=Decimal("0"),
        eth_usd_price=ETH_USD_FALLBACK_PRICE,
        usdc_balance=Decimal("0"),
        fallback_used=True,
        fetched_at=now,
        cache_age_seconds=0,
    )


async def fetch(wallet_address: str, *, web3: Any | None = None) -> WalletBalanceResponse:
    """Partner ウォレット残高を取得する (60 秒 cache)。

    Args:
        wallet_address: 0x プレフィックス付きアドレス。
        web3: テスト時の Web3 注入。本番は None で _get_web3() を使う。

    Returns:
        WalletBalanceResponse。
    """
    key = _normalize_wallet_address(wallet_address)
    now_mono = time.monotonic()

    # Cache hit?
    entry = _CACHE.get(key)
    if entry is not None:
        age = int(now_mono - entry.fetched_at_monotonic)
        if age < CACHE_TTL_SECONDS:
            # 既存 response の cache_age_seconds だけ差し替えて返す
            resp = entry.response
            return resp.model_copy(update={"cache_age_seconds": age})

    # Cache miss: fetch fresh
    w3 = web3 if web3 is not None else _get_web3()
    if w3 is None:
        resp = _all_fallback_response(key)
        _CACHE[key] = _CacheEntry(response=resp, fetched_at_monotonic=now_mono)
        return resp

    eth_balance, eth_err = _fetch_eth_balance(w3, wallet_address)
    usdc_balance, usdc_err = _fetch_usdc_balance(w3, wallet_address)
    eth_usd_price, price_err = _fetch_eth_usd_price(w3)
    fallback_used = eth_err or usdc_err or price_err

    fetched_at = datetime.now(timezone.utc)
    resp = _build_response(
        wallet_address=key,
        eth_balance=eth_balance,
        eth_usd_price=eth_usd_price,
        usdc_balance=usdc_balance,
        fallback_used=fallback_used,
        fetched_at=fetched_at,
        cache_age_seconds=0,
    )
    _CACHE[key] = _CacheEntry(response=resp, fetched_at_monotonic=now_mono)
    return resp


def clear_cache() -> None:
    """Test 用 cache クリア。"""
    _CACHE.clear()
