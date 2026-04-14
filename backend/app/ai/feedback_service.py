# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/ai/feedback_service.py
"""AI判定フィードバックサービス (Layer 4)。

責務:
- フィードバックの記録（DB への永続化）
- JudgmentLogger の outcome 同期更新（fail-open: JSONL 更新失敗でも DB 記録は成功）
- 統計計算
- HOWL レビューからの自動フィードバック一括登録
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.judgment_log import get_judgment_logger
from app.ai.models import AIDecision

from .feedback_models import AIFeedback, AIFeedbackCreate, AIFeedbackStats

logger = logging.getLogger(__name__)


class FeedbackService:
    """AI判定フィードバックサービス。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_feedback(
        self,
        data: AIFeedbackCreate,
        recorded_by: str,
        feedback_source: str = "manual",
    ) -> AIFeedback:
        """フィードバックを記録し、JudgmentLogger の outcome も同期更新する。

        JudgmentLogger 側の更新は best-effort (fail-open)。
        JSONL 更新が失敗しても DB 側の記録はそのまま返す。
        """
        feedback = AIFeedback(
            ai_decision_id=data.ai_decision_id,
            is_correct=data.is_correct,
            actual_outcome=data.actual_outcome,
            pnl_usd=data.pnl_usd,
            expected_apy=data.expected_apy,
            actual_apy=data.actual_apy,
            improvement_suggestion=data.improvement_suggestion,
            feedback_source=feedback_source,
            recorded_by=recorded_by,
        )
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)

        # JudgmentLogger の JSONL を best-effort で更新（fail-open）
        if data.is_correct is not None:
            try:
                self._try_update_judgment_log(data)
            except Exception as exc:  # noqa: BLE001
                logger.warning("JudgmentLogger sync update skipped: %s", exc)

        return feedback

    def get_feedback_by_decision(self, ai_decision_id: int) -> list[AIFeedback]:
        """指定された AI 判定 ID に対するフィードバック一覧を返す。"""
        stmt = (
            select(AIFeedback)
            .where(AIFeedback.ai_decision_id == ai_decision_id)
            .order_by(AIFeedback.recorded_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_stats(self, days: int = 30) -> AIFeedbackStats:
        """期間指定のフィードバック統計を返す。

        Args:
            days: 集計対象日数（0 = 全期間）
        """
        stmt = select(AIFeedback)
        if days > 0:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            stmt = stmt.where(AIFeedback.recorded_at >= since)

        feedbacks = list(self.db.scalars(stmt).all())
        total = len(feedbacks)
        correct = sum(1 for f in feedbacks if f.is_correct is True)
        incorrect = sum(1 for f in feedbacks if f.is_correct is False)
        decided = correct + incorrect
        accuracy_rate: Optional[float] = (correct / decided) if decided > 0 else None

        # avg_pnl_usd — pnl_usd が設定されているものだけ平均
        pnl_values = [f.pnl_usd for f in feedbacks if f.pnl_usd is not None]
        avg_pnl: Optional[str] = None
        if pnl_values:
            avg = sum(Decimal(str(v)) for v in pnl_values) / Decimal(len(pnl_values))
            avg_pnl = str(avg.quantize(Decimal("0.000001")))

        # feedback_by_source カウント
        source_counts: dict[str, int] = {}
        for f in feedbacks:
            source_counts[f.feedback_source] = source_counts.get(f.feedback_source, 0) + 1

        return AIFeedbackStats(
            total_feedbacks=total,
            correct_count=correct,
            incorrect_count=incorrect,
            accuracy_rate=accuracy_rate,
            avg_pnl_usd=avg_pnl,
            feedback_by_source=source_counts,
        )

    def bulk_auto_feedback(
        self,
        feedbacks: list[AIFeedbackCreate],
        source: str = "auto_howl",
    ) -> list[AIFeedback]:
        """HOWL レビューなどからの自動フィードバックを一括登録する。

        Args:
            feedbacks: フィードバックリスト
            source: フィードバックソース（デフォルト: "auto_howl"）
        """
        if not feedbacks:
            return []

        results: list[AIFeedback] = []
        for data in feedbacks:
            try:
                fb = self.record_feedback(data, recorded_by="auto", feedback_source=source)
                results.append(fb)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "bulk_auto_feedback: failed to record feedback for decision_id=%d: %s",
                    data.ai_decision_id,
                    exc,
                )
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _try_update_judgment_log(self, data: AIFeedbackCreate) -> None:
        """JudgmentLogger の JSONL outcome を best-effort で更新する。

        ai_decision_id に対応する AIDecision の created_at を timestamp として使用。
        JSONL はタイムスタンプで検索されるため、ミスマッチ時は無害にスキップ。
        """
        try:
            decision = self.db.scalars(
                select(AIDecision).where(AIDecision.id == data.ai_decision_id)
            ).first()
            if decision is None:
                return

            jlog = get_judgment_logger()
            coro = jlog.update_outcome(
                timestamp=decision.created_at,
                was_correct=bool(data.is_correct),
                apy_change=str(data.actual_apy) if data.actual_apy is not None else None,
            )
            # イベントループが実行中なら fire-and-forget タスクとして登録
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(coro)
            except RuntimeError:
                # イベントループなし（テスト等の同期コンテキスト）→ コルーチンを閉じる
                coro.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "JudgmentLogger outcome update skipped (non-critical): decision_id=%d, err=%s",
                data.ai_decision_id,
                exc,
            )
