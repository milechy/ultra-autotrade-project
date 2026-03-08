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
from pathlib import Path

import pytest


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
