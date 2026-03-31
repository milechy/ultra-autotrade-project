# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/exchange/client.py

"""
Exchange クライアント層（Bybit Sandbox / bitFlyer）。

- ExchangeClientError / ExchangeConnectionError / ExchangeOrderError: 例外定義
- BybitSandboxClient: ccxt.bybit を使った実クライアント（sync）
- BitFlyerClient: ccxt.bitflyer を使ったクライアント（sandbox なし、dry_run 強制）
- DummyExchangeClient: テスト・開発用のダミークライアント
"""

import logging
import math
import time
from typing import Any, Dict, List

from .config import ExchangeSettings, get_exchange_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 例外定義
# ---------------------------------------------------------------------------


class ExchangeClientError(Exception):
    """Exchange クライアント全般の基底例外。"""


class ExchangeConnectionError(ExchangeClientError):
    """接続エラー・タイムアウト時の例外。"""


class ExchangeOrderError(ExchangeClientError):
    """注文送信・実行エラー。"""


# ---------------------------------------------------------------------------
# 実クライアント
# ---------------------------------------------------------------------------


class BybitSandboxClient:
    """
    Bybit Sandbox 向け取引クライアント（ccxt 経由）。

    - ccxt.bybit を同期モードで使用する
    - sandbox=True がデフォルトであり、本番環境への誤送信を防止する
    - ccxt は遅延インポートしてテスト時にモックしやすくする
    - BYBIT_API_KEY が空文字列または "dry-run" の場合は DRY-RUN モードで動作する
    """

    # DRY-RUN モード時のダミー価格（BTC/USDT 相当の固定値）
    _DRY_RUN_TICKER_PRICE = 50000.0

    def __init__(self, settings: ExchangeSettings | None = None) -> None:
        """
        BybitSandboxClient を初期化する。

        Args:
            settings: ExchangeSettings インスタンス。省略時は環境変数から取得。

        Raises:
            ExchangeClientError: ccxt パッケージが未インストールの場合（非 DRY-RUN 時）
            ExchangeConnectionError: 取引所への接続確立に失敗した場合（非 DRY-RUN 時）
        """
        self._settings = settings or get_exchange_settings()
        self._dry_run = (not self._settings.api_key) or self._settings.api_key == "dry-run"
        self._dry_run_counter = 0

        if self._dry_run:
            logger.info("BybitSandboxClient initialized in DRY-RUN mode (no API key)")
            return

        try:
            import ccxt
        except ImportError as exc:
            raise ExchangeClientError(
                "ccxt package is required. Install with: pip install ccxt"
            ) from exc

        logger.info(
            "Initializing BybitSandboxClient (sandbox=%s, symbol=%s)",
            self._settings.sandbox,
            self._settings.default_symbol,
        )

        self._exchange = ccxt.bybit(
            {
                "apiKey": self._settings.api_key,
                "secret": self._settings.api_secret,
                "timeout": self._settings.timeout_seconds * 1000,  # ccxt はミリ秒
                "enableRateLimit": True,
                "hostname": self._settings.hostname,
                "options": {
                    "defaultType": "spot",
                },
            }
        )

        if self._settings.sandbox:
            self._exchange.set_sandbox_mode(True)
            logger.info(
                "Bybit sandbox mode enabled (endpoint: https://api-testnet.%s)",
                self._settings.hostname,
            )
        else:
            logger.warning(
                "BybitSandboxClient running in PRODUCTION mode (sandbox=False) — real funds at risk"
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
                "[DRY-RUN] Order: %s %s %s",
                side.upper(),
                symbol,
                amount,
            )
            return {
                "id": f"dry-run-{self._dry_run_counter:04d}",
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
            # DRY-RUN: サイン波ベースのダミーOHLCVデータを生成
            now_ms = int(time.time() * 1000)
            interval_ms = 3600 * 1000  # 1時間 = 3600000ms
            base_price = self._DRY_RUN_TICKER_PRICE
            candles: List[List[Any]] = []
            for i in range(limit):
                ts = now_ms - (limit - i) * interval_ms
                # サイン波で価格変動をシミュレート（振幅1000、周期50）
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


# ---------------------------------------------------------------------------
# bitFlyer クライアント
# ---------------------------------------------------------------------------


class BitFlyerClient:
    """
    bitFlyer 向け取引クライアント（ccxt 経由）。

    - bitFlyer にはサンドボックスモードがないため、常に dry_run=True で動作する
    - BITFLYER_API_KEY が空文字列の場合も dry_run モード
    - 通貨ペア: BTC/JPY（bitFlyer は USDT 建てなし）
    - amount_usd は JPY 換算して処理する（設定レート使用）
    """

    # DRY-RUN モード時のダミー価格（BTC/JPY 相当の固定値）
    _DRY_RUN_TICKER_PRICE = 10_000_000.0

    def __init__(self, settings: ExchangeSettings | None = None) -> None:
        """
        BitFlyerClient を初期化する。

        Args:
            settings: ExchangeSettings インスタンス。省略時は環境変数から取得。

        Raises:
            ExchangeClientError: ccxt パッケージが未インストールの場合（非 DRY-RUN 時）
        """
        self._settings = settings or get_exchange_settings()
        # bitFlyer はサンドボックスなし → APIキーがあっても dry_run=True で安全動作
        self._dry_run = (not self._settings.api_key) or self._settings.api_key == "dry-run"
        self._dry_run_counter = 0

        if self._dry_run:
            logger.info("BitFlyerClient initialized in DRY-RUN mode")
            return

        try:
            import ccxt
        except ImportError as exc:
            raise ExchangeClientError(
                "ccxt package is required. Install with: pip install ccxt"
            ) from exc

        self._exchange = ccxt.bitflyer(
            {
                "apiKey": self._settings.api_key,
                "secret": self._settings.api_secret,
                "timeout": self._settings.timeout_seconds * 1000,
                "enableRateLimit": True,
            }
        )
        logger.info("BitFlyerClient initialized (symbol=%s)", self._settings.default_symbol)

    def create_market_order(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        成行注文を送信する。

        Args:
            symbol: 取引シンボル（例: "BTC/JPY"）
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
                "[DRY-RUN] BitFlyer Order: %s %s %s",
                side.upper(),
                symbol,
                amount,
            )
            return {
                "id": f"bitflyer-dry-run-{self._dry_run_counter:04d}",
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
                "JPY": {
                    "free": 1_000_000.0,
                    "used": 0.0,
                    "total": 1_000_000.0,
                },
                "BTC": {
                    "free": 0.01,
                    "used": 0.0,
                    "total": 0.01,
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
            symbol: 取引シンボル（例: "BTC/JPY"）

        Returns:
            ccxt が返すティッカー情報の辞書（DRY-RUN 時はダミーデータ）

        Raises:
            ExchangeConnectionError: ティッカー取得に失敗した場合（非 DRY-RUN 時）
        """
        if self._dry_run:
            return {
                "symbol": symbol,
                "last": self._DRY_RUN_TICKER_PRICE,
                "bid": self._DRY_RUN_TICKER_PRICE - 1000.0,
                "ask": self._DRY_RUN_TICKER_PRICE + 1000.0,
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


# ---------------------------------------------------------------------------
# bitFlyer クライアント
# ---------------------------------------------------------------------------


class BitFlyerClient:
    """
    bitFlyer 向け取引クライアント（ccxt 経由）。

    - bitFlyer にはサンドボックスモードがないため、常に dry_run=True で動作する
    - BITFLYER_API_KEY が空文字列の場合も dry_run モード
    - 通貨ペア: BTC/JPY（bitFlyer は USDT 建てなし）
    - amount_usd は JPY 換算して処理する（設定レート使用）
    """

    # DRY-RUN モード時のダミー価格（BTC/JPY 相当の固定値）
    _DRY_RUN_TICKER_PRICE = 10_000_000.0

    def __init__(self, settings: ExchangeSettings | None = None) -> None:
        """
        BitFlyerClient を初期化する。

        Args:
            settings: ExchangeSettings インスタンス。省略時は環境変数から取得。

        Raises:
            ExchangeClientError: ccxt パッケージが未インストールの場合（非 DRY-RUN 時）
        """
        self._settings = settings or get_exchange_settings()
        # bitFlyer はサンドボックスなし → APIキーがあっても dry_run=True で安全動作
        self._dry_run = (not self._settings.api_key) or self._settings.api_key == "dry-run"
        self._dry_run_counter = 0

        if self._dry_run:
            logger.info("BitFlyerClient initialized in DRY-RUN mode")
            return

        try:
            import ccxt
        except ImportError as exc:
            raise ExchangeClientError(
                "ccxt package is required. Install with: pip install ccxt"
            ) from exc

        self._exchange = ccxt.bitflyer(
            {
                "apiKey": self._settings.api_key,
                "secret": self._settings.api_secret,
                "timeout": self._settings.timeout_seconds * 1000,
                "enableRateLimit": True,
            }
        )
        logger.info("BitFlyerClient initialized (symbol=%s)", self._settings.default_symbol)

    def create_market_order(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        成行注文を送信する。

        Args:
            symbol: 取引シンボル（例: "BTC/JPY"）
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
                "[DRY-RUN] BitFlyer Order: %s %s %s",
                side.upper(),
                symbol,
                amount,
            )
            return {
                "id": f"bitflyer-dry-run-{self._dry_run_counter:04d}",
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
                "JPY": {
                    "free": 1_000_000.0,
                    "used": 0.0,
                    "total": 1_000_000.0,
                },
                "BTC": {
                    "free": 0.01,
                    "used": 0.0,
                    "total": 0.01,
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
            symbol: 取引シンボル（例: "BTC/JPY"）

        Returns:
            ccxt が返すティッカー情報の辞書（DRY-RUN 時はダミーデータ）

        Raises:
            ExchangeConnectionError: ティッカー取得に失敗した場合（非 DRY-RUN 時）
        """
        if self._dry_run:
            return {
                "symbol": symbol,
                "last": self._DRY_RUN_TICKER_PRICE,
                "bid": self._DRY_RUN_TICKER_PRICE - 1000.0,
                "ask": self._DRY_RUN_TICKER_PRICE + 1000.0,
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


# ---------------------------------------------------------------------------
# ダミークライアント（テスト・開発用）
# ---------------------------------------------------------------------------


class DummyExchangeClient:
    """
    テスト・開発用のダミー Exchange クライアント。

    - 実際の取引所には一切アクセスしない
    - 送信した注文を orders リストに記録する
    - 固定のダミー残高・ティッカーデータを返す
    """

    # ダミーティッカーの価格（BTC/USDT 相当の固定値）
    DUMMY_TICKER_PRICE = 50000.0

    def __init__(self) -> None:
        self.orders: List[Dict[str, Any]] = []
        self._order_counter = 0

    def create_market_order(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        ダミーの成行注文を作成し、orders リストに記録して返す。
        """
        self._order_counter += 1
        order_id = f"dummy-order-{self._order_counter:04d}"

        order = {
            "id": order_id,
            "symbol": symbol,
            "type": "market",
            "side": side,
            "amount": amount,
            "price": self.DUMMY_TICKER_PRICE,
            "status": "closed",
            "filled": amount,
            "cost": amount * self.DUMMY_TICKER_PRICE,
        }
        self.orders.append(order)
        logger.info("DummyExchangeClient: order created %s", order_id)
        return order

    def fetch_balance(self) -> Dict[str, Any]:
        """
        ダミーの残高情報を返す。
        """
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

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        ダミーのティッカー情報を返す。
        """
        return {
            "symbol": symbol,
            "last": self.DUMMY_TICKER_PRICE,
            "bid": self.DUMMY_TICKER_PRICE - 10.0,
            "ask": self.DUMMY_TICKER_PRICE + 10.0,
            "timestamp": None,
        }

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> List[List[Any]]:
        """
        ダミーのOHLCVデータを返す（固定価格の連続データ）。
        """
        now_ms = int(time.time() * 1000)
        interval_ms = 3600 * 1000
        candles: List[List[Any]] = []
        for i in range(limit):
            ts = now_ms - (limit - i) * interval_ms
            close = self.DUMMY_TICKER_PRICE
            candles.append([ts, close - 50.0, close + 100.0, close - 100.0, close, 10.0])
        return candles
