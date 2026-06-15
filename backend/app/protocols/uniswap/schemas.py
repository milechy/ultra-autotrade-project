# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Uniswap V4 スワップ統合 Pydantic スキーマ定義（Phase 1 scaffold）。

本ファイルは **意図・検証用途のみ** の純粋型定義を提供する。
calldata / to アドレス / tx_hash / approvals 等の実行系フィールドは
HUMAN-REVIEW-REQUIRED スコープ（Phase 2 以降）で追加する:
  - Phase 2: SDK calldata 取得（dry_run=True 前提）
  - Phase 3: Privy 署名 + broadcast（HUMAN-REVIEW-REQUIRED）
  - Phase 4: main.py ルーター配線（Tier S）
これらのフィールドを本ファイルに追加する際は Planner の事前承認を必要とする。

セキュリティ:
- 秘密鍵・署名情報をフィールドとして保持しない
- 金融計算フィールドは全て Decimal 型（float 禁止）
- Decimal は JSON シリアライズ時に文字列で返却する
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_serializer, field_validator


class UniswapV4SwapIntent(BaseModel):
    """Uniswap V4 スワップ意図（read-only リクエスト容器）。

    NOTE: チェーンは V4 Pool Manager がデプロイされているチェーンに限定する。
    デプロイ済みチェーンアドレスは【要確認】— Universal Router 正式アドレスの
    chain 別マッピングを Phase 2 着手前に SDK / 公式ドキュメントで確認すること。
    現在 Literal は暫定値（Ethereum Mainnet / Arbitrum / Base / Optimism / Polygon を想定）。
    """

    token_in: str = Field(
        ..., description="入力トークンアドレス（ERC-20 / ネイティブは '0xEeeee...' 等）"
    )
    token_out: str = Field(..., description="出力トークンアドレス")
    amount_in: Decimal = Field(..., gt=Decimal("0"), description="入力量（ネイティブ単位）")
    slippage: Decimal = Field(
        default=Decimal("0.005"),
        gt=Decimal("0"),
        le=Decimal("0.05"),
        description="スリッページ許容幅（0.005 = 0.5%）。0 < slippage <= 0.05（5%）",
    )
    deadline_unix: int = Field(
        ..., description="スワップ期限（Unix 秒）。現在時刻を超えていれば拒否"
    )
    receiver: str = Field(..., description="スワップ受取アドレス（空文字は拒否）")
    portfolio_value_usd: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0"),
        description="ポートフォリオ総額（USD）。10%上限チェック用。amount_in_usd と併用必須",
    )
    amount_in_usd: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0"),
        description=(
            "トレード金額（USD）。portfolio_value_usd と併用必須。"
            "片方のみ指定時は fail-closed で拒否（10%上限が検証不能なため）"
        ),
    )
    chain: Literal["ethereum", "arbitrum", "base", "optimism", "polygon"] = Field(
        ...,
        description=(
            "対象チェーン。【要確認】Universal Router 正式アドレスは chain 別に異なる。"
            "Phase 2 着手前に公式ドキュメントで確認すること。"
        ),
    )
    dry_run: bool = Field(
        True,
        description="True の場合バリデーションのみ実行（デフォルト）。SDK calldata 取得は Phase 2 以降",
    )

    @field_validator("amount_in", mode="before")
    @classmethod
    def _coerce_amount_in(cls, v: object) -> Decimal:
        """float / 文字列を Decimal に変換する（float 禁止ルール準拠）。"""
        return Decimal(str(v))

    @field_validator("slippage", mode="before")
    @classmethod
    def _coerce_slippage(cls, v: object) -> Decimal:
        """float / 文字列を Decimal に変換する。"""
        return Decimal(str(v))

    @field_validator("amount_in_usd", mode="before")
    @classmethod
    def _coerce_amount_in_usd(cls, v: object) -> Optional[Decimal]:
        """float / 文字列を Decimal に変換する。None の場合はそのまま。"""
        if v is None:
            return None
        return Decimal(str(v))

    @field_validator("portfolio_value_usd", mode="before")
    @classmethod
    def _coerce_portfolio_value_usd(cls, v: object) -> Optional[Decimal]:
        """float / 文字列を Decimal に変換する。None の場合はそのまま。"""
        if v is None:
            return None
        return Decimal(str(v))

    @field_serializer("amount_in", "slippage")
    def _serialize_decimal(self, v: Decimal) -> str:
        """Decimal フィールドを文字列でシリアライズ（JSON 精度保持）。"""
        return str(v)

    @field_serializer("amount_in_usd", "portfolio_value_usd")
    def _serialize_optional_decimal(self, v: Optional[Decimal]) -> Optional[str]:
        """Optional[Decimal] フィールドを文字列でシリアライズ。"""
        if v is None:
            return None
        return str(v)


class UniswapV4SwapEstimate(BaseModel):
    """Uniswap V4 スワップ推定結果（read-only 容器）。

    バリデータが返す純粋な検証結果を保持する。
    実行系情報（calldata / to / tx_hash / approvals）は含まない。
    これらは HUMAN-REVIEW-REQUIRED スコープ（Phase 2/3）で別途定義する。
    """

    amount_out_estimate: Optional[Decimal] = Field(
        default=None,
        description="推定受取量（外部 quoting API から取得、Phase 1 では None）",
    )
    min_amount_out: Optional[Decimal] = Field(
        default=None,
        description="最小受取量（amount_out_estimate * (1 - slippage)）",
    )
    price_impact_pct: Optional[Decimal] = Field(
        default=None,
        description="価格インパクト（%）。外部 quoting API から取得、Phase 1 では None",
    )
    is_valid: bool = Field(..., description="バリデーション通過フラグ")
    validation_errors: list[str] = Field(
        default_factory=list,
        description="バリデーションエラーリスト（is_valid=False の場合に詳細を格納）",
    )

    @field_serializer("amount_out_estimate", "min_amount_out", "price_impact_pct")
    def _serialize_optional_decimal(self, v: Optional[Decimal]) -> Optional[str]:
        """Optional[Decimal] フィールドを文字列でシリアライズ。"""
        if v is None:
            return None
        return str(v)
