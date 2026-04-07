# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/ai/accuracy.py
"""AI判定的中率計算ロジック。"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AIDecision


@dataclass
class ActionAccuracy:
    """アクション別的中率。"""

    total: int
    correct: int
    pct: Decimal


@dataclass
class AccuracyResult:
    """的中率計算結果。"""

    total_decisions: int
    correct_count: int
    accuracy_pct: Decimal
    last_30d_accuracy_pct: Decimal
    by_action: dict[str, ActionAccuracy] = field(default_factory=dict)


def _calc_pct(correct: int, total: int) -> Decimal:
    """的中率をDecimalで返す。ゼロ除算は0を返す。"""
    if total == 0:
        return Decimal("0.00")
    return (Decimal(correct) / Decimal(total) * Decimal("100")).quantize(Decimal("0.01"))


def calculate_accuracy(db: Session, days: Optional[int] = None) -> AccuracyResult:
    """
    AIDecisionテーブルからBUY/SELL判定の的中率を計算する。

    - HOLDは除外
    - agreed=True → 的中
    - days指定時はその期間内のレコードのみ対象
    """
    base_stmt = select(AIDecision).where(AIDecision.action.in_(["BUY", "SELL"]))
    if days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        base_stmt = base_stmt.where(AIDecision.created_at >= since)

    all_decisions = db.scalars(base_stmt).all()
    total = len(all_decisions)
    correct = sum(1 for d in all_decisions if d.agreed)
    accuracy_pct = _calc_pct(correct, total)

    # last_30d
    since_30d = datetime.now(timezone.utc) - timedelta(days=30)
    stmt_30d = select(AIDecision).where(
        AIDecision.action.in_(["BUY", "SELL"]),
        AIDecision.created_at >= since_30d,
    )
    decisions_30d = db.scalars(stmt_30d).all()
    total_30d = len(decisions_30d)
    correct_30d = sum(1 for d in decisions_30d if d.agreed)
    last_30d_accuracy_pct = _calc_pct(correct_30d, total_30d)

    # by_action
    by_action: dict[str, ActionAccuracy] = {}
    for action in ("BUY", "SELL"):
        action_decisions = [d for d in all_decisions if d.action == action]
        a_total = len(action_decisions)
        a_correct = sum(1 for d in action_decisions if d.agreed)
        by_action[action] = ActionAccuracy(
            total=a_total,
            correct=a_correct,
            pct=_calc_pct(a_correct, a_total),
        )

    return AccuracyResult(
        total_decisions=total,
        correct_count=correct,
        accuracy_pct=accuracy_pct,
        last_30d_accuracy_pct=last_30d_accuracy_pct,
        by_action=by_action,
    )
