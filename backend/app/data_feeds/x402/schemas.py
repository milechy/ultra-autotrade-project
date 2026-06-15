# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/data_feeds/x402/schemas.py
"""
x402 AI自律データ購入 — 購入意図・予算ポリシー Pydantic スキーマ (read-only scaffold)

設計方針:
  - 外部I/O・HTTP・blockchain・秘密鍵・ウォレット署名には一切触れない
  - 全金額フィールドは Decimal 型 (float 禁止 / Security Rules 準拠)
  - field_serializer で文字列化 (JSON シリアライズ / API レスポンス互換)
  - rebalance_schemas.py の Decimal パターンを踏襲

HUMAN-REVIEW-REQUIRED スコープ (本ファイルでは実装しない):
  - payment header 生成・検証
  - facilitator 通信
  - ウォレット署名・秘密鍵操作
  - contract address 保持
  - 実決済実行
"""

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

# ===== Enums =====


class X402PaymentToken(str, Enum):
    """x402 決済で使用するトークンの種別 (symbol のみ)。

    contract address は持たせない:
      - チェーン・環境依存 (mainnet/testnet で異なる)
      - 鍵管理・blockchain 設定は HUMAN-REVIEW スコープ
      - 将来の Phase 2/3 で facilitator から解決する
    """

    USDC = "USDC"
    USDT = "USDT"
    # 将来追加可: DAI, ETH など (Phase 2 設計時に検討)


# ===== スキーマ =====


class X402PurchaseIntent(BaseModel):
    """AI が生成する有料データ購入意図。

    read-only な意図表明のみ。実HTTP・署名・payment header は含まない。
    外部 I/O / blockchain 操作は一切行わない。

    全金額フィールドは Decimal 型 (float 禁止)。
    """

    model_config = ConfigDict(strict=False)

    resource_url: str = Field(
        ...,
        description="購入対象のデータリソース URL (例: https://api.example.com/v1/premium-data)",
    )

    # float 禁止: 金融計算は Decimal 型のみ (Security Rules 11)
    amount_usd: Decimal = Field(
        ...,
        description="購入金額 (USD 建て)。正の値のみ許容。float 禁止。",
    )

    token: X402PaymentToken = Field(
        default=X402PaymentToken.USDC,
        description="決済トークン種別 (symbol)。contract address は Phase 2 で解決。",
    )

    description: Optional[str] = Field(
        default=None,
        description="購入理由の自然言語説明 (AI ログ用)。",
    )

    @field_serializer("amount_usd")
    def serialize_amount_usd(self, v: Decimal) -> str:
        """Decimal を文字列で返却 (JSON シリアライズ / API レスポンス互換)。"""
        return str(v)


class X402BudgetPolicy(BaseModel):
    """x402 決済の予算ポリシー。

    設計思想:
      - workflow.py の安全装置と同じ Decimal-only 思想を踏襲
        (daily_limit = total_assets * 30% / HF < Decimal("1.6") HARD_STOP)
      - emergency stop は OR ロジック (Security Rules 6) — 手動停止は上書き不可
      - 予算超過 / facilitator 不通時は購入せず None フォールバック (fail-open 原則)

    全金額フィールドは Decimal 型 (float 禁止 / Security Rules 11)。
    """

    model_config = ConfigDict(strict=False)

    # float 禁止: 金融計算は Decimal 型のみ (Security Rules 11)
    max_per_request_usd: Decimal = Field(
        ...,
        description="1リクエストあたりの最大購入金額 (USD 建て)。float 禁止。",
    )

    # float 禁止: 金融計算は Decimal 型のみ (Security Rules 11)
    daily_budget_usd: Decimal = Field(
        ...,
        description=(
            "日次購入予算上限 (USD 建て)。"
            "workflow.py daily_limit (total_assets * 30%) と同様の思想。float 禁止。"
        ),
    )

    @field_serializer("max_per_request_usd", "daily_budget_usd")
    def serialize_decimal(self, v: Decimal) -> str:
        """Decimal を文字列で返却 (JSON シリアライズ / API レスポンス互換)。"""
        return str(v)
