# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/users/test_withdrawals_router.py
"""POST/GET /api/users/withdrawals (non-custodial 出金記録) のテスト。

対象: backend/app/users/withdrawals_router.py

カバー範囲:
- amount_usdc > WITHDRAWAL_MAX_USDC → 422 (pydantic validation)
- amount_usdc <= 0 → 422 (Field gt=0)
- 別ユーザーの tx_hash 上書き → 409
- 同一ユーザー同一 tx_hash 再 POST → 200 (冪等)
- network != "base" → 422
- Decimal 精度保持 (文字列授受 → Decimal, float 不使用)
- 未認証 → 401
- ENABLE_WITHDRAWALS=false 時に route 未登録 → 404

route 配線ガード (ENABLE_WITHDRAWALS) は create_app() 内で評価されるため、
本テストでは flag on で app を生成する。flag off の網羅は
backend/tests/test_withdrawals_flag.py と本ファイル末尾の 1 ケースで担保。

認証: /auth/register は initial-admin 1 名のみ許可するため、複数ユーザーを
扱うテスト (409 / list 分離) では require_active_user を fake user で override する
(test_notification_settings_api.py と同じパターン)。401 ケースのみ override しない。

★ #391 money gate を通すまで本番 .env で ENABLE_WITHDRAWALS=true にしないこと。
"""

import os
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-withdrawals-router")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "withdraw_admin@example.com")

from app.auth.dependencies import require_active_user  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

_WITHDRAW_PATH = "/api/users/withdrawals"
_VALID_TX = "0x" + "a" * 64
_VALID_TX_2 = "0x" + "b" * 64
_VALID_TO = "0x" + "1" * 40


@dataclass
class _FakeUser:
    """require_active_user の戻り値スタブ (router が参照する属性のみ)。"""

    id: int
    email: str
    is_active: bool = True


