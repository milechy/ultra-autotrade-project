# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/tests/test_scheduler_color_guard.py
"""Blue/Green scheduler color ガードのユニットテスト。

Stream 4 (2026-05-21): BACKEND_COLOR / ACTIVE_BACKEND_COLOR による
scheduler 二重起動防止ロジック (_is_scheduler_enabled) を検証する。
"""

import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-color-guard")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")


# ---------------------------------------------------------------------------
# ヘルパー: _is_scheduler_enabled を隔離して呼び出す
# ---------------------------------------------------------------------------


def _call_is_scheduler_enabled(env: dict) -> bool:
    """指定の env パッチ下で app.main._is_scheduler_enabled() を呼び出す。"""
    # DB 接続等の副作用を回避するため、実際の import は行わず
    # 環境変数を直接パッチして同一モジュールの関数を再評価する。
    with patch.dict(os.environ, env, clear=False):
        # 既にロード済みのモジュールを使う（re-import 不要）
        import app.main as main_module  # noqa: PLC0415

        return main_module._is_scheduler_enabled()


# ---------------------------------------------------------------------------
# テスト: 既存の DISABLE_AI_JUDGMENT_SCHEDULER ロジックが不変であること
# ---------------------------------------------------------------------------


class TestExistingDisableLogicUnchanged:
    """Color ガード追加後も既存の DISABLE/ENABLE ロジックが不変であること。"""

    def test_disable_flag_takes_priority(self) -> None:
        """DISABLE_AI_JUDGMENT_SCHEDULER=1 は color に関係なく False を返す。"""
        env = {
            "DISABLE_AI_JUDGMENT_SCHEDULER": "1",
            "BACKEND_COLOR": "blue",
            "ACTIVE_BACKEND_COLOR": "blue",
        }
        assert _call_is_scheduler_enabled(env) is False

    def test_enable_zero_legacy_flag(self) -> None:
        """ENABLE_AI_JUDGMENT_SCHEDULER=0 は False を返す（旧方式互換）。"""
        env = {
            "DISABLE_AI_JUDGMENT_SCHEDULER": "0",
            "ENABLE_AI_JUDGMENT_SCHEDULER": "0",
            "BACKEND_COLOR": "blue",
            "ACTIVE_BACKEND_COLOR": "blue",
        }
        assert _call_is_scheduler_enabled(env) is False

    def test_no_disable_flag_enables_scheduler(self) -> None:
        """DISABLE フラグなし、color 一致 → True。"""
        env = {
            "DISABLE_AI_JUDGMENT_SCHEDULER": "0",
            "BACKEND_COLOR": "blue",
            "ACTIVE_BACKEND_COLOR": "blue",
        }
        # ENABLE_AI_JUDGMENT_SCHEDULER が設定されていない状態を確認するため除去
        patched = {k: v for k, v in env.items()}
        with patch.dict(os.environ, patched, clear=False):
            os.environ.pop("ENABLE_AI_JUDGMENT_SCHEDULER", None)
            import app.main as main_module  # noqa: PLC0415

            result = main_module._is_scheduler_enabled()
        assert result is True


# ---------------------------------------------------------------------------
# テスト: Color ガード（本体）
# ---------------------------------------------------------------------------


