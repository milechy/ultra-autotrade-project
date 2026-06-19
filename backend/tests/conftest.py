# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/conftest.py
"""
Pytest configuration for Ultra AutoTrade backend tests.

- Ensures that the project root (backend/) is added to sys.path
  so that `import app.*` works correctly in tests.
- Ensures required environment variables for tests are set
  with safe dummy values (e.g., NOTION_API_KEY, NOTION_DATABASE_ID).
"""

import os
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp.streams as _aiohttp_streams
import pytest

# aiohttp 3.10+ removed AsyncStreamReaderMixin; vcrpy still needs it.
if not hasattr(_aiohttp_streams, "AsyncStreamReaderMixin"):

    class _AsyncStreamReaderMixin:  # type: ignore[no-redef]
        pass

    _aiohttp_streams.AsyncStreamReaderMixin = _AsyncStreamReaderMixin  # type: ignore[attr-defined]


def _ensure_project_root_in_sys_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project_root_str = str(project_root)

    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


def _ensure_test_env_vars() -> None:
    """
    Set dummy environment variables required for tests.

    These values are only for local testing and do NOT contain real secrets.
    In real environments, proper values should be provided via .env or system env.
    """
    os.environ.setdefault("NOTION_API_KEY", "dummy-notion-api-key-for-tests")
    os.environ.setdefault("NOTION_DATABASE_ID", "dummy-notion-db-id-for-tests")
    os.environ.setdefault("OPENAI_API_KEY", "dummy-openai-key-for-tests")
    os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-anthropic-key-for-tests")
    os.environ.setdefault("BYBIT_API_KEY", "dummy-bybit-key-for-tests")
    os.environ.setdefault("BYBIT_API_SECRET", "dummy-bybit-secret-for-tests")
    os.environ.setdefault("BYBIT_SANDBOX", "true")
    os.environ.setdefault("EXCHANGE_CLIENT_TYPE", "dummy")
    os.environ.setdefault("INITIAL_ADMIN_EMAIL", "terms_admin@example.com")
    os.environ.setdefault("LOGIN_RATE_LIMIT", "1000/minute")
    # 2026-05-01: Web3AaveClient.__init__ で pool_address required 化したため
    # 既存テスト互換用に Sepolia ダミー値を default で供給する。
    # 個別テストで env を明示的に空にする / 別値で上書きすることは可能。
    os.environ.setdefault("AAVE_POOL_ADDRESS", "0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951")
    os.environ.setdefault("AAVE_USDC_ADDRESS", "0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8")


_ensure_project_root_in_sys_path()
_ensure_test_env_vars()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# VCR (pytest-recording) グローバル設定
#
# カセット更新時は以下を実行:
#   VCR_RECORD_MODE=new_episodes pytest tests/test_ai_service.py tests/test_knowledge_service.py
#
# CI では VCR_RECORD_MODE=none が設定されており、実 API は呼ばれない。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CompoundRiskAssessor グローバルモック (workflow 統合テスト保護)
#
# CompoundRiskAssessor は Lido/Pendle のネットワーク呼び出しを行う。
# テスト環境では RPC/API に疎通できず should_evacuate=True (CRITICAL) になるため、
# workflow.process_pending_knowledge() が全件 HOLD を返してしまう。
# autouse fixture でモックし、should_evacuate=False (LOW) を固定する。
# テストで実際の CompoundRiskAssessor 動作を検証する場合は @pytest.mark.real_compound_risk で除外できる。
# ---------------------------------------------------------------------------


def _make_safe_compound_risk_assessment():
    """should_evacuate=False の安全な CompoundRiskAssessment を返す。"""
    from app.protocols.risk.schemas import CompoundRiskAssessment, RiskLevel

    return CompoundRiskAssessment(
        overall_risk=RiskLevel.LOW,
        protocol_risks=[],
        peg_status=None,
        maturity_alerts=[],
        total_exposure_usd=Decimal("0"),
        risk_score=Decimal("10"),
        recommendations=[],
        should_evacuate=False,
        evacuation_reason=None,
    )


@pytest.fixture(autouse=True)
def _mock_compound_risk_assessor(request):
    """CompoundRiskAssessor をモックし、テスト環境でのネットワーク呼び出しをブロックする。

    @pytest.mark.real_compound_risk マーク付きテストはスキップ（実 Assessor を使う）。
    """
    if request.node.get_closest_marker("real_compound_risk"):
        yield
        return

    safe_assessment = _make_safe_compound_risk_assessment()
    mock_assessor = MagicMock()
    mock_assessor.assess = AsyncMock(return_value=safe_assessment)

    with patch(
        "app.protocols.risk.compound_risk.CompoundRiskAssessor",
        return_value=mock_assessor,
    ):
        yield


@pytest.fixture(autouse=True)
def _reset_monitoring_state():
    """共有 MonitoringService シングルトンをテスト毎にリセットする（状態リーク防止）。

    緊急停止など global monitoring 状態を設定するテストが reset を怠ると、後続テストへ
    リークする。スライス0-E2 で _execute_aave_for_proposal が safety gate 経由で
    global monitoring を参照するようになり、このリークが顕在化した。
    state.reset_state() は本用途のために提供されている（state.py docstring 参照）。
    """
    from app.automation.state import reset_state

    reset_state()
    yield
    reset_state()


@pytest.fixture(scope="module")
def vcr_config():
    """VCR グローバル設定。APIキーをカセットから除外する。"""
    return {
        "filter_headers": ["authorization", "x-api-key"],
        "filter_post_data_headers": ["authorization"],
        "record_mode": os.environ.get("VCR_RECORD_MODE", "none"),
        "cassette_library_dir": str(Path(__file__).parent / "cassettes"),
        "decode_compressed_response": True,
    }
