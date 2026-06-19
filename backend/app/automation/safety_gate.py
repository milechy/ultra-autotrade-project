# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/automation/safety_gate.py
"""経路非依存の HARD_STOP 安全ゲート（v4 完全おまかせ自動運用 Phase 0 / スライス0-E1）。

`process_pending_knowledge`（CEX 経路）にインライン埋め込みされている HARD_STOP 判定
（rule engine / StressController / MacroSafeMode / CompoundRiskAssessor）と同一の判定を、
**副作用なしの純関数**として提供する。これにより Aave 自動執行経路（0-E2）からも
同じ安全判定を呼べるようにする。

設計方針（2026-06-19 ユーザー確定: 新関数追加・低リスク）:
- 本モジュールは workflow.py の既存インラインコードを **変更しない**（CEX 経路リグレッション回避）。
  同一ロジックを忠実にミラーする。安全判定の真実源統合（インライン置換）は将来の別 PR で行う。
- knowledge status 更新 / Slack 通知 / WorkflowRunResult 生成などの副作用は **呼び出し側**に残す。
  本関数は「止めるべきか・理由・どのチェックか」だけを返す。
- fail-closed / fail-open のセマンティクスは CEX 経路と一致させる:
  - MacroSafeMode 評価失敗 → fail-closed（blocked=True）
  - CompoundRiskAssessor 失敗 → fail-open（継続）
  - StressController 失敗 → skip（継続）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HardStopResult:
    """HARD_STOP 判定結果（副作用なし）。

    Attributes:
        blocked: True なら取引を止めるべき（全アイテム HOLD）。
        reason: 機械可読な理由（rule engine の reason / stress reason / macro reason 等）。
        source: どのチェックが発火したか
            ("rule_engine" | "stress" | "macro" | "compound_risk" | "")。
        stress_stage: StressController 発火時の stage（withdraw plan 生成に使う）。0 = 非該当。
    """

    blocked: bool
    reason: str = ""
    source: str = ""
    stress_stage: int = 0


def evaluate_hard_stop(
    monitoring_service: object | None,
    hf: Optional[Decimal],
    *,
    daily_traded_usd: Optional[Decimal] = None,
    total_assets_usd: Optional[Decimal] = None,
    run_compound_risk: bool = True,
) -> HardStopResult:
    """HARD_STOP 安全判定を順に評価し、最初に発火したものを返す（副作用なし）。

    評価順は CEX 経路（process_pending_knowledge）と同一:
    1. rule engine（HF<1.6 / daily limit / emergency stop / oracle / reserve）
    2. StressController（高ボラ SAFE_MODE / HARD_STOP）
    3. MacroSafeMode（FOMC/CPI 等イベント窓・評価失敗は fail-closed）
    4. CompoundRiskAssessor（複合リスク避難・失敗は fail-open）

    Args:
        monitoring_service: MonitoringService（None なら rule engine は通過扱い）。
        hf: 現在の Health Factor（StressController に渡す。None なら 999 扱い）。
        daily_traded_usd / total_assets_usd: rule engine の daily limit 判定に使う（任意）。
        run_compound_risk: False で CompoundRiskAssessor をスキップ（テスト/軽量呼出用）。

    Returns:
        HardStopResult。blocked=True なら呼び出し側で HOLD 処理を行う。
    """
    # 1. rule engine（HF / daily / emergency / oracle / reserve）
    from app.automation.workflow import check_rule_engine  # noqa: PLC0415

    can_trade, rule_reason = check_rule_engine(
        monitoring_service,  # type: ignore[arg-type]
        daily_traded_usd=daily_traded_usd,
        total_assets_usd=total_assets_usd,
    )
    if not can_trade:
        logger.info("safety_gate: rule engine blocked (%s)", rule_reason)
        return HardStopResult(blocked=True, reason=rule_reason, source="rule_engine")

    # 2. StressController（高ボラ HOLD）。失敗時は skip して継続（CEX 経路と同一）。
    if monitoring_service is not None:
        try:
            from app.aave.schemas import AaveOperationMode  # noqa: PLC0415
            from app.automation.stress_controller import (  # noqa: PLC0415
                MarketStressData,
                StressController,
            )

            last_pct = getattr(monitoring_service, "_last_price_change_24h", None)
            if last_pct is not None:
                # _last_price_change_24h はパーセント値（例: -15.0）。StressController は
                # 小数形式（例: -0.15）を期待するため /100 で変換する（CEX 経路と同一）。
                stress_data = MarketStressData(
                    price_change_24h=Decimal(str(last_pct)) / Decimal("100"),
                    health_factor=hf if hf is not None else Decimal("999"),
                    manual_stop=not monitoring_service.is_trading_allowed(),  # type: ignore[attr-defined]
                    current_mode=AaveOperationMode.NORMAL,
                    current_stage=0,
                )
                stress_eval = StressController().evaluate(stress_data)
                if stress_eval.mode in (
                    AaveOperationMode.SAFE_MODE,
                    AaveOperationMode.HARD_STOP,
                ):
                    logger.warning(
                        "safety_gate: StressController triggered %s (stage=%d, reason=%s)",
                        stress_eval.mode.value,
                        stress_eval.stage,
                        stress_eval.reason,
                    )
                    return HardStopResult(
                        blocked=True,
                        reason=stress_eval.reason,
                        source="stress",
                        stress_stage=stress_eval.stage,
                    )
        except Exception as _stress_exc:  # noqa: BLE001
            logger.warning("safety_gate: StressController check failed (skipping): %s", _stress_exc)

    # 3. MacroSafeMode（評価失敗は fail-closed = blocked）。
    try:
        from app.automation.macro_safe_mode import MacroSafeMode  # noqa: PLC0415

        macro_status = MacroSafeMode().is_safe_mode_active()
        if macro_status.active:
            logger.info("safety_gate: MacroSafeMode active (%s)", macro_status.reason)
            return HardStopResult(blocked=True, reason=macro_status.reason, source="macro")
    except Exception as _macro_exc:
        logger.error(
            "safety_gate: MacroSafeMode evaluation FAILED - fail-closed, blocking: %s", _macro_exc
        )
        return HardStopResult(blocked=True, reason="macro_safe_mode_eval_failed", source="macro")

    # 4. CompoundRiskAssessor（失敗は fail-open = 継続）。
    if run_compound_risk:
        try:
            import asyncio as _asyncio  # noqa: PLC0415
            import concurrent.futures  # noqa: PLC0415

            from app.protocols.risk.compound_risk import CompoundRiskAssessor  # noqa: PLC0415

            _assessor = CompoundRiskAssessor()
            # sync から async assess() を呼ぶ: ThreadPoolExecutor で独立ループを生成（CEX 経路と同一）。
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
                _risk = _pool.submit(_asyncio.run, _assessor.assess()).result(timeout=10)

            logger.info(
                "safety_gate: CompoundRiskAssessor overall_risk=%s, score=%s, should_evacuate=%s",
                _risk.overall_risk.value,
                _risk.risk_score,
                _risk.should_evacuate,
            )
            if _risk.should_evacuate:
                return HardStopResult(
                    blocked=True,
                    reason=_risk.evacuation_reason or "compound_risk_evacuate",
                    source="compound_risk",
                )
        except Exception as _cra_exc:  # noqa: BLE001
            logger.warning(
                "safety_gate: CompoundRiskAssessor check failed (fail-open, continuing): %s",
                _cra_exc,
            )

    return HardStopResult(blocked=False)
