# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
統合ポートフォリオ集約スキーマ

3ソース (Aave V3 / Privy Wallet / Bybit CEX) を横断する統合ポートフォリオビュー用の
Pydantic v2 スキーマ定義。

設計書: docs/59_unified_portfolio_dashboard_design.md

注意:
- 既存の app.portfolio.schemas (Aave単一ソース履歴用) とは別ファイル。混在禁止。
- 全 Decimal フィールドは field_serializer で文字列シリアライズ (CLAUDE.md Security Rule 11)
- HF 無限大処理は既存 _cap_hf_inf 思想踏襲 (backend/app/portfolio/schemas.py L12-15)
"""

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator


def _cap_hf_inf(v: Optional[Decimal]) -> Optional[Decimal]:
    """Health Factor の無限大 (Decimal('inf')) を 999.0 にキャップする。

    参照: backend/app/portfolio/schemas.py の同名関数 (L12-15)
    """
    if v is not None and isinstance(v, Decimal) and not v.is_finite():
        return Decimal("999.0")
    return v


class SourceBalance(BaseModel):
    """ソース別残高。集約関数 (aggregation.py) への入力単位。

    available=False の場合、そのソースのデータ取得は失敗しているが
    fail-open 設計により他ソースの表示は継続する。
    """

    model_config = ConfigDict()

    source: Literal["aave", "wallet", "cex"]
    total_usd: Decimal
    """ソース内合計 USD。
    - aave: total_collateral_usd - total_debt_usd (純資産)
    - wallet: eth_usd_value + usdc_usd_value (Aave supply 分を含まない)
    - cex: balance_usdt (USDT ≈ USD 1:1)
    """
    available: bool = True
    """データ取得成功フラグ。False = fail-open フォールバック値。"""

    # Aave 専用フィールド
    supply_usd: Optional[Decimal] = None
    """Aave 担保総額 (total_collateral_usd)。aave ソース専用。"""
    borrow_usd: Optional[Decimal] = None
    """Aave 借入総額 (total_debt_usd)。aave ソース専用。"""
    health_factor: Optional[Decimal] = None
    """Aave 健全性指標。aave ソース専用。Decimal('inf') は _cap_hf_inf でキャップ。"""

    @field_validator("health_factor", mode="before")
    @classmethod
    def cap_infinity_hf(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return _cap_hf_inf(v)

    @field_serializer("total_usd")
    def serialize_total_usd(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("supply_usd")
    def serialize_supply_usd(self, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None

    @field_serializer("borrow_usd")
    def serialize_borrow_usd(self, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None

    @field_serializer("health_factor")
    def serialize_health_factor(self, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None


class UnifiedPortfolioInput(BaseModel):
    """集約関数 aggregate_portfolio() への入力。

    各ソースが Optional。欠落 = そのソースの取得が失敗したことを示す (fail-open)。
    欠落ソースは grand_total から除外され、degraded=True が設定される。
    """

    model_config = ConfigDict()

    aave: Optional[SourceBalance] = None
    """Aave V3 ポジション。None = Aave データ取得失敗。"""
    wallet: Optional[SourceBalance] = None
    """Privy Wallet 残高 (Base mainnet ETH + USDC)。None = Wallet データ取得失敗。"""
    cex: Optional[SourceBalance] = None
    """Bybit CEX 残高 (USDT)。None = CEX データ取得失敗。"""


class SourceAllocation(BaseModel):
    """ソース別配分情報。UnifiedPortfolioView.allocations の要素。"""

    model_config = ConfigDict()

    source: str
    """ソース識別子。"aave" | "wallet" | "cex"。"""
    total_usd: Decimal
    """ソース残高 (USD)。"""
    allocation_pct: Decimal
    """ポートフォリオ全体に対する比率 (%)。grand_total=0 の場合は 0。"""
    available: bool
    """データ取得成功フラグ。"""

    @field_serializer("total_usd", "allocation_pct")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)


class UnifiedPortfolioView(BaseModel):
    """統合ポートフォリオビュー。aggregate_portfolio() の出力。

    fail-open: 1ソース以上欠落しても他ソースの値を返す。
    欠落ソースの USD は grand_total から除外される。
    """

    model_config = ConfigDict()

    grand_total_usd: Decimal
    """3ソース合算 USD 総額 (available=True のソースのみ)。"""
    aave_net_usd: Decimal
    """Aave 純資産 USD (unavailable / 欠落時は 0)。"""
    wallet_usd: Decimal
    """Wallet 残高 USD (unavailable / 欠落時は 0)。"""
    cex_usd: Decimal
    """CEX 残高 USD (unavailable / 欠落時は 0)。"""
    health_factor: Optional[Decimal] = None
    """Health Factor。Aave ソースが available な場合のみ設定。それ以外は None。"""
    allocations: list[SourceAllocation]
    """ソース別配分リスト。"""
    sources_available: int
    """正常取得できたソース数 (0-3)。"""
    sources_total: int = 3
    """総ソース数 (常に3)。"""
    degraded: bool
    """1ソース以上欠落している場合 True。表示側での警告表示用。"""

    @field_validator("health_factor", mode="before")
    @classmethod
    def cap_infinity_hf(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return _cap_hf_inf(v)

    @field_serializer("grand_total_usd", "aave_net_usd", "wallet_usd", "cex_usd")
    def serialize_usd(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("health_factor")
    def serialize_health_factor(self, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None
