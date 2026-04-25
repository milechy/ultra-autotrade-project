# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/__init__.py
"""Fee Model v10 サービス層 (F-5 〜)。

純粋関数の手数料計算エンジンを提供する。I/O / 副作用は持たない。

公開:
- ``FeeCalculator``        : 月次手数料計算エンジン
- ``FeeCalculationInput``  : 入力 dataclass (frozen, Decimal)
- ``FeeCalculationResult`` : 出力 dataclass (frozen, Decimal)
- ``JPY_QUANTIZE``         : 円未満切り捨て用 Decimal 単位
"""

from .calculator import (
    JPY_QUANTIZE,
    FeeCalculationInput,
    FeeCalculationResult,
    FeeCalculator,
)

__all__ = [
    "JPY_QUANTIZE",
    "FeeCalculationInput",
    "FeeCalculationResult",
    "FeeCalculator",
]
