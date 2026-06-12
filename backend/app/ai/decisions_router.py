# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/ai/decisions_router.py
"""AI判定履歴API ルーター定義。"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin, require_editor, require_viewer
from app.auth.models import User
from app.database import get_db

from .decisions_schemas import AIDecisionCreate, AIDecisionListResponse, AIDecisionResponse
from .models import AIDecision, AiDecisionFeature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai/decisions", tags=["ai-decisions"])


@router.get("/latest", response_model=AIDecisionResponse, summary="最新AI判定取得")
def get_latest_decision(
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> AIDecisionResponse:
    """最新の判定結果1件を返す。"""
    stmt = select(AIDecision).order_by(AIDecision.created_at.desc()).limit(1)
    decision = db.scalars(stmt).first()
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No decisions found")
    return AIDecisionResponse.model_validate(decision)


@router.get("", response_model=AIDecisionListResponse, summary="AI判定履歴リスト")
def list_decisions(
    limit: int = 20,
    offset: int = 0,
    action: Optional[str] = None,
    min_confidence: Optional[int] = None,
    max_confidence: Optional[int] = None,
    agreed: Optional[bool] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current_user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> AIDecisionListResponse:
    """判定履歴リストを返す（ページネーション・フィルタ付き）。"""
    limit = min(limit, 100)
    stmt = select(AIDecision)
    if action:
        stmt = stmt.where(AIDecision.action == action)
    if min_confidence is not None:
        stmt = stmt.where(AIDecision.confidence >= min_confidence)
    if max_confidence is not None:
        stmt = stmt.where(AIDecision.confidence <= max_confidence)
    if agreed is not None:
        stmt = stmt.where(AIDecision.agreed == agreed)
    if date_from:
        stmt = stmt.where(AIDecision.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AIDecision.created_at <= date_to)
    total_items = db.scalars(stmt).all()
    total = len(total_items)
    stmt = stmt.order_by(AIDecision.created_at.desc()).offset(offset).limit(limit)
    items = db.scalars(stmt).all()
    return AIDecisionListResponse(
        items=[AIDecisionResponse.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# A/B 計測エンドポイント (EPIC-1 1-12)
# /{decision_id} より前に定義することで static path が優先される
# ---------------------------------------------------------------------------

_EMPTY_BUCKET: Dict[str, Any] = {
    "count": 0,
    "action_distribution": {"BUY": 0, "SELL": 0, "HOLD": 0},
    "avg_confidence": None,
    "verdict_distribution": {},
}


def _build_empty_ab_response() -> Dict[str, Any]:
    """集計失敗時の fail-open レスポンス。"""
    return {
        "days": 14,
        "buckets": {
            "legacy": dict(_EMPTY_BUCKET),
            "new": dict(_EMPTY_BUCKET),
        },
    }


def _safe_avg_confidence(rows: List[Any]) -> Optional[str]:
    """Decimal で平均を計算し文字列で返す。空リストは None。"""
    if not rows:
        return None
    total = Decimal(0)
    count = 0
    for row in rows:
        try:
            total += Decimal(str(row.confidence))
            count += 1
        except (InvalidOperation, TypeError, AttributeError):
            pass
    if count == 0:
        return None
    return str((total / Decimal(count)).quantize(Decimal("0.01")))


def _count_verdicts(rows: List[Any]) -> Dict[str, int]:
    """deterministic_breakdown->>'action' の分布を集計する。"""
    counts: Dict[str, int] = {}
    for row in rows:
        breakdown = row.deterministic_breakdown
        if not isinstance(breakdown, dict):
            continue
        action = breakdown.get("action")
        if isinstance(action, str):
            counts[action] = counts.get(action, 0) + 1
    return counts


@router.get(
    "/consensus-ab-metrics",
    summary="コンセンサス A/B 計測集計",
    response_model=None,
)
def get_consensus_ab_metrics(
    days: int = Query(14, ge=1, le=90, description="集計対象日数（デフォルト14日）"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """bucket(id % 2)別に judge_action 分布・confidence 平均・verdict 分布を返す。

    - bucket=0: legacy（偶数 id）
    - bucket=1: new（奇数 id）
    - SELECT のみ。write 禁止。
    - 集計失敗時は 500 にせず空 distribution + logger.warning (fail-open)。
    - confidence 平均等の数値は Decimal で計算し文字列で返却。
    """
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # ai_decisions と ai_decision_features を JOIN して対象期間の行を取得
        stmt = (
            select(
                AIDecision.id,
                AiDecisionFeature.judge_action,
                AiDecisionFeature.confidence,
                AiDecisionFeature.deterministic_breakdown,
            )
            .join(
                AiDecisionFeature,
                AiDecisionFeature.ai_decision_id == AIDecision.id,
            )
            .where(AIDecision.created_at >= since)
        )
        rows = db.execute(stmt).fetchall()

        # bucket 振り分け: id % 2 == 0 → legacy, id % 2 == 1 → new
        buckets: Dict[str, List[Any]] = {"legacy": [], "new": []}
        for row in rows:
            bucket_key = "new" if row.id % 2 == 1 else "legacy"
            buckets[bucket_key].append(row)

        result: Dict[str, Any] = {"days": days, "buckets": {}}
        for bucket_key, bucket_rows in buckets.items():
            action_dist: Dict[str, int] = {"BUY": 0, "SELL": 0, "HOLD": 0}
            for row in bucket_rows:
                action = row.judge_action
                if action in action_dist:
                    action_dist[action] += 1
                else:
                    # 予期しない action 値もカウント（SELL-spam 監視用）
                    action_dist[action] = action_dist.get(action, 0) + 1

            result["buckets"][bucket_key] = {
                "count": len(bucket_rows),
                "action_distribution": action_dist,
                "avg_confidence": _safe_avg_confidence(bucket_rows),
                "verdict_distribution": _count_verdicts(bucket_rows),
            }

        return result

    except Exception as exc:  # noqa: BLE001
        logger.warning("consensus-ab-metrics 集計失敗 (fail-open): %s", exc)
        return _build_empty_ab_response()


@router.get("/{decision_id}", response_model=AIDecisionResponse, summary="AI判定詳細")
def get_decision(
    decision_id: int,
    current_user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> AIDecisionResponse:
    """指定IDの判定詳細を返す。"""
    stmt = select(AIDecision).where(AIDecision.id == decision_id)
    decision = db.scalars(stmt).first()
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return AIDecisionResponse.model_validate(decision)


@router.post(
    "",
    response_model=AIDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="AI判定記録",
)
def create_decision(
    request: AIDecisionCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AIDecisionResponse:
    """判定結果を記録する（内部呼び出し用）。"""
    decision = AIDecision(
        user_id=request.user_id,
        query=request.query,
        action=request.action,
        confidence=request.confidence,
        reason=request.reason,
        primary_provider=request.primary_provider,
        primary_action=request.primary_action,
        primary_confidence=request.primary_confidence,
        secondary_provider=request.secondary_provider,
        secondary_action=request.secondary_action,
        secondary_confidence=request.secondary_confidence,
        agreed=request.agreed,
        rag_context_json=request.rag_context_json,
        prompt_version=request.prompt_version,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return AIDecisionResponse.model_validate(decision)
