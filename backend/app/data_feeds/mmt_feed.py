# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""MMT Market Data API フィード。

mmt.gg から暗号通貨マーケットデータ（funding rate、OI、candles）を取得し、
AI 判定の MarketContext に提供する。

データは 30 分間隔のバックグラウンドループでキャッシュに保持される。
AI 判定はキャッシュから読み取るため ~0.01s で完了する。

環境変数:
- MMT_API_KEY: APIキー（空の場合はフィード無効）
- MMT_API_ENABLED: 有効化フラグ（デフォルト: false）
- MMT_UPDATE_INTERVAL: 更新間隔秒（デフォルト: 1800）
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

MMT_BASE_URL = "https://eu-central-1.mmt.gg/api/v1"
DEFAULT_SYMBOLS = ["btc/usd", "eth/usd"]
DEFAULT_EXCHANGE = "binancef"


# ============================================================
# Schemas
# ============================================================


@dataclass
class MMTStats:
    """Funding Rate、板厚等の統計データ。"""

    symbol: str
    exchange: str
    funding_rate: Optional[Decimal] = None
    bid_depth_usd: Optional[Decimal] = None
    ask_depth_usd: Optional[Decimal] = None
    timestamp: Optional[int] = None


@dataclass
class MMTOpenInterest:
    """Open Interest データ。"""

    symbol: str
    exchange: str
    open_interest: Optional[Decimal] = None
    oi_change_pct: Optional[float] = None  # 前回比変化率（%）
    timestamp: Optional[int] = None


@dataclass
class MMTCandle:
    """OHLCV ローソク足（1h 足）。"""

    symbol: str
    exchange: str
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    close: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    timestamp: Optional[int] = None


@dataclass
class MMTData:
    """MMT フィードの統合データ。"""

    stats: list[MMTStats] = field(default_factory=list)
    open_interest: list[MMTOpenInterest] = field(default_factory=list)
    candles: dict[str, list[MMTCandle]] = field(default_factory=dict)
    fetched_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_prompt_section(self) -> str:
        """LLM プロンプト用のテキストセクションを生成。データがなければ空文字列。"""
        if not self.stats and not self.open_interest:
            return ""

        lines = ["## MMT Market Data"]

        for s in self.stats:
            if s.funding_rate is not None:
                if s.funding_rate > 0:
                    sentiment = "ロング過多"
                elif s.funding_rate < 0:
                    sentiment = "ショート過多"
                else:
                    sentiment = "中立"
                lines.append(f"- {s.symbol} Funding Rate: {s.funding_rate:.6f} ({sentiment})")

        for oi in self.open_interest:
            if oi.open_interest is not None:
                change = (
                    f", 変化率: {oi.oi_change_pct:+.2f}%" if oi.oi_change_pct is not None else ""
                )
                lines.append(f"- {oi.symbol} OI: ${oi.open_interest:,.0f}{change}")

        return "\n".join(lines) if len(lines) > 1 else ""


# ============================================================
# モジュールレベルキャッシュ（既存フィードパターン準拠）
# ============================================================
_cached_mmt: Optional[MMTData] = None
_cache_lock = asyncio.Lock()
_previous_oi: dict[str, Decimal] = {}  # OI 変化率計算用


def get_cached_mmt_data() -> Optional[MMTData]:
    """キャッシュされた MMT データを返す。未キャッシュなら None。"""
    return _cached_mmt


# ============================================================
# 個別エンドポイント取得
# ============================================================


