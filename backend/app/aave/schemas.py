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

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

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

    @field_validator("health_factor", mode="before")
    @classmethod
    def cap_infinity_hf(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Aave V3 ではポジションがないと HF=∞ を返す。Pydantic の finite_number 制約を回避するため 999.0 に丸める。"""
        if v is not None and isinstance(v, Decimal) and not v.is_finite():
            return Decimal("999.0")
        return v

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
        description="対象チェーン名。未指定時は AAVE_ACTIVE_CHAINS の先頭チェーン（本番デフォルト: base）を使用する。",
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

    @field_validator("before_health_factor", "after_health_factor", mode="before")
    @classmethod
    def cap_infinity_hf(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Aave V3 ではポジションがないと HF=∞ を返す。finite_number 制約を回避するため 999.0 に丸める。"""
        if v is not None and isinstance(v, Decimal) and not v.is_finite():
            return Decimal("999.0")
        return v


class AaveRebalanceResponse(BaseModel):
    """
    /aave/rebalance のレスポンスボディ。
    """

    result: AaveOperationResult = Field(
        ...,
        description="今回のリバランスで行われた操作結果。",
    )


class ClaimableReward(BaseModel):
    """1 トークンの未請求リワード情報。"""

    asset_name: str = Field(description="リワードトークン名 (例: AAVE, GHO)。")
    reward_token_address: str = Field(description="リワードトークンのコントラクトアドレス。")
    amount: Decimal = Field(ge=0, description="未請求リワード量（人間単位）。")
    amount_usd: Decimal = Field(ge=0, description="未請求リワードの USD 換算額。")

    @field_serializer("amount", "amount_usd")
    @classmethod
    def _serialize_claimable_decimal(cls, v: Decimal) -> str:
        return str(v)


class RewardClaimResult(BaseModel):
    """リワード Claim + 再投資の実行結果。"""

    claimed: bool = Field(description="Claim が実行されたかどうか。")
    total_usd: Decimal = Field(ge=0, description="Claim したリワードの合計 USD 額。")
    rewards: list[ClaimableReward] = Field(
        default_factory=list, description="Claim したリワード一覧。"
    )
    supply_tx_hash: Optional[str] = Field(None, description="再投資 supply の tx ハッシュ。")
    skip_reason: Optional[str] = Field(None, description="Claim スキップ理由（閾値未満など）。")
    claimed_at: Optional[str] = Field(None, description="Claim 実行日時 (ISO 8601)。")
    claimed_but_not_resupplied: list[str] = Field(
        default_factory=list,
        description="Claim 済みだが Aave 未対応のため supply をスキップしたトークン名一覧。",
    )
    error: Optional[str] = Field(None, description="エラーメッセージ（fail-open 時）。")

    @field_serializer("total_usd")
    @classmethod
    def _serialize_total_usd(cls, v: Decimal) -> str:
        return str(v)


class RewardsListResponse(BaseModel):
    """GET /aave/rewards のレスポンス。"""

    rewards: list[ClaimableReward] = Field(default_factory=list, description="未請求リワード一覧。")
    total_usd: Decimal = Field(ge=0, description="未請求リワードの合計 USD 額。")
    fetched_at: str = Field(description="取得日時 (ISO 8601)。")
    note: Optional[str] = Field(None, description="補足情報（設定未完了時など）。")

    @field_serializer("total_usd")
    @classmethod
    def _serialize_total_usd_list(cls, v: Decimal) -> str:
        return str(v)


class AaveBalanceInfo(BaseModel):
    """ウォレットの Aave 関連残高情報。"""

    wallet_address: str = Field(description="監視対象のウォレットアドレス。")
    usdc_balance: Decimal = Field(ge=0, description="USDC 残高（人間単位）。")
    a_usdc_balance: Decimal = Field(ge=0, description="aUSDC 残高（人間単位）。")

    @field_serializer("usdc_balance", "a_usdc_balance")
    @classmethod
    def _serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


class OracleAlert(BaseModel):
    """
    多重 Oracle 検証の結果アラート。

    level:
    - "OK"        — 全 Oracle が一致（乖離 < 閾値）
    - "WARN"      — 一部 Oracle が取得不可（fail-open 継続）
    - "HARD_STOP" — 価格乖離が閾値超過（取引停止を推奨）
    """

    asset: str = Field(..., description="対象アセットシンボル（例: USDC）")
    level: str = Field(..., description="アラートレベル: OK / WARN / HARD_STOP")
    max_deviation_pct: Optional[str] = Field(
        None, description="3価格間の最大乖離率 (%) 文字列。取得不可の場合は None"
    )
    chainlink_price: Optional[str] = Field(None, description="Chainlink 価格（USD建て）文字列")
    pyth_price: Optional[str] = Field(None, description="Pyth Network 価格（USD建て）文字列")
    twap_price: Optional[str] = Field(
        None, description="Uniswap V3 30分 TWAP 価格（USD建て）文字列"
    )
    detail: Optional[str] = Field(None, description="アラート詳細メッセージ")
    checked_at: str = Field(..., description="検証日時 (ISO 8601)")


class OracleStatusResponse(BaseModel):
    """GET /api/aave/oracle-status のレスポンス。"""

    alerts: list[OracleAlert] = Field(default_factory=list, description="全アセットのアラート一覧")


class EModeInfo(BaseModel):
    """Aave V3 eMode カテゴリ情報。"""

    category_id: int = Field(
        ge=0, description="eMode カテゴリ ID (0=なし, 1=ステーブル, 2=ETH相関)"
    )
    label: str = Field(description="カテゴリラベル (例: 'No eMode', 'Stablecoins')")
    ltv_bps: Decimal = Field(ge=0, description="Loan-to-Value 比率 (bps 単位, 例: 9000 = 90%)")
    liquidation_threshold_bps: Decimal = Field(
        ge=0, description="清算閾値 (bps 単位, 例: 9300 = 93%)"
    )

    @field_serializer("ltv_bps", "liquidation_threshold_bps")
    @classmethod
    def _serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


class EModeRecommendation(BaseModel):
    """eMode 最適化の推奨結果。"""

    current_category_id: int = Field(ge=0, description="現在の eMode カテゴリ ID")
    recommended_category_id: int = Field(ge=0, description="推奨 eMode カテゴリ ID")
    current_ltv_bps: Decimal = Field(ge=0, description="現在の実効 LTV (bps)")
    recommended_ltv_bps: Decimal = Field(ge=0, description="推奨後の実効 LTV (bps)")
    ltv_improvement_pct: Decimal = Field(description="LTV 改善率 (パーセント, 例: 20.0 = 20% 向上)")
    reason: str = Field(description="推奨理由（担保資産の構成）")
    collateral_assets: list[str] = Field(
        default_factory=list, description="現在の担保資産シンボル一覧"
    )

    @field_serializer("current_ltv_bps", "recommended_ltv_bps", "ltv_improvement_pct")
    @classmethod
    def _serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


class EModeGetResponse(BaseModel):
    """GET /aave/emode のレスポンス。"""

    current_emode: EModeInfo = Field(description="現在の eMode 情報")
    recommendation: EModeRecommendation = Field(description="最適化推奨")
    fetched_at: str = Field(description="取得日時 (ISO 8601)")


class EModeSetRequest(BaseModel):
    """POST /aave/emode のリクエストボディ。"""

    category_id: int = Field(ge=0, le=255, description="設定する eMode カテゴリ ID (uint8)")
    dry_run: bool = Field(
        False,
        description="True の場合、チェーンへの tx 送信を行わず効果を試算のみ返す",
    )


class EModeSetResponse(BaseModel):
    """POST /aave/emode のレスポンス。"""

    category_id: int = Field(description="設定した eMode カテゴリ ID")
    tx_hash: Optional[str] = Field(None, description="tx ハッシュ (dry_run=True の場合は None)")
    dry_run: bool = Field(description="ドライランかどうか")
    message: str = Field(description="結果メッセージ")


class AaveMonitorStatus(BaseModel):
    """GET /aave/status のレスポンス。"""

    health_factor: Optional[Decimal] = Field(
        None, description="最新の Health Factor。取得失敗時は None。"
    )
    balance: AaveBalanceInfo = Field(description="USDC / aUSDC 残高。")
    client_type: str = Field(description="AAVE_CLIENT_TYPE 環境変数の値。")
    fetched_at: str = Field(description="取得日時 (ISO 8601)。")

    @field_validator("health_factor", mode="before")
    @classmethod
    def cap_infinity_hf(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Aave V3 ではポジションがないと HF=∞ を返す。finite_number 制約を回避するため 999.0 に丸める。"""
        if v is not None and isinstance(v, Decimal) and not v.is_finite():
            return Decimal("999.0")
        return v

    @field_serializer("health_factor")
    @classmethod
    def _serialize_hf(cls, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None


# ===== LiquidationSentinel: ストレステスト + プール赤字ヘルス =====


class StressTestScenarioResponse(BaseModel):
    """ストレステストの各シナリオ（価格ドロップ率）に対するレスポンス。"""

    price_drop_pct: str = Field(description="価格下落率（文字列 Decimal 例: '0.10' = 10%）")
    simulated_hf: Optional[str] = Field(
        None, description="シミュレーション後の Health Factor。計算不能時は null。"
    )
    collateral_after_usd: Optional[str] = Field(
        None, description="価格下落後の担保 USD 評価額（Decimal 文字列）。"
    )


class StressTestResponse(BaseModel):
    """GET /api/aave/stress-test のレスポンス。"""

    wallet_address: str = Field(description="対象ウォレットアドレス。")
    current_hf: Optional[str] = Field(None, description="現在の Health Factor（Decimal 文字列）。")
    current_collateral_usd: Optional[str] = Field(
        None, description="現在の担保 USD 評価額（Decimal 文字列）。"
    )
    current_debt_usd: Optional[str] = Field(
        None, description="現在の総借入 USD（Decimal 文字列）。"
    )
    liquidation_threshold: Optional[str] = Field(
        None, description="清算しきい値（Decimal 文字列、例: '0.75'）。"
    )
    scenarios: list[StressTestScenarioResponse] = Field(
        default_factory=list,
        description="価格下落シナリオ（-10%, -20%）ごとのシミュレーション結果。",
    )
    error: Optional[str] = Field(None, description="エラーが発生した場合のメッセージ。")


class PoolDeficitInfoResponse(BaseModel):
    """アセット単位のプール赤字情報レスポンス。"""

    asset_symbol: str = Field(description="アセットシンボル（例: USDC, WETH）。")
    deficit_usd: str = Field(description="赤字額（概算 USD、Decimal 文字列）。")
    alert_triggered: bool = Field(description="閾値を超えてアラートが発火したか。")


class PoolHealthResponse(BaseModel):
    """GET /api/aave/pool-health のレスポンス。"""

    chain_name: str = Field(description="対象チェーン名。")
    deficits: list[PoolDeficitInfoResponse] = Field(
        default_factory=list,
        description="アセットごとの赤字情報。",
    )
    total_deficit_usd: str = Field(description="総赤字額（概算 USD、Decimal 文字列）。")
    alert_triggered: bool = Field(description="いずれかのアセットでアラートが発火したか。")
    error: Optional[str] = Field(None, description="エラーが発生した場合のメッセージ。")
