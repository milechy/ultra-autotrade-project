# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/onramp/schemas.py
"""フィアット オンランプ スキーマ定義 (Phase A: read-only 意図 / 着金イベント)。

I/O / 外部 API / DB 接続 / 秘密情報は一切含まない。
Stripe SDK import 禁止。webhook secret / signature フィールド禁止。

状態遷移 (docs/60_stripe_privy_fiat_onramp_design.md §5 と一致):
    CREATED → PENDING : セッション開始
    CREATED → FAILED  : 即時失敗
    PENDING → SETTLED : 着金完了
    PENDING → FAILED  : タイムアウト / 失敗
    SETTLED, FAILED   : 終端（遷移不可）
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class OnrampStatus(str, Enum):
    """オンランプセッションの状態。

    値は docs/60_stripe_privy_fiat_onramp_design.md §5 の状態遷移図と一致させる。
    ``str`` を継承しているため JSON シリアライズで文字列として扱われる。
    """

    CREATED = "created"
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"


@dataclass(frozen=True)
class OnrampSessionIntent:
    """フィアット オンランプ セッション意図 (read-only, I/O なし)。

    ユーザーがオンランプ開始を要求する際のパラメータを保持する。
    秘密情報 (API キー / webhook secret / 署名) は含めない。

    全ての金額は ``Decimal`` (Rule 11: float 禁止)。
    ``fiat_currency`` / ``target_crypto`` の許可リスト検証は
    ``validators.validate_fiat_currency`` / ``validators.validate_target_crypto`` で行う。
    ``destination_wallet_address`` の形式検証は ``validators.validate_wallet_address`` で行う。

    Fields:
        user_id: UATa ユーザー ID。
        fiat_amount: フィアット金額 (Decimal, 正値)。
        fiat_currency: ISO 4217 通貨コード (例: "USD", "EUR", "JPY")。
        target_crypto: 購入対象暗号資産シンボル (例: "ETH", "USDC")。
        destination_wallet_address: 着金先 EVM ウォレットアドレス (0x...42 文字)。
    """

    user_id: int
    fiat_amount: Decimal
    fiat_currency: str
    target_crypto: str
    destination_wallet_address: str


@dataclass(frozen=True)
class OnrampSettlementEvent:
    """フィアット オンランプ 着金イベント (read-only)。

    Stripe webhook 受信後に構築される着金通知データ。
    秘密情報 (Stripe-Signature / webhook secret / HMAC) は含めない。
    webhook signature 検証はフェーズ B (HUMAN-REVIEW-REQUIRED) で別モジュールが担当する。

    Fields:
        intent_id: 対応する OnrampSessionIntent の識別子。
        status: 現在の状態 (OnrampStatus)。
        crypto_amount_received: 着金した暗号資産量 (SETTLED 時のみ設定、Decimal)。
        vendor_reference_id: Stripe セッション参照 ID (省略可)。
            fee_transactions.vendor_reference_id と同一命名規約だが別テーブル向け。
            【要確認】Stripe Crypto Onramp webhook payload での参照 ID フィールド名を
            フェーズ B 実装前に確認すること。
    """

    intent_id: str
    status: OnrampStatus
    crypto_amount_received: Optional[Decimal] = None
    vendor_reference_id: Optional[str] = None
