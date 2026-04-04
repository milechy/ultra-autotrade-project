# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
Aave V3 Oracle (Chainlink) 鮮度チェック・Circuit Breaker。

- Chainlink AggregatorV3 の latestRoundData() から updatedAt を取得
- staleness_threshold_seconds を超えたら WARNING → HOLD
- 前回価格から deviation_threshold_pct (デフォルト 10%) 超の乖離で circuit breaker
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

_AGGREGATOR_ABI = [
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

_SEQUENCER_ABI = [
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
class OracleCheckResult:
    feed_address: str
    is_stale: bool
    is_circuit_breaker: bool
    updated_at: Optional[datetime]
    price: Optional[Decimal]
    age_seconds: Optional[int]
    deviation_pct: Optional[Decimal]
    should_hold: bool
    reasons: list[str] = field(default_factory=list)


def check_oracle_staleness(
    feed_address: str,
    rpc_url: str,
    staleness_threshold_seconds: int = 3600,
    deviation_threshold_pct: Decimal = Decimal("10"),
    previous_price: Optional[Decimal] = None,
) -> Optional[OracleCheckResult]:
    """
    Chainlink price feed の鮮度と価格乖離を検証する。

    Returns None if web3 is unavailable or RPC call fails.
    """
    try:
        from web3 import Web3  # noqa: PLC0415
    except ImportError:
        logger.warning("[oracle_checker] web3 not installed; skipping oracle check")
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        feed = w3.eth.contract(
            address=Web3.to_checksum_address(feed_address),
            abi=_AGGREGATOR_ABI,
        )
        round_data = feed.functions.latestRoundData().call()
        _round_id, answer, _started_at, updated_at_ts, _answered_in_round = round_data
    except Exception as exc:  # noqa: BLE001
        logger.warning("[oracle_checker] latestRoundData failed for %s: %s", feed_address, exc)
        return None

    now = datetime.now(timezone.utc)
    updated_at = datetime.fromtimestamp(updated_at_ts, tz=timezone.utc)
    age_seconds = int((now - updated_at).total_seconds())

    price = Decimal(answer) / Decimal(10**8)  # Chainlink USD feeds use 8 decimals

    reasons: list[str] = []
    is_stale = age_seconds > staleness_threshold_seconds
    if is_stale:
        reasons.append(
            f"oracle price is stale: age={age_seconds}s > threshold={staleness_threshold_seconds}s"
        )

    deviation_pct: Optional[Decimal] = None
    is_circuit_breaker = False
    if previous_price is not None and previous_price > Decimal("0"):
        deviation_pct = abs(price - previous_price) / previous_price * Decimal("100")
        if deviation_pct > deviation_threshold_pct:
            is_circuit_breaker = True
            reasons.append(
                f"price deviation {deviation_pct:.2f}% exceeds threshold {deviation_threshold_pct}%"
            )

    should_hold = is_stale or is_circuit_breaker
    if should_hold:
        logger.warning(
            "[oracle_checker] HOLD triggered for feed=%s reasons=%s", feed_address, reasons
        )

    return OracleCheckResult(
        feed_address=feed_address,
        is_stale=is_stale,
        is_circuit_breaker=is_circuit_breaker,
        updated_at=updated_at,
        price=price,
        age_seconds=age_seconds,
        deviation_pct=deviation_pct,
        should_hold=should_hold,
        reasons=reasons,
    )


# L2 Sequencer uptime check (Base / Arbitrum)
# Sequencer feed addresses (mainnet):
# Arbitrum: 0xFdB631F5EE196F0ed6FAa767959853A9F217697D
# Base:     0xBCF85224fc0756B9Fa45aA7892530B47e10b6b4E
_GRACE_PERIOD_SECONDS = 3600  # 1 hour after sequencer recovery


def check_sequencer_uptime(
    sequencer_feed_address: str,
    rpc_url: str,
) -> bool:
    """
    L2 sequencer uptime feed を確認する。

    Returns True if sequencer is UP and grace period has passed.
    Returns False (-> HOLD) if sequencer is DOWN or in grace period.
    Returns False if web3 unavailable (fail-closed).
    """
    try:
        from web3 import Web3  # noqa: PLC0415
    except ImportError:
        logger.error("[oracle_checker] web3 not installed; sequencer check fail-closed")
        return False

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        feed = w3.eth.contract(
            address=Web3.to_checksum_address(sequencer_feed_address),
            abi=_SEQUENCER_ABI,
        )
        _round_id, answer, started_at_ts, _updated_at, _answered_in_round = (
            feed.functions.latestRoundData().call()
        )
    except Exception as exc:
        logger.error("[oracle_checker] sequencer feed check failed - fail-closed: %s", exc)
        return False  # fail-closed

    # answer=0 means sequencer is UP
    if answer != 0:
        logger.warning("[oracle_checker] L2 sequencer is DOWN (answer=%s)", answer)
        return False

    # Check grace period
    now = datetime.now(timezone.utc)
    recovered_at = datetime.fromtimestamp(started_at_ts, tz=timezone.utc)
    seconds_since_recovery = int((now - recovered_at).total_seconds())
    if seconds_since_recovery < _GRACE_PERIOD_SECONDS:
        logger.warning(
            "[oracle_checker] L2 sequencer recently recovered; grace period remaining=%ds",
            _GRACE_PERIOD_SECONDS - seconds_since_recovery,
        )
        return False

    return True


def is_oracle_fresh(
    feed_address: Optional[str] = None,
    rpc_url: Optional[str] = None,
) -> bool:
    """Zero-arg convenience wrapper for use in rule engine.

    Reads AAVE_ORACLE_FEED_ADDRESS and WEB3_RPC_URL from environment if not provided.
    Returns True if oracle data is fresh (safe to trade).
    Returns False (fail-closed) if RPC fails or oracle is stale.
    If env vars are not configured, oracle check is skipped (returns True).
    """
    import os  # noqa: PLC0415

    _feed = feed_address or os.getenv("AAVE_ORACLE_FEED_ADDRESS")
    _rpc = rpc_url or os.getenv("WEB3_RPC_URL") or os.getenv("POLYGON_RPC_URL")

    if not _feed or not _rpc:
        logger.warning(
            "[oracle_checker] AAVE_ORACLE_FEED_ADDRESS or RPC URL not configured - "
            "oracle check skipped (treating as fresh)"
        )
        return True  # env not configured → skip check

    try:
        result = check_oracle_staleness(_feed, _rpc)
    except Exception as exc:
        logger.error("[oracle_checker] is_oracle_fresh call failed - fail-closed: %s", exc)
        return False

    if result is None:
        logger.error("[oracle_checker] Oracle check returned None (RPC failure) - fail-closed")
        return False

    return not result.should_hold
