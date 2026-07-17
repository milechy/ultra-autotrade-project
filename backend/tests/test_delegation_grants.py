# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_delegation_grants.py
"""委譲枠 (delegation grant) のテスト（v4 完全おまかせ自動運用 Phase 0 / スライス0-C）。

- DelegationGrant モデル + get_active_grant ヘルパー（active/expired/revoked/最新）
- PolicyEngine Rule 8（AUTO 執行は有効 grant 必須・手動経路は不影響）
- grant/revoke/get API（consent・取消・上限ハードキャップ検証）
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-delegation")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "deleg_admin@example.com")

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.policy.engine import PolicyContext, PolicyEngine  # noqa: E402
from app.users.models import (  # noqa: E402
    DELEGATION_STATUS_ACTIVE,
    DELEGATION_STATUS_REVOKED,
    DelegationGrant,
    get_active_grant,
)


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

    yield override_get_db, SessionLocal
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def db_session(test_db) -> Generator[Session, None, None]:
    _, SessionLocal = test_db
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(test_db) -> TestClient:
    override_get_db, _ = test_db
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def register_and_login(client: TestClient, email: str | None = None) -> str:
    # 初期 admin 登録は INITIAL_ADMIN_EMAIL に一致する最初のユーザーのみ許可される。
    # conftest が同 env を設定済みのため、実行時の値を読む（各テストは fresh DB）。
    if email is None:
        email = os.environ.get("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    client.post(
        "/auth/register",
        json={"email": email, "username": "deleguser", "password": "userpassword123"},
    )
    r = client.post("/auth/login", json={"email": email, "password": "userpassword123"})
    return r.json()["access_token"]


def _make_grant(user_id: int, **overrides) -> DelegationGrant:
    now = datetime.now(timezone.utc)
    defaults = dict(
        user_id=user_id,
        wallet_address="0x" + "a" * 40,
        status=DELEGATION_STATUS_ACTIVE,
        max_single_trade_pct=Decimal("10"),
        max_daily_trade_pct=Decimal("30"),
        hf_floor=Decimal("1.6"),
        allowed_protocols=["aave"],
        allowed_assets=["USDC"],
        consent_at=now,
        expires_at=now + timedelta(days=30),
    )
    defaults.update(overrides)
    return DelegationGrant(**defaults)


# ---------------------------------------------------------------------------
# get_active_grant ヘルパー
# ---------------------------------------------------------------------------


class TestGetActiveGrant:
    def test_returns_active_grant(self, db_session: Session) -> None:
        db_session.add(_make_grant(1))
        db_session.commit()
        grant = get_active_grant(1, db_session)
        assert grant is not None
        assert grant.status == DELEGATION_STATUS_ACTIVE

    def test_none_when_no_grant(self, db_session: Session) -> None:
        assert get_active_grant(999, db_session) is None

    def test_expired_grant_not_returned(self, db_session: Session) -> None:
        past = datetime.now(timezone.utc) - timedelta(days=1)
        db_session.add(_make_grant(1, expires_at=past))
        db_session.commit()
        assert get_active_grant(1, db_session) is None

    def test_revoked_grant_not_returned(self, db_session: Session) -> None:
        db_session.add(
            _make_grant(
                1,
                status=DELEGATION_STATUS_REVOKED,
                revoked_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()
        assert get_active_grant(1, db_session) is None

    def test_returns_latest_when_multiple(self, db_session: Session) -> None:
        old = _make_grant(1, max_single_trade_pct=Decimal("5"))
        db_session.add(old)
        db_session.commit()
        new = _make_grant(1, max_single_trade_pct=Decimal("8"))
        db_session.add(new)
        db_session.commit()
        grant = get_active_grant(1, db_session)
        assert grant is not None
        assert grant.max_single_trade_pct == Decimal("8")


# ---------------------------------------------------------------------------
# PolicyEngine Rule 8: AUTO 執行は有効 grant 必須
# ---------------------------------------------------------------------------


class TestPolicyEngineAutoGrantRule:
    def _ctx(self, **kw) -> PolicyContext:
        base = dict(
            user_id=1,
            asset="USDC",
            operation="SUPPLY",
            amount_usd=Decimal("100"),
        )
        base.update(kw)
        return PolicyContext(**base)

    def test_auto_without_grant_is_blocked(self, db_session: Session) -> None:
        engine = PolicyEngine()
        result = engine.check(self._ctx(is_auto_execution=True), db_session)
        assert result.blocked
        assert any("delegation grant" in v for v in result.violations)

    def test_auto_with_active_grant_passes(self, db_session: Session) -> None:
        db_session.add(_make_grant(1))
        db_session.commit()
        engine = PolicyEngine()
        result = engine.check(self._ctx(is_auto_execution=True), db_session)
        assert result.passed, result.violations

    def test_manual_path_unaffected_by_missing_grant(self, db_session: Session) -> None:
        """is_auto_execution=False（手動承認）は grant 不在でも Rule 8 で弾かれない。"""
        engine = PolicyEngine()
        result = engine.check(self._ctx(is_auto_execution=False), db_session)
        assert result.passed, result.violations


# ---------------------------------------------------------------------------
# grant / revoke / get API
# ---------------------------------------------------------------------------


class TestDelegationAPI:
    # allowed_protocols は委譲可能集合 (aave / pendle) のみ。以前は ["aave","lido"] を
    # そのまま round-trip していたが、lido は policy_mapper が写像できず prepare が 502 に
    # なるため grant だけ通るのは乖離だった（schema で 422 に統一）。
    _VALID = {
        "max_single_trade_pct": "10",
        "max_daily_trade_pct": "30",
        "hf_floor": "1.6",
        "allowed_protocols": ["aave"],
        "allowed_assets": ["USDC"],
        "expires_in_days": 30,
    }

    def test_requires_auth(self, client: TestClient) -> None:
        assert client.get("/api/user/delegation").status_code == 401
        assert client.post("/api/user/delegation/grant", json=self._VALID).status_code == 401

    def test_create_get_revoke_flow(self, client: TestClient) -> None:
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}

        # 初期は null
        assert client.get("/api/user/delegation", headers=h).json() is None

        # consent
        r = client.post("/api/user/delegation/grant", json=self._VALID, headers=h)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "active"
        assert data["allowed_protocols"] == ["aave"]

        # get は有効枠を返す
        got = client.get("/api/user/delegation", headers=h).json()
        assert got is not None and got["status"] == "active"

        # revoke
        rv = client.post("/api/user/delegation/revoke", headers=h).json()
        assert rv["status"] == "revoked"

        # revoke 後は null
        assert client.get("/api/user/delegation", headers=h).json() is None

    def test_recreate_revokes_previous(self, client: TestClient) -> None:
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        client.post("/api/user/delegation/grant", json=self._VALID, headers=h)
        client.post("/api/user/delegation/grant", json=self._VALID, headers=h)
        # 常に1枠のみ有効（再作成で前枠は revoke される）
        got = client.get("/api/user/delegation", headers=h).json()
        assert got is not None and got["status"] == "active"

    @pytest.mark.parametrize(
        "protocols",
        [
            ["aave", "lido"],  # lido は委譲経路が未対応（policy_mapper が写像不能）
            ["uniswap"],  # 未知プロトコル
            ["aave", ""],  # 空要素
        ],
    )
    def test_undelegatable_protocols_rejected(
        self, client: TestClient, protocols: list[str]
    ) -> None:
        """委譲可能集合の外は grant でも 422（prepare だけ 502 という乖離を無くす）。"""
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        payload = dict(self._VALID)
        payload["allowed_protocols"] = protocols
        r = client.post("/api/user/delegation/grant", json=payload, headers=h)
        assert r.status_code == 422, r.text

    def test_protocols_normalized(self, client: TestClient) -> None:
        """大文字 / 前後空白 / 重複は正規化して保存する。

        `_should_use_scw_route` は grant 値を lower するが strip しないため、" pendle" は
        policy 側を通って routing 側だけで落ちる。入口で揃えることでその乖離を防ぐ。
        """
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        payload = dict(self._VALID)
        payload["allowed_protocols"] = [" AAVE ", "aave"]
        r = client.post("/api/user/delegation/grant", json=payload, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["allowed_protocols"] == ["aave"]

    def test_pendle_grant_requires_aggressive_ack(self, client: TestClient) -> None:
        """Pendle 委譲はリスク開示同意が無ければ 412（開示モーダルの迂回を防ぐ）。"""
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        payload = dict(self._VALID)
        payload["allowed_protocols"] = ["aave", "pendle"]

        r = client.post("/api/user/delegation/grant", json=payload, headers=h)
        assert r.status_code == 412, r.text
        assert client.get("/api/user/delegation", headers=h).json() is None

        # 開示に同意すると通る
        assert client.post("/api/user/aggressive-consent", headers=h).status_code == 200
        r2 = client.post("/api/user/delegation/grant", json=payload, headers=h)
        assert r2.status_code == 200, r2.text
        assert r2.json()["allowed_protocols"] == ["aave", "pendle"]

    def test_aave_only_grant_does_not_require_ack(self, client: TestClient) -> None:
        """Aave のみの委譲は従来どおり同意不要（既存ユーザーの挙動を変えない）。"""
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/user/delegation/grant", json=self._VALID, headers=h)
        assert r.status_code == 200, r.text

    @pytest.mark.parametrize(
        "field,value",
        [
            ("max_single_trade_pct", "10.01"),  # >10
            ("max_daily_trade_pct", "30.01"),  # >30
            ("hf_floor", "1.59"),  # <1.6
            ("expires_in_days", 0),  # <1
            ("expires_in_days", 999),  # >365
        ],
    )
    def test_bounds_rejected(self, client: TestClient, field: str, value: object) -> None:
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        payload = dict(self._VALID)
        payload[field] = value
        r = client.post("/api/user/delegation/grant", json=payload, headers=h)
        assert r.status_code == 422, r.text

    def test_revoke_idempotent_when_no_grant(self, client: TestClient) -> None:
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        assert client.post("/api/user/delegation/revoke", headers=h).json() is None

    def test_prepare_dormant_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L1 prepare はフラグ/L0 未設定（既定）で 503・Privy を叩かない。"""
        monkeypatch.delenv("DELEGATION_PRIVY_POLICY_ENABLED", raising=False)
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/user/delegation/prepare", json=self._VALID, headers=h)
        assert r.status_code == 503, r.text

    def test_prepare_requires_auth(self, client: TestClient) -> None:
        assert client.post("/api/user/delegation/prepare", json=self._VALID).status_code == 401

    def test_grant_persists_privy_ids(self, client: TestClient) -> None:
        """L3: grant に privy_policy_id/privy_signer_id を渡すと保存される。"""
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        payload = dict(self._VALID)
        payload["privy_policy_id"] = "policy_xyz"
        payload["privy_signer_id"] = "kq_server_1"
        r = client.post("/api/user/delegation/grant", json=payload, headers=h)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["privy_policy_id"] == "policy_xyz"
        assert data["privy_signer_id"] == "kq_server_1"

    def test_grant_without_privy_ids_stays_null(self, client: TestClient) -> None:
        """後方互換: privy id を渡さない既存フローは None のまま。"""
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/user/delegation/grant", json=self._VALID, headers=h)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["privy_policy_id"] is None
        assert data["privy_signer_id"] is None

    def test_grant_persists_privy_wallet_id_to_user(
        self, client: TestClient, test_db: tuple
    ) -> None:
        """2026-07-16: grant に privy_wallet_id を渡すと users.privy_wallet_id へ保存される
        （ログイン時点では未委譲で null のため、consent 完了時点(本エンドポイント)が唯一の
        確実な解決経路）。"""
        _override, SessionLocal = test_db
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        payload = dict(self._VALID)
        payload["privy_wallet_id"] = "frob784a2upmpff5z7yi300u"
        r = client.post("/api/user/delegation/grant", json=payload, headers=h)
        assert r.status_code == 200, r.text

        from app.auth.models import User  # noqa: PLC0415

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == os.environ["INITIAL_ADMIN_EMAIL"]).first()
            assert user is not None
            assert user.privy_wallet_id == "frob784a2upmpff5z7yi300u"
        finally:
            db.close()

    def test_grant_without_privy_wallet_id_does_not_touch_user(
        self, client: TestClient, test_db: tuple
    ) -> None:
        """後方互換: privy_wallet_id を渡さない既存フローは user.privy_wallet_id を変更しない。"""
        _override, SessionLocal = test_db
        token = register_and_login(client)
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/user/delegation/grant", json=self._VALID, headers=h)
        assert r.status_code == 200, r.text

        from app.auth.models import User  # noqa: PLC0415

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == os.environ["INITIAL_ADMIN_EMAIL"]).first()
            assert user is not None
            assert user.privy_wallet_id is None
        finally:
            db.close()
