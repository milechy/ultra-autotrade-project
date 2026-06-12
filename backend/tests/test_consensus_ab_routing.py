# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_consensus_ab_routing.py
"""CONSENSUS_4AXIS_MODE="a_b" 50/50 A/B ルーティングのテスト (EPIC-1 1-11)。

対象:
- ai_judgment_scheduler._consensus_ab_bucket
- ai_judgment_scheduler.run_ai_judgment_job (a_b 分岐 / 不変性ガード)

検証観点:
A. bucket 安定性: _consensus_ab_bucket の偶奇判定・同一 id 再呼出・decisions_router 式との突合
B. 50/50 分布: id=1..1000 で new/legacy 各 500
C. mode != "a_b" 不変性: off/shadow/on で a_b ロジックを通らず元の result.final_action で routing
D. A/B ルーティング統合:
   - a_b + 偶数 id → LLM action で routing
   - a_b + 奇数 id → verdict action で routing（verdict != LLM action のケースで verdict 側が採用）
   - fail-open: deterministic_breakdown None → legacy フォールバック（例外で落ちない）
   - new バケット HOLD → proposals 作成なし

モックパッチ方針:
  get_ai_settings は run_ai_judgment_job 内でローカルインポート
  (``from app.ai.config import get_ai_settings``) しているため、
  正しいパッチターゲットは "app.ai.config.get_ai_settings" のみ。
  "app.automation.ai_judgment_scheduler.get_ai_settings" は存在しないため使わない。
"""

import os
import tempfile
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-consensus-ab-routing")
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
    _consensus_ab_bucket,
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


def _make_decision(session, action: str = "HOLD") -> AIDecision:
    d = AIDecision(
        query="test",
        action=action,
        confidence=60,
        primary_provider="claude",
        primary_action=action,
        primary_confidence=60,
        agreed=True,
    )
    session.add(d)
    session.flush()
    return d


def _make_result(
    action: TradeAction = TradeAction.HOLD, confidence: int = 80
) -> CrossValidationResult:
    primary = LLMDecision(
        provider=LLMProvider.CLAUDE,
        action=action,
        confidence=confidence,
        reason="テスト判定",
    )
    return CrossValidationResult(
        primary=primary,
        secondary=None,
        agreed=True,
        final_action=action,
        final_confidence=confidence,
        final_reason="テスト判定理由",
    )


def _make_aave_data() -> AaveMarketData:
    return {
        "utilization_rate": Decimal("45.5"),
        "supply_apy": Decimal("3.2"),
        "borrow_apy": Decimal("5.1"),
        "health_factor": Decimal("2.1"),
    }


def _make_agent_ctx_bullish() -> MultiAgentContext:
    """全軸 BULLISH conf=100 → verdict action=BUY を期待。"""

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


def _ensure_even_next_id(db_session) -> None:
    """db_session の次の AIDecision.id が偶数になるよう調整する。

    SQLite は autoincrement なので、現在の最大 id が奇数なら 1 件追加して偶数にする。
    """
    from sqlalchemy import func  # noqa: PLC0415

    from app.ai.models import AIDecision as _AD  # noqa: PLC0415

    max_id = db_session.scalar(func.max(_AD.id)) or 0
    if max_id % 2 == 0:
        # 次の id が奇数になるので、1 件追加して偶数→偶数+1(奇数) → さらに1件追加で偶数
        _dummy = _AD(
            query="dummy-even",
            action="HOLD",
            confidence=50,
            primary_provider="claude",
            primary_action="HOLD",
            primary_confidence=50,
            agreed=True,
        )
        db_session.add(_dummy)
        db_session.flush()


def _ensure_odd_next_id(db_session) -> None:
    """db_session の次の AIDecision.id が奇数になるよう調整する。"""
    from sqlalchemy import func  # noqa: PLC0415

    from app.ai.models import AIDecision as _AD  # noqa: PLC0415

    max_id = db_session.scalar(func.max(_AD.id)) or 0
    if max_id % 2 == 1:
        # 次の id が偶数になるので、1 件追加して奇数になるよう調整
        _dummy = _AD(
            query="dummy-odd",
            action="HOLD",
            confidence=50,
            primary_provider="claude",
            primary_action="HOLD",
            primary_confidence=50,
            agreed=True,
        )
        db_session.add(_dummy)
        db_session.flush()


