# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_consensus_shadow_wiring.py
"""4 軸コンセンサス Shadow 書込配線のテスト (EPIC-1 1-7 / PR-3)。

対象: ai_judgment_scheduler._write_shadow_consensus / save_ai_decision_features。

検証観点:
- shadow 有効 (mode="shadow") で deterministic_breakdown がセットされる
- mode="off" で None のまま (Shadow skip)
- evaluate_4axis_consensus が例外を投げても判定保存が継続する (fail-open)
- market_ctx が dict (degraded) のとき skip される
- Shadow = 記録のみで既存の保存項目は不変
"""

import os
import tempfile
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-consensus-shadow-wiring")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")

from app.ai.agents import AgentSignal, Bias, MultiAgentContext  # noqa: E402
from app.ai.models import AIDecision, AiDecisionFeature  # noqa: E402
from app.ai.schemas import (  # noqa: E402
    CrossValidationResult,
    LLMDecision,
    LLMProvider,
    TradeAction,
)
from app.automation.aave_data_fetcher import AaveMarketData  # noqa: E402
from app.automation.ai_judgment_scheduler import (  # noqa: E402
    _write_shadow_consensus,
    save_ai_decision_features,
)
from app.data_feeds.context import MarketContext  # noqa: E402
from app.database import Base  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


def _make_decision(session) -> AIDecision:
    d = AIDecision(
        query="test",
        action="HOLD",
        confidence=60,
        primary_provider="claude",
        primary_action="HOLD",
        primary_confidence=60,
        agreed=True,
    )
    session.add(d)
    session.flush()
    return d


def _make_feature(session, decision: AIDecision) -> AiDecisionFeature:
    feature = AiDecisionFeature(
        ai_decision_id=decision.id,
        agent_signals=None,
        raw_features={"utilization_rate": "45.5"},
        judge_action="HOLD",
        confidence=60,
        cross_verify=True,
        embedding=None,
    )
    session.add(feature)
    session.flush()
    return feature


def _make_result() -> CrossValidationResult:
    primary = LLMDecision(
        provider=LLMProvider.CLAUDE,
        action=TradeAction.HOLD,
        confidence=80,
        reason="テスト判定",
    )
    return CrossValidationResult(
        primary=primary,
        secondary=None,
        agreed=True,
        final_action=TradeAction.HOLD,
        final_confidence=80,
        final_reason="テスト判定理由",
    )


def _make_aave_data() -> AaveMarketData:
    return {
        "utilization_rate": Decimal("45.5"),
        "supply_apy": Decimal("3.2"),
        "borrow_apy": Decimal("5.1"),
        "health_factor": Decimal("2.1"),
    }


def _make_agent_ctx() -> MultiAgentContext:
    """全軸 BULLISH conf=100 の MultiAgentContext (score=+1.0 → BUY を期待)。"""

    def _sig(name: str) -> AgentSignal:
        return AgentSignal(
            agent_name=name,
            bias=Bias.BULLISH,
            confidence=100,
            reasoning="test",
        )

    return MultiAgentContext(
        indicator_signal=_sig("Indicator Agent"),
        pattern_signal=_sig("Pattern Agent"),
        risk_signal=_sig("Risk Agent"),
        macro_signal=_sig("Macro Agent"),
    )


def _settings(mode: str) -> SimpleNamespace:
    return SimpleNamespace(
        consensus_4axis_mode=mode,
        consensus_score_threshold=Decimal("0.40"),
        consensus_conf_threshold=65,
    )


# ---------------------------------------------------------------------------
# _write_shadow_consensus 直接テスト
# ---------------------------------------------------------------------------


def test_shadow_mode_sets_deterministic_breakdown(db_session):
    """mode="shadow" で deterministic_breakdown が verdict の dict でセットされる。"""
    decision = _make_decision(db_session)
    feature = _make_feature(db_session, decision)

    with (
        patch("app.ai.config.get_ai_settings", return_value=_settings("shadow")),
        patch("app.ai.agents.run_all_agents", return_value=_make_agent_ctx()),
    ):
        _write_shadow_consensus(db_session, feature, MarketContext())

    row = db_session.query(AiDecisionFeature).filter_by(ai_decision_id=decision.id).one()
    assert row.deterministic_breakdown is not None
    # 全軸 BULLISH conf=100 → action=BUY, agreeing_count=4
    assert row.deterministic_breakdown["action"] == "BUY"
    assert row.deterministic_breakdown["agreeing_count"] == 4
    assert "per_agent_contribution" in row.deterministic_breakdown