async def fetch_mmt_stats(
    client: httpx.AsyncClient,
    api_key: str,
    symbol: str,
    exchange: str,
) -> Optional[MMTStats]:
    """GET /stats — funding rate、板厚を取得。エラー時は None（fail-open）。"""
    try:
        now = int(time.time())
        resp = await client.get(
            f"{MMT_BASE_URL}/stats",
            params={
                "exchange": exchange,
                "symbol": symbol,
                "tf": "1h",
                "from": now - 3600,
                "to": now,
            },
            headers={"X-API-Key": api_key},
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("data", [])
        if not items:
            return MMTStats(symbol=symbol, exchange=exchange)

        latest = items[-1]
        return MMTStats(
            symbol=symbol,
            exchange=exchange,
            funding_rate=(Decimal(str(latest["fr"])) if latest.get("fr") is not None else None),
            bid_depth_usd=(Decimal(str(latest["bd"])) if latest.get("bd") is not None else None),
            ask_depth_usd=(Decimal(str(latest["ad"])) if latest.get("ad") is not None else None),
            timestamp=latest.get("t"),
        )
    except Exception as exc:
        logger.warning("MMT stats fetch failed for %s: %s", symbol, exc)
        return None


async def fetch_mmt_oi(
    client: httpx.AsyncClient,
    api_key: str,
    symbol: str,
    exchange: str,
) -> Optional[MMTOpenInterest]:
    """GET /oi — Open Interest を取得。前回値との変化率も計算する。"""
    try:
        now = int(time.time())
        resp = await client.get(
            f"{MMT_BASE_URL}/oi",
            params={
                "exchange": exchange,
                "symbol": symbol,
                "tf": "1h",
                "from": now - 3600,
                "to": now,
            },
            headers={"X-API-Key": api_key},
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("data", [])
        if not items:
            return MMTOpenInterest(symbol=symbol, exchange=exchange)

        latest = items[-1]
        current_oi = Decimal(str(latest["oi"])) if latest.get("oi") is not None else None

        # OI 変化率計算（前回キャッシュがある場合のみ）
        oi_change: Optional[float] = None
        if current_oi is not None and symbol in _previous_oi and _previous_oi[symbol] > 0:
            oi_change = float((current_oi - _previous_oi[symbol]) / _previous_oi[symbol] * 100)
        if current_oi is not None:
            _previous_oi[symbol] = current_oi

        return MMTOpenInterest(
            symbol=symbol,
            exchange=exchange,
            open_interest=current_oi,
            oi_change_pct=oi_change,
            timestamp=latest.get("t"),
        )
    except Exception as exc:
        logger.warning("MMT OI fetch failed for %s: %s", symbol, exc)
        return None


async def fetch_mmt_candles(
    client: httpx.AsyncClient,
    api_key: str,
    symbol: str,
    exchange: str,
) -> list[MMTCandle]:
    """GET /candles — 直近 24h の 1h 足を取得。エラー時は空リスト（fail-open）。"""
    try:
        now = int(time.time())
        resp = await client.get(
            f"{MMT_BASE_URL}/candles",
            params={
                "exchange": exchange,
                "symbol": symbol,
                "tf": "1h",
                "from": now - 86400,
                "to": now,
            },
            headers={"X-API-Key": api_key},
        )
        resp.raise_for_status()
        data = resp.json()

        candles = []
        for item in data.get("data", []):
            candles.append(
                MMTCandle(
                    symbol=symbol,
                    exchange=exchange,
                    open=(Decimal(str(item["o"])) if item.get("o") is not None else None),
                    high=(Decimal(str(item["h"])) if item.get("h") is not None else None),
                    low=(Decimal(str(item["l"])) if item.get("l") is not None else None),
                    close=(Decimal(str(item["c"])) if item.get("c") is not None else None),
                    volume=(Decimal(str(item["v"])) if item.get("v") is not None else None),
                    timestamp=item.get("t"),
                )
            )
        return candles
    except Exception as exc:
        logger.warning("MMT candles fetch failed for %s: %s", symbol, exc)
        return []


# ============================================================
# 一括取得 + キャッシュ更新
# ============================================================


async def fetch_mmt_data() -> Optional[MMTData]:
    """全 MMT データを一括取得してキャッシュを更新する。

    MMT_API_ENABLED=false または MMT_API_KEY 未設定の場合は None を返す。
    各シンボルの個別エラーは警告ログのみで他シンボルへの影響なし（fail-open）。
    """
    global _cached_mmt

    api_key = os.getenv("MMT_API_KEY", "")
    enabled_str = os.getenv("MMT_API_ENABLED", "false").lower()
    enabled = enabled_str in ("true", "1", "yes")

    if not enabled or not api_key:
        logger.debug("MMT feed disabled or MMT_API_KEY not set — skipping fetch")
        return None

    mmt_data = MMTData(fetched_at=datetime.now(timezone.utc))

    async with httpx.AsyncClient(timeout=20.0) as client:
        for symbol in DEFAULT_SYMBOLS:
            stats = await fetch_mmt_stats(client, api_key, symbol, DEFAULT_EXCHANGE)
            if stats:
                mmt_data.stats.append(stats)

            oi = await fetch_mmt_oi(client, api_key, symbol, DEFAULT_EXCHANGE)
            if oi:
                mmt_data.open_interest.append(oi)

            candles = await fetch_mmt_candles(client, api_key, symbol, DEFAULT_EXCHANGE)
            if candles:
                mmt_data.candles[symbol] = candles

    async with _cache_lock:
        _cached_mmt = mmt_data

    logger.info(
        "MMT data updated: %d stats, %d OI records, %d candle sets",
        len(mmt_data.stats),
        len(mmt_data.open_interest),
        len(mmt_data.candles),
    )
    return mmt_data


# ============================================================
# バックグラウンドループ
# ============================================================


async def start_mmt_background_task(interval_minutes: int = 30) -> None:
    """MMT データを定期取得するバックグラウンドループ。

    API 障害時はエラーログのみ記録し、次サイクルまで旧キャッシュを保持する。
    """
    logger.info("Starting MMT data feed background task (every %dmin)", interval_minutes)
    while True:
        try:
            await fetch_mmt_data()
        except Exception as exc:
            logger.error("MMT background task error: %s", exc, exc_info=True)
        await asyncio.sleep(interval_minutes * 60)