# ---------------------------------------------------------------------------
# A. bucket 安定性テスト
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "decision_id,expected",
    [
        (0, "legacy"),
        (1, "new"),
        (2, "legacy"),
        (3, "new"),
    ],
)
def test_bucket_even_odd(decision_id: int, expected: str) -> None:
    """_consensus_ab_bucket: 偶数 → "legacy"、奇数 → "new"。"""
    assert _consensus_ab_bucket(decision_id) == expected


def test_bucket_stability_same_id() -> None:
    """同一 id を複数回呼び出しても同じバケットが返る（決定論的）。"""
    for decision_id in (0, 1, 42, 99, 1000):
        first = _consensus_ab_bucket(decision_id)
        for _ in range(10):
            assert _consensus_ab_bucket(decision_id) == first


@pytest.mark.parametrize(
    "decision_id",
    [0, 1, 2, 3, 7, 100, 999, 1000],
)
def test_bucket_matches_decisions_router_formula(decision_id: int) -> None:
    """_consensus_ab_bucket の式が decisions_router の計測式と一致すること。

    decisions_router.py の bucket 振り分け:
        bucket_key = "new" if row.id % 2 == 1 else "legacy"
    この式と同一であることを parametrize で突き合わせる。
    """
    expected = "new" if decision_id % 2 == 1 else "legacy"
    assert _consensus_ab_bucket(decision_id) == expected


# ---------------------------------------------------------------------------
# B. 50/50 分布テスト
# ---------------------------------------------------------------------------


def test_bucket_50_50_distribution() -> None:
    """id=1..1000 で new/legacy が各 500 件（厳密な 50/50）。"""
    new_count = sum(1 for i in range(1, 1001) if _consensus_ab_bucket(i) == "new")
    legacy_count = sum(1 for i in range(1, 1001) if _consensus_ab_bucket(i) == "legacy")
    assert new_count == 500
    assert legacy_count == 500


# ---------------------------------------------------------------------------
# C. mode != "a_b" 不変性テスト
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["off", "shadow", "on"])
def test_non_ab_mode_does_not_change_routing(db_session, mode: str) -> None:
    """mode が off/shadow/on のとき、_create_proposals_for_users は元の result.final_action で呼ばれる。

    a_b 分岐ロジックを通過しないことを _create_proposals_for_users の mock で検証する。

    get_ai_settings は run_ai_judgment_job 内でローカルインポートされるため、
    正しいパッチターゲットは "app.ai.config.get_ai_settings"。
    """
    from app.automation.ai_judgment_scheduler import run_ai_judgment_job

    llm_action = TradeAction.BUY
    result = _make_result(llm_action, confidence=80)

    with (
        patch(
            "app.automation.ai_judgment_scheduler.KnowledgeService",
            return_value=MagicMock(search=MagicMock(return_value=[])),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=_make_aave_data(),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.get_judgment_logger",
            return_value=MagicMock(get_cognitive_state=MagicMock(return_value=None)),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.build_market_context",
            return_value=MarketContext(),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.AIService",
            return_value=MagicMock(judge_with_rag=MagicMock(return_value=result)),
        ),
        # get_ai_settings はローカルインポートなので app.ai.config 側のみパッチ
        patch("app.ai.config.get_ai_settings", return_value=_settings(mode)),
        patch("app.ai.agents.run_all_agents", return_value=_make_agent_ctx_bullish()),
        patch(
            "app.automation.ai_judgment_scheduler._create_proposals_for_users",
        ) as mock_proposals,
        patch(
            "app.automation.ai_judgment_scheduler._generate_embedding",
            return_value=None,
        ),
    ):
        mock_proposals.return_value = 0
        run_ai_judgment_job(db=db_session)

    # _create_proposals_for_users に渡された result の final_action が元の LLM action のまま
    assert mock_proposals.called
    _passed_result = mock_proposals.call_args[0][2]  # positional arg[2] = result
    assert _passed_result.final_action == llm_action, (
        f"mode={mode}: expected routing via {llm_action.value}, "
        f"got {_passed_result.final_action.value}"
    )


# ---------------------------------------------------------------------------
# D. A/B ルーティング統合テスト
# ---------------------------------------------------------------------------


