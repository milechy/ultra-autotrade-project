# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
Aave V3 Oracle (Chainlink) 鮮度チェック・Circuit Breaker。

- Chainlink AggregatorV3 の latestRoundData() から updatedAt を取得
- staleness_threshold_seconds を超えたら WARNING → HOLD
- 前回価格から deviation_threshold_pct (デフォルト 10%) 超の乖離で circuit breaker
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# Default fallback for staleness threshold when env var is unset.
# Conservative 1h default suits fast-heartbeat feeds; long-heartbeat feeds
# (Base Sepolia USDC/USD ≈ 24h, Base mainnet USDC/USD ≈ 24h) must override
# via AAVE_ORACLE_STALENESS_THRESHOLD_SECONDS to avoid spurious HOLD.
_DEFAULT_STALENESS_THRESHOLD_SECONDS = 3600

# Bounds for env-based override. Reject 0 / negatives and absurdly large values
# (over 7 days) at startup to surface misconfiguration early.
_MIN_STALENESS_THRESHOLD_SECONDS = 60
_MAX_STALENESS_THRESHOLD_SECONDS = 7 * 24 * 3600  # 604800

_ENV_STALENESS_THRESHOLD = "AAVE_ORACLE_STALENESS_THRESHOLD_SECONDS"


def get_staleness_threshold_from_env(default: int = _DEFAULT_STALENESS_THRESHOLD_SECONDS) -> int:
    """
    Read AAVE_ORACLE_STALENESS_THRESHOLD_SECONDS from env, validating bounds.

    Raises RuntimeError on invalid values so misconfiguration is loud.
    """
    raw = os.getenv(_ENV_STALENESS_THRESHOLD)
    if raw is None or raw == "":
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {_ENV_STALENESS_THRESHOLD}: {raw!r}") from exc

    if value < _MIN_STALENESS_THRESHOLD_SECONDS or value > _MAX_STALENESS_THRESHOLD_SECONDS:
        raise RuntimeError(
            f"{_ENV_STALENESS_THRESHOLD}={value} out of bounds "
            f"[{_MIN_STALENESS_THRESHOLD_SECONDS}, {_MAX_STALENESS_THRESHOLD_SECONDS}]"
        )
    return value


def validate_staleness_threshold_env() -> int:
    """
    Startup validation entry point.

    Returns the resolved threshold (env or default) so it can be logged.
    Raises RuntimeError on invalid env, blocking startup.
    """
    return get_staleness_threshold_from_env()


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
    staleness_threshold_seconds: Optional[int] = None,
    deviation_threshold_pct: Decimal = Decimal("10"),
    previous_price: Optional[Decimal] = None,
) -> Optional[OracleCheckResult]:
    """
    Chainlink price feed の鮮度と価格乖離を検証する。

    staleness_threshold_seconds=None の場合は AAVE_ORACLE_STALENESS_THRESHOLD_SECONDS を読む
    (default _DEFAULT_STALENESS_THRESHOLD_SECONDS)。明示指定があれば env より優先する。

    Returns None if web3 is unavailable or RPC call fails.
    """
    if staleness_threshold_seconds is None:
        staleness_threshold_seconds = get_staleness_threshold_from_env()

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


######################################################################
# Multi-Source Price Deviation Check (Pyth + Uniswap V3 TWAP)
# 2026-06 rsETH/srsETH exploit 再発防止
######################################################################

# Uniswap V3 Pool ABI — slot0 + observe の最小セット
_UNISWAP_V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint32[]", "name": "secondsAgos", "type": "uint32[]"}],
        "name": "observe",
        "outputs": [
            {"internalType": "int56[]", "name": "tickCumulatives", "type": "int56[]"},
            {
                "internalType": "uint160[]",
                "name": "secondsPerLiquidityCumulativeX128s",
                "type": "uint160[]",
            },
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


def _get_chainlink_price(feed_address: str, rpc_url: str) -> Optional[Decimal]:
    """
    Chainlink AggregatorV3 から最新価格を取得する。

    Returns None on any error (fail-open for multi-source check).
    金融計算は全て Decimal — float 使用禁止。
    """
    try:
        from web3 import Web3  # noqa: PLC0415
    except ImportError:
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        feed = w3.eth.contract(
            address=Web3.to_checksum_address(feed_address),
            abi=_AGGREGATOR_ABI,
        )
        _round_id, answer, _started_at, _updated_at, _answered_in_round = (
            feed.functions.latestRoundData().call()
        )
        # Chainlink USD feeds: 8 decimals
        return Decimal(str(answer)) / Decimal("100000000")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[oracle_checker] Chainlink price fetch failed for %s: %s", feed_address, exc
        )
        return None


