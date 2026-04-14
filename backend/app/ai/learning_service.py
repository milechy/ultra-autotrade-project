# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/ai/learning_service.py
"""AI継続学習サービス (Layer 4)。

6時間ごとの学習サイクルで以下を実行する:
  1. 未評価判定の自動フィードバック生成（HOWLロジック経由）
  2. フィードバック統計の集計
  3. CognitiveState の win_rate 更新（アクション別正答率含む）
  4. 学習レポートのログ出力

設計原則:
  - fail-open: 各ステップのエラーが他ステップ・本番AI判定に伝播しない
  - 既存 FeedbackService / JudgmentLogger / evaluate_judgment() を最大活用
  - DB 操作は同期 Session（既存パターン準拠）、async メソッドでラップ
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.feedback_models import AIFeedback, AIFeedbackCreate, AIFeedbackStats
from app.ai.feedback_service import FeedbackService
from app.ai.judgment_log import JudgmentRecord, get_judgment_logger
from app.ai.models import AIDecision
from app.automation.howl_review import evaluate_judgment

logger = logging.getLogger(__name__)

# 自動フィードバック生成の対象期間（時間）
AUTO_FEEDBACK_WINDOW_HOURS = 48
# 一度に処理する最大件数
MAX_DECISIONS_PER_CYCLE = 50


# ============================================================
# 結果データクラス
# ============================================================
@dataclass
class AutoFeedbackResult:
    """自動フィードバック生成の結果。"""

    evaluated_count: int = 0
    feedback_created: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class CognitiveUpdate:
    """CognitiveState 更新の結果。"""

    previous_win_rate: float = 0.0
    new_win_rate: float = 0.0
    action_accuracy: dict[str, float] = field(default_factory=dict)
    updated: bool = False


@dataclass
class LearningCycleResult:
    """学習サイクル全体の結果。"""

    auto_feedback: Optional[AutoFeedbackResult] = None
    auto_feedback_error: Optional[str] = None
    stats: Optional[AIFeedbackStats] = None
    cognitive_update: Optional[CognitiveUpdate] = None
    completed_at: Optional[datetime] = None


# ============================================================
# AILearningService
# ============================================================
class AILearningService:
    """AI判定の継続学習パイプライン。

    FeedbackService、JudgmentLogger、HOWL evaluate_judgment() を組み合わせて
    6時間ごとの学習サイクルを実行する。
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.feedback_service = FeedbackService(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_learning_cycle(self) -> LearningCycleResult:
        """学習サイクルの全ステップを順次実行。各ステップは独立してfail-open。"""
        results = LearningCycleResult()

        # Step 1: 未評価判定の自動フィードバック生成
        try:
            results.auto_feedback = await self._generate_auto_feedback()
            logger.info(
                "Step 1 done: evaluated=%d, created=%d, skipped=%d",
                results.auto_feedback.evaluated_count,
                results.auto_feedback.feedback_created,
                results.auto_feedback.skipped_count,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Step 1 (auto feedback) failed: %s", exc)
            results.auto_feedback_error = str(exc)

        # Step 2: フィードバック統計集計
        try:
            results.stats = self.feedback_service.get_stats(days=30)
            logger.debug(
                "Step 2 done: total=%d, correct=%d, accuracy=%s",
                results.stats.total_feedbacks,
                results.stats.correct_count,
                f"{results.stats.accuracy_rate:.1%}" if results.stats.accuracy_rate else "N/A",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Step 2 (stats aggregation) failed: %s", exc)

        # Step 3: CognitiveState 更新
        try:
            results.cognitive_update = await self._update_cognitive_state(results.stats)
            if results.cognitive_update.updated:
                logger.info(
                    "Step 3 done: win_rate %.2f → %.2f",
                    results.cognitive_update.previous_win_rate,
                    results.cognitive_update.new_win_rate,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Step 3 (cognitive state update) failed: %s", exc)

        # Step 4: 学習レポート生成（ログ出力）
        try:
            await self._generate_learning_report(results)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Step 4 (learning report) failed: %s", exc)

        results.completed_at = datetime.now(timezone.utc)
        return results

    # ------------------------------------------------------------------
    # Private: Step 1 — 自動フィードバック生成
    # ------------------------------------------------------------------

    async def _generate_auto_feedback(self) -> AutoFeedbackResult:
        """直近 48h の未評価判定を取得し HOWLロジックで評価してフィードバック登録。"""
        result = AutoFeedbackResult()

        # 1. 直近 48h かつ AIFeedback 未登録の AIDecision を取得
        cutoff = datetime.now(timezone.utc) - timedelta(hours=AUTO_FEEDBACK_WINDOW_HOURS)
        stmt = (
            select(AIDecision)
            .outerjoin(AIFeedback, AIDecision.id == AIFeedback.ai_decision_id)
            .where(AIFeedback.id.is_(None))
            .where(AIDecision.created_at >= cutoff)
            .order_by(AIDecision.created_at.desc())
            .limit(MAX_DECISIONS_PER_CYCLE)
        )
        unevaluated: list[AIDecision] = list(self.db.scalars(stmt).all())
        result.evaluated_count = len(unevaluated)

        if not unevaluated:
            return result

        # 2. 現在の地政学リスクスコアを取得（失敗時はデフォルト値）
        current_geo_risk = self._get_current_geo_risk()

        # 3. 各判定を evaluate_judgment() で評価
        feedbacks_to_create: list[AIFeedbackCreate] = []
        for decision in unevaluated:
            try:
                record = JudgmentRecord(
                    timestamp=decision.created_at,
                    action=decision.action,
                    confidence=decision.confidence,
                    reason=decision.reason,
                    primary_action=decision.primary_action,
                    secondary_action=decision.secondary_action,
                    agreed=decision.agreed,
                )
                review = evaluate_judgment(
                    record,
                    current_hf=None,  # HF は現時点では取得しない（後続フェーズで追加）
                    current_geo_risk=current_geo_risk,
                )

                if review.was_correct is None:
                    # 結論が出なかった（不確定）→ スキップ
                    result.skipped_count += 1
                    continue

                actual_outcome = "profit" if review.was_correct else "loss"
                feedbacks_to_create.append(
                    AIFeedbackCreate(
                        ai_decision_id=decision.id,
                        is_correct=review.was_correct,
                        actual_outcome=actual_outcome,
                        improvement_suggestion=(
                            review.reason_correct if not review.was_correct else None
                        ),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "evaluate_judgment failed for decision_id=%s: %s",
                    getattr(decision, "id", "?"),
                    exc,
                )
                result.errors.append(str(exc))

        # 4. 一括フィードバック登録（feedback_source="auto_howl"）
        if feedbacks_to_create:
            created = self.feedback_service.bulk_auto_feedback(feedbacks_to_create)
            result.feedback_created = len(created)

        return result

    def _get_current_geo_risk(self) -> int:
        """現在の地政学リスクスコアを取得する（fail-open: 失敗時は50を返す）。"""
        try:
            from app.data_feeds.geopolitical import get_cached_geo_risk  # noqa: PLC0415

            geo = get_cached_geo_risk()
            return geo.geo_risk_score
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_cached_geo_risk failed, using default: %s", exc)
            return 50  # デフォルト: 中リスク

    # ------------------------------------------------------------------
    # Private: Step 3 — CognitiveState 更新
    # ------------------------------------------------------------------

    async def _update_cognitive_state(
        self,
        stats: Optional[AIFeedbackStats],
    ) -> CognitiveUpdate:
        """フィードバック統計から CognitiveState の win_rate を更新する。"""
        update = CognitiveUpdate()

        if stats is None or stats.accuracy_rate is None:
            logger.debug("No stats or accuracy_rate; skipping CognitiveState update")
            return update

        jlog = get_judgment_logger()
        cognitive = jlog.get_cognitive_state()

        update.previous_win_rate = cognitive.win_rate or 0.0
        update.new_win_rate = stats.accuracy_rate

        # in-memory CognitiveState を直接更新
        # （get_cognitive_state() は内部 _cognitive を参照渡しで返す設計）
        cognitive.win_rate = stats.accuracy_rate

        # アクション別正答率を計算
        try:
            update.action_accuracy = self._compute_action_accuracy()
        except Exception as exc:  # noqa: BLE001
            logger.debug("action_accuracy computation failed (non-critical): %s", exc)

        update.updated = True
        return update

    def _compute_action_accuracy(self) -> dict[str, float]:
        """AIDecision と AIFeedback を結合してアクション別正答率を計算する。"""
        stmt = (
            select(AIDecision.action, AIFeedback.is_correct)
            .join(AIFeedback, AIDecision.id == AIFeedback.ai_decision_id)
            .where(AIFeedback.is_correct.is_not(None))
        )
        rows = list(self.db.execute(stmt).all())

        action_results: dict[str, list[bool]] = {}
        for action, is_correct in rows:
            if action not in action_results:
                action_results[action] = []
            action_results[action].append(bool(is_correct))

        return {action: sum(vals) / len(vals) for action, vals in action_results.items() if vals}

    # ------------------------------------------------------------------
    # Private: Step 4 — 学習レポート生成
    # ------------------------------------------------------------------

    async def _generate_learning_report(self, results: LearningCycleResult) -> None:
        """学習サイクルの結果をログに出力する（将来の Slack/DB 拡張ポイント）。"""
        auto_fb = results.auto_feedback
        stats = results.stats
        cog = results.cognitive_update

        lines = ["=== AI Learning Cycle Report ==="]

        if auto_fb:
            lines.append(
                f"  AutoFeedback: evaluated={auto_fb.evaluated_count}, "
                f"created={auto_fb.feedback_created}, "
                f"skipped={auto_fb.skipped_count}, "
                f"errors={len(auto_fb.errors)}"
            )
        elif results.auto_feedback_error:
            lines.append(f"  AutoFeedback: FAILED — {results.auto_feedback_error}")

        if stats:
            acc = f"{stats.accuracy_rate:.1%}" if stats.accuracy_rate else "N/A"
            lines.append(
                f"  Stats(30d): total={stats.total_feedbacks}, "
                f"correct={stats.correct_count}, "
                f"incorrect={stats.incorrect_count}, "
                f"accuracy={acc}"
            )

        if cog and cog.updated:
            lines.append(
                f"  CognitiveState: win_rate {cog.previous_win_rate:.2f} → {cog.new_win_rate:.2f}"
            )
            if cog.action_accuracy:
                acc_str = ", ".join(f"{k}={v:.2f}" for k, v in sorted(cog.action_accuracy.items()))
                lines.append(f"  ActionAccuracy: {acc_str}")

        logger.info("\n".join(lines))
