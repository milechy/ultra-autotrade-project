# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/__init__.py
"""Fee Model v10 サービス層 (F-5 〜)。

純粋関数の手数料計算エンジンを提供する。I/O / 副作用は持たない。

公開:
- ``FeeCalculator``          : 月次手数料計算エンジン
- ``FeeCalculationInput``    : 入力 dataclass (frozen, Decimal)
- ``FeeCalculationResult``   : 出力 dataclass (frozen, Decimal)
- ``JPY_QUANTIZE``           : 円未満切り捨て用 Decimal 単位
- ``MarketFeeResult``        : トレードゲート判定結果 (§4)
- ``calculate_fee_by_market``: §4 トレードゲート (予想利益 > 経費チェック)
- ``BillingVendorAdapter``   : 課金ベンダー抽象プロトコル (F-7 vendor-agnostic)
- ``ChargeRequest``          : 課金リクエスト dataclass
- ``ChargeResult``           : 課金結果 dataclass
- ``StubBillingAdapter``     : ベンダー未定期間スタブ (ログのみ)
"""

from .billing_adapter import (
    BillingVendorAdapter,
    ChargeRequest,
    ChargeResult,
    StubBillingAdapter,
)
from .calculator import (
    JPY_QUANTIZE,
    FeeCalculationInput,
    FeeCalculationResult,
    FeeCalculator,
)
from .trade_gate import (
    MarketFeeResult,
    calculate_fee_by_market,
)

__all__ = [
    "BillingVendorAdapter",
    "ChargeRequest",
    "ChargeResult",
    "StubBillingAdapter",
    "JPY_QUANTIZE",
    "FeeCalculationInput",
    "FeeCalculationResult",
    "FeeCalculator",
    "MarketFeeResult",
    "calculate_fee_by_market",
]
