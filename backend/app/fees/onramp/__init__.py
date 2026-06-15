# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/onramp/__init__.py
"""フィアット オンランプ サブモジュール (Stripe x Privy 統合 Phase A)。

純粋関数のスキーマ定義とバリデータを提供する。I/O / 副作用 / 外部 API は持たない。

公開:
- ``OnrampStatus``           : オンランプ状態 Enum (CREATED/PENDING/SETTLED/FAILED)
- ``OnrampSessionIntent``    : オンランプ意図 dataclass (frozen, Decimal)
- ``OnrampSettlementEvent``  : 着金イベント dataclass (frozen, read-only)
- ``validate_fiat_amount``   : フィアット金額の最小/最大バリデータ
- ``validate_fiat_currency`` : フィアット通貨許可リスト検証
- ``validate_target_crypto`` : 対象暗号資産許可リスト検証
- ``validate_wallet_address``: EVM ウォレットアドレス形式検証
- ``is_valid_transition``    : 状態遷移バリデータ

注意: Stripe SDK / API キー / webhook secret / HMAC 検証は含まない。
      フェーズ B (HUMAN-REVIEW-REQUIRED) で別モジュールに実装する。
"""

from __future__ import annotations

from .schemas import (
    OnrampSessionIntent,
    OnrampSettlementEvent,
    OnrampStatus,
)
from .validators import (
    is_valid_transition,
    validate_fiat_amount,
    validate_fiat_currency,
    validate_target_crypto,
    validate_wallet_address,
)

__all__ = [
    "OnrampStatus",
    "OnrampSessionIntent",
    "OnrampSettlementEvent",
    "validate_fiat_amount",
    "validate_fiat_currency",
    "validate_target_crypto",
    "validate_wallet_address",
    "is_valid_transition",
]