def test_off_mode_leaves_breakdown_none(db_session):
    """mode="off" のとき deterministic_breakdown は None のまま (Shadow skip)。"""
    decision = _make_decision(db_session)
    feature = _make_feature(db_session, decision)

    with (
        patch("app.ai.config.get_ai_settings", return_value=_settings("off")),
        patch("app.ai.agents.run_all_agents") as mock_run,
    ):
        _write_shadow_consensus(db_session, feature, MarketContext())
        # off では run_all_agents すら呼ばれない
        mock_run.assert_not_called()

    row = db_session.query(AiDecisionFeature).filter_by(ai_decision_id=decision.id).one()
    assert row.deterministic_breakdown is None


def test_degraded_dict_market_ctx_is_skipped(db_session):
    """market_ctx が dict (degraded) のとき Shadow は skip され breakdown は None。"""
    decision = _make_decision(db_session)
    feature = _make_feature(db_session, decision)
    degraded = {"degraded": True, "reason": "feed down"}

    with (
        patch("app.ai.config.get_ai_settings", return_value=_settings("shadow")),
        patch("app.ai.agents.run_all_agents") as mock_run,
    ):
        _write_shadow_consensus(db_session, feature, degraded)
        mock_run.assert_not_called()

    row = db_session.query(AiDecisionFeature).filter_by(ai_decision_id=decision.id).one()
    assert row.deterministic_breakdown is None


def test_evaluate_exception_is_fail_open(db_session):
    """evaluate_4axis_consensus が例外を投げても _write_shadow_consensus は例外を伝播しない。"""
    decision = _make_decision(db_session)
    feature = _make_feature(db_session, decision)

    with (
        patch("app.ai.config.get_ai_settings", return_value=_settings("shadow")),
        patch(
            "app.ai.agents.run_all_agents",
            side_effect=RuntimeError("agents boom"),
        ),
    ):
        # 例外を握り潰す (fail-open) — raise しないこと
        _write_shadow_consensus(db_session, feature, MarketContext())

    row = db_session.query(AiDecisionFeature).filter_by(ai_decision_id=decision.id).one()
    assert row.deterministic_breakdown is None


# ---------------------------------------------------------------------------
# save_ai_decision_features 経由の統合テスト (Shadow = 記録のみ)
# ---------------------------------------------------------------------------


def test_save_features_continues_when_shadow_raises(db_session):
    """Shadow 算出が例外を投げても save_ai_decision_features は feature を保存し続ける (fail-open)。"""
    decision = _make_decision(db_session)
    result = _make_result()

    with (
        patch("app.ai.config.get_ai_settings", return_value=_settings("shadow")),
        patch(
            "app.ai.agents.run_all_agents",
            side_effect=RuntimeError("agents boom"),
        ),
    ):
        save_ai_decision_features(db_session, decision, result, _make_aave_data(), MarketContext())

    # feature 自体は保存され、Shadow 失敗で deterministic_breakdown は None
    row = db_session.query(AiDecisionFeature).filter_by(ai_decision_id=decision.id).one()
    assert row.judge_action == "HOLD"
    assert row.confidence == 80
    assert row.deterministic_breakdown is None


def test_save_features_records_breakdown_when_shadow_on(db_session):
    """save_ai_decision_features 経由でも shadow 有効なら deterministic_breakdown が記録される。"""
    decision = _make_decision(db_session)
    result = _make_result()

    with (
        patch("app.ai.config.get_ai_settings", return_value=_settings("shadow")),
        patch("app.ai.agents.run_all_agents", return_value=_make_agent_ctx()),
    ):
        save_ai_decision_features(db_session, decision, result, _make_aave_data(), MarketContext())

    row = db_session.query(AiDecisionFeature).filter_by(ai_decision_id=decision.id).one()
    # 既存の保存項目は不変
    assert row.judge_action == "HOLD"
    assert row.cross_verify is True
    # Shadow 記録が追加される
    assert row.deterministic_breakdown is not None
    assert row.deterministic_breakdown["action"] == "BUY"