def test_ab_even_id_uses_llm_action(db_session) -> None:
    """a_b + 偶数 id (legacy バケット) → LLM の final_action で routing。"""
    from app.automation.ai_judgment_scheduler import run_ai_judgment_job

    llm_action = TradeAction.BUY
    result = _make_result(llm_action, confidence=80)

    # 次の AIDecision.id が偶数になるよう調整
    _ensure_even_next_id(db_session)

    with (
        patch(
            "app.automation.ai_judgment_scheduler.KnowledgeService",
            return_value=MagicMock(search=MagicMock(return_value=[])),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=_make_aave_data(),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.get_judgment_logger",
            return_value=MagicMock(get_cognitive_state=MagicMock(return_value=None)),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.build_market_context",
            return_value=MarketContext(),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.AIService",
            return_value=MagicMock(judge_with_rag=MagicMock(return_value=result)),
        ),
        patch("app.ai.config.get_ai_settings", return_value=_settings("a_b")),
        patch("app.ai.agents.run_all_agents", return_value=_make_agent_ctx_bullish()),
        patch(
            "app.automation.ai_judgment_scheduler._create_proposals_for_users",
        ) as mock_proposals,
        patch(
            "app.automation.ai_judgment_scheduler._generate_embedding",
            return_value=None,
        ),
    ):
        mock_proposals.return_value = 0
        job_result = run_ai_judgment_job(db=db_session)

    new_decision_id = job_result["decision_id"]
    assert new_decision_id % 2 == 0, f"expected even id, got {new_decision_id}"
    assert mock_proposals.called
    _passed_result = mock_proposals.call_args[0][2]
    # 偶数 = legacy バケット → LLM action (BUY) がそのまま routing
    assert _passed_result.final_action == llm_action


def test_ab_odd_id_uses_verdict_action(db_session) -> None:
    """a_b + 奇数 id (new バケット) → verdict action で routing（verdict != LLM action のケース）。

    LLM action = HOLD、verdict action = BUY のときに BUY が採用されることを確認。
    """
    from app.automation.ai_judgment_scheduler import run_ai_judgment_job

    llm_action = TradeAction.HOLD
    verdict_action = TradeAction.BUY  # 全軸 BULLISH → BUY
    result = _make_result(llm_action, confidence=70)

    # 次の AIDecision.id が奇数になるよう調整
    _ensure_odd_next_id(db_session)

    with (
        patch(
            "app.automation.ai_judgment_scheduler.KnowledgeService",
            return_value=MagicMock(search=MagicMock(return_value=[])),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=_make_aave_data(),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.get_judgment_logger",
            return_value=MagicMock(get_cognitive_state=MagicMock(return_value=None)),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.build_market_context",
            return_value=MarketContext(),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.AIService",
            return_value=MagicMock(judge_with_rag=MagicMock(return_value=result)),
        ),
        patch("app.ai.config.get_ai_settings", return_value=_settings("a_b")),
        patch("app.ai.agents.run_all_agents", return_value=_make_agent_ctx_bullish()),
        patch(
            "app.automation.ai_judgment_scheduler._create_proposals_for_users",
        ) as mock_proposals,
        patch(
            "app.automation.ai_judgment_scheduler._generate_embedding",
            return_value=None,
        ),
    ):
        mock_proposals.return_value = 0
        job_result = run_ai_judgment_job(db=db_session)

    new_decision_id = job_result["decision_id"]
    assert new_decision_id % 2 == 1, f"expected odd id, got {new_decision_id}"
    assert mock_proposals.called
    _passed_result = mock_proposals.call_args[0][2]
    # 奇数 = new バケット → verdict action (BUY) が採用される
    assert _passed_result.final_action == verdict_action, (
        f"expected verdict_action={verdict_action.value}, got {_passed_result.final_action.value}"
    )
    # 記録済みの judge_action は LLM action (HOLD) のまま — routing_result で汚染されていない
    feature_row = (
        db_session.query(AiDecisionFeature).filter_by(ai_decision_id=new_decision_id).one()
    )
    assert feature_row.judge_action == llm_action.value, (
        f"judge_action must not be overwritten: expected {llm_action.value}, "
        f"got {feature_row.judge_action}"
    )


