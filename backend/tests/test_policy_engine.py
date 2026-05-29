# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_policy_engine.py
"""PolicyEngine — 各ポリシールールの pass/fail ユニットテスト。"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# 環境変数を import 前に設定（PolicyEngine.__init__ は init 時に env を読む）
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-policy")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")

from app.database import Base  # noqa: E402
from app.policy.engine import PolicyContext, PolicyEngine  # noqa: E402
from app.proposals.models import Proposal  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """インメモリ SQLite セッション。velocity/cooldown テスト用。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    os.unlink(path)


def _engine() -> PolicyEngine:
    """デフォルト設定の PolicyEngine。"""
    return PolicyEngine()


def _ctx(**kwargs) -> PolicyContext:
    defaults = dict(
        user_id=1,
        asset="USDC",
        operation="SUPPLY",
        amount_usd=Decimal("100"),
        expected_hf_after=Decimal("2.0"),
    )
    defaults.update(kwargs)
    return PolicyContext(**defaults)


def _approved_proposal(
    user_id: int,
    amount_usd: Decimal,
    approved_at: datetime,
    proposal_id: int = 1,
) -> Proposal:
    """DB に挿入する approved Proposal のファクトリ。"""
    return Proposal(
        id=proposal_id,
        user_id=user_id,
        operation="SUPPLY",
        asset="USDC",
        amount=amount_usd,
        amount_usd=amount_usd,
        reason="test",
        status="approved",
        approved_at=approved_at,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
    )


# ---------------------------------------------------------------------------
# Rule 1: asset whitelist
# ---------------------------------------------------------------------------


def test_asset_whitelist_pass():
    result = _engine().check(_ctx(asset="USDC"), db=None)
    assert result.passed


def test_asset_whitelist_fail_eth():
    result = _engine().check(_ctx(asset="ETH"), db=None)
    assert result.blocked
    assert any("asset" in v and "ETH" in v for v in result.violations)


def test_asset_whitelist_case_insensitive_pass():
    result = _engine().check(_ctx(asset="usdc"), db=None)
    assert result.passed


def test_asset_whitelist_fail_wbtc():
    result = _engine().check(_ctx(asset="WBTC"), db=None)
    assert result.blocked


# ---------------------------------------------------------------------------
# Rule 2: allowed contracts (Aave only = SUPPLY/WITHDRAW)
# ---------------------------------------------------------------------------


def test_operation_supply_pass():
    result = _engine().check(_ctx(operation="SUPPLY"), db=None)
    assert result.passed


def test_operation_withdraw_pass():
    result = _engine().check(_ctx(operation="WITHDRAW"), db=None)
    assert result.passed


def test_operation_borrow_fail():
    result = _engine().check(_ctx(operation="BORROW"), db=None)
    assert result.blocked
    assert any("operation" in v and "BORROW" in v for v in result.violations)


def test_operation_repay_fail():
    result = _engine().check(_ctx(operation="REPAY"), db=None)
    assert result.blocked


def test_operation_unknown_fail():
    result = _engine().check(_ctx(operation="SWAP"), db=None)
    assert result.blocked


# ---------------------------------------------------------------------------
# Rule 3: max position size
# ---------------------------------------------------------------------------


def test_max_position_pass():
    result = _engine().check(_ctx(amount_usd=Decimal("9999")), db=None)
    assert result.passed


def test_max_position_exact_boundary_pass():
    result = _engine().check(_ctx(amount_usd=Decimal("10000")), db=None)
    assert result.passed


def test_max_position_fail():
    result = _engine().check(_ctx(amount_usd=Decimal("10001")), db=None)
    assert result.blocked
    assert any("max_position" in v for v in result.violations)


def test_max_position_env_override(monkeypatch):
    monkeypatch.setenv("POLICY_MAX_POSITION_USD", "500")
    eng = PolicyEngine()
    assert eng.check(_ctx(amount_usd=Decimal("499")), db=None).passed
    assert eng.check(_ctx(amount_usd=Decimal("501")), db=None).blocked


# ---------------------------------------------------------------------------
# Rule 4: daily velocity cap
# ---------------------------------------------------------------------------


def test_daily_velocity_pass(db_session):
    # 今日の承認済み合計 0 → 100 USD 追加は 50000 を超えない
    result = _engine().check(_ctx(amount_usd=Decimal("100")), db=db_session)
    assert result.passed


def test_daily_velocity_fail(db_session):
    # 今日 49,950 USD 承認済み → 100 追加で 50,050 > 50,000
    now = datetime.now(timezone.utc)
    db_session.add(_approved_proposal(1, Decimal("49950"), now))
    db_session.commit()

    result = _engine().check(_ctx(amount_usd=Decimal("100")), db=db_session)
    assert result.blocked
    assert any("daily velocity" in v for v in result.violations)


