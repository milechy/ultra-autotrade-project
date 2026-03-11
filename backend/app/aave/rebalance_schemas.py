# backend/app/aave/rebalance_schemas.py

"""
ポートフォリオリバランス機能用の Pydantic スキーマ定義。

- RebalanceProposal: リバランス提案（確認前）
- RebalanceResult: リバランス実行結果
- RebalanceStatusResponse: 現在のポートフォリオ状態
- RebalanceSimulateRequest/Response: ドライラン
- RebalanceExecuteRequest/Response: 実行
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.aave.schemas import AaveOperationResult, AaveOperationType

# ===== Enums =====


class RebalanceExecutionStatus(str, Enum):
    """リバランス実行の最終ステータス。"""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


# ===== 内部モデル =====


class AssetAllocation(BaseModel):
    """
    単一資産の現在・目標配分情報。

    全ての金額フィールドは Decimal 型を使用する（float 禁止）。
    """

    asset_symbol: str = Field(..., description="トークンシンボル（例: USDC, WETH）。")
    current_amount_usd: Decimal = Field(
        ...,
        ge=0,
        description="現在の保有金額（USD 換算）。",
    )
    current_pct: Decimal = Field(
        ...,
        ge=0,
        le=100,
        description="現在のポートフォリオに占める割合（%）。",
    )
    target_pct: Decimal = Field(
        ...,
        ge=0,
        le=100,
        description="目標のポートフォリオに占める割合（%）。",
    )
    deviation_pct: Decimal = Field(
        ...,
        description="目標からの乖離（current_pct - target_pct, %）。正=過剰、負=不足。",
    )

    model_config = ConfigDict()

    @field_serializer("current_amount_usd", "current_pct", "target_pct", "deviation_pct")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


class ProposedOperation(BaseModel):
    """
    リバランスのために提案された単一操作。

    全ての金額フィールドは Decimal 型を使用する（float 禁止）。
    """

    asset_symbol: str = Field(..., description="対象トークンシンボル。")
    operation: AaveOperationType = Field(
        ..., description="実行する操作の種類（DEPOSIT/WITHDRAW/NOOP）。"
    )
    amount_usd: Decimal = Field(
        ...,
        ge=0,
        description="操作金額（USD 換算）。",
    )
    reason: str = Field(..., description="この操作が提案された理由（人間向け説明）。")

    model_config = ConfigDict()

    @field_serializer("amount_usd")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


# ===== 提案モデル =====


class RebalanceProposal(BaseModel):
    """
    リバランス提案。実行前にユーザーが確認するためのオブジェクト。

    confirmation_token を RebalanceExecuteRequest に含めることで実行を承認する。
    全ての金額フィールドは Decimal 型を使用する（float 禁止）。
    """

    proposal_id: str = Field(..., description="提案の一意識別子（UUID）。")
    created_at: datetime = Field(..., description="提案が生成された日時（UTC）。")
    health_factor_before: Decimal = Field(
        ...,
        ge=0,
        description="提案生成時点のヘルスファクター。",
    )
    total_value_usd: Decimal = Field(
        ...,
        ge=0,
        description="ポートフォリオ総資産（USD 換算）。",
    )
    allocations: list[AssetAllocation] = Field(
        ...,
        description="各資産の現在・目標配分リスト。",
    )
    operations: list[ProposedOperation] = Field(
        ...,
        description="実行が提案された操作リスト。",
    )
    estimated_health_factor_after: Optional[Decimal] = Field(
        None,
        ge=0,
        description="リバランス後の推定ヘルスファクター（計算不可能な場合は None）。",
    )
    max_single_trade_pct: Decimal = Field(
        ...,
        ge=0,
        le=100,
        description="単一取引の上限（総資産に対する %）。セキュリティルール: 10%。",
    )
    confirmation_token: str = Field(
        ...,
        description="実行承認に使用するワンタイムトークン。",
    )
    is_executable: bool = Field(
        ...,
        description="True の場合、全てのガードレールを通過しており実行可能。",
    )
    rejection_reasons: list[str] = Field(
        default_factory=list,
        description="is_executable=False の場合、拒否理由のリスト。",
    )

    model_config = ConfigDict()

    @field_serializer("health_factor_before", "total_value_usd", "max_single_trade_pct")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)

    @field_serializer("estimated_health_factor_after")
    @classmethod
    def serialize_optional_decimal(cls, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None

    @field_serializer("created_at")
    @classmethod
    def serialize_datetime(cls, v: datetime) -> str:
        return v.isoformat()


# ===== 実行結果モデル =====


class RebalanceResult(BaseModel):
    """
    リバランス実行結果。

    全ての金額フィールドは Decimal 型を使用する（float 禁止）。
    """

    proposal_id: str = Field(..., description="対応する提案の識別子。")
    executed_at: datetime = Field(..., description="実行が完了した日時（UTC）。")
    operations: list[AaveOperationResult] = Field(
        ...,
        description="実際に実行された各操作の結果リスト。",
    )
    health_factor_before: Decimal = Field(
        ...,
        ge=0,
        description="リバランス前のヘルスファクター。",
    )
    health_factor_after: Optional[Decimal] = Field(
        None,
        ge=0,
        description="リバランス後のヘルスファクター（取得不可の場合は None）。",
    )
    status: RebalanceExecutionStatus = Field(..., description="実行の最終ステータス。")
    message: Optional[str] = Field(
        None,
        description="人間向けの実行サマリーメッセージ。",
    )

    model_config = ConfigDict()

    @field_serializer("health_factor_before")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)

    @field_serializer("health_factor_after")
    @classmethod
    def serialize_optional_decimal(cls, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None

    @field_serializer("executed_at")
    @classmethod
    def serialize_datetime(cls, v: datetime) -> str:
        return v.isoformat()


# ===== 履歴モデル =====


class RebalanceHistoryEntry(BaseModel):
    """
    リバランス履歴の 1 件分のサマリー。

    全ての金額フィールドは Decimal 型を使用する（float 禁止）。
    """

    proposal_id: str = Field(..., description="提案の一意識別子。")
    created_at: datetime = Field(..., description="提案が生成された日時（UTC）。")
    executed_at: Optional[datetime] = Field(
        None,
        description="実行が完了した日時（未実行の場合は None）。",
    )
    status: RebalanceExecutionStatus = Field(..., description="実行の最終ステータス。")
    total_value_usd: Decimal = Field(
        ...,
        ge=0,
        description="実行時点のポートフォリオ総資産（USD 換算）。",
    )
    operations_count: int = Field(
        ...,
        ge=0,
        description="実行された操作の件数。",
    )
    health_factor_before: Decimal = Field(
        ...,
        ge=0,
        description="リバランス前のヘルスファクター。",
    )
    health_factor_after: Optional[Decimal] = Field(
        None,
        ge=0,
        description="リバランス後のヘルスファクター（取得不可の場合は None）。",
    )

    model_config = ConfigDict()

    @field_serializer("total_value_usd", "health_factor_before")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)

    @field_serializer("health_factor_after")
    @classmethod
    def serialize_optional_decimal(cls, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None

    @field_serializer("created_at")
    @classmethod
    def serialize_datetime_required(cls, v: datetime) -> str:
        return v.isoformat()

    @field_serializer("executed_at")
    @classmethod
    def serialize_datetime_optional(cls, v: Optional[datetime]) -> Optional[str]:
        return v.isoformat() if v is not None else None


# ===== ステータスレスポンス =====


class RebalanceStatusResponse(BaseModel):
    """
    現在のポートフォリオ状態とリバランス必要性の概要。

    全ての金額フィールドは Decimal 型を使用する（float 禁止）。
    """

    current_allocations: list[AssetAllocation] = Field(
        ...,
        description="現在の各資産配分リスト。",
    )
    target_allocations: list[AssetAllocation] = Field(
        ...,
        description="目標の各資産配分リスト。",
    )
    health_factor: Decimal = Field(
        ...,
        ge=0,
        description="現在のヘルスファクター。",
    )
    total_value_usd: Decimal = Field(
        ...,
        ge=0,
        description="現在のポートフォリオ総資産（USD 換算）。",
    )
    deviation_threshold_pct: Decimal = Field(
        ...,
        ge=0,
        description="リバランスをトリガーする乖離閾値（%）。",
    )
    needs_rebalance: bool = Field(
        ...,
        description="True の場合、いずれかの資産が閾値を超えて乖離している。",
    )
    last_rebalance_at: Optional[datetime] = Field(
        None,
        description="最後にリバランスが実行された日時（UTC）。未実行の場合は None。",
    )
    cooldown_remaining_seconds: int = Field(
        ...,
        ge=0,
        description="次のリバランスまでのクールダウン残り秒数（0 の場合は即時実行可能）。",
    )

    model_config = ConfigDict()

    @field_serializer("health_factor", "total_value_usd", "deviation_threshold_pct")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)

    @field_serializer("last_rebalance_at")
    @classmethod
    def serialize_optional_datetime(cls, v: Optional[datetime]) -> Optional[str]:
        return v.isoformat() if v is not None else None


# ===== API リクエスト / レスポンス =====


class RebalanceSimulateRequest(BaseModel):
    """
    /aave/rebalance/simulate のリクエストボディ。

    dry_run=True がデフォルトで、実際のトランザクションは送信しない。
    """

    dry_run: bool = Field(
        True,
        description="True の場合、Aave へのトランザクション送信をスキップし提案のみを返す。",
    )


class RebalanceSimulateResponse(BaseModel):
    """
    /aave/rebalance/simulate のレスポンスボディ。
    """

    proposal: RebalanceProposal = Field(
        ...,
        description="生成されたリバランス提案。is_executable を確認してから execute へ送る。",
    )


class RebalanceExecuteRequest(BaseModel):
    """
    /aave/rebalance/execute のリクエストボディ。

    simulate で取得した proposal_id と confirmation_token の両方が必要。
    """

    proposal_id: str = Field(..., description="実行する提案の識別子。")
    confirmation_token: str = Field(
        ...,
        description="simulate レスポンスの RebalanceProposal.confirmation_token と一致する必要がある。",
    )


class RebalanceExecuteResponse(BaseModel):
    """
    /aave/rebalance/execute のレスポンスボディ。
    """

    result: RebalanceResult = Field(
        ...,
        description="リバランス実行結果。status と health_factor_after を確認すること。",
    )
