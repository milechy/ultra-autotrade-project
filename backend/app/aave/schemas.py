# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/schemas.py

"""
Aave 操作用の Pydantic スキーマ定義。

- /aave/rebalance のリクエスト / レスポンス
- 内部で利用する AaveOperationResult など
- システム状態管理用の AaveSystemState
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.ai.schemas import TradeAction

# ===== システム状態管理用 =====


class AaveOperationMode(str, Enum):
    """
    Aave 運用の動作モード。

    - NORMAL: 通常運用（deposit/withdraw 両方可能）
    - SAFE_MODE: 安全モード（withdraw のみ、deposit 不可）
    - HARD_STOP: 完全停止（手動操作のみ）
    """

    NORMAL = "normal"
    SAFE_MODE = "safe_mode"
    HARD_STOP = "hard_stop"


class AaveSystemState(BaseModel):
    """
    システム状態ファイル（state.json）のスキーマ。

    backend と nginx 間で共有し、緊急停止や動作モードを管理する。
    """

    emergency_stop: bool = Field(
        ...,
        description="緊急停止フラグ。True の場合は全操作を停止。",
    )
    mode: AaveOperationMode = Field(
        ...,
        description="現在の動作モード。",
    )
    health_factor: Optional[Decimal] = Field(
        None,
        description="最後に取得したヘルスファクター。",
    )
    last_update: datetime = Field(
        ...,
        description="状態の最終更新日時（ISO 8601形式）。",
    )
    reason: Optional[str] = Field(
        None,
        description="現在のモード/停止状態の理由。",
    )
    circuit_closed: bool = Field(
        ...,
        description="Circuit Breaker の状態。True=閉（動作可）、False=開（停止）。",
    )
    stale_threshold_seconds: int = Field(
        300,
        description="状態が古いとみなす閾値（秒）。",
    )

    model_config = ConfigDict()

    @field_serializer("health_factor")
    @classmethod
    def serialize_decimal(cls, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None

    @field_serializer("last_update")
    @classmethod
    def serialize_datetime(cls, v: datetime) -> str:
        return v.isoformat()


# ===== Aave 操作用 =====


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
    chain_name: Optional[str] = Field(
        None,
        description="対象チェーン名。未指定時はプライマリチェーン（arbitrum）を使用する。",
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
    chain_name: Optional[str] = Field(
        None,
        description="操作が実行されたチェーン名。",
    )


class AaveRebalanceResponse(BaseModel):
    """
    /aave/rebalance のレスポンスボディ。
    """

    result: AaveOperationResult = Field(
        ...,
        description="今回のリバランスで行われた操作結果。",
    )


class AaveBalanceInfo(BaseModel):
    """ウォレットの Aave 関連残高情報。"""

    wallet_address: str = Field(description="監視対象のウォレットアドレス。")
    usdc_balance: Decimal = Field(ge=0, description="USDC 残高（人間単位）。")
    a_usdc_balance: Decimal = Field(ge=0, description="aUSDC 残高（人間単位）。")

    @field_serializer("usdc_balance", "a_usdc_balance")
    @classmethod
    def _serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


class AaveMonitorStatus(BaseModel):
    """GET /aave/status のレスポンス。"""

    health_factor: Optional[Decimal] = Field(
        None, description="最新の Health Factor。取得失敗時は None。"
    )
    balance: AaveBalanceInfo = Field(description="USDC / aUSDC 残高。")
    client_type: str = Field(description="AAVE_CLIENT_TYPE 環境変数の値。")
    fetched_at: str = Field(description="取得日時 (ISO 8601)。")

    @field_serializer("health_factor")
    @classmethod
    def _serialize_hf(cls, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None
