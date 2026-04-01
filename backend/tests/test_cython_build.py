# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Tests to verify Cython-compiled AI modules are importable.

When .so files exist (production build), they are used instead of .py sources.
This test verifies that the AI module imports correctly in both cases.
"""

import importlib
import os


class TestAIModuleImports:
    """AI判定モジュールが正常にimportできること。"""

    def test_ai_service_importable(self) -> None:
        """app.ai.service が import できること（.so または .py）。"""
        mod = importlib.import_module("app.ai.service")
        assert mod is not None

    def test_ai_config_importable(self) -> None:
        """app.ai.config が import できること。"""
        mod = importlib.import_module("app.ai.config")
        assert mod is not None

    def test_ai_prompts_importable(self) -> None:
        """app.ai.prompts が import できること。"""
        mod = importlib.import_module("app.ai.prompts")
        assert mod is not None

    def test_ai_prefilter_importable(self) -> None:
        """app.ai.prefilter が import できること。"""
        mod = importlib.import_module("app.ai.prefilter")
        assert mod is not None


class TestCythonBuildArtifacts:
    """Cythonビルド成果物の存在チェック（production ビルド時のみ）。"""

    def test_so_files_present_in_production(self) -> None:
        """BUILD_MODE=production のとき .so ファイルが存在すること。"""
        build_mode = os.getenv("BUILD_MODE", "development")
        if build_mode != "production":
            return  # development では .so 不要

        import glob

        ai_dir = os.path.join(os.path.dirname(__file__), "..", "app", "ai")
        so_files = glob.glob(os.path.join(ai_dir, "*.so"))
        assert len(so_files) > 0, (
            f"BUILD_MODE=production but no .so files found in {ai_dir}. "
            "Run: python setup_cython.py build_ext --inplace"
        )

    def test_py_sources_removed_in_production(self) -> None:
        """BUILD_MODE=production のとき対象.pyファイルが削除されていること。"""
        build_mode = os.getenv("BUILD_MODE", "development")
        if build_mode != "production":
            return  # development では .py が存在して正常

        exclude = {
            "__init__.py",
            "schemas.py",
            "router.py",
            "decisions_router.py",
            "decisions_schemas.py",
            "models.py",
        }
        ai_dir = os.path.join(os.path.dirname(__file__), "..", "app", "ai")
        remaining_py = [f for f in os.listdir(ai_dir) if f.endswith(".py") and f not in exclude]
        assert remaining_py == [], (
            f"BUILD_MODE=production but .py source files still present: {remaining_py}"
        )
