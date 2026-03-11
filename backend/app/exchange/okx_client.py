# backend/app/exchange/okx_client.py
"""
OKX 取引クライアント（ccxt 経由）。

- OKX_API_KEY / OKX_API_SECRET / OKX_PASSPHRASE で認証
- sandbox=True の場合はサンドボックスモードで動作
- API キーが空または "dry-run" の場合は DRY-RUN モードで動作
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Dict, List

from .client import ExchangeClientError, ExchangeConnectionError, ExchangeOrderError
from .config import ExchangeSettings, get_okx_settings

logger = logging.getLogger(__name__)


class OKXClient:
    """
    OKX 向け取引クライアント（ccxt 経由）。

    - ccxt.okx を同期モードで使用する
    - OKX_API_KEY が空文字列または "dry-run" の場合は DRY-RUN モードで動作する
    - sandbox=True の場合は OKX のサンドボックス環境に接続する
    - ccxt は遅延インポートしてテスト時にモックしやすくする
    """

    # DRY-RUN モード時のダミー価格（BTC/USDT 相当の固定値）
    _DRY_RUN_TICKER_PRICE = 50000.0

    def __init__(self, settings: ExchangeSettings | None = None) -> None:
        """
        OKXClient を初期化する。

        Args:
            settings: ExchangeSettings インスタンス。省略時は OKX 専用設定を取得。

        Raises:
            ExchangeClientError: ccxt パッケージが未インストールの場合（非 DRY-RUN 時）
            ExchangeConnectionError: 取引所への接続確立に失敗した場合（非 DRY-RUN 時）
        """
        self._settings = settings or get_okx_settings()
        api_key = self._settings.api_key
        self._dry_run = not api_key or api_key == "dry-run"
        self._dry_run_counter = 0

        if self._dry_run:
            logger.info("OKXClient initialized in DRY-RUN mode (no API key)")
            return

        try:
            import ccxt
        except ImportError as exc:
            raise ExchangeClientError(
                "ccxt package is required. Install with: pip install ccxt"
            ) from exc

        passphrase = self._settings.passphrase

        logger.info(
            "Initializing OKXClient (sandbox=%s, symbol=%s)",
            self._settings.sandbox,
            self._settings.default_symbol,
        )

        self._exchange = ccxt.okx(
            {
                "apiKey": self._settings.api_key,
                "secret": self._settings.api_secret,
                "password": passphrase,
                "timeout": self._settings.timeout_seconds * 1000,  # ccxt はミリ秒
                "enableRateLimit": True,
            }
        )

        if self._settings.sandbox:
            self._exchange.set_sandbox_mode(True)
            logger.info("OKX sandbox mode enabled")
        else:
            logger.warning(
                "OKXClient running in PRODUCTION mode (sandbox=False) — real funds at risk"
            )

    def create_market_order(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        成行注文を送信する。

        Args:
            symbol: 取引シンボル（例: "BTC/USDT"）
            side: 注文方向（"buy" または "sell"）
            amount: 取引数量（基軸通貨単位、例: BTC 0.001）

        Returns:
            ccxt が返す注文情報の辞書（DRY-RUN 時はダミーデータ）

        Raises:
            ExchangeOrderError: 注文送信に失敗した場合（非 DRY-RUN 時）
        """
        if self._dry_run:
            self._dry_run_counter += 1
            logger.info(
                "[DRY-RUN] OKX Order: %s %s %s",
                side.upper(),
                symbol,
                amount,
            )
            return {
                "id": f"okx-dry-run-{self._dry_run_counter:04d}",
                "symbol": symbol,
                "type": "market",
                "side": side,
                "amount": amount,
                "price": self._DRY_RUN_TICKER_PRICE,
                "status": "closed",
                "filled": amount,
                "cost": amount * self._DRY_RUN_TICKER_PRICE,
            }

        try:
            logger.info(
                "Creating market order: symbol=%s, side=%s, amount=%s",
                symbol,
                side,
                amount,
            )
            order = self._exchange.create_market_order(symbol, side, amount)
            logger.info("Market order created: order_id=%s", order.get("id"))
            return dict(order)
        except Exception as exc:
            logger.error("Failed to create market order: %s", exc)
            raise ExchangeOrderError(f"Failed to create market order: {exc}") from exc

    def fetch_balance(self) -> Dict[str, Any]:
        """
        口座残高を取得する。

        Returns:
            ccxt が返す残高情報の辞書（DRY-RUN 時はダミーデータ）

        Raises:
            ExchangeConnectionError: 残高取得に失敗した場合（非 DRY-RUN 時）
        """
        if self._dry_run:
            return {
                "USDT": {
                    "free": 10000.0,
                    "used": 0.0,
                    "total": 10000.0,
                },
                "BTC": {
                    "free": 0.1,
                    "used": 0.0,
                    "total": 0.1,
                },
            }

        try:
            balance = self._exchange.fetch_balance()
            logger.info("Balance fetched successfully")
            return dict(balance)
        except Exception as exc:
            logger.error("Failed to fetch balance: %s", exc)
            raise ExchangeConnectionError(f"Failed to fetch balance: {exc}") from exc

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        指定シンボルのティッカー情報を取得する。

        Args:
            symbol: 取引シンボル（例: "BTC/USDT"）

        Returns:
            ccxt が返すティッカー情報の辞書（DRY-RUN 時はダミーデータ）

        Raises:
            ExchangeConnectionError: ティッカー取得に失敗した場合（非 DRY-RUN 時）
        """
        if self._dry_run:
            return {
                "symbol": symbol,
                "last": self._DRY_RUN_TICKER_PRICE,
                "bid": self._DRY_RUN_TICKER_PRICE - 10.0,
                "ask": self._DRY_RUN_TICKER_PRICE + 10.0,
                "timestamp": None,
            }

        try:
            ticker = self._exchange.fetch_ticker(symbol)
            logger.info(
                "Ticker fetched: symbol=%s, last=%s",
                symbol,
                ticker.get("last"),
            )
            return dict(ticker)
        except Exception as exc:
            logger.error("Failed to fetch ticker for %s: %s", symbol, exc)
            raise ExchangeConnectionError(f"Failed to fetch ticker for {symbol}: {exc}") from exc

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[List[Any]]:
        """
        OHLCVデータを取得する（テクニカル指標計算用）。

        Args:
            symbol: 取引シンボル（例: "BTC/USDT"）
            timeframe: タイムフレーム（例: "1h", "4h", "1d"）
            limit: 取得件数（デフォルト: 100）

        Returns:
            [[timestamp, open, high, low, close, volume], ...] の形式のリスト
            DRY-RUN 時はサイン波ベースのダミーデータを返す

        Raises:
            ExchangeConnectionError: データ取得に失敗した場合（非 DRY-RUN 時）
        """
        if self._dry_run:
            now_ms = int(time.time() * 1000)
            interval_ms = 3600 * 1000  # 1時間 = 3600000ms
            base_price = self._DRY_RUN_TICKER_PRICE
            candles: List[List[Any]] = []
            for i in range(limit):
                ts = now_ms - (limit - i) * interval_ms
                wave = math.sin(i * 2 * math.pi / 50) * 1000.0
                close = base_price + wave
                open_p = close - 50.0
                high = close + 100.0
                low = close - 100.0
                volume = 10.0 + i % 5
                candles.append([ts, open_p, high, low, close, volume])
            return candles

        try:
            ohlcv = self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            logger.info(
                "OHLCV fetched: symbol=%s, timeframe=%s, count=%d",
                symbol,
                timeframe,
                len(ohlcv),
            )
            return [list(candle) for candle in ohlcv]
        except Exception as exc:
            logger.error("Failed to fetch OHLCV for %s: %s", symbol, exc)
            raise ExchangeConnectionError(f"Failed to fetch OHLCV for {symbol}: {exc}") from exc
