# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_ai_shadow_mode.py
"""Shadow Mode 関連のテスト。

対象モジュール:
- app.ai.schemas.ShadowModeLog
- app.ai.config.get_ai_settings（shadow_mode フィールド）
- app.ai.service.AIService.judge_with_rag（shadow_mode=True のフラグ付加）
- app.automation.shadow_mode_service.ShadowModeService
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch  # noqa: F401


class TestShadowModeLogSchema:
    """ShadowModeLog スキーマのフィールド検証テスト。"""

    def test_shadow_mode_log_schema(self):
        """ShadowModeLog の全フィールドが正しく設定されること。"""
        from app.ai.schemas import ShadowModeLog, TradeAction

        log = ShadowModeLog(
            item_id="item-001",
            action=TradeAction.HOLD,
            confidence=75,
            reason="テスト理由",
            timestamp=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            prompt_version="v1",
            shadow_mode=True,
            provider="claude",
        )

        assert log.item_id == "item-001"
        assert log.action == TradeAction.HOLD
        assert log.confidence == 75
        assert log.reason == "テスト理由"
        assert log.prompt_version == "v1"
        assert log.shadow_mode is True
        assert log.provider == "claude"

    def test_shadow_mode_log_shadow_mode_is_always_true(self):
        """shadow_mode フィールドのデフォルト値が True であること。"""
        from app.ai.schemas import ShadowModeLog, TradeAction

        log = ShadowModeLog(
            item_id="item-002",
            action=TradeAction.BUY,
            confidence=80,
            timestamp=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert log.shadow_mode is True


class TestShadowModeConfig:
    """AISettings の shadow_mode フィールドのテスト。"""

    def test_shadow_mode_disabled_by_default(self):
        """AI_SHADOW_MODE 未設定のとき shadow_mode=False であること。"""
        from app.ai.config import get_ai_settings

        env = {k: v for k, v in os.environ.items() if k != "AI_SHADOW_MODE"}
        with patch.dict(os.environ, env, clear=True):
            settings = get_ai_settings()
        assert settings.shadow_mode is False

    def test_shadow_mode_enabled_via_env(self):
        """AI_SHADOW_MODE=true のとき shadow_mode=True であること。"""
        from app.ai.config import get_ai_settings

        with patch.dict(os.environ, {"AI_SHADOW_MODE": "true"}):
            settings = get_ai_settings()
        assert settings.shadow_mode is True

    def test_shadow_mode_enabled_via_env_1(self):
        """AI_SHADOW_MODE=1 のとき shadow_mode=True であること。"""
        from app.ai.config import get_ai_settings

        with patch.dict(os.environ, {"AI_SHADOW_MODE": "1"}):
            settings = get_ai_settings()
        assert settings.shadow_mode is True

    def test_shadow_mode_disabled_via_env_false(self):
        """AI_SHADOW_MODE=false のとき shadow_mode=False であること。"""
        from app.ai.config import get_ai_settings

        with patch.dict(os.environ, {"AI_SHADOW_MODE": "false"}):
            settings = get_ai_settings()
        assert settings.shadow_mode is False


class TestJudgeWithRagShadowMode:
    """judge_with_rag における shadow_mode フラグのテスト。"""

    def test_judge_with_rag_shadow_mode_flag(self):
        """shadow_mode=True の AISettings を渡すと CrossValidationResult.shadow_mode が True になること。"""
        from app.ai.config import AISettings
        from app.ai.schemas import RAGContext
        from app.ai.service import AIService

        # shadow_mode=True の設定を作成
        settings = AISettings(
            anthropic_api_key=None,
            openai_api_key=None,
            claude_model="claude-sonnet-4-20250514",
            openai_model="gpt-4o",
            min_confidence_threshold=40,
            cross_validation_enabled=False,
            prompt_version="v1",
            shadow_mode=True,
            ai_fallback_model="claude-sonnet-4-20250514",
        )
        rag_context = RAGContext(chunks=[], query="BTC price", source_count=0)
        service = AIService()

        result = service.judge_with_rag("BTC price", rag_context, settings=settings)

        assert result.shadow_mode is True

    def test_judge_with_rag_no_shadow_mode_flag_by_default(self):
        """shadow_mode=False の AISettings を渡すと CrossValidationResult.shadow_mode が False になること。"""
        from app.ai.config import AISettings
        from app.ai.schemas import RAGContext
        from app.ai.service import AIService

        settings = AISettings(
            anthropic_api_key=None,
            openai_api_key=None,
            claude_model="claude-sonnet-4-20250514",
            openai_model="gpt-4o",
            min_confidence_threshold=40,
            cross_validation_enabled=False,
            prompt_version="v1",
            shadow_mode=False,
            ai_fallback_model="claude-sonnet-4-20250514",
        )
        rag_context = RAGContext(chunks=[], query="BTC price", source_count=0)
        service = AIService()

        result = service.judge_with_rag("BTC price", rag_context, settings=settings)

        assert result.shadow_mode is False


class TestShadowModeService:
    """ShadowModeService のテスト。"""

    def test_shadow_mode_service_record(self, caplog):
        """ShadowModeService.record() がログを出力して ShadowModeLog を返すこと。"""
        import logging

        from app.ai.schemas import (
            CrossValidationResult,
            LLMDecision,
            LLMProvider,
            TradeAction,
        )
        from app.automation.shadow_mode_service import ShadowModeService

        primary = LLMDecision(
            provider=LLMProvider.CLAUDE,
            action=TradeAction.BUY,
            confidence=75,
            reason="ポジティブシグナル",
            prompt_version="v1",
        )
        cross_result = CrossValidationResult(
            primary=primary,
            secondary=None,
            agreed=True,
            final_action=TradeAction.BUY,
            final_confidence=75,
            final_reason="ポジティブシグナル",
            prompt_version="v1",
            shadow_mode=True,
        )

        service = ShadowModeService()
        with caplog.at_level(logging.INFO, logger="app.automation.shadow_mode_service"):
            log = service.record(cross_result, "item-123")

        # 戻り値の検証
        assert log.item_id == "item-123"
        assert log.action == TradeAction.BUY
        assert log.confidence == 75
        assert log.shadow_mode is True
        assert log.provider == "claude"

        # ログ出力の検証
        assert any("SHADOW_MODE" in msg for msg in caplog.messages)

    def test_shadow_mode_service_is_enabled_true(self):
        """AI_SHADOW_MODE=true のとき is_enabled() が True を返すこと。"""
        from app.automation.shadow_mode_service import ShadowModeService

        service = ShadowModeService()
        with patch.dict(os.environ, {"AI_SHADOW_MODE": "true"}):
            assert service.is_enabled() is True

    def test_shadow_mode_service_is_enabled_false_by_default(self):
        """AI_SHADOW_MODE 未設定のとき is_enabled() が False を返すこと。"""
        from app.automation.shadow_mode_service import ShadowModeService

        service = ShadowModeService()
        env = {k: v for k, v in os.environ.items() if k != "AI_SHADOW_MODE"}
        with patch.dict(os.environ, env, clear=True):
            assert service.is_enabled() is False

    def test_shadow_mode_service_is_enabled(self):
        """環境変数連動の動作確認: true/false の両方を確認。"""
        from app.automation.shadow_mode_service import ShadowModeService

        service = ShadowModeService()

        with patch.dict(os.environ, {"AI_SHADOW_MODE": "true"}):
            assert service.is_enabled() is True

        with patch.dict(os.environ, {"AI_SHADOW_MODE": "false"}):
            assert service.is_enabled() is False

        with patch.dict(os.environ, {"AI_SHADOW_MODE": "1"}):
            assert service.is_enabled() is True

        with patch.dict(os.environ, {"AI_SHADOW_MODE": "yes"}):
            assert service.is_enabled() is True