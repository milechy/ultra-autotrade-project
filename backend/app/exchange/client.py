# backend/app/exchange/client.py

"""
Exchange（Bybit Sandbox）クライアント層。

- ExchangeClientError / ExchangeConnectionError / ExchangeOrderError: 例外定義
- BybitSandboxClient: ccxt.bybit を使った実クライアント（sync）
- DummyExchangeClient: テスト・開発用のダミークライアント
"""

import logging
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
    """

    def __init__(self, settings: ExchangeSettings | None = None) -> None:
        """
        BybitSandboxClient を初期化する。

        Args:
            settings: ExchangeSettings インスタンス。省略時は環境変数から取得。

        Raises:
            ExchangeClientError: ccxt パッケージが未インストールの場合
            ExchangeConnectionError: 取引所への接続確立に失敗した場合
        """
        try:
            import ccxt
        except ImportError as exc:
            raise ExchangeClientError(
                "ccxt package is required. Install with: pip install ccxt"
            ) from exc

        self._settings = settings or get_exchange_settings()

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
            }
        )

        if self._settings.sandbox:
            self._exchange.set_sandbox_mode(True)
            logger.info("Bybit sandbox mode enabled")

    def create_market_order(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        成行注文を送信する。

        Args:
            symbol: 取引シンボル（例: "BTC/USDT"）
            side: 注文方向（"buy" または "sell"）
            amount: 取引数量（基軸通貨単位、例: BTC 0.001）

        Returns:
            ccxt が返す注文情報の辞書

        Raises:
            ExchangeOrderError: 注文送信に失敗した場合
        """
        try:
            logger.info(
                "Creating market order: symbol=%s, side=%s, amount=%s",
                symbol,
                side,
                amount,
            )
            order = self._exchange.create_market_order(symbol, side, amount)
            logger.info("Market order created: order_id=%s", order.get("id"))
            return order
        except Exception as exc:
            logger.error("Failed to create market order: %s", exc)
            raise ExchangeOrderError(f"Failed to create market order: {exc}") from exc

    def fetch_balance(self) -> Dict[str, Any]:
        """
        口座残高を取得する。

        Returns:
            ccxt が返す残高情報の辞書

        Raises:
            ExchangeConnectionError: 残高取得に失敗した場合
        """
        try:
            balance = self._exchange.fetch_balance()
            logger.info("Balance fetched successfully")
            return balance
        except Exception as exc:
            logger.error("Failed to fetch balance: %s", exc)
            raise ExchangeConnectionError(f"Failed to fetch balance: {exc}") from exc

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        指定シンボルのティッカー情報を取得する。

        Args:
            symbol: 取引シンボル（例: "BTC/USDT"）

        Returns:
            ccxt が返すティッカー情報の辞書（'last' キーに最終取引価格が入る）

        Raises:
            ExchangeConnectionError: ティッカー取得に失敗した場合
        """
        try:
            ticker = self._exchange.fetch_ticker(symbol)
            logger.info(
                "Ticker fetched: symbol=%s, last=%s",
                symbol,
                ticker.get("last"),
            )
            return ticker
        except Exception as exc:
            logger.error("Failed to fetch ticker for %s: %s", symbol, exc)
            raise ExchangeConnectionError(
                f"Failed to fetch ticker for {symbol}: {exc}"
            ) from exc


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
