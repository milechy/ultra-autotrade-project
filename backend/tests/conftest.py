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


def _ensure_project_root_in_sys_path() -> None:
    # This file is located at: backend/tests/conftest.py
    # parents[1] -> backend/
    project_root = Path(__file__).resolve().parents[1]
    project_root_str = str(project_root)

    if project_root_str not in sys.path:
        # Insert at the beginning so it has priority over site-packages, etc.
        sys.path.insert(0, project_root_str)


def _ensure_test_env_vars() -> None:
    """
    Set dummy environment variables required for tests.

    These values are only for local testing and do NOT contain real secrets.
    In real environments, proper values should be provided via .env or system env.
    """
    os.environ.setdefault("NOTION_API_KEY", "dummy-notion-api-key-for-tests")
    os.environ.setdefault("NOTION_DATABASE_ID", "dummy-notion-db-id-for-tests")
    # 将来必要になりそうなキーも、必要に応じてここに追加していける


_ensure_project_root_in_sys_path()
_ensure_test_env_vars()