class TestColorGuard:
    """BACKEND_COLOR / ACTIVE_BACKEND_COLOR による scheduler 起動制御。"""

    def test_active_blue_container_is_blue_starts_scheduler(self) -> None:
        """BACKEND_COLOR=blue / ACTIVE_BACKEND_COLOR=blue → scheduler 起動 (True)。"""
        env = {
            "DISABLE_AI_JUDGMENT_SCHEDULER": "0",
            "BACKEND_COLOR": "blue",
            "ACTIVE_BACKEND_COLOR": "blue",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("ENABLE_AI_JUDGMENT_SCHEDULER", None)
            import app.main as main_module  # noqa: PLC0415

            result = main_module._is_scheduler_enabled()
        assert result is True

    def test_active_green_container_is_green_starts_scheduler(self) -> None:
        """BACKEND_COLOR=green / ACTIVE_BACKEND_COLOR=green → scheduler 起動 (True)。"""
        env = {
            "DISABLE_AI_JUDGMENT_SCHEDULER": "0",
            "BACKEND_COLOR": "green",
            "ACTIVE_BACKEND_COLOR": "green",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("ENABLE_AI_JUDGMENT_SCHEDULER", None)
            import app.main as main_module  # noqa: PLC0415

            result = main_module._is_scheduler_enabled()
        assert result is True

    def test_inactive_blue_container_with_active_green_skips_scheduler(self) -> None:
        """BACKEND_COLOR=blue / ACTIVE_BACKEND_COLOR=green → inactive → False。"""
        env = {
            "DISABLE_AI_JUDGMENT_SCHEDULER": "0",
            "BACKEND_COLOR": "blue",
            "ACTIVE_BACKEND_COLOR": "green",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("ENABLE_AI_JUDGMENT_SCHEDULER", None)
            import app.main as main_module  # noqa: PLC0415

            result = main_module._is_scheduler_enabled()
        assert result is False

    def test_inactive_green_container_with_active_blue_skips_scheduler(self) -> None:
        """BACKEND_COLOR=green / ACTIVE_BACKEND_COLOR=blue → inactive → False。"""
        env = {
            "DISABLE_AI_JUDGMENT_SCHEDULER": "0",
            "BACKEND_COLOR": "green",
            "ACTIVE_BACKEND_COLOR": "blue",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("ENABLE_AI_JUDGMENT_SCHEDULER", None)
            import app.main as main_module  # noqa: PLC0415

            result = main_module._is_scheduler_enabled()
        assert result is False


# ---------------------------------------------------------------------------
# テスト: フォールバック（後方互換）
# ---------------------------------------------------------------------------


class TestColorGuardFallback:
    """BACKEND_COLOR / ACTIVE_BACKEND_COLOR が未設定の場合の後方互換動作。"""

    def test_no_color_vars_falls_back_to_enabled(self) -> None:
        """両変数ともに未設定 → 従来通り有効 (True)。

        v1 以前の環境（.env に ACTIVE_BACKEND_COLOR がない）でデグレしない。
        """
        with patch.dict(os.environ, {"DISABLE_AI_JUDGMENT_SCHEDULER": "0"}, clear=False):
            os.environ.pop("BACKEND_COLOR", None)
            os.environ.pop("ACTIVE_BACKEND_COLOR", None)
            os.environ.pop("ENABLE_AI_JUDGMENT_SCHEDULER", None)
            import app.main as main_module  # noqa: PLC0415

            result = main_module._is_scheduler_enabled()
        assert result is True

    def test_only_backend_color_set_falls_back_to_enabled(self) -> None:
        """BACKEND_COLOR のみ設定（ACTIVE_BACKEND_COLOR 未設定） → 有効 (True)。

        deploy script が ACTIVE_BACKEND_COLOR をまだ書き込んでいない
        初回フルデプロイ後の猶予状態を想定。
        """
        with patch.dict(
            os.environ, {"DISABLE_AI_JUDGMENT_SCHEDULER": "0", "BACKEND_COLOR": "blue"}, clear=False
        ):
            os.environ.pop("ACTIVE_BACKEND_COLOR", None)
            os.environ.pop("ENABLE_AI_JUDGMENT_SCHEDULER", None)
            import app.main as main_module  # noqa: PLC0415

            result = main_module._is_scheduler_enabled()
        assert result is True

    def test_only_active_backend_color_set_falls_back_to_enabled(self) -> None:
        """ACTIVE_BACKEND_COLOR のみ設定（BACKEND_COLOR 未設定） → 有効 (True)。"""
        with patch.dict(
            os.environ,
            {"DISABLE_AI_JUDGMENT_SCHEDULER": "0", "ACTIVE_BACKEND_COLOR": "green"},
            clear=False,
        ):
            os.environ.pop("BACKEND_COLOR", None)
            os.environ.pop("ENABLE_AI_JUDGMENT_SCHEDULER", None)
            import app.main as main_module  # noqa: PLC0415

            result = main_module._is_scheduler_enabled()
        assert result is True

    def test_empty_string_color_vars_fall_back_to_enabled(self) -> None:
        """空文字列の色変数 → 後方互換で有効 (True)。

        compose で ${ACTIVE_BACKEND_COLOR:-} が空に展開される初期状態を想定。
        """
        with patch.dict(
            os.environ,
            {
                "DISABLE_AI_JUDGMENT_SCHEDULER": "0",
                "BACKEND_COLOR": "blue",
                "ACTIVE_BACKEND_COLOR": "",
            },
            clear=False,
        ):
            os.environ.pop("ENABLE_AI_JUDGMENT_SCHEDULER", None)
            import app.main as main_module  # noqa: PLC0415

            result = main_module._is_scheduler_enabled()
        assert result is True
