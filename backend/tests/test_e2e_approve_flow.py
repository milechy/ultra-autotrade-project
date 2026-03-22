# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_e2e_approve_flow.py
"""
取引承認フロー バックエンドAPIテスト（Phase 1）

Phase 1 では /api/proposals/* エンドポイントは未実装。
テスト構造を完成させ、実装時にスキップを外して使えるようにする。
"""

import pytest
from fastapi.testclient import TestClient


def _get_auth_token(client: TestClient) -> str:
    """
    認証トークンを取得するヘルパー関数。

    Note: auth エンドポイントは /api/auth/login または /auth/login の
    可能性があるため、実装確認後にパスを修正すること。
    """
    response = client.post(
        "/api/auth/login",  # または "/auth/login"
        json={"email": "test@example.com", "password": "testpassword"},
    )
    assert response.status_code == 200, f"ログイン失敗: {response.text}"
    data = response.json()
    return data["access_token"]


class TestProposalsPendingUnauthenticated:
    """GET /api/proposals/pending - 認証なしアクセスのテスト"""

    def test_get_pending_proposals_without_auth_returns_401_or_404(
        self, client: TestClient
    ) -> None:
        """認証ヘッダなしでリクエストした場合、401 または 404 が返ること。

        Phase 1 ではエンドポイント自体が未実装（404）の可能性があるため、
        401 と 404 の両方を許容する。
        """
        response = client.get("/api/proposals/pending")
        assert response.status_code in (401, 404), (
            f"期待: 401 または 404、実際: {response.status_code}\nレスポンス: {response.text}"
        )


class TestProposalsPendingAuthenticated:
    """GET /api/proposals/pending - 認証付きアクセスのテスト（Phase 2 実装予定）"""

    @pytest.mark.skip(reason="GET /api/proposals/pending は Phase 2 で実装予定")
    def test_get_pending_proposals_with_auth_returns_200(self, client: TestClient) -> None:
        """認証トークン付きで GET /api/proposals/pending を呼ぶと 200 が返り、
        レスポンスにリスト形式のデータが含まれること。
        """
        token = _get_auth_token(client)
        response = client.get(
            "/api/proposals/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"レスポンスがリストではない: {type(data)}"


class TestProposalApprove:
    """POST /api/proposals/{id}/approve - 承認エンドポイントのテスト（Phase 2 実装予定）"""

    @pytest.mark.skip(reason="POST /api/proposals/{id}/approve は Phase 2 で実装予定")
    def test_approve_proposal_with_auth_returns_200(self, client: TestClient) -> None:
        """認証トークン付きで POST /api/proposals/{id}/approve を呼ぶと
        承認処理が実行され、200 とトランザクション情報が返ること。
        """
        token = _get_auth_token(client)
        proposal_id = "prop-001"
        response = client.post(
            f"/api/proposals/{proposal_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        # 承認後は txHash が含まれること
        assert "tx_hash" in data or "txHash" in data, f"txHash フィールドが含まれていない: {data}"


class TestProposalReject:
    """POST /api/proposals/{id}/reject - 却下エンドポイントのテスト（Phase 2 実装予定）"""

    @pytest.mark.skip(reason="POST /api/proposals/{id}/reject は Phase 2 で実装予定")
    def test_reject_proposal_with_auth_returns_200(self, client: TestClient) -> None:
        """認証トークン付きで POST /api/proposals/{id}/reject を呼ぶと
        却下処理が実行され、200 が返ること。
        """
        token = _get_auth_token(client)
        proposal_id = "prop-001"
        response = client.post(
            f"/api/proposals/{proposal_id}/reject",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        # 却下後はステータスが rejected になること
        assert data.get("status") == "rejected", f"status が 'rejected' ではない: {data}"


class TestProposalResponseSchema:
    """GET /api/proposals/pending レスポンス スキーマ検証（Phase 2 実装後に有効化）"""

    @pytest.mark.skip(reason="スキーマ検証は Phase 2 実装後に有効化")
    def test_pending_proposals_response_schema(self, client: TestClient) -> None:
        """GET /api/proposals/pending のレスポンスが期待するスキーマを満たすこと。

        各要素に以下のフィールドが含まれること:
        - id: str
        - operation: str (SUPPLY / WITHDRAW / BORROW / REPAY)
        - asset: str (USDC / WETH など)
        - amount: float または str
        - reason: str (AI判定理由)
        """
        token = _get_auth_token(client)
        response = client.get(
            "/api/proposals/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()

        # レスポンスがリスト型であること
        assert isinstance(data, list), f"レスポンスがリストではない: {type(data)}"

        # 各要素のスキーマを検証
        required_fields = {"id", "operation", "asset", "amount", "reason"}
        for i, proposal in enumerate(data):
            missing_fields = required_fields - set(proposal.keys())
            assert not missing_fields, (
                f"proposals[{i}] に必須フィールドが不足: {missing_fields}\n"
                f"実際のキー: {set(proposal.keys())}"
            )
            # operation は許可された値のみ
            valid_operations = {"SUPPLY", "WITHDRAW", "BORROW", "REPAY"}
            assert proposal["operation"] in valid_operations, (
                f"proposals[{i}].operation が無効: {proposal['operation']}"
            )
