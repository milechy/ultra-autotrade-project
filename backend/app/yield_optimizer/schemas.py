# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/yield_optimizer/schemas.py
"""
Yield Optimizer スキーマ定義。

Privy Earn / Morpho Vaults アイドル資本自動運用で使用するデータモデル。
API レスポンスの Decimal フィールドは全て str 型で返す（JSON シリアライズ安全）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class MorphoVault(BaseModel):
    """Morpho Vault 情報。"""

    vault_address: str = Field(..., description="Vault のコントラクトアドレス")
    name: str = Field(..., description="Vault 名称 (例: 'USDC Vault')")
    apy: str = Field(..., description="年利 (Decimal 文字列, 例: '0.0523' = 5.23%)")
    tvl_usd: str = Field(..., description="TVL USD (Decimal 文字列)")


class YieldPosition(BaseModel):
    """Morpho Vault 内のポジション情報。"""

    vault_address: str = Field(..., description="Vault のコントラクトアドレス")
    deposited_amount: str = Field(..., description="預け入れ USDC 数量 (Decimal 文字列)")
    current_value: str = Field(..., description="現在価値 USDC (Decimal 文字列)")
    earned_usd: str = Field(..., description="獲得利息 USD (Decimal 文字列)")
    last_updated: Optional[str] = Field(None, description="最終更新日時 ISO8601")


class IdleCapitalReport(BaseModel):
    """アイドル資本レポート。"""

    bybit_free_usdc: str = Field(..., description="Bybit USDC 空き残高 (Decimal 文字列)")
    deployed_amount: str = Field(..., description="Morpho 運用中 USDC (Decimal 文字列)")
    idle_amount: str = Field(
        ..., description="アイドル USDC = bybit_free - deployed (Decimal 文字列)"
    )
    should_deploy: bool = Field(..., description="Morpho への入金を推奨するか")
    threshold: str = Field(
        default="100.00",
        description="デプロイ閾値 USDC (Decimal 文字列)",
    )
    reason: Optional[str] = Field(None, description="should_deploy=False の理由")
    checked_at: str = Field(..., description="チェック日時 ISO8601")


class DepositRequest(BaseModel):
    """Morpho Vault への入金リクエスト (admin 専用)。"""

    vault_address: str = Field(..., description="入金先 Vault のコントラクトアドレス")
    amount_usdc: Decimal = Field(..., gt=Decimal("0"), description="入金 USDC 数量 (正の値)")


class WithdrawRequest(BaseModel):
    """Morpho Vault からの出金リクエスト (admin 専用)。"""

    vault_address: str = Field(..., description="出金元 Vault のコントラクトアドレス")
    amount: Decimal = Field(..., gt=Decimal("0"), description="出金 USDC 数量 (正の値)")


class TxResult(BaseModel):
    """トランザクション送信結果。"""

    tx_hash: str = Field(..., description="トランザクションハッシュ")
    vault_address: str = Field(..., description="操作対象 Vault アドレス")
    operation: str = Field(..., description="操作種別 ('deposit' | 'withdraw')")
    amount: str = Field(..., description="操作 USDC 数量 (Decimal 文字列)")
    submitted_at: str = Field(..., description="送信日時 ISO8601")


class VaultListResponse(BaseModel):
    """Vault 一覧レスポンス。"""

    vaults: list[MorphoVault]
    best_apy_vault: Optional[MorphoVault] = Field(None, description="最高 APY の Vault")
    fetched_at: str = Field(..., description="取得日時 ISO8601")


class PositionListResponse(BaseModel):
    """ポジション一覧レスポンス。"""

    positions: list[YieldPosition]
    total_deposited_usdc: str = Field(..., description="合計預け入れ USDC (Decimal 文字列)")
    total_earned_usd: str = Field(..., description="合計獲得利息 USD (Decimal 文字列)")
    fetched_at: str = Field(..., description="取得日時 ISO8601")
