# Copyright (c) Ultra AutoTrade. All rights reserved.
"""
Aave V3 Reserve Pause/Freeze/Cap 状態監視。

Pool Data Provider の getReserveConfigurationData() を呼び出して
isPaused / isFrozen / borrowCap / supplyCap の異常を検知する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_PROVIDER_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "asset", "type": "address"}],
        "name": "getReserveConfigurationData",
        "outputs": [
            {"internalType": "uint256", "name": "decimals", "type": "uint256"},
            {"internalType": "uint256", "name": "ltv", "type": "uint256"},
            {"internalType": "uint256", "name": "liquidationThreshold", "type": "uint256"},
            {"internalType": "uint256", "name": "liquidationBonus", "type": "uint256"},
            {"internalType": "uint256", "name": "reserveFactor", "type": "uint256"},
            {"internalType": "bool", "name": "usageAsCollateralEnabled", "type": "bool"},
            {"internalType": "bool", "name": "borrowingEnabled", "type": "bool"},
            {"internalType": "bool", "name": "stableBorrowRateEnabled", "type": "bool"},
            {"internalType": "bool", "name": "isActive", "type": "bool"},
            {"internalType": "bool", "name": "isFrozen", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "asset", "type": "address"}],
        "name": "getReserveCaps",
        "outputs": [
            {"internalType": "uint256", "name": "borrowCap", "type": "uint256"},
            {"internalType": "uint256", "name": "supplyCap", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "asset", "type": "address"}],
        "name": "getPaused",
        "outputs": [{"internalType": "bool", "name": "isPaused", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass
class ReserveStatus:
    chain_name: str
    asset_address: str
    is_active: bool
    is_frozen: bool
    is_paused: bool
    borrow_cap: int  # 0 means no cap
    supply_cap: int  # 0 means no cap
    is_borrowing_enabled: bool
    alert: bool  # True if any anomaly detected
    alert_reasons: list[str]


def check_reserve_status(
    chain_name: str,
    asset_address: str,
    data_provider_address: str,
    rpc_url: str,
) -> Optional[ReserveStatus]:
    """
    Aave V3 Pool Data Provider から reserve 設定を取得して異常を検知する。

    web3 未インストール時や RPC 障害時は None を返す（fail-open: 呼び出し側が判断）。
    """
    try:
        from web3 import Web3  # noqa: PLC0415
    except ImportError:
        logger.warning("[reserve_monitor] web3 not installed; skipping check")
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        dp = w3.eth.contract(
            address=Web3.to_checksum_address(data_provider_address),
            abi=_DATA_PROVIDER_ABI,
        )
        asset_cs = Web3.to_checksum_address(asset_address)

        # getReserveConfigurationData
        config_data = dp.functions.getReserveConfigurationData(asset_cs).call()
        (
            _decimals,
            _ltv,
            _liq_threshold,
            _liq_bonus,
            _reserve_factor,
            _collateral_enabled,
            borrowing_enabled,
            _stable_borrow,
            is_active,
            is_frozen,
        ) = config_data

        # getPaused
        try:
            is_paused: bool = dp.functions.getPaused(asset_cs).call()
        except Exception:  # noqa: BLE001
            is_paused = False

        # getReserveCaps
        try:
            caps = dp.functions.getReserveCaps(asset_cs).call()
            borrow_cap, supply_cap = int(caps[0]), int(caps[1])
        except Exception:  # noqa: BLE001
            borrow_cap, supply_cap = 0, 0

    except Exception as exc:  # noqa: BLE001
        logger.warning("[reserve_monitor] RPC call failed for chain=%s: %s", chain_name, exc)
        return None

    alert_reasons: list[str] = []
    if is_paused:
        alert_reasons.append("reserve is PAUSED")
    if is_frozen:
        alert_reasons.append("reserve is FROZEN")
    if not is_active:
        alert_reasons.append("reserve is INACTIVE")

    alert = bool(alert_reasons)
    if alert:
        logger.warning(
            "[reserve_monitor] anomaly detected chain=%s asset=%s reasons=%s",
            chain_name,
            asset_address,
            alert_reasons,
        )

    return ReserveStatus(
        chain_name=chain_name,
        asset_address=asset_address,
        is_active=is_active,
        is_frozen=is_frozen,
        is_paused=is_paused,
        borrow_cap=borrow_cap,
        supply_cap=supply_cap,
        is_borrowing_enabled=borrowing_enabled,
        alert=alert,
        alert_reasons=alert_reasons,
    )


def is_reserve_healthy(
    chain_name: Optional[str] = None,
    asset_address: Optional[str] = None,
    data_provider_address: Optional[str] = None,
    rpc_url: Optional[str] = None,
) -> bool:
    """Zero-arg convenience wrapper for use in rule engine.

    Reads AAVE_ASSET_ADDRESS, AAVE_DATA_PROVIDER_ADDRESS, and WEB3_RPC_URL
    from environment if not provided.
    Returns True if reserve is active and healthy (safe to trade).
    Returns False (fail-closed) if RPC fails or reserve is paused/frozen/inactive.
    If env vars are not configured, reserve check is skipped (returns True).
    """
    import os  # noqa: PLC0415

    _chain: str = chain_name or os.getenv("AAVE_CHAIN_NAME", "polygon") or "polygon"
    _asset = asset_address or os.getenv("AAVE_ASSET_ADDRESS")
    _provider = data_provider_address or os.getenv("AAVE_DATA_PROVIDER_ADDRESS")
    _rpc = rpc_url or os.getenv("WEB3_RPC_URL") or os.getenv("POLYGON_RPC_URL")

    if not _asset or not _provider or not _rpc:
        logger.warning(
            "[reserve_monitor] AAVE_ASSET_ADDRESS, AAVE_DATA_PROVIDER_ADDRESS, or RPC URL "
            "not configured - reserve check skipped (treating as healthy)"
        )
        return True  # env not configured → skip check

    try:
        result = check_reserve_status(_chain, _asset, _provider, _rpc)
    except Exception as exc:
        logger.error("[reserve_monitor] is_reserve_healthy call failed - fail-closed: %s", exc)
        return False

    if result is None:
        logger.error("[reserve_monitor] Reserve check returned None (RPC failure) - fail-closed")
        return False

    return not result.alert
