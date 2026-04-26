# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Aave マーケットデータを fail-open で取得する同期ヘルパー。

ai_judgment_scheduler.run_ai_judgment_job (sync, executor 上で呼ばれる)
から利用される。個別フィールドの取得失敗は None を返し、scheduler 全体は
継続させる (落とさない)。

設計判断:
- Web3AaveClient.get_health_factor は同期 → 直接呼ぶ
- Aave Liquidity API (`UtilizationMonitor` と同じ HTTP エンドポイント) は async →
  asyncio.new_event_loop で囲む。executor スレッド上には running loop が
  存在しないためこのパターンが安全
- Decimal("inf") (借入なし) は health_factor=None として返す。
  「借入なしで HF 無限大」は LLM プロンプトに有用情報を与えないため
"""

import asyncio
import logging
from decimal import Decimal
from typing import Optional, TypedDict

import httpx

from app.aave.client import AaveClientError, get_default_aave_client

logger = logging.getLogger(__name__)


_AAVE_LIQUIDITY_API = "https://aave-api-v2.aave.com"


class AaveMarketData(TypedDict):
    utilization_rate: Optional[Decimal]
    supply_apy: Optional[Decimal]
    borrow_apy: Optional[Decimal]
    health_factor: Optional[Decimal]


def _empty_result() -> AaveMarketData:
    return {
        "utilization_rate": None,
        "supply_apy": None,
        "borrow_apy": None,
        "health_factor": None,
    }


def _fetch_health_factor() -> Optional[Decimal]:
    """Aave V3 Pool から Health Factor を同期取得。

    Web3AaveClient はコンストラクタ時の wallet_private_key (AAVE_WALLET_PRIVATE_KEY)
    から導出した self.account.address をデフォルトで読む。production は単一ウォレット
    運用なので追加の wallet 引数は不要。

    取得失敗 / Decimal("inf") (借入なし) の場合は None を返す。
    """
    try:
        client = get_default_aave_client()
        hf = client.get_health_factor()
        if hf is None or hf == Decimal("inf"):
            return None
        return hf
    except AaveClientError as exc:
        logger.warning("aave_health_factor_fetch_failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("aave_health_factor_fetch_unexpected_error: %s", exc)
        return None


async def _fetch_utilization_async(asset_symbol: str) -> dict[str, Decimal]:
    """Aave Liquidity API を 1 回叩く (httpx クライアントは context で close)。"""
    async with httpx.AsyncClient(base_url=_AAVE_LIQUIDITY_API, timeout=10.0) as client:
        response = await client.get(f"/data/liquidity/v2?poolId={asset_symbol}")
        response.raise_for_status()
        data = response.json()
        return {
            "utilization_rate": Decimal(str(data["utilizationRate"])),
            "supply_apy": Decimal(str(data["supplyAPY"])),
            "borrow_apy": Decimal(str(data["borrowAPY"])),
        }


def _fetch_utilization_sync(asset_symbol: str) -> dict[str, Optional[Decimal]]:
    """async fetch を sync コンテキストから呼ぶ (executor スレッド前提)。"""
    try:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_fetch_utilization_async(asset_symbol))
            return dict(result)
        finally:
            loop.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("aave_utilization_fetch_failed: %s", exc)
        return {"utilization_rate": None, "supply_apy": None, "borrow_apy": None}


def fetch_aave_market_data_safe(asset_symbol: str = "USDC") -> AaveMarketData:
    """fail-open で Aave マーケットデータを取得する。

    個別失敗 → そのフィールドのみ None。全失敗 → 全 None dict。
    例外を呼び出し側に投げないことで scheduler の継続性を担保する。

    Returns:
        AaveMarketData (utilization_rate / supply_apy / borrow_apy / health_factor)
    """
    result = _empty_result()
    result["health_factor"] = _fetch_health_factor()

    util = _fetch_utilization_sync(asset_symbol)
    if util.get("utilization_rate") is not None:
        result["utilization_rate"] = util["utilization_rate"]
    if util.get("supply_apy") is not None:
        result["supply_apy"] = util["supply_apy"]
    if util.get("borrow_apy") is not None:
        result["borrow_apy"] = util["borrow_apy"]

    return result
