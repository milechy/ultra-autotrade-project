# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_protocols_pendle_integration.py
"""Pendle Finance API 統合テスト。

DummyPendleClient / DummyLidoClient を用いて Router → Service → Client の
全レイヤーを HTTP レベルで検証する。実 RPC / 実 DB 不使用。

カバー範囲:
  1. /api/protocols/pendle/markets         — マーケット一覧
  2. /api/protocols/pendle/market/{addr}   — マーケット詳細
  3. /api/protocols/pendle/mint            — PT/YT ミント (dry_run)
  4. /api/protocols/pendle/redeem          — PT/YT リデーム (dry_run)
  5. /api/protocols/pendle/strategies      — 戦略比較
  6. /api/protocols/health/pendle          — ProtocolMonitor 正常パス
  7. 入力バリデーション (422)
  8. staging 環境での DummyClient 禁止ガード (500/503)
  9. /api/protocols/pendle/positions       — ポジション一覧 (RBAC + Decimal 文字列化)

注意: Phase 4 実機検証 (staging-new) は P0-1 fix (LIDO_SANDBOX=false in staging) 完了後。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

# テスト対象 router
from app.auth.dependencies import require_admin
from app.protocols.pendle.router import router as pendle_router
from app.protocols.risk.router import router as health_router

DUMMY_MARKET_ADDRESS = "0x" + "ab" * 20


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _admin_user() -> MagicMock:
    u = MagicMock()
    u.id = 1
    u.role = "admin"
    u.is_active = True
    return u


@pytest.fixture(scope="module")
def pendle_app() -> FastAPI:
    """Pendle 関連エンドポイントのみを持つ最小 FastAPI アプリ (DB 不要)。

    positions エンドポイントが require_admin を依存するため、admin override を注入済み。
    """
    app = FastAPI()
    app.include_router(pendle_router)
    app.include_router(health_router)
    app.dependency_overrides[require_admin] = lambda: _admin_user()
    return app


@pytest.fixture(autouse=True)
def sandbox_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """development + sandbox モードでテストを実行する。

    APP_ENV を未設定にすると get_pendle_client / get_lido_client 内の
    デフォルト "development" に倒れ、LIDO_SANDBOX=true + PENDLE_SANDBOX=true でも
    DummyClient が許可される。
    """
    monkeypatch.setenv("PENDLE_SANDBOX", "true")
    monkeypatch.setenv("LIDO_SANDBOX", "true")
    monkeypatch.delenv("APP_ENV", raising=False)


@pytest.fixture()
def client(pendle_app: FastAPI, sandbox_env: None) -> TestClient:  # noqa: ARG001
    return TestClient(pendle_app)


# ---------------------------------------------------------------------------
# 1. マーケット一覧 GET /api/protocols/pendle/markets
# ---------------------------------------------------------------------------


class TestMarketsEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/protocols/pendle/markets")
        assert resp.status_code == 200

    def test_returns_list_with_one_market(self, client: TestClient) -> None:
        data = client.get("/api/protocols/pendle/markets").json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_market_has_required_fields(self, client: TestClient) -> None:
        market = client.get("/api/protocols/pendle/markets").json()[0]
        for field in ("market_address", "implied_apy", "pt_price", "yt_price", "tvl_usd"):
            assert field in market, f"フィールド '{field}' が見つかりません"

    def test_implied_apy_is_numeric_string(self, client: TestClient) -> None:
        """Decimal は JSON 上で文字列シリアライズされること。"""
        market = client.get("/api/protocols/pendle/markets").json()[0]
        float(market["implied_apy"])  # 数値変換可能であることを確認


# ---------------------------------------------------------------------------
# 2. マーケット詳細 GET /api/protocols/pendle/market/{address}
# ---------------------------------------------------------------------------


class TestMarketDetailEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get(f"/api/protocols/pendle/market/{DUMMY_MARKET_ADDRESS}")
        assert resp.status_code == 200

    def test_market_address_matches_request(self, client: TestClient) -> None:
        data = client.get(f"/api/protocols/pendle/market/{DUMMY_MARKET_ADDRESS}").json()
        assert data["market_address"] == DUMMY_MARKET_ADDRESS

    def test_underlying_asset_is_steth(self, client: TestClient) -> None:
        data = client.get(f"/api/protocols/pendle/market/{DUMMY_MARKET_ADDRESS}").json()
        assert data["underlying_asset"] == "stETH"

    def test_days_to_maturity_is_positive(self, client: TestClient) -> None:
        data = client.get(f"/api/protocols/pendle/market/{DUMMY_MARKET_ADDRESS}").json()
        assert int(data["days_to_maturity"]) > 0


# ---------------------------------------------------------------------------
# 3. ミント POST /api/protocols/pendle/mint
# ---------------------------------------------------------------------------


class TestMintEndpoint:
    @staticmethod
    def _payload(strategy: str = "pt_fixed", dry_run: bool = True) -> dict[str, object]:
        return {
            "asset": "stETH",
            "amount": "1.0",
            "strategy": strategy,
            "market_address": DUMMY_MARKET_ADDRESS,
            "dry_run": dry_run,
        }

    def test_pt_fixed_dry_run_returns_200(self, client: TestClient) -> None:
        resp = client.post("/api/protocols/pendle/mint", json=self._payload())
        assert resp.status_code == 200

    def test_pt_fixed_operation_is_mint_pt(self, client: TestClient) -> None:
        data = client.post("/api/protocols/pendle/mint", json=self._payload()).json()
        assert data["operation"] == "MINT_PT"

    def test_pt_fixed_dry_run_flag_is_true(self, client: TestClient) -> None:
        data = client.post("/api/protocols/pendle/mint", json=self._payload()).json()
        assert data["dry_run"] is True

    def test_pt_fixed_tx_hash_is_null_on_dry_run(self, client: TestClient) -> None:
        """dry_run=True では tx_hash が null であること (オンチェーン未実行)。"""
        data = client.post("/api/protocols/pendle/mint", json=self._payload()).json()
        assert data["tx_hash"] is None

    def test_yt_leverage_dry_run_returns_200(self, client: TestClient) -> None:
        resp = client.post("/api/protocols/pendle/mint", json=self._payload("yt_leverage"))
        assert resp.status_code == 200

    def test_yt_leverage_operation_is_mint_yt(self, client: TestClient) -> None:
        data = client.post("/api/protocols/pendle/mint", json=self._payload("yt_leverage")).json()
        assert data["operation"] == "MINT_YT"

    def test_amount_zero_returns_422(self, client: TestClient) -> None:
        payload = {**self._payload(), "amount": "0"}
        assert client.post("/api/protocols/pendle/mint", json=payload).status_code == 422

    def test_invalid_strategy_returns_422(self, client: TestClient) -> None:
        payload = {**self._payload(), "strategy": "invalid_strategy"}
        assert client.post("/api/protocols/pendle/mint", json=payload).status_code == 422


# ---------------------------------------------------------------------------
# 4. リデーム POST /api/protocols/pendle/redeem
# ---------------------------------------------------------------------------


class TestRedeemEndpoint:
    @staticmethod
    def _payload(token_type: str = "PT") -> dict[str, object]:
        return {
            "token_type": token_type,
            "amount": "1.0",
            "market_address": DUMMY_MARKET_ADDRESS,
            "dry_run": True,
        }

    def test_redeem_pt_before_maturity_returns_503(self, client: TestClient) -> None:
        """DummyClient は days_to_maturity > 0 を返すため PT リデームは満期前エラーになる。"""
        assert (
            client.post("/api/protocols/pendle/redeem", json=self._payload("PT")).status_code == 503
        )

    def test_redeem_pt_before_maturity_error_message(self, client: TestClient) -> None:
        data = client.post("/api/protocols/pendle/redeem", json=self._payload("PT")).json()
        assert "maturity" in data.get("detail", "").lower()

    def test_redeem_yt_operation_is_redeem_yt(self, client: TestClient) -> None:
        data = client.post("/api/protocols/pendle/redeem", json=self._payload("YT")).json()
        assert data["operation"] == "REDEEM_YT"

    def test_redeem_yt_returns_200(self, client: TestClient) -> None:
        assert (
            client.post("/api/protocols/pendle/redeem", json=self._payload("YT")).status_code == 200
        )

    def test_invalid_token_type_returns_422(self, client: TestClient) -> None:
        payload = {**self._payload(), "token_type": "SY"}  # Literal["PT","YT"] 外
        assert client.post("/api/protocols/pendle/redeem", json=payload).status_code == 422


# ---------------------------------------------------------------------------
# 5. 戦略比較 GET /api/protocols/pendle/strategies
# ---------------------------------------------------------------------------


class TestStrategiesEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/protocols/pendle/strategies?amount=1.0")
        assert resp.status_code == 200

    def test_has_best_strategy_and_strategies_fields(self, client: TestClient) -> None:
        data = client.get("/api/protocols/pendle/strategies?amount=1.0").json()
        assert "best_strategy" in data
        assert "strategies" in data

    def test_strategies_count_is_at_least_two(self, client: TestClient) -> None:
        """複数の戦略比較オプションを返すこと (aave_only / lido_aave / lido_pendle_pt 等)。"""
        data = client.get("/api/protocols/pendle/strategies?amount=1.0").json()
        assert len(data["strategies"]) >= 2

    def test_invalid_amount_returns_400(self, client: TestClient) -> None:
        resp = client.get("/api/protocols/pendle/strategies?amount=not_a_number")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 6. プロトコルヘルス GET /api/protocols/health/pendle
# ---------------------------------------------------------------------------


class TestProtocolHealthPendleEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/protocols/health/pendle")
        assert resp.status_code == 200

    def test_protocol_field_is_pendle(self, client: TestClient) -> None:
        data = client.get("/api/protocols/health/pendle").json()
        assert data["protocol"] == "pendle"

    def test_risk_level_is_valid(self, client: TestClient) -> None:
        data = client.get("/api/protocols/health/pendle").json()
        assert data["risk_level"] in ("low", "medium", "high", "critical")

    def test_is_operational_is_bool(self, client: TestClient) -> None:
        data = client.get("/api/protocols/health/pendle").json()
        assert isinstance(data["is_operational"], bool)


# ---------------------------------------------------------------------------
# 7. 環境別 DummyClient 許可ガード (Phase 1: staging 許可 / production 禁止)
# ---------------------------------------------------------------------------


class TestEnvGuard:
    def test_staging_env_with_sandbox_returns_200(
        self, pendle_app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Phase 1 期間中、APP_ENV=staging + PENDLE_SANDBOX=true は DummyClient で 200 を返す（docs/13 §1.4）。"""
        monkeypatch.setenv("APP_ENV", "staging")
        staging_client = TestClient(pendle_app, raise_server_exceptions=False)
        resp = staging_client.get("/api/protocols/pendle/markets")
        assert resp.status_code == 200

    def test_production_env_with_sandbox_returns_5xx(
        self, pendle_app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """APP_ENV=production + PENDLE_SANDBOX=true は 5xx を返す。"""
        monkeypatch.setenv("APP_ENV", "production")
        staging_client = TestClient(pendle_app, raise_server_exceptions=False)
        resp = staging_client.get("/api/protocols/pendle/markets")
        assert resp.status_code in (500, 503)


# ---------------------------------------------------------------------------
# 9. ポジション一覧 GET /api/protocols/pendle/positions
# ---------------------------------------------------------------------------


class TestPositionsEndpoint:
    """GET /api/protocols/pendle/positions のテスト。

    RBAC・Decimal 文字列化・フロント契約 (frontend/lib/api/pendle.ts) を検証する。
    """

    def test_returns_200_with_admin(self, client: TestClient) -> None:
        """admin override 有り（pendle_app fixture）で 200 を返すこと。"""
        resp = client.get("/api/protocols/pendle/positions")
        assert resp.status_code == 200

    def test_response_has_positions_and_total(self, client: TestClient) -> None:
        """レスポンスに positions と total_value_usd フィールドが存在すること。"""
        data = client.get("/api/protocols/pendle/positions").json()
        assert "positions" in data
        assert "total_value_usd" in data

    def test_sandbox_returns_one_position(self, client: TestClient) -> None:
        """sandbox モードではダミー 1 件のポジションを返すこと。"""
        data = client.get("/api/protocols/pendle/positions").json()
        assert len(data["positions"]) == 1

    def test_decimal_fields_are_strings(self, client: TestClient) -> None:
        """Decimal フィールド (pt_amount / yt_amount / pt_price_usd / yt_price_usd / implied_apy) が
        文字列で返却されること。（フロントエンド契約: Number(str).toFixed() で受ける）"""
        pos = client.get("/api/protocols/pendle/positions").json()["positions"][0]
        for field in ("pt_amount", "yt_amount", "pt_price_usd", "yt_price_usd", "implied_apy"):
            assert isinstance(pos[field], str), f"{field} が文字列ではありません"
            # 数値変換可能であることも確認
            float(pos[field])

    def test_total_value_usd_is_string(self, client: TestClient) -> None:
        """total_value_usd が文字列で返却されること。"""
        data = client.get("/api/protocols/pendle/positions").json()
        assert isinstance(data["total_value_usd"], str)
        float(data["total_value_usd"])

    def test_position_has_all_frontend_contract_fields(self, client: TestClient) -> None:
        """フロント契約 (frontend/lib/api/pendle.ts PendlePosition) のフィールドが全て存在すること。"""
        pos = client.get("/api/protocols/pendle/positions").json()["positions"][0]
        required_fields = (
            "id",
            "market_address",
            "underlying_asset",
            "pt_amount",
            "yt_amount",
            "pt_price_usd",
            "yt_price_usd",
            "implied_apy",
            "maturity",
            "days_to_maturity",
            "fetched_at",
        )
        for field in required_fields:
            assert field in pos, f"フロント契約フィールド '{field}' が見つかりません"

    def test_days_to_maturity_is_int(self, client: TestClient) -> None:
        """days_to_maturity が整数で返却されること。"""
        pos = client.get("/api/protocols/pendle/positions").json()["positions"][0]
        assert isinstance(pos["days_to_maturity"], int)

    def test_maturity_is_iso8601(self, client: TestClient) -> None:
        """maturity / fetched_at が ISO8601 文字列であること。"""
        from datetime import datetime

        pos = client.get("/api/protocols/pendle/positions").json()["positions"][0]
        # 例外が出なければ OK
        datetime.fromisoformat(pos["maturity"].replace("Z", "+00:00"))
        datetime.fromisoformat(pos["fetched_at"].replace("Z", "+00:00"))

    def test_rbac_unauthenticated_returns_401_or_403(self, pendle_app: FastAPI) -> None:
        """admin override を外すと 401/403 を返すこと。"""

        def _deny() -> None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
            )

        # 認証拒否用の別アプリを作成（既存 pendle_app の override を汚染しない）
        deny_app = FastAPI()
        deny_app.include_router(pendle_router)
        deny_app.dependency_overrides[require_admin] = _deny
        deny_client = TestClient(deny_app, raise_server_exceptions=False)
        resp = deny_client.get("/api/protocols/pendle/positions")
        assert resp.status_code in (401, 403)
