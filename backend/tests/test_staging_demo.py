# Copyright (c) Ultra AutoTrade. All rights reserved.
"""staging_demo（審査用デモシード）の単体テスト。

本番 no-op の二重ガード / 冪等 / best-effort を検証する。
"""

from unittest.mock import MagicMock

from app.staging_demo import maybe_seed_review_demo, review_demo_seed_enabled


def test_disabled_by_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """env 未設定なら無効。"""
    monkeypatch.delenv("STAGING_REVIEW_DEMO_SEED", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert review_demo_seed_enabled() is False


def test_production_always_disabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """APP_ENV=production ならフラグが true でも無効（二重ガード）。"""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STAGING_REVIEW_DEMO_SEED", "true")
    assert review_demo_seed_enabled() is False


def test_enabled_only_in_staging(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """非 production かつフラグ true のときのみ有効。"""
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("STAGING_REVIEW_DEMO_SEED", "true")
    assert review_demo_seed_enabled() is True


def test_seed_noop_when_disabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """無効時は DB に一切触れない。"""
    monkeypatch.delenv("STAGING_REVIEW_DEMO_SEED", raising=False)
    db = MagicMock()
    maybe_seed_review_demo(db, MagicMock(id=11))
    db.query.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_seed_creates_decision_and_proposal(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """有効時、AI判定 + 保留中提案の 2 レコードを add して commit する。"""
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("STAGING_REVIEW_DEMO_SEED", "true")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # 既存なし
    maybe_seed_review_demo(db, MagicMock(id=11))
    assert db.add.call_count == 2  # AIDecision + Proposal
    db.commit.assert_called_once()


def test_seed_idempotent_when_proposal_exists(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """既に提案を持つユーザーは skip（冪等）。"""
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("STAGING_REVIEW_DEMO_SEED", "true")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock()  # 既存あり
    maybe_seed_review_demo(db, MagicMock(id=11))
    db.add.assert_not_called()
    db.commit.assert_not_called()
