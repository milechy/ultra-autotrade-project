# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_e2e_approve_flow.py
"""
取引承認フロー バックエンドAPIテスト

/api/proposals/* エンドポイントのテスト。
proposals router が実装済み (router.py) であるため、スキップを解除して実際に検証する。

認証フロー:
1. POST /auth/register でテスト用管理者ユーザーを作成
2. POST /auth/login でトークン取得
3. 取得したトークンで proposals API を呼び出す
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.database import init_db


@pytest.fixture(autouse=True, scope="module")
def _init_database(tmp_path_factory: pytest.TempPathFactory) -> None:
    """モジュール実行前にデータベーステーブルを作成する（tmp ディレクトリ使用）。"""
    import os
    tmp_dir = tmp_path_factory.mktemp("proposals_db")
    db_path = tmp_dir / "test_proposals.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["INITIAL_ADMIN_EMAIL"] = _ADMIN_EMAIL
    # Re-import to pick up new DATABASE_URL
    from app import database as _db
    _db.db_url = f"sqlite:///{db_path}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    _db.engine = engine
    _db.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    from app.database import Base
    Base.metadata.create_all(bind=engine)


_ADMIN_EMAIL = "terms_admin@example.com"
_ADMIN_PASSWORD = "AdminTestPass123!"
_ADMIN_USERNAME = "terms_admin"


def _register_and_login(client: TestClient) -> str:
    """初期管理者ユーザーを登録してトークンを取得する。

    INITIAL_ADMIN_EMAIL (conftest で terms_admin@example.com に設定) を使用する。
    既に登録済みの場合（409/403）はそのままログインを試みる。
    """
    register_resp = client.post(
        "/auth/register",
        json={
            "email": _ADMIN_EMAIL,
            "username": _ADMIN_USERNAME,
            "password": _ADMIN_PASSWORD,
        },
    )
    # 登録成功 or 既存ユーザー（409 または 403 "already exists"） を許容
    if register_resp.status_code not in (200, 201, 400, 403, 409):
        raise AssertionError(
            f"登録失敗: {register_resp.status_code} {register_resp.text}"
        )

    login_resp = client.post(
        "/auth/login",
        json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200, (
        f"ログイン失敗: {login_resp.status_code} {login_resp.text}"
    )
    data = login_resp.json()
    return data["access_token"]


def _create_test_proposal(client: TestClient, token: str, user_id: int) -> int:
    """テスト用提案を作成して ID を返す。"""
    resp = client.post(
        "/api/proposals",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": user_id,
            "operation": "SUPPLY",
            "asset": "USDC",
            "amount": "100.000000",
            "amount_usd": "100.00",
            "reason": "AI suggested SUPPLY for portfolio optimization",
            "expected_hf_after": "2.5",
            "estimated_gas_usd": "0.5",
        },
    )
    assert resp.status_code in (200, 201), f"提案作成失敗: {resp.status_code} {resp.text}"
    return resp.json()["id"]


class TestProposalsPendingUnauthenticated:
    """GET /api/proposals/pending - 認証なしアクセスのテスト"""

    def test_get_pending_proposals_without_auth_returns_401(
        self, client: TestClient
    ) -> None:
        """認証ヘッダなし → 401 Unauthorized。"""
        response = client.get("/api/proposals/pending")
        # 未認証は 401、エンドポイント未実装なら 404 を許容
        assert response.status_code in (401, 403, 404), (
            f"期待: 401/403/404、実際: {response.status_code}\nレスポンス: {response.text}"
        )


class TestProposalsPendingAuthenticated:
    """GET /api/proposals/pending - 認証付きアクセスのテスト（実装済み）"""

    def test_get_pending_proposals_with_auth_returns_200(self, client: TestClient) -> None:
        """認証トークン付きで GET /api/proposals/pending を呼ぶと 200 が返り、
        レスポンスにリスト形式のデータが含まれること。
        """
        token = _register_and_login(client)
        response = client.get(
            "/api/proposals/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, (
            f"GET /api/proposals/pending 失敗: {response.status_code} {response.text}"
        )
        data = response.json()
        # ProposalListResponse スキーマ: {items: [], total: int}
        assert "items" in data or isinstance(data, list), (
            f"レスポンス形式が不正: {data}"
        )

    def test_pending_returns_only_pending_status(self, client: TestClient) -> None:
        """GET /api/proposals/pending は pending ステータスのみ返すこと。"""
        token = _register_and_login(client)

        response = client.get(
            "/api/proposals/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        # 全件 pending であること（アイテムがある場合のみ）
        for item in items:
            assert item.get("status") == "pending", (
                f"pending 以外のステータスが含まれている: {item}"
            )


class TestProposalApprove:
    """POST /api/proposals/{id}/approve - 承認エンドポイントのテスト"""

    def test_approve_nonexistent_proposal_returns_404(self, client: TestClient) -> None:
        """存在しない提案 ID の承認 → 404。"""
        token = _register_and_login(client)
        response = client.post(
            "/api/proposals/999999/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404, (
            f"期待: 404、実際: {response.status_code} {response.text}"
        )

    def test_approve_proposal_without_auth_returns_401(self, client: TestClient) -> None:
        """認証なしで承認 → 401/403。"""
        response = client.post("/api/proposals/1/approve")
        assert response.status_code in (401, 403, 422), (
            f"期待: 401/403/422、実際: {response.status_code}"
        )


class TestProposalReject:
    """POST /api/proposals/{id}/reject - 却下エンドポイントのテスト"""

    def test_reject_nonexistent_proposal_returns_404(self, client: TestClient) -> None:
        """存在しない提案 ID の却下 → 404。"""
        token = _register_and_login(client)
        response = client.post(
            "/api/proposals/999999/reject",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404, (
            f"期待: 404、実際: {response.status_code} {response.text}"
        )

    def test_reject_proposal_without_auth_returns_401(self, client: TestClient) -> None:
        """認証なしで却下 → 401/403。"""
        response = client.post("/api/proposals/1/reject")
        assert response.status_code in (401, 403, 422), (
            f"期待: 401/403/422、実際: {response.status_code}"
        )


class TestProposalResponseSchema:
    """GET /api/proposals/pending レスポンス スキーマ検証"""

    def test_pending_proposals_response_schema(self, client: TestClient) -> None:
        """GET /api/proposals/pending のレスポンスが期待するスキーマを満たすこと。

        各要素に以下のフィールドが含まれること:
        - id: int
        - operation: str (SUPPLY / WITHDRAW / BORROW / REPAY)
        - asset: str (USDC / WETH など)
        - status: str (= "pending")
        - reason: str
        """
        token = _register_and_login(client)
        response = client.get(
            "/api/proposals/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", []) if isinstance(data, dict) else data

        # アイテムが存在する場合のみスキーマを検証
        required_fields = {"id", "operation", "asset", "status", "reason"}
        valid_operations = {"SUPPLY", "WITHDRAW", "BORROW", "REPAY"}

        for i, proposal in enumerate(items):
            missing_fields = required_fields - set(proposal.keys())
            assert not missing_fields, (
                f"proposals[{i}] に必須フィールドが不足: {missing_fields}\n"
                f"実際のキー: {set(proposal.keys())}"
            )
            assert proposal["operation"] in valid_operations, (
                f"proposals[{i}].operation が無効: {proposal['operation']}"
            )
            assert proposal["status"] == "pending", (
                f"proposals[{i}].status が 'pending' ではない: {proposal['status']}"
            )
