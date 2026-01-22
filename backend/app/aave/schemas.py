# backend/app/aave/schemas.py

"""
Aave 操作用の Pydantic スキーマ定義。

- /aave/rebalance のリクエスト / レスポンス
- 内部で利用する AaveOperationResult など
"""

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.ai.schemas import TradeAction


class AaveOperationType(str, Enum):
    """Aave へ行う操作の種類。"""

    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    NOOP = "NOOP"


class AaveOperationStatus(str, Enum):
    """操作結果のステータス。"""

    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


class AaveRebalanceRequest(BaseModel):
    """
    /aave/rebalance のリクエストボディ。

    BUY / SELL / HOLD のアクションと金額を受け取り、
    内部で deposit / withdraw / NOOP に変換する。
    """

    action: TradeAction = Field(
        ...,
        description="AI 判定または OctoBot シグナルから受け取るアクション（BUY/SELL/HOLD）。",
    )
    amount: Decimal = Field(
        ...,
        gt=0,
        description="対象資産の金額（USD 相当を想定）。0 より大きい必要がある。",
    )
    asset_symbol: Optional[str] = Field(
        None,
        description="対象となるトークンシンボル。未指定の場合は設定値のデフォルト（例: USDC）を利用する。",
    )
    dry_run: bool = Field(
        False,
        description=(
            "True の場合、Aave クライアントに対して実際のトランザクションは送信せず、"
            "実行されるであろう結果のみを返す。"
        ),
    )


class AaveOperationResult(BaseModel):
    """
    Aave 上での 1 回の操作結果。

    - operation: 実行した（または実行しなかった）操作の種類
    - status: 成功 / スキップ / エラー
    - tx_hash: 実際に送信されたトランザクションのハッシュ（NOOP や dry-run では None）
    """

    operation: AaveOperationType = Field(..., description="実行された操作の種類。")
    status: AaveOperationStatus = Field(..., description="操作の結果ステータス。")
    asset_symbol: str = Field(..., description="対象トークンのシンボル。")
    amount: Decimal = Field(
        ...,
        ge=0,
        description="実際に Aave に対して扱った金額。NOOP 時は 0。",
    )
    tx_hash: Optional[str] = Field(
        None,
        description="ブロックチェーンのトランザクションハッシュ。NOOP やエラー時は None。",
    )
    message: Optional[str] = Field(
        None,
        description="人間向けの説明メッセージ（スキップ理由など）。",
    )
    before_health_factor: Optional[Decimal] = Field(
        None,
        ge=0,
        description="操作前のヘルスファクター（取得できなかった場合は None）。",
    )
    after_health_factor: Optional[Decimal] = Field(
        None,
        ge=0,
        description="操作後のヘルスファクター（取得できなかった場合は None）。",
    )


class AaveRebalanceResponse(BaseModel):
    """
    /aave/rebalance のレスポンスボディ。
    """

    result: AaveOperationResult = Field(
        ...,
        description="今回のリバランスで行われた操作結果。",
    )
