# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/ai/outcome_labeling_service.py
"""Layer 2 outcome label 収集バッチ (OutcomeLabelingService)。

AI判定から 24h / 48h 後に portfolio_snapshots を後付け join して
ai_decision_outcomes に realized_yield_delta / hf_min_after /
regret_score / is_positive_example を INSERT する。

設計原則:
  - fail-open: 個別判定の計算失敗は skip して次へ進む
  - idempotent: (decision_id, horizon_hours) が既存ならスキップ
  - multi-asset/protocol 対応: asset / protocol 列を最初から持つ
  - DB 操作は同期 Session (既存パターン準拠)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import AIDecision, AiDecisionFeature, AiDecisionOutcome
from app.portfolio.models import PortfolioSnapshot

logger = logging.getLogger(__name__)

# 判定後に outcome を計算するホライゾン (時間)
OUTCOME_HORIZONS: list[int] = [24, 48]

# 基準スナップショットの検索ウィンドウ（分）：判定時刻の ±この分以内
SNAPSHOT_WINDOW_MINUTES: int = 60

# 一度に処理する最大判定数 / ホライゾン
MAX_DECISIONS_PER_BATCH: int = 100

# regret_score の分母スケール: この APY % 差 = regret 1.0
REGRET_SCALE_PCT: float = 10.0

# is_positive_example の閾値 (annualized %)
POSITIVE_THRESHOLD_PCT: float = 0.5
NEGATIVE_THRESHOLD_PCT: float = 2.0


# ---------------------------------------------------------------------------
# 結果データクラス
# ---------------------------------------------------------------------------


@dataclass
class HorizonResult:
    """1 ホライゾン分の処理結果。"""

    horizon_hours: int = 0
    processed: int = 0
    skipped_existing: int = 0
    skipped_no_snapshot: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class OutcomeLabelingResult:
    """バッチ全体の結果。"""

    horizons: list[HorizonResult] = field(default_factory=list)
    completed_at: Optional[datetime] = None

    @property
    def total_processed(self) -> int:
        return sum(h.processed for h in self.horizons)

    @property
    def total_errors(self) -> int:
        return sum(len(h.errors) for h in self.horizons)


# ---------------------------------------------------------------------------
# OutcomeLabelingService
# ---------------------------------------------------------------------------


class OutcomeLabelingService:
    """AI判定の outcome label 収集バッチ。

    Args:
        db: SQLAlchemy Session (呼び出し元が管理)
        asset: 対象資産識別子 (将来の複数資産対応: デフォルト "USDC")
        protocol: 対象プロトコル識別子 (デフォルト "aave_v3")
    """

    def __init__(
        self,
        db: Session,
        *,
        asset: str = "USDC",
        protocol: str = "aave_v3",
    ) -> None:
        self.db = db
        self.asset = asset
        self.protocol = protocol

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_batch(self) -> OutcomeLabelingResult:
        """24h / 48h の各ホライゾンで outcome label を INSERT する。"""
        result = OutcomeLabelingResult()
        for horizon in OUTCOME_HORIZONS:
            try:
                hr = self._process_horizon(horizon)
                result.horizons.append(hr)
                logger.info(
                    "outcome_labeling horizon=%dh: processed=%d skipped_existing=%d"
                    " skipped_no_snap=%d errors=%d",
                    horizon,
                    hr.processed,
                    hr.skipped_existing,
                    hr.skipped_no_snapshot,
                    len(hr.errors),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("outcome_labeling horizon=%dh failed: %s", horizon, exc)
                result.horizons.append(
                    HorizonResult(horizon_hours=horizon, errors=[str(exc)])
                )
        result.completed_at = datetime.now(timezone.utc)
        return result

    # ------------------------------------------------------------------
    # Private: per-horizon processing
    # ------------------------------------------------------------------

    def _process_horizon(self, horizon_hours: int) -> HorizonResult:
        hr = HorizonResult(horizon_hours=horizon_hours)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=horizon_hours)

        # ホライゾン経過済みかつ未 INSERT の AIDecision を取得
        existing_ids_stmt = select(AiDecisionOutcome.decision_id).where(
            AiDecisionOutcome.horizon_hours == horizon_hours
        )
        stmt = (
            select(AIDecision)
            .where(
                AIDecision.created_at <= cutoff,
                AIDecision.id.not_in(existing_ids_stmt),
            )
            .order_by(AIDecision.created_at.asc())
            .limit(MAX_DECISIONS_PER_BATCH)
        )
        decisions: list[AIDecision] = list(self.db.scalars(stmt).all())

        for decision in decisions:
            try:
                outcome = self._compute_outcome(decision, horizon_hours)
                if outcome is None:
                    hr.skipped_no_snapshot += 1
                    continue
                self.db.add(outcome)
                hr.processed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "outcome_labeling: decision_id=%d horizon=%dh error: %s",
                    decision.id,
                    horizon_hours,
                    exc,
                )
                hr.errors.append(f"decision_id={decision.id}: {exc}")

        if hr.processed > 0:
            try:
                self.db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.error("outcome_labeling commit failed: %s", exc)
                self.db.rollback()
                raise

        return hr

    # ------------------------------------------------------------------
    # Private: compute metrics for one decision
    # ------------------------------------------------------------------

    def _compute_outcome(
        self, decision: AIDecision, horizon_hours: int
    ) -> Optional[AiDecisionOutcome]:
        """1 判定 × 1 ホライゾンの outcome 行を計算して返す。スナップショット不足時は None。"""
        t_decision = decision.created_at
        t_horizon = t_decision + timedelta(hours=horizon_hours)

        supply_before = self._get_total_supply_near(t_decision)
        supply_after = self._get_total_supply_near(t_horizon)

        if supply_before is None or supply_after is None:
            return None

        # HF: ホライゾン期間中の最小値
        hf_min = self._get_hf_min_in_window(t_decision, t_horizon)

        # realized_yield_delta: 年率換算 (%)
        realized_yield = _annualized_yield_pct(supply_before, supply_after, horizon_hours)

        # action 正規化
        action = (decision.action or "").upper()

        regret = _compute_regret_score(action, realized_yield)
        is_positive = _compute_is_positive_example(action, realized_yield)

        return AiDecisionOutcome(
            decision_id=decision.id,
            horizon_hours=horizon_hours,
            realized_yield_delta=Decimal(str(round(realized_yield, 8))),
            gas_cost_usd=None,  # オンチェーン tx データは別フェーズで追加
            hf_min_after=Decimal(str(round(hf_min, 4))) if hf_min is not None else None,
            partner_approved=None,
            regret_score=Decimal(str(round(regret, 4))),
            is_positive_example=is_positive,
            asset=self.asset,
            protocol=self.protocol,
        )

    # ------------------------------------------------------------------
    # Private: snapshot aggregation helpers
    # ------------------------------------------------------------------

    def _get_total_supply_near(self, target_time: datetime) -> Optional[Decimal]:
        """target_time の ±SNAPSHOT_WINDOW_MINUTES 以内の最近傍スナップショットで
        全ユーザーの total_supply_usd 合計を返す。"""
        window = timedelta(minutes=SNAPSHOT_WINDOW_MINUTES)
        lo = target_time - window
        hi = target_time + window

        # 最近傍の recorded_at 時刻を 1 つ選ぶ (ABS 距離最小)
        # SQLite には ABS(epoch diff) で近傍選択、PostgreSQL も同様に動く
        nearest_time_stmt = (
            select(PortfolioSnapshot.recorded_at)
            .where(
                PortfolioSnapshot.recorded_at >= lo,
                PortfolioSnapshot.recorded_at <= hi,
            )
            .order_by(
                func.abs(
                    func.extract("epoch", PortfolioSnapshot.recorded_at)
                    - func.extract("epoch", target_time)
                )
            )
            .limit(1)
        )
        nearest_time = self.db.scalar(nearest_time_stmt)
        if nearest_time is None:
            return None

        total = self.db.scalar(
            select(func.sum(PortfolioSnapshot.total_supply_usd)).where(
                PortfolioSnapshot.recorded_at == nearest_time
            )
        )
        return Decimal(str(total)) if total is not None else None

    def _get_hf_min_in_window(
        self, t_start: datetime, t_end: datetime
    ) -> Optional[float]:
        """[t_start, t_end] 区間の health_factor 最小値 (全ユーザー min)。"""
        result = self.db.scalar(
            select(func.min(PortfolioSnapshot.health_factor)).where(
                PortfolioSnapshot.recorded_at >= t_start,
                PortfolioSnapshot.recorded_at <= t_end,
                PortfolioSnapshot.health_factor.isnot(None),
            )
        )
        if result is None:
            return None
        return float(result)


# ---------------------------------------------------------------------------
# Pure computation helpers (no DB access, easy to test in isolation)
# ---------------------------------------------------------------------------


def _annualized_yield_pct(
    supply_before: Decimal,
    supply_after: Decimal,
    horizon_hours: int,
) -> float:
    """スナップショット供給量変化から年率換算リターン (%) を計算する。

    formula: (supply_after / supply_before - 1) * (8760 / horizon_hours) * 100
    supply_before が 0 または負の場合は 0.0 を返す (ゼロ除算防止)。
    """
    if supply_before <= Decimal("0"):
        return 0.0
    raw_return = float((supply_after - supply_before) / supply_before)
    annualized = raw_return * (8760 / horizon_hours) * 100
    # 外れ値を ±500% でクランプ (スナップショット異常値対策)
    return max(-500.0, min(500.0, annualized))


def _compute_regret_score(action: str, realized_yield_annualized_pct: float) -> float:
    """regret_score ∈ [0, 1] を計算する。

    高いほど「惜しい判定」（機会損失 or 悪タイミング）。

    - HOLD: 正のリターンを見逃した分だけ regret が上がる
    - SUPPLY/BUY: 負のリターンが続いた分だけ regret が上がる
    - SELL/WITHDRAW: 正のリターンを逃した分だけ regret が上がる
    """
    y = realized_yield_annualized_pct
    if action in ("SUPPLY", "BUY"):
        missed = max(0.0, -y)
    elif action in ("SELL", "WITHDRAW"):
        missed = max(0.0, y)
    else:  # HOLD
        missed = max(0.0, y)

    return min(1.0, missed / REGRET_SCALE_PCT)


def _compute_is_positive_example(
    action: str,
    realized_yield_annualized_pct: float,
) -> Optional[bool]:
    """is_positive_example を決定する。

    Returns:
        True  — 良い判定 (正例として学習に使える)
        False — 悪い判定 (負例として学習に使える)
        None  — 判断保留 (閾値未達)
    """
    y = realized_yield_annualized_pct
    if action in ("SUPPLY", "BUY"):
        if y > POSITIVE_THRESHOLD_PCT:
            return True
        if y < -POSITIVE_THRESHOLD_PCT:
            return False
    elif action == "HOLD":
        if y < -POSITIVE_THRESHOLD_PCT:
            return True  # HOLD 正解: リターンがマイナスだった
        if y > NEGATIVE_THRESHOLD_PCT:
            return False  # HOLD 失敗: 大きな機会損失
    elif action in ("SELL", "WITHDRAW"):
        if y < -POSITIVE_THRESHOLD_PCT:
            return True  # SELL 正解: 売ってよかった
        if y > POSITIVE_THRESHOLD_PCT:
            return False  # SELL 失敗: 売らなければよかった
    return None
