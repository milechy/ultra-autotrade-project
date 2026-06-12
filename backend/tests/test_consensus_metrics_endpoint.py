# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_consensus_metrics_endpoint.py
"""コンセンサス A/B 計測エンドポイントのテスト (EPIC-1 1-12)。

検証観点:
- bucket(id % 2)別の action_distribution が正しく集計される
- RBAC: 非 admin が 403
- fail-open: DB 例外 mock 時に 200 + 空 distribution
- days パラメータのフィルタリング
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-consensus-metrics")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin_metrics@example.com")

from app.ai.models import AIDecision, AiDecisionFeature  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def client(test_db) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture()
def db_session(test_db):
    _, engine = test_db
    Session_ = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()


def get_admin_token(client: TestClient) -> str:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "admin_metrics@example.com")
    client.post(
        "/auth/register",
        json={
            "email": email,
            "username": "admin_metrics",
            "password": "adminpass123",
        },
    )
    r = client.post("/auth/login", json={"email": email, "password": "adminpass123"})
    return r.json()["access_token"]


def _insert_decision_with_feature(
    session: Session,
    *,
    action: str = "HOLD",
    judge_action: str = "HOLD",
    confidence: int = 70,
    deterministic_breakdown: object = None,
    created_at: datetime | None = None,
) -> AIDecision:
    """ai_decisions + ai_decision_features を 1 セットINSERTする。"""
    now = created_at or datetime.now(timezone.utc)
    decision = AIDecision(
        query="test query",
        action=action,
        confidence=confidence,
        primary_provider="claude",
        primary_action=action,
        primary_confidence=confidence,
        agreed=True,
        created_at=now,
    )
    session.add(decision)
    session.flush()  # id 確定

    feature = AiDecisionFeature(
        ai_decision_id=decision.id,
        judge_action=judge_action,
        confidence=confidence,
        cross_verify=True,
        deterministic_breakdown=deterministic_breakdown,
    )
    session.add(feature)
    session.flush()
    return decision


# ---------------------------------------------------------------------------
# bucket 集計の正しさ
# ---------------------------------------------------------------------------


class TestBucketAggregation:
    def test_empty_db_returns_zero_counts(self, client: TestClient) -> None:
        """データなしのとき各 bucket の count=0。"""
        token = get_admin_token(client)
        r = client.get(
            "/api/ai/decisions/consensus-ab-metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "buckets" in data
        assert data["buckets"]["legacy"]["count"] == 0
        assert data["buckets"]["new"]["count"] == 0

    def test_bucket_separation_by_id_parity(self, client: TestClient, db_session: Session) -> None:
        """偶数 id → legacy bucket、奇数 id → new bucket に振り分けられる。

        DB に 3 件挿入し、id が偶奇で正しく分類されることを確認する。
        SQLite は autoincrement で 1 始まり（奇数→new）。
        """
        # 3件挿入: id=1(奇数→new), id=2(偶数→legacy), id=3(奇数→new)
        _insert_decision_with_feature(db_session, action="BUY", judge_action="BUY", confidence=80)
        _insert_decision_with_feature(db_session, action="HOLD", judge_action="HOLD", confidence=60)
        _insert_decision_with_feature(db_session, action="SELL", judge_action="SELL", confidence=70)
        db_session.commit()

        token = get_admin_token(client)
        r = client.get(
            "/api/ai/decisions/consensus-ab-metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        buckets = data["buckets"]

        # id=1(new), id=3(new) → new に 2 件
        assert buckets["new"]["count"] == 2
        # id=2(legacy) → legacy に 1 件
        assert buckets["legacy"]["count"] == 1

    def test_action_distribution_correctness(self, client: TestClient, db_session: Session) -> None:
        """judge_action の分布が bucket ごとに正確にカウントされる。"""
        # id=1(奇数→new): BUY
        _insert_decision_with_feature(db_session, judge_action="BUY", confidence=80)
        # id=2(偶数→legacy): HOLD
        _insert_decision_with_feature(db_session, judge_action="HOLD", confidence=60)
        # id=3(奇数→new): SELL
        _insert_decision_with_feature(db_session, judge_action="SELL", confidence=70)
        # id=4(偶数→legacy): HOLD
        _insert_decision_with_feature(db_session, judge_action="HOLD", confidence=65)
        db_session.commit()

        token = get_admin_token(client)
        r = client.get(
            "/api/ai/decisions/consensus-ab-metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        buckets = r.json()["buckets"]

        new_dist = buckets["new"]["action_distribution"]
        legacy_dist = buckets["legacy"]["action_distribution"]

        # new(id=1,3): BUY=1, SELL=1, HOLD=0
        assert new_dist["BUY"] == 1
        assert new_dist["SELL"] == 1
        assert new_dist.get("HOLD", 0) == 0

        # legacy(id=2,4): HOLD=2
        assert legacy_dist.get("HOLD", 0) == 2
        assert legacy_dist.get("BUY", 0) == 0

    def test_avg_confidence_is_string(self, client: TestClient, db_session: Session) -> None:
        """avg_confidence は文字列（Decimal 計算）で返る。"""
        _insert_decision_with_feature(db_session, confidence=80)
        _insert_decision_with_feature(db_session, confidence=60)
        db_session.commit()

        token = get_admin_token(client)
        r = client.get(
            "/api/ai/decisions/consensus-ab-metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        buckets = r.json()["buckets"]

        # 少なくとも 1 つの bucket で avg_confidence が文字列
        all_avgs = [
            b["avg_confidence"] for b in buckets.values() if b["avg_confidence"] is not None
        ]
        assert len(all_avgs) > 0
        for avg in all_avgs:
            assert isinstance(avg, str)
            # 数値として変換可能であること
            float(avg)

    def test_sell_count_visible_in_distribution(
        self, client: TestClient, db_session: Session
    ) -> None:
        """SELL 件数が各 bucket に正しく表示される（SELL-spam 再発監視要件）。"""
        # id=1(new): SELL
        _insert_decision_with_feature(db_session, judge_action="SELL")
        # id=2(legacy): SELL
        _insert_decision_with_feature(db_session, judge_action="SELL")
        # id=3(new): SELL
        _insert_decision_with_feature(db_session, judge_action="SELL")
        db_session.commit()

        token = get_admin_token(client)
        r = client.get(
            "/api/ai/decisions/consensus-ab-metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        buckets = r.json()["buckets"]

        assert buckets["new"]["action_distribution"].get("SELL", 0) == 2
        assert buckets["legacy"]["action_distribution"].get("SELL", 0) == 1

    def test_verdict_distribution_from_deterministic_breakdown(
        self, client: TestClient, db_session: Session
    ) -> None:
        """deterministic_breakdown->>'action' の分布が verdict_distribution に含まれる。"""
        breakdown_buy = {"action": "BUY", "score": 0.8, "agreeing_count": 4}
        breakdown_hold = {"action": "HOLD", "score": 0.3, "agreeing_count": 2}

        # id=1(new): verdict=BUY
        _insert_decision_with_feature(
            db_session, judge_action="BUY", deterministic_breakdown=breakdown_buy
        )
        # id=2(legacy): verdict=HOLD
        _insert_decision_with_feature(
            db_session, judge_action="HOLD", deterministic_breakdown=breakdown_hold
        )
        # id=3(new): breakdown なし → verdict_distribution に含まれない
        _insert_decision_with_feature(db_session, judge_action="HOLD")
        db_session.commit()

        token = get_admin_token(client)
        r = client.get(
            "/api/ai/decisions/consensus-ab-metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        buckets = r.json()["buckets"]

        # new(id=1,3): id=1 に breakdown あり → BUY=1
        new_verdict = buckets["new"]["verdict_distribution"]
        assert new_verdict.get("BUY", 0) == 1

        # legacy(id=2): HOLD=1
        legacy_verdict = buckets["legacy"]["verdict_distribution"]
        assert legacy_verdict.get("HOLD", 0) == 1

    def test_days_filter_excludes_old_records(
        self, client: TestClient, db_session: Session
    ) -> None:
        """days パラメータで集計期間外のレコードは除外される。"""
        old_time = datetime.now(timezone.utc) - timedelta(days=30)
        _insert_decision_with_feature(db_session, judge_action="BUY", created_at=old_time)
        db_session.commit()

        token = get_admin_token(client)
        # days=7 なら 30日前のレコードは除外
        r = client.get(
            "/api/ai/decisions/consensus-ab-metrics?days=7",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["days"] == 7
        total = data["buckets"]["legacy"]["count"] + data["buckets"]["new"]["count"]
        assert total == 0


# ---------------------------------------------------------------------------
# RBAC: 非 admin が 403
# ---------------------------------------------------------------------------


class TestRBAC:
    def test_viewer_gets_403(self, client: TestClient) -> None:
        """viewer ロールは consensus-ab-metrics に 403。"""
        admin_token = get_admin_token(client)
        client.post(
            "/users",
            json={
                "email": "viewer_ab@test.com",
                "username": "viewer_ab",
                "password": "viewerpass123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        r = client.post(
            "/auth/login",
            json={"email": "viewer_ab@test.com", "password": "viewerpass123"},
        )
        viewer_token = r.json()["access_token"]

        r = client.get(
            "/api/ai/decisions/consensus-ab-metrics",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403

    def test_unauthenticated_gets_401(self, client: TestClient) -> None:
        """未認証は 401。"""
        r = client.get("/api/ai/decisions/consensus-ab-metrics")
        assert r.status_code == 401

    def test_admin_gets_200(self, client: TestClient) -> None:
        """admin ロールは 200 を返す。"""
        token = get_admin_token(client)
        r = client.get(
            "/api/ai/decisions/consensus-ab-metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# fail-open: DB 例外時に 200 + 空 distribution
# ---------------------------------------------------------------------------


class TestFailOpen:
    def test_db_exception_returns_200_with_empty_distribution(self, client: TestClient) -> None:
        """DB 例外発生時に 500 にならず 200 + 空 distribution を返す (fail-open)。

        datetime.now をパッチして try ブロック冒頭で RuntimeError を発生させることで
        実際の DB なしに fail-open パスを通過させる。
        """
        token = get_admin_token(client)

        with patch("app.ai.decisions_router.datetime") as mock_dt:
            mock_dt.now.side_effect = RuntimeError("db boom")
            r = client.get(
                "/api/ai/decisions/consensus-ab-metrics",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert r.status_code == 200
        data = r.json()
        assert "buckets" in data
        assert data["buckets"]["legacy"]["count"] == 0
        assert data["buckets"]["new"]["count"] == 0
        assert data["buckets"]["legacy"]["action_distribution"] == {
            "BUY": 0,
            "SELL": 0,
            "HOLD": 0,
        }
