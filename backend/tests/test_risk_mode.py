# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_risk_mode.py
"""F-3: RiskMode enum / 日本語ラベル / Phase 1 制限 / API endpoint テスト。

関連:
- docs/45_fee_model_v10_migration_plan.md §1.3
- docs/47_users_risk_mode_migration_plan.md
- backend/app/auth/models.py (RiskMode + dictionaries)
- backend/app/auth/router.py (PUT /auth/risk-mode + GET /auth/risk-modes)
"""

import os
import tempfile
from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["JWT_SECRET_KEY"] = "test-secret-key-risk-mode"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["INITIAL_ADMIN_EMAIL"] = "risk_admin@example.com"

from app.auth.models import (  # noqa: E402
    PHASE_1_ALLOWED_RISK_MODES,
    RISK_MODE_JP_LABELS,
    RISK_MODE_PHASE,
    RISK_MODE_PROTOCOLS,
    RISK_MODE_SUBSCRIPTION_RATES,
    RiskMode,
    _allowed_risk_modes_from_env,
    get_risk_mode_label,
)
from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# Pure unit tests (no DB needed)
# ---------------------------------------------------------------------------


class TestRiskModeEnum:
    """RiskMode enum の値が v9 内部値と一致することを保証する (リネーム禁止)。"""

    def test_conservative_value_is_lowercase(self) -> None:
        assert RiskMode.CONSERVATIVE.value == "conservative"

    def test_balanced_value_is_lowercase(self) -> None:
        assert RiskMode.BALANCED.value == "balanced"

    def test_aggressive_value_is_lowercase(self) -> None:
        assert RiskMode.AGGRESSIVE.value == "aggressive"

    def test_all_three_values(self) -> None:
        assert {m.value for m in RiskMode} == {"conservative", "balanced", "aggressive"}


class TestRiskModeJpLabels:
    """日本語ラベル辞書テスト。"""

    def test_all_modes_have_japanese_label(self) -> None:
        for mode in RiskMode:
            assert mode in RISK_MODE_JP_LABELS
            assert RISK_MODE_JP_LABELS[mode] != ""

    def test_jp_labels_match_v10_spec(self) -> None:
        assert RISK_MODE_JP_LABELS[RiskMode.CONSERVATIVE] == "ローリスク"
        assert RISK_MODE_JP_LABELS[RiskMode.BALANCED] == "ミドルリスク"
        assert RISK_MODE_JP_LABELS[RiskMode.AGGRESSIVE] == "ハイリスク"

    def test_get_risk_mode_label_for_known_value(self) -> None:
        assert get_risk_mode_label("conservative") == "ローリスク"
        assert get_risk_mode_label("balanced") == "ミドルリスク"
        assert get_risk_mode_label("aggressive") == "ハイリスク"

    def test_get_risk_mode_label_for_null_falls_back_to_lowrisk(self) -> None:
        assert get_risk_mode_label(None) == "ローリスク"
        assert get_risk_mode_label("") == "ローリスク"

    def test_get_risk_mode_label_for_unknown_falls_back_to_lowrisk(self) -> None:
        assert get_risk_mode_label("unknown_mode") == "ローリスク"


class TestPhase1RiskMode:
    """Phase 1 制限定数のテスト。"""

    def test_phase_1_only_allows_conservative(self) -> None:
        assert RiskMode.CONSERVATIVE in PHASE_1_ALLOWED_RISK_MODES
        assert RiskMode.BALANCED not in PHASE_1_ALLOWED_RISK_MODES
        assert RiskMode.AGGRESSIVE not in PHASE_1_ALLOWED_RISK_MODES

    def test_phase_assignment(self) -> None:
        assert RISK_MODE_PHASE[RiskMode.CONSERVATIVE] == 1
        assert RISK_MODE_PHASE[RiskMode.BALANCED] == 2
        assert RISK_MODE_PHASE[RiskMode.AGGRESSIVE] == 2