def test_daily_velocity_excludes_old_proposals(db_session):
    # 昨日の承認は日次カウントに含まれない
    yesterday = datetime.now(timezone.utc) - timedelta(days=1, seconds=1)
    db_session.add(_approved_proposal(1, Decimal("49950"), yesterday))
    db_session.commit()

    result = _engine().check(_ctx(amount_usd=Decimal("100")), db=db_session)
    assert result.passed


# ---------------------------------------------------------------------------
# Rule 5: hourly velocity cap
# ---------------------------------------------------------------------------


def test_hourly_velocity_pass(db_session):
    result = _engine().check(_ctx(amount_usd=Decimal("100")), db=db_session)
    assert result.passed


def test_hourly_velocity_fail(db_session):
    # 過去1時間で 19,950 USD 承認済み → 100 追加で 20,050 > 20,000
    now = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.add(_approved_proposal(1, Decimal("19950"), now))
    db_session.commit()

    result = _engine().check(_ctx(amount_usd=Decimal("100")), db=db_session)
    assert result.blocked
    assert any("hourly velocity" in v for v in result.violations)


def test_hourly_velocity_excludes_old_proposals(db_session):
    # 2時間前の承認は時間毎カウントに含まれない
    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.add(_approved_proposal(1, Decimal("19950"), two_hours_ago))
    db_session.commit()

    result = _engine().check(_ctx(amount_usd=Decimal("100")), db=db_session)
    assert result.passed


# ---------------------------------------------------------------------------
# Rule 6: cooldown window
# ---------------------------------------------------------------------------


def test_cooldown_pass_no_history(db_session):
    # 過去の承認なし → クールダウン不要
    result = _engine().check(_ctx(), db=db_session)
    assert result.passed


def test_cooldown_pass_elapsed(db_session):
    # 700s 以上前の承認 → クールダウン (600s) 経過済み
    long_ago = datetime.now(timezone.utc) - timedelta(seconds=700)
    db_session.add(_approved_proposal(1, Decimal("100"), long_ago))
    db_session.commit()

    result = _engine().check(_ctx(), db=db_session)
    assert result.passed


def test_cooldown_fail_recent(db_session):
    # 60s 前の承認 → クールダウン (600s) 未経過
    recent = datetime.now(timezone.utc) - timedelta(seconds=60)
    db_session.add(_approved_proposal(1, Decimal("100"), recent))
    db_session.commit()

    result = _engine().check(_ctx(), db=db_session)
    assert result.blocked
    assert any("cooldown" in v for v in result.violations)


def test_cooldown_excludes_other_users(db_session):
    # 他ユーザーの直近承認は自ユーザーのクールダウンに影響しない
    recent = datetime.now(timezone.utc) - timedelta(seconds=60)
    db_session.add(_approved_proposal(user_id=99, amount_usd=Decimal("100"), approved_at=recent))
    db_session.commit()

    result = _engine().check(_ctx(user_id=1), db=db_session)
    assert result.passed


# ---------------------------------------------------------------------------
# Rule 7: HF floor
# ---------------------------------------------------------------------------


def test_hf_floor_pass():
    result = _engine().check(_ctx(expected_hf_after=Decimal("2.0")), db=None)
    assert result.passed


def test_hf_floor_exact_boundary_pass():
    result = _engine().check(_ctx(expected_hf_after=Decimal("1.5")), db=None)
    assert result.passed


def test_hf_floor_fail():
    result = _engine().check(_ctx(expected_hf_after=Decimal("1.4")), db=None)
    assert result.blocked
    assert any("expected_hf_after" in v and "floor" in v for v in result.violations)


def test_hf_floor_none_skipped():
    # expected_hf_after が None の場合はチェックをスキップ
    result = _engine().check(_ctx(expected_hf_after=None), db=None)
    assert result.passed


def test_hf_floor_env_override(monkeypatch):
    monkeypatch.setenv("POLICY_HF_FLOOR", "2.0")
    eng = PolicyEngine()
    assert eng.check(_ctx(expected_hf_after=Decimal("2.1")), db=None).passed
    assert eng.check(_ctx(expected_hf_after=Decimal("1.9")), db=None).blocked


# ---------------------------------------------------------------------------
# Multiple violations reported together
# ---------------------------------------------------------------------------


def test_multiple_violations_all_returned():
    result = _engine().check(
        _ctx(
            asset="ETH",
            operation="BORROW",
            amount_usd=Decimal("99999"),
            expected_hf_after=Decimal("1.0"),
        ),
        db=None,
    )
    assert result.blocked
    # 4 violations: asset + operation + position + HF
    assert len(result.violations) >= 4


# ---------------------------------------------------------------------------
# Clean proposal (all rules pass)
# ---------------------------------------------------------------------------


def test_clean_proposal_all_pass(db_session):
    result = _engine().check(
        _ctx(
            asset="USDC",
            operation="SUPPLY",
            amount_usd=Decimal("500"),
            expected_hf_after=Decimal("2.5"),
        ),
        db=db_session,
    )
    assert result.passed
    assert result.violations == []
