# backend/app/exchange/schemas.py

"""
Exchange（Bybit Sandbox）操作用の Pydantic スキーマ定義。

- /exchange/order のリクエスト / レスポンス
- /exchange/status のレスポンス
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.ai.schemas import TradeAction


class OrderSide(str, Enum):
    """注文の方向。"""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """注文処理の結果ステータス。"""

    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


class OrderRequest(BaseModel):
    """
    /exchange/order のリクエストボディ。

    AI 判定結果（BUY / SELL / HOLD）を受け取り、
    内部で成行注文または SKIPPED に変換する。
    """

    action: TradeAction = Field(
        ...,
        description="AI 判定または OctoBot シグナルから受け取るアクション（BUY/SELL/HOLD）。",
    )
    symbol: Optional[str] = Field(
        None,
        description="取引シンボル（例: 'BTC/USDT'）。未指定の場合は設定のデフォルトを使用。",
    )
    amount_usd: Decimal = Field(
        ...,
        gt=0,
        description="注文金額（USD 相当）。0 より大きい必要がある。",
    )
    reason: Optional[str] = Field(
        None,
        description="注文の根拠となる理由（ログ・監査用の補足情報）。",
    )
    dry_run: bool = Field(
        False,
        description=(
            "True の場合、取引所に対して実際の注文は送信せず、実行されるであろう結果のみを返す。"
        ),
    )


class OrderResult(BaseModel):
    """
    /exchange/order のレスポンスボディ。

    - 成功時は order_id と price が設定される
    - スキップ・失敗時は message にその理由が入る
    """

    order_id: Optional[str] = Field(
        None,
        description="取引所が発行した注文 ID。SKIPPED / FAILED 時は None。",
    )
    status: OrderStatus = Field(..., description="注文処理の結果ステータス。")
    side: Optional[OrderSide] = Field(
        None,
        description="注文の方向（buy / sell）。HOLD や SKIPPED 時は None。",
    )
    symbol: str = Field(..., description="取引シンボル（例: 'BTC/USDT'）。")
    amount_usd: Decimal = Field(
        ...,
        ge=0,
        description="注文金額（USD 相当）。",
    )
    price: Optional[Decimal] = Field(
        None,
        description="注文執行時の価格（USD）。SKIPPED / FAILED 時は None。",
    )
    message: Optional[str] = Field(
        None,
        description="人間向けの説明メッセージ（スキップ理由、エラー内容など）。",
    )
    timestamp: datetime = Field(
        ...,
        description="注文処理を行った時刻（UTC）。",
    )


class ExchangeStatusResponse(BaseModel):
    """
    /exchange/status のレスポンスボディ。

    取引所への接続状態および本日の取引状況を返す。
    """

    sandbox_mode: bool = Field(
        ...,
        description="True の場合、サンドボックス環境で動作中。",
    )
    connected: bool = Field(
        ...,
        description="取引所への接続が確立されているかどうか。",
    )
    balance_usdt: Optional[Decimal] = Field(
        None,
        description="USDT 建ての残高。接続失敗時は None。",
    )
    daily_trades_used: int = Field(
        ...,
        ge=0,
        description="本日実行した取引件数。",
    )
    daily_trade_limit: int = Field(
        ...,
        ge=0,
        description="1日あたりの取引上限件数。",
    )
    last_trade_at: Optional[datetime] = Field(
        None,
        description="最後に取引を実行した時刻（UTC）。取引がなければ None。",
    )