class TestAllowedRiskModesFromEnv:
    """``ALLOWED_RISK_MODES`` env による解禁制御（環境ごとに開けるための仕組み）。"""

    def test_unset_defaults_to_conservative_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """**未設定なら従来どおり閉じたまま**（本番の既定挙動が変わらないこと）。"""
        monkeypatch.delenv("ALLOWED_RISK_MODES", raising=False)
        assert _allowed_risk_modes_from_env() == frozenset({RiskMode.CONSERVATIVE})

    def test_blank_defaults_to_conservative_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOWED_RISK_MODES", "   ")
        assert _allowed_risk_modes_from_env() == frozenset({RiskMode.CONSERVATIVE})

    def test_opens_aggressive_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """staging だけ aggressive を開ける（本番 env は未設定のまま閉じる）。"""
        monkeypatch.setenv("ALLOWED_RISK_MODES", "conservative,aggressive")
        modes = _allowed_risk_modes_from_env()
        assert modes == frozenset({RiskMode.CONSERVATIVE, RiskMode.AGGRESSIVE})

    def test_conservative_always_included(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """conservative を書き忘れても常に選べる（全モードを塞いで詰まないため）。"""
        monkeypatch.setenv("ALLOWED_RISK_MODES", "aggressive")
        assert RiskMode.CONSERVATIVE in _allowed_risk_modes_from_env()

    def test_unknown_value_ignored_not_opened(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """typo は無視する（意図せず解禁が広がらない fail-safe）。"""
        monkeypatch.setenv("ALLOWED_RISK_MODES", "aggresive,BOGUS")  # 綴り誤り
        assert _allowed_risk_modes_from_env() == frozenset({RiskMode.CONSERVATIVE})

    def test_case_and_space_tolerant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOWED_RISK_MODES", " AGGRESSIVE , balanced ")
        assert _allowed_risk_modes_from_env() == frozenset(
            {RiskMode.CONSERVATIVE, RiskMode.AGGRESSIVE, RiskMode.BALANCED}
        )


class TestRiskModeMetadata:
    """v10 spec §1 の数値・プロトコル定義との一致テスト。"""

    def test_subscription_rates_match_spec(self) -> None:
        assert RISK_MODE_SUBSCRIPTION_RATES[RiskMode.CONSERVATIVE] == Decimal("0")
        assert RISK_MODE_SUBSCRIPTION_RATES[RiskMode.BALANCED] == Decimal("0.003")
        assert RISK_MODE_SUBSCRIPTION_RATES[RiskMode.AGGRESSIVE] == Decimal("0.010")

    def test_subscription_rates_cover_all_modes(self) -> None:
        assert set(RISK_MODE_SUBSCRIPTION_RATES.keys()) == set(RiskMode)

    def test_protocols_conservative_aave_only(self) -> None:
        assert RISK_MODE_PROTOCOLS[RiskMode.CONSERVATIVE] == frozenset({"aave"})

    def test_protocols_balanced_includes_lido(self) -> None:
        assert "aave" in RISK_MODE_PROTOCOLS[RiskMode.BALANCED]
        assert "lido" in RISK_MODE_PROTOCOLS[RiskMode.BALANCED]

    def test_protocols_aggressive_includes_pendle(self) -> None:
        assert "aave" in RISK_MODE_PROTOCOLS[RiskMode.AGGRESSIVE]
        assert "lido" in RISK_MODE_PROTOCOLS[RiskMode.AGGRESSIVE]
        assert "pendle" in RISK_MODE_PROTOCOLS[RiskMode.AGGRESSIVE]


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
    # 他のテスト (test_auth.py 等) が INITIAL_ADMIN_EMAIL を上書きする可能性があるため
    # fixture スコープで再設定する。これがないと先に走ったテストの値が残り、
    # 初回登録が admin にならず login 時に access_token が返らない。
    os.environ["INITIAL_ADMIN_EMAIL"] = "risk_admin@example.com"
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _register_and_login(
    client: TestClient,
    email: str = "risk_admin@example.com",
    username: str = "riskadmin",
    password: str = "password123",
) -> str:
    client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    r = client.post("/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


class TestRiskModeUpdatePhase1:
    """PUT /auth/risk-mode の Phase 1 制限テスト。"""

    def test_update_to_conservative_returns_200(self, client: TestClient) -> None:
        token = _register_and_login(client)
        r = client.put(
            "/auth/risk-mode",
            json={"mode": "conservative"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "conservative"
        assert body["label"] == "ローリスク"

    def test_update_to_balanced_returns_403_with_japanese(self, client: TestClient) -> None:
        token = _register_and_login(client)
        r = client.put(
            "/auth/risk-mode",
            json={"mode": "balanced"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        assert "ミドルリスク" in r.json()["detail"]
        assert "Phase 2" in r.json()["detail"]

    def test_update_to_aggressive_returns_403_with_japanese(self, client: TestClient) -> None:
        token = _register_and_login(client)
        r = client.put(
            "/auth/risk-mode",
            json={"mode": "aggressive"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        assert "ハイリスク" in r.json()["detail"]
        assert "Phase 2" in r.json()["detail"]

    def test_update_to_invalid_value_returns_422_from_pydantic(self, client: TestClient) -> None:
        # Pydantic pattern validation で 422 になる (Phase 1 検査前に弾かれる)
        token = _register_and_login(client)
        r = client.put(
            "/auth/risk-mode",
            json={"mode": "extreme"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422


class TestRiskModesListEndpoint:
    """GET /auth/risk-modes (新規) の振る舞いテスト。"""

    def test_requires_auth(self, client: TestClient) -> None:
        r = client.get("/auth/risk-modes")
        assert r.status_code == 401

    def test_returns_three_modes(self, client: TestClient) -> None:
        token = _register_and_login(client)
        r = client.get(
            "/auth/risk-modes",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "modes" in body
        assert len(body["modes"]) == 3

    def test_modes_payload_structure(self, client: TestClient) -> None:
        token = _register_and_login(client)
        r = client.get(
            "/auth/risk-modes",
            headers={"Authorization": f"Bearer {token}"},
        )
        modes = {m["mode"]: m for m in r.json()["modes"]}

        assert modes["conservative"]["label"] == "ローリスク"
        assert modes["conservative"]["phase"] == 1
        assert modes["conservative"]["allowed_in_phase_1"] is True
        assert modes["conservative"]["subscription_rate"] == "0"
        assert modes["conservative"]["protocols"] == ["aave"]

        assert modes["balanced"]["label"] == "ミドルリスク"
        assert modes["balanced"]["phase"] == 2
        assert modes["balanced"]["allowed_in_phase_1"] is False
        assert modes["balanced"]["subscription_rate"] == "0.003"
        assert "lido" in modes["balanced"]["protocols"]

        assert modes["aggressive"]["label"] == "ハイリスク"
        assert modes["aggressive"]["phase"] == 2
        assert modes["aggressive"]["allowed_in_phase_1"] is False
        assert modes["aggressive"]["subscription_rate"] == "0.010"
        assert "pendle" in modes["aggressive"]["protocols"]


class TestUserResponseRiskModeLabel:
    """/auth/me レスポンスの risk_mode_label computed field テスト。"""

    def test_me_includes_risk_mode_label(self, client: TestClient) -> None:
        token = _register_and_login(client)
        r = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "risk_mode" in body
        assert "risk_mode_label" in body
        # 新規ユーザーはデフォルト conservative → ローリスク
        assert body["risk_mode"] == "conservative"
        assert body["risk_mode_label"] == "ローリスク"