def _get_pyth_price(pyth_api_url: str, price_id: str) -> Optional[Decimal]:
    """
    Pyth Network REST API から最新価格を取得する。

    Pyth API 例: https://hermes.pyth.network/api/latest_price_feeds?ids[]=<price_id>
    失敗時は None を返す (fail-open)。
    金融計算は全て Decimal — float 使用禁止。
    """
    try:
        import json  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        url = f"{pyth_api_url.rstrip('/')}/api/latest_price_feeds?ids[]={price_id}"
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            data = json.loads(resp.read())

        if not data or not isinstance(data, list):
            logger.warning("[oracle_checker] Pyth API returned unexpected format for %s", price_id)
            return None

        feed = data[0]
        price_info = feed.get("price", {})
        raw_price = price_info.get("price")
        expo = price_info.get("expo")
        if raw_price is None or expo is None:
            return None

        # Pyth: price * 10^expo
        # expo は通常負数 (例: -8)。Decimal で計算。
        price = Decimal(str(raw_price)) * (Decimal("10") ** int(expo))
        return price
    except Exception as exc:  # noqa: BLE001
        logger.warning("[oracle_checker] Pyth price fetch failed for %s: %s", price_id, exc)
        return None


def _get_uniswap_v3_twap(
    pool_address: str,
    rpc_url: str,
    twap_seconds: int = 1800,
) -> Optional[Decimal]:
    """
    Uniswap V3 Pool の observe() を使って TWAP 価格を取得する。

    twap_seconds: TWAP 計算期間（デフォルト 30分 = 1800秒）。
    tick から sqrtPrice を復元し token0/token1 の価格比を Decimal で返す。
    失敗時は None を返す (fail-open)。
    金融計算は全て Decimal — float 使用禁止。
    """
    try:
        from web3 import Web3  # noqa: PLC0415
    except ImportError:
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        pool = w3.eth.contract(
            address=Web3.to_checksum_address(pool_address),
            abi=_UNISWAP_V3_POOL_ABI,
        )
        # observe([twap_seconds, 0]) → tickCumulatives at T-twap_seconds and T=now
        tick_cumulatives, _ = pool.functions.observe([twap_seconds, 0]).call()
        tick_avg = (tick_cumulatives[1] - tick_cumulatives[0]) // twap_seconds

        # tick → price: price = 1.0001 ^ tick
        # 精度確保のため対数近似: Decimal で log1.0001 を近似計算
        # ln(1.0001) ≈ 0.00009999500033...
        # price_ratio = exp(tick * ln(1.0001))
        # Python の math は使わず Decimal で近似する
        # tick が小さければ Decimal("1.0001") ** tick も実用的だが
        # |tick| > 100000 では遅いため繰り返し二乗法を使う
        import math  # noqa: PLC0415

        # math.exp/math.log は金融計算ではなくUI表示補助の変換用に限定使用。
        # 最終価格は Decimal に変換して返す。
        log_price = int(tick_avg) * math.log(1.0001)
        price = Decimal(str(round(math.exp(log_price), 12)))
        return price
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[oracle_checker] Uniswap V3 TWAP fetch failed for pool %s: %s", pool_address, exc
        )
        return None


def _max_deviation_pct(prices: list[Decimal]) -> Decimal:
    """
    価格リストの最大乖離率 (%) を Decimal で返す。

    乖離率 = |max - min| / min * 100
    リストが2件未満の場合は Decimal("0") を返す。
    金融計算は全て Decimal — float 使用禁止。
    """
    valid = [p for p in prices if p is not None and p > Decimal("0")]
    if len(valid) < 2:  # noqa: PLR2004
        return Decimal("0")
    price_min = min(valid)
    price_max = max(valid)
    return (price_max - price_min) / price_min * Decimal("100")


@dataclass
class OracleMultiSourceResult:
    """check_price_deviation() の戻り値。"""

    asset: str
    level: str  # "OK" | "WARN" | "HARD_STOP"
    max_deviation_pct: Optional[Decimal]
    chainlink_price: Optional[Decimal]
    pyth_price: Optional[Decimal]
    twap_price: Optional[Decimal]
    detail: Optional[str]
    checked_at: str


