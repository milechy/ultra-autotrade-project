# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/ai/prefilter.py
"""
AIプレフィルタリング: テクニカル指標によるLLM呼び出し前の事前判定。

責務:
- exchange/client.py 経由でBTC/USDTの価格データ（OHLCV）を取得する
- RSI(14) と MA クロス（短期7 vs 長期25）を計算する
- シグナルをまとめた PrefilterResult を返す
- 呼び出し元（service.py）はシグナルを参考にLLM呼び出しの要否を判断できる
"""

import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Protocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

RSI_PERIOD = 14
MA_SHORT_PERIOD = 7
MA_LONG_PERIOD = 25
RSI_OVERSOLD_THRESHOLD = 30.0
RSI_OVERBOUGHT_THRESHOLD = 70.0


# ---------------------------------------------------------------------------
# Protocol（テスト時にモックしやすくする）
# ---------------------------------------------------------------------------


class OHLCVClient(Protocol):
    """OHLCVデータを提供できるクライアントのプロトコル定義。"""

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[List[Any]]:
        """[[timestamp, open, high, low, close, volume], ...] 形式で返す。"""
        ...


# ---------------------------------------------------------------------------
# 結果データクラス
# ---------------------------------------------------------------------------


@dataclass
class PrefilterResult:
    """
    テクニカル指標の計算結果。

    Attributes:
        symbol: 対象シンボル（例: "BTC/USDT"）
        rsi: RSI値（14期間）。None = データ不足で計算不可
        ma_short: 短期移動平均（7期間）。None = データ不足で計算不可
        ma_long: 長期移動平均（25期間）。None = データ不足で計算不可
        signal: テクニカルシグナル（"BUY_LEAN" / "SELL_LEAN" / "NEUTRAL" / "INSUFFICIENT_DATA"）
        rsi_signal: RSI単体のシグナル（"OVERSOLD" / "OVERBOUGHT" / "NEUTRAL"）
        ma_signal: MAクロスのシグナル（"GOLDEN_CROSS" / "DEAD_CROSS" / "NEUTRAL"）
    """

    symbol: str
    rsi: Optional[float]
    ma_short: Optional[float]
    ma_long: Optional[float]
    signal: str
    rsi_signal: str
    ma_signal: str


# ---------------------------------------------------------------------------
# テクニカル指標計算
# ---------------------------------------------------------------------------


def calculate_rsi(closes: List[float], period: int = RSI_PERIOD) -> Optional[float]:
    """
    RSI（相対力指数）を計算する。

    Args:
        closes: 終値リスト（古い順）
        period: 計算期間（デフォルト14）

    Returns:
        RSI値（0〜100）。データ不足の場合は None
    """
    if len(closes) < period + 1:
        return None

    # 直近の period+1 本分を使用
    prices = closes[-(period + 1) :]
    gains: List[float] = []
    losses: List[float] = []

    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0.0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_ma(closes: List[float], period: int) -> Optional[float]:
    """
    単純移動平均（SMA）を計算する。

    Args:
        closes: 終値リスト（古い順）
        period: 計算期間

    Returns:
        移動平均値。データ不足の場合は None
    """
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


# ---------------------------------------------------------------------------
# シグナル判定
# ---------------------------------------------------------------------------


def _rsi_signal(rsi: Optional[float]) -> str:
    if rsi is None:
        return "NEUTRAL"
    if rsi < RSI_OVERSOLD_THRESHOLD:
        return "OVERSOLD"
    if rsi > RSI_OVERBOUGHT_THRESHOLD:
        return "OVERBOUGHT"
    return "NEUTRAL"


def _ma_signal(ma_short: Optional[float], ma_long: Optional[float]) -> str:
    if ma_short is None or ma_long is None:
        return "NEUTRAL"
    if ma_short > ma_long:
        return "GOLDEN_CROSS"
    if ma_short < ma_long:
        return "DEAD_CROSS"
    return "NEUTRAL"


def _combine_signal(rsi_sig: str, ma_sig: str) -> str:
    """
    RSIとMAクロスのシグナルを組み合わせて総合シグナルを返す。

    - RSI oversold かつ Golden Cross → BUY_LEAN
    - RSI overbought かつ Dead Cross → SELL_LEAN
    - 片方のみ → 弱いシグナルとして BUY_LEAN / SELL_LEAN
    - 相反するシグナル → NEUTRAL
    """
    buy_signals = (rsi_sig == "OVERSOLD", ma_sig == "GOLDEN_CROSS")
    sell_signals = (rsi_sig == "OVERBOUGHT", ma_sig == "DEAD_CROSS")

    buy_count = sum(buy_signals)
    sell_count = sum(sell_signals)

    if buy_count > sell_count:
        return "BUY_LEAN"
    if sell_count > buy_count:
        return "SELL_LEAN"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# メインエントリーポイント
# ---------------------------------------------------------------------------


def run_prefilter(
    client: OHLCVClient,
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
) -> PrefilterResult:
    """
    テクニカル指標を計算してPrefilterResultを返す。

    Args:
        client: OHLCVデータを取得できるExchangeクライアント
        symbol: 対象シンボル（デフォルト: "BTC/USDT"）
        timeframe: タイムフレーム（デフォルト: "1h"）

    Returns:
        PrefilterResult（テクニカル指標とシグナルを含む）
    """
    # MA_LONG + RSI_PERIOD 分のデータが必要
    limit = MA_LONG_PERIOD + RSI_PERIOD + 10

    try:
        ohlcv = client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    except Exception as exc:
        logger.warning("Failed to fetch OHLCV for prefilter: %s", exc)
        return PrefilterResult(
            symbol=symbol,
            rsi=None,
            ma_short=None,
            ma_long=None,
            signal="INSUFFICIENT_DATA",
            rsi_signal="NEUTRAL",
            ma_signal="NEUTRAL",
        )

    if not ohlcv:
        logger.warning("Empty OHLCV data for symbol=%s", symbol)
        return PrefilterResult(
            symbol=symbol,
            rsi=None,
            ma_short=None,
            ma_long=None,
            signal="INSUFFICIENT_DATA",
            rsi_signal="NEUTRAL",
            ma_signal="NEUTRAL",
        )

    # OHLCV形式: [timestamp, open, high, low, close, volume]
    closes = [float(candle[4]) for candle in ohlcv]

    rsi = calculate_rsi(closes, period=RSI_PERIOD)
    ma_short = calculate_ma(closes, period=MA_SHORT_PERIOD)
    ma_long = calculate_ma(closes, period=MA_LONG_PERIOD)

    rsi_sig = _rsi_signal(rsi)
    ma_sig = _ma_signal(ma_short, ma_long)
    signal = _combine_signal(rsi_sig, ma_sig)

    logger.info(
        "Prefilter result: symbol=%s rsi=%.2f ma_short=%.2f ma_long=%.2f signal=%s",
        symbol,
        rsi if rsi is not None else float("nan"),
        ma_short if ma_short is not None else float("nan"),
        ma_long if ma_long is not None else float("nan"),
        signal,
    )

    return PrefilterResult(
        symbol=symbol,
        rsi=rsi,
        ma_short=ma_short,
        ma_long=ma_long,
        signal=signal,
        rsi_signal=rsi_sig,
        ma_signal=ma_sig,
    )