@pytest.fixture()
def test_db() -> Generator[tuple[Any, Any], None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Any, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db, engine
    Base.metadata.drop_all(bind=engine)
    os.unlink(path)


@pytest.fixture()
def app(test_db: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    # ENABLE_WITHDRAWALS=1 で route を登録 (create_app 評価前に設定必須)
    monkeypatch.setenv("ENABLE_WITHDRAWALS", "1")
    # 上限を明示 (default 100000 だが env で固定して assertion を安定させる)
    monkeypatch.setenv("WITHDRAWAL_MAX_USDC", "100000")
    # RPC verify は無効 (ネットワーク呼び出し回避)
    monkeypatch.setenv("RPC_VERIFY", "false")
    # in-memory rate limiter をリセット (他テストとの干渉防止)
    from app.users import withdrawals_router as wr

    wr._rate_limiter.reset()

    override_get_db, _ = test_db
    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    return application


def _client_as(app: FastAPI, user: _FakeUser | None) -> TestClient:
    """user を指定すると認証 override 付き、None で未認証クライアント。"""
    if user is not None:
        app.dependency_overrides[require_active_user] = lambda: user
    else:
        app.dependency_overrides.pop(require_active_user, None)
    return TestClient(app)


def _payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "tx_hash": _VALID_TX,
        "to_address": _VALID_TO,
        "amount_usdc": "100.5",
        "network": "base",
    }
    base.update(overrides)
    return base


class TestWithdrawalsRouter:
    def test_requires_auth(self, app: FastAPI) -> None:
        """未認証 → 401。"""
        client = _client_as(app, None)
        r = client.post(_WITHDRAW_PATH, json=_payload())
        assert r.status_code == 401

    def test_amount_exceeds_max_returns_422(self, app: FastAPI) -> None:
        """amount_usdc > WITHDRAWAL_MAX_USDC → 422 (pydantic validation)。"""
        client = _client_as(app, _FakeUser(id=1, email="over@example.com"))
        r = client.post(_WITHDRAW_PATH, json=_payload(amount_usdc="100000.000001"))
        assert r.status_code == 422

    def test_amount_zero_returns_422(self, app: FastAPI) -> None:
        """amount_usdc == 0 → 422 (Field gt=0)。"""
        client = _client_as(app, _FakeUser(id=1, email="zero@example.com"))
        r = client.post(_WITHDRAW_PATH, json=_payload(amount_usdc="0"))
        assert r.status_code == 422

    def test_amount_negative_returns_422(self, app: FastAPI) -> None:
        """amount_usdc < 0 → 422 (Field gt=0)。"""
        client = _client_as(app, _FakeUser(id=1, email="neg@example.com"))
        r = client.post(_WITHDRAW_PATH, json=_payload(amount_usdc="-1"))
        assert r.status_code == 422

    def test_network_not_base_returns_422(self, app: FastAPI) -> None:
        """network != "base" → 422。"""
        client = _client_as(app, _FakeUser(id=1, email="net@example.com"))
        r = client.post(_WITHDRAW_PATH, json=_payload(network="ethereum"))
        assert r.status_code == 422

    def test_create_returns_201_and_decimal_as_string(self, app: FastAPI) -> None:
        """新規記録 → 201 + amount_usdc は文字列で返る (Decimal シリアライズ, float 不使用)。

        CLAUDE.md Security: API レスポンスの Decimal は文字列で返却。
        注: SQLite Numeric は float 格納のため高精度の round-trip は本テスト DB では
        担保できない (本番 PostgreSQL Numeric は保持)。ここでは
        (1) レスポンスが文字列であること (Decimal 経由) と
        (2) 単純な値が等価で round-trip すること を検証する。
        """
        client = _client_as(app, _FakeUser(id=1, email="ok@example.com"))
        amount = "100.5"
        r = client.post(_WITHDRAW_PATH, json=_payload(amount_usdc=amount))
        assert r.status_code == 201
        body = r.json()
        # Decimal は JSON 文字列で返る (数値型でない = float 誤差混入なし)
        assert isinstance(body["amount_usdc"], str)
        assert Decimal(body["amount_usdc"]) == Decimal(amount)
        assert body["tx_hash"] == _VALID_TX
        assert body["network"] == "base"
        assert body["status"] == "completed"

    def test_idempotent_same_user_same_tx_returns_200(self, app: FastAPI) -> None:
        """同一ユーザー同一 tx_hash 再 POST → 200 (冪等)。"""
        client = _client_as(app, _FakeUser(id=1, email="idem@example.com"))
        first = client.post(_WITHDRAW_PATH, json=_payload())
        assert first.status_code == 201
        first_id = first.json()["id"]

        second = client.post(_WITHDRAW_PATH, json=_payload())
        assert second.status_code == 200
        # 既存レコードがそのまま返る (新規作成されない)
        assert second.json()["id"] == first_id

    def test_other_user_tx_conflict_returns_409(self, app: FastAPI) -> None:
        """別ユーザーが同一 tx_hash を上書きしようとする → 409。"""
        client_a = _client_as(app, _FakeUser(id=1, email="usera@example.com"))
        r1 = client_a.post(_WITHDRAW_PATH, json=_payload())
        assert r1.status_code == 201

        client_b = _client_as(app, _FakeUser(id=2, email="userb@example.com"))
        r2 = client_b.post(_WITHDRAW_PATH, json=_payload())
        assert r2.status_code == 409

    def test_list_returns_only_own_withdrawals(self, app: FastAPI) -> None:
        """GET は自分の出金のみ返す。"""
        client_a = _client_as(app, _FakeUser(id=1, email="lista@example.com"))
        client_a.post(_WITHDRAW_PATH, json=_payload(tx_hash=_VALID_TX))

        client_b = _client_as(app, _FakeUser(id=2, email="listb@example.com"))
        client_b.post(_WITHDRAW_PATH, json=_payload(tx_hash=_VALID_TX_2))

        # user A の一覧には自分の 1 件のみ
        client_a = _client_as(app, _FakeUser(id=1, email="lista@example.com"))
        ra = client_a.get(_WITHDRAW_PATH)
        assert ra.status_code == 200
        items_a = ra.json()["items"]
        assert len(items_a) == 1
        assert items_a[0]["tx_hash"] == _VALID_TX


def test_route_404_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENABLE_WITHDRAWALS 未設定 → route 未登録 → 404 (money gate 既定 off)。"""
    monkeypatch.delenv("ENABLE_WITHDRAWALS", raising=False)
    client = TestClient(create_app())
    r = client.post(_WITHDRAW_PATH, json=_payload())
    assert r.status_code == 404