def test_ab_new_bucket_deterministic_breakdown_none_falls_back_to_legacy(db_session) -> None:
    """a_b + new バケット + save_ai_decision_features=None → legacy フォールバック（例外で落ちない）。

    save_ai_decision_features が None を返す（挿入失敗）ケースをシミュレートして、
    fail-open により LLM action (legacy フォールバック) で routing されることを確認。
    """
    from app.automation.ai_judgment_scheduler import run_ai_judgment_job

    llm_action = TradeAction.BUY
    result = _make_result(llm_action, confidence=80)

    # 次の AIDecision.id が奇数になるよう調整
    _ensure_odd_next_id(db_session)

    with (
        patch(
            "app.automation.ai_judgment_scheduler.KnowledgeService",
            return_value=MagicMock(search=MagicMock(return_value=[])),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=_make_aave_data(),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.get_judgment_logger",
            return_value=MagicMock(get_cognitive_state=MagicMock(return_value=None)),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.build_market_context",
            return_value=MarketContext(),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.AIService",
            return_value=MagicMock(judge_with_rag=MagicMock(return_value=result)),
        ),
        patch("app.ai.config.get_ai_settings", return_value=_settings("a_b")),
        # save_ai_decision_features が None を返す（feature 挿入失敗のシミュレート）
        patch(
            "app.automation.ai_judgment_scheduler.save_ai_decision_features",
            return_value=None,
        ),
        patch(
            "app.automation.ai_judgment_scheduler._create_proposals_for_users",
        ) as mock_proposals,
    ):
        mock_proposals.return_value = 0
        # 例外が伝播しないこと (fail-open)
        job_result = run_ai_judgment_job(db=db_session)

    new_decision_id = job_result["decision_id"]
    assert new_decision_id % 2 == 1, f"expected odd id, got {new_decision_id}"
    assert mock_proposals.called
    _passed_result = mock_proposals.call_args[0][2]
    # feature=None → legacy フォールバック → LLM action (BUY) で routing
    assert _passed_result.final_action == llm_action


def test_ab_new_bucket_hold_verdict_no_proposals_via_feature(db_session) -> None:
    """a_b + new バケット + deterministic_breakdown["action"]="HOLD" → proposals 作成なし。

    save_ai_decision_features を直接 mock して HOLD verdict をシミュレートする。
    LLM が BUY でも、verdict が HOLD なら routing_result.final_action = HOLD となり
    _create_proposals_for_users が呼ばれないことを確認。
    """
    from app.automation.ai_judgment_scheduler import run_ai_judgment_job

    llm_action = TradeAction.BUY
    result = _make_result(llm_action, confidence=80)

    # 次の AIDecision.id が奇数になるよう調整
    _ensure_odd_next_id(db_session)

    # deterministic_breakdown で HOLD を返す feature mock
    mock_feature = MagicMock()
    mock_feature.deterministic_breakdown = {"action": "HOLD", "agreeing_count": 0}

    with (
        patch(
            "app.automation.ai_judgment_scheduler.KnowledgeService",
            return_value=MagicMock(search=MagicMock(return_value=[])),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.fetch_aave_market_data_safe",
            return_value=_make_aave_data(),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.get_judgment_logger",
            return_value=MagicMock(get_cognitive_state=MagicMock(return_value=None)),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.build_market_context",
            return_value=MarketContext(),
        ),
        patch(
            "app.automation.ai_judgment_scheduler.AIService",
            return_value=MagicMock(judge_with_rag=MagicMock(return_value=result)),
        ),
        patch("app.ai.config.get_ai_settings", return_value=_settings("a_b")),
        patch(
            "app.automation.ai_judgment_scheduler.save_ai_decision_features",
            return_value=mock_feature,
        ),
        patch(
            "app.automation.ai_judgment_scheduler._create_proposals_for_users",
        ) as mock_proposals,
    ):
        mock_proposals.return_value = 0
        job_result = run_ai_judgment_job(db=db_session)

    new_decision_id = job_result["decision_id"]
    assert new_decision_id % 2 == 1, f"expected odd id, got {new_decision_id}"
    # HOLD verdict → BUY/SELL でないので _create_proposals_for_users が呼ばれない
    assert not mock_proposals.called, "HOLD verdict in a_b new bucket must not create proposals"
    assert job_result["proposals_created"] == 0