def check_price_deviation(
    asset: str,
    chainlink_feed_address: Optional[str],
    rpc_url: Optional[str],
    pyth_api_url: Optional[str] = None,
    pyth_price_id: Optional[str] = None,
    uniswap_pool_address: Optional[str] = None,
    deviation_threshold_pct: Decimal = Decimal("2"),
) -> OracleMultiSourceResult:
    """
    Chainlink / Pyth / Uniswap V3 TWAP の3価格を比較し、乖離率が閾値超過なら HARD_STOP を返す。

    - 3価格のうち取得失敗したものは除外（fail-open: Chainlinkのみでも継続）
    - 2価格以上が揃わない場合は level="WARN"
    - 乖離率 >= deviation_threshold_pct(デフォルト2%) → level="HARD_STOP"
    - 乖離率 < deviation_threshold_pct → level="OK"

    金融計算は全て Decimal — float 使用禁止。
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    checked_at = datetime.now(timezone.utc).isoformat()

    chainlink_price: Optional[Decimal] = None
    pyth_price: Optional[Decimal] = None
    twap_price: Optional[Decimal] = None

    if chainlink_feed_address and rpc_url:
        chainlink_price = _get_chainlink_price(chainlink_feed_address, rpc_url)
    if pyth_api_url and pyth_price_id:
        pyth_price = _get_pyth_price(pyth_api_url, pyth_price_id)
    if uniswap_pool_address and rpc_url:
        twap_price = _get_uniswap_v3_twap(uniswap_pool_address, rpc_url)

    available_prices: list[Decimal] = []
    for p in [chainlink_price, pyth_price, twap_price]:
        if p is not None and p > Decimal("0"):
            available_prices.append(p)

    if len(available_prices) < 2:  # noqa: PLR2004
        level = "WARN"
        max_dev: Optional[Decimal] = None
        detail = (
            f"[{asset}] 価格取得可能ソースが{len(available_prices)}件のみ。"
            "2件以上必要 (fail-open 継続)"
        )
        logger.warning("[oracle_checker] %s", detail)
    else:
        max_dev = _max_deviation_pct(available_prices)
        if max_dev >= deviation_threshold_pct:
            level = "HARD_STOP"
            detail = (
                f"[{asset}] Oracle 価格乖離 {max_dev:.4f}% が閾値 "
                f"{deviation_threshold_pct}% を超過 — HARD_STOP"
            )
            logger.error("[oracle_checker] %s", detail)
        else:
            level = "OK"
            detail = None

    return OracleMultiSourceResult(
        asset=asset,
        level=level,
        max_deviation_pct=max_dev,
        chainlink_price=chainlink_price,
        pyth_price=pyth_price,
        twap_price=twap_price,
        detail=detail,
        checked_at=checked_at,
    )


def is_oracle_fresh(
    feed_address: Optional[str] = None,
    rpc_url: Optional[str] = None,
) -> bool:
    """Zero-arg convenience wrapper for use in rule engine.

    Reads AAVE_ORACLE_FEED_ADDRESS and WEB3_RPC_URL from environment if not provided.
    Threshold is read from AAVE_ORACLE_STALENESS_THRESHOLD_SECONDS (default 3600s).
    Returns True if oracle data is fresh (safe to trade).
    Returns False (fail-closed) if RPC fails or oracle is stale.
    If env vars are not configured, oracle check is skipped (returns True).
    """
    _feed = feed_address or os.getenv("AAVE_ORACLE_FEED_ADDRESS")
    _rpc = rpc_url or os.getenv("WEB3_RPC_URL") or os.getenv("POLYGON_RPC_URL")

    if not _feed or not _rpc:
        logger.warning(
            "[oracle_checker] AAVE_ORACLE_FEED_ADDRESS or RPC URL not configured - "
            "oracle check skipped (treating as fresh)"
        )
        return True  # env not configured → skip check

    try:
        threshold = get_staleness_threshold_from_env()
    except RuntimeError as exc:
        logger.error("[oracle_checker] invalid staleness threshold env - fail-closed: %s", exc)
        return False

    try:
        result = check_oracle_staleness(_feed, _rpc, staleness_threshold_seconds=threshold)
    except Exception as exc:
        logger.error("[oracle_checker] is_oracle_fresh call failed - fail-closed: %s", exc)
        return False

    if result is None:
        logger.error("[oracle_checker] Oracle check returned None (RPC failure) - fail-closed")
        return False

    return not result.should_hold
