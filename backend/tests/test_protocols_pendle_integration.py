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

注意: Phase 4 実機検証 (staging-new) は P0-1 fix (LIDO_SANDBOX=false in staging) 完了後。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# テスト対象 router
from app.protocols.pendle.router import router as pendle_router
from app.protocols.risk.router import router as health_router

DUMMY_MARKET_ADDRESS = "0x" + "ab" * 20


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pendle_app() -> FastAPI:
    """Pendle 関連エンドポイントのみを持つ最小 FastAPI アプリ (DB 不要)。"""
    app = FastAPI()
    app.include_router(pendle_router)
    app.include_router(health_router)
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
# 7. staging 環境 DummyClient 禁止ガード
# ---------------------------------------------------------------------------


class TestStagingGuard:
    def test_staging_env_with_sandbox_returns_5xx(
        self, pendle_app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """APP_ENV=staging + PENDLE_SANDBOX=true は 5xx を返す。

        TestClient を raise_server_exceptions=False で生成して
        RuntimeError が HTTP 500 にマップされることを確認する。
        """
        monkeypatch.setenv("APP_ENV", "staging")
        staging_client = TestClient(pendle_app, raise_server_exceptions=False)
        resp = staging_client.get("/api/protocols/pendle/markets")
        assert resp.status_code in (500, 503)
