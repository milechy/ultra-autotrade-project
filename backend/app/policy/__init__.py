# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/policy/__init__.py
"""Transaction Policy Engine (P0-7 MVP).

Pre-sign rule evaluation. 純粋関数ベース、I/O なし。呼出し側が context を組み立てて
``evaluate(...)`` に渡す。Verdict (allow / hold / deny) と理由文字列で返す。
"""

from app.policy.engine import (
    DEFAULT_RULES,
    PolicyDecision,
    TransactionContext,
    Verdict,
    evaluate,
)

__all__ = [
    "DEFAULT_RULES",
    "PolicyDecision",
    "TransactionContext",
    "Verdict",
    "evaluate",
]
