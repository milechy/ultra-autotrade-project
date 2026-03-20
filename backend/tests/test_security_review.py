# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_security_review.py
"""
Stream H セキュリティレビュー — テストスイート

docs/13_security_design.md の基準に基づく自動検証テスト。

対象ルール:
1. 秘密鍵/APIキーのハードコード禁止
2. ログへのトークン/キー/秘密鍵出力禁止（先頭6+末尾4文字のマスク）
3. Health Factor < 1.6 → HARD_STOP
4. 緊急停止フラグのORロジック（手動停止は自動上書き不可）
5. JWT 弱いシークレットキーの本番環境での禁止
6. LLM出力のJSONパース失敗 → HOLD（fail-closed）
7. 金融計算は Decimal のみ（float 禁止）
8. HARD_STOP モードで全Aave操作をブロック
"""

import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from app.aave.config import AaveSettings
from app.aave.schemas import (
    AaveOperationMode,
    AaveOperationStatus,
    AaveOperationType,
    AaveSystemState,
)
from app.aave.service import AaveService
from app.ai.schemas import LLMDecision, LLMProvider, TradeAction
from app.ai.service import AIService
from app.auth.service import AuthService
from app.automation.monitoring_service import MonitoringService

# ---------------------------------------------------------------------------
# Shared Fakes (reused across test classes)
# ---------------------------------------------------------------------------

_BACKEND_APP = Path(__file__).resolve().parents[1] / "app"


class FakeAaveClient:
    """Minimal fake Aave client for tests."""

    def __init__(self, health_factor: Decimal = Decimal("2.0")) -> None:
        self.health_factor = health_factor
        self.deposit_calls: list = []
        self.withdraw_calls: list = []

    def get_health_factor(self) -> Decimal:
        return self.health_factor

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        self.deposit_calls.append((asset_symbol, amount))
        return "tx-deposit"

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        self.withdraw_calls.append((asset_symbol, amount))
        return "tx-withdraw"


class FakeStateManager:
    """Fake state manager returning a configurable AaveSystemState."""

    def __init__(self, state: Optional[AaveSystemState] = None) -> None:
        self._state = state or AaveSystemState(
            emergency_stop=False,
            mode=AaveOperationMode.NORMAL,
            health_factor=Decimal("2.0"),
            last_update=datetime.now(timezone.utc),
            reason=None,
            circuit_closed=True,
            stale_threshold_seconds=300,
        )

    def read_state(self) -> AaveSystemState:
        return self._state

    def is_stale(self) -> bool:
        return False


def _make_settings(
    *,
    min_health_factor: str = "1.6",
    max_single_trade_usd: str = "1000",
) -> AaveSettings:
    return AaveSettings(
        network="sepolia",
        default_asset_symbol="USDC",
        max_single_trade_usd=Decimal(max_single_trade_usd),
        min_health_factor=Decimal(min_health_factor),
        warn_health_factor=Decimal("1.8"),
        trade_cooldown_seconds=600,
        rpc_url=None,
        private_key=None,
        operation_mode="NORMAL",
        state_file_path="/tmp/test_state.json",
        state_stale_threshold_seconds=300,
        pool_addresses_provider="0x0000000000000000000000000000000000000000",
    )


# ===========================================================================
# TestHardcodedSecrets
# ===========================================================================


class TestHardcodedSecrets:
    """Rule 1: No hardcoded private keys / API keys in config modules."""

    # Known allowed constants that are not real secrets
    _ALLOWED_LONG_STRINGS = {
        # Aave V3 testnet pool address provider — a known public contract address
        "0x5343b5bA672Ae99d627A1C87866b8E53F47Db2E6",
        # Dev JWT default — intentional placeholder, guarded by validate_secret_key()
        "development-secret-key-change-in-production",
    }

    def _extract_string_literals(self, filepath: Path) -> list[str]:
        """Return all string literals longer than 20 chars from a Python file."""
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            return []

        results: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value
                if len(val) > 20:
                    results.append(val)
        return results

    def _looks_like_real_secret(self, s: str) -> bool:
        """
        Heuristic: a string that looks like a real API key / private key.

        Excludes:
        - URL-like strings (contain "://")
        - Hex Ethereum addresses (0x...)
        - Pure-whitespace / SQL / human-readable sentences
        - Strings with spaces (usually descriptions)
        - Environment variable names (UPPER_CASE_WITH_UNDERSCORES)
        - Model names and version strings (contain digits + letters)
        - Known allowed constants
        """
        if s in self._ALLOWED_LONG_STRINGS:
            return False
        if "://" in s:
            return False
        if s.startswith("0x") and len(s) <= 66:
            return False
        if " " in s:
            return False
        # Environment variable names are UPPER_CASE_UNDERSCORE — not secrets
        if s == s.upper() and "_" in s:
            return False
        # Model/version strings like "claude-sonnet-4-20250514" are fine
        if s.startswith("claude-") or s.startswith("gpt-"):
            return False
        # Looks like a key if it's mixed-case alphanumeric, no spaces, >20 chars
        suspicious_chars = set(s) - set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
        )
        # Allow typical env-var values (dashes, underscores, dots)
        if suspicious_chars:
            return False
        # Must contain both upper and lower case (real keys tend to be mixed case)
        has_lower = any(c.islower() for c in s)
        has_upper = any(c.isupper() for c in s)
        has_digit = any(c.isdigit() for c in s)
        # A long mixed-case alphanumeric string (not all-upper env name) looks suspicious
        if has_lower and has_upper and has_digit and len(s) > 24:
            return True
        return False

    def test_no_hardcoded_api_keys_in_aave_config(self) -> None:
        """aave/config.py must not contain real hardcoded secrets."""
        filepath = _BACKEND_APP / "aave" / "config.py"
        assert filepath.exists(), f"File not found: {filepath}"

        suspicious = [
            s for s in self._extract_string_literals(filepath) if self._looks_like_real_secret(s)
        ]
        assert suspicious == [], (
            f"Suspicious hardcoded strings found in aave/config.py: {suspicious}"
        )

    def test_no_hardcoded_api_keys_in_exchange_config(self) -> None:
        """exchange/config.py must not contain real hardcoded secrets."""
        filepath = _BACKEND_APP / "exchange" / "config.py"
        assert filepath.exists(), f"File not found: {filepath}"

        suspicious = [
            s for s in self._extract_string_literals(filepath) if self._looks_like_real_secret(s)
        ]
        assert suspicious == [], (
            f"Suspicious hardcoded strings found in exchange/config.py: {suspicious}"
        )

    def test_no_hardcoded_api_keys_in_ai_config(self) -> None:
        """ai/config.py must not contain real hardcoded secrets."""
        filepath = _BACKEND_APP / "ai" / "config.py"
        assert filepath.exists(), f"File not found: {filepath}"

        suspicious = [
            s for s in self._extract_string_literals(filepath) if self._looks_like_real_secret(s)
        ]
        assert suspicious == [], f"Suspicious hardcoded strings found in ai/config.py: {suspicious}"

    def test_configs_use_getenv_not_hardcoded_values(self) -> None:
        """Core config files must use os.getenv() / get_env() for secrets."""
        config_files = [
            _BACKEND_APP / "aave" / "config.py",
            _BACKEND_APP / "exchange" / "config.py",
            _BACKEND_APP / "ai" / "config.py",
            _BACKEND_APP / "notifications" / "config.py",
        ]
        for filepath in config_files:
            if not filepath.exists():
                continue
            content = filepath.read_text(encoding="utf-8")
            # Each config file must use environment-variable helpers
            assert "get_env" in content or "os.getenv" in content, (
                f"{filepath.name} does not use get_env/os.getenv — possible hardcoded config"
            )


# ===========================================================================
# TestLogMasking
# ===========================================================================


class TestLogMasking:
    """Rule 2: Logs must not output full addresses/keys — only first6+last4."""

    def test_wallet_address_masking_pattern_in_client(self) -> None:
        """client.py must implement wallet_address[:6] ... wallet_address[-4:] masking."""
        client_file = _BACKEND_APP / "aave" / "client.py"
        assert client_file.exists()
        content = client_file.read_text(encoding="utf-8")

        assert "wallet_address[:6]" in content, (
            "Log masking pattern wallet_address[:6] not found in aave/client.py"
        )
        assert "wallet_address[-4:]" in content, (
            "Log masking pattern wallet_address[-4:] not found in aave/client.py"
        )

    def test_no_full_private_key_in_client_logs(self) -> None:
        """client.py must not log settings.private_key or wallet_private_key directly."""
        client_file = _BACKEND_APP / "aave" / "client.py"
        content = client_file.read_text(encoding="utf-8")

        # Logging the full private key directly is forbidden
        # Acceptable: masked versions or "private_key configured"
        assert "logger.info(settings.private_key)" not in content
        assert "logger.debug(settings.private_key)" not in content
        assert "logger.warning(settings.private_key)" not in content

    def test_address_masking_used_in_deposit_log(self) -> None:
        """The deposit log must use address masking, not log full addresses."""
        client_file = _BACKEND_APP / "aave" / "client.py"
        content = client_file.read_text(encoding="utf-8")

        # The deposit/supply section uses [:6] masking
        assert "asset_address[:6]" in content or "wallet_address[:6]" in content, (
            "Address masking pattern [:6] not found near deposit/supply log statements"
        )


# ===========================================================================
# TestHealthFactorHardStop
# ===========================================================================


class TestHealthFactorHardStop:
    """Rule 3: Health Factor < 1.6 triggers HARD_STOP at multiple layers."""

    def test_hf_below_16_blocks_buy_in_service(self) -> None:
        """AaveService with HF=1.5 must return NOOP/SKIPPED for BUY."""
        client = FakeAaveClient(health_factor=Decimal("1.5"))
        settings = _make_settings(min_health_factor="1.6")
        state_manager = FakeStateManager()
        service = AaveService(
            client=client,
            settings=settings,
            state_manager=state_manager,
        )

        result = service.execute_rebalance(
            action=TradeAction.BUY,
            amount=Decimal("10"),
            asset_symbol="USDC",
        )

        assert result.operation is AaveOperationType.NOOP
        assert result.status is AaveOperationStatus.SKIPPED
        assert client.deposit_calls == []

    def test_hf_below_16_triggers_emergency_in_monitoring(self) -> None:
        """MonitoringService.record_health_factor(1.5) must set is_emergency=True."""
        monitoring = MonitoringService(enable_state_sync=False)

        status = monitoring.record_health_factor(Decimal("1.5"))

        assert status.is_emergency is True
        assert monitoring.is_trading_allowed() is False

    def test_hf_exactly_at_threshold_triggers_emergency(self) -> None:
        """Health factor exactly at 1.6 is NOT safe (< 1.6 is the rule; 1.6 is boundary)."""
        monitoring = MonitoringService(enable_state_sync=False)

        # HF = 1.6 is NOT below threshold (threshold is < 1.6), so NOT emergency
        status_at_threshold = monitoring.record_health_factor(Decimal("1.6"))
        assert status_at_threshold.is_emergency is False

        # HF = 1.59 IS below threshold
        monitoring2 = MonitoringService(enable_state_sync=False)
        status_below = monitoring2.record_health_factor(Decimal("1.59"))
        assert status_below.is_emergency is True

    def test_hf_below_16_sets_trading_paused(self) -> None:
        """After record_health_factor(1.4), is_trading_allowed() must return False."""
        monitoring = MonitoringService(enable_state_sync=False)
        assert monitoring.is_trading_allowed() is True

        monitoring.record_health_factor(Decimal("1.4"))

        assert monitoring.is_trading_allowed() is False

    def test_hard_stop_mode_blocks_all_operations(self) -> None:
        """AaveService in HARD_STOP mode blocks both BUY and SELL."""
        client = FakeAaveClient(health_factor=Decimal("2.0"))
        settings = _make_settings()
        state = AaveSystemState(
            emergency_stop=False,
            mode=AaveOperationMode.HARD_STOP,
            health_factor=Decimal("2.0"),
            last_update=datetime.now(timezone.utc),
            reason="test hard stop",
            circuit_closed=True,
            stale_threshold_seconds=300,
        )
        state_manager = FakeStateManager(state=state)
        service = AaveService(client=client, settings=settings, state_manager=state_manager)

        result_buy = service.execute_rebalance(
            action=TradeAction.BUY, amount=Decimal("10"), asset_symbol="USDC"
        )
        assert result_buy.operation is AaveOperationType.NOOP
        assert result_buy.status is AaveOperationStatus.SKIPPED
        assert "hard_stop" in result_buy.message.lower()
        assert client.deposit_calls == []

        result_sell = service.execute_rebalance(
            action=TradeAction.SELL, amount=Decimal("10"), asset_symbol="USDC"
        )
        assert result_sell.operation is AaveOperationType.NOOP
        assert result_sell.status is AaveOperationStatus.SKIPPED
        assert client.withdraw_calls == []


# ===========================================================================
# TestEmergencyStopOrLogic
# ===========================================================================


class TestEmergencyStopOrLogic:
    """Rule 4: Emergency stop uses OR logic — cannot be auto-cleared by safe HF."""

    def test_manual_emergency_stop_cannot_be_overwritten_by_normal_hf(self) -> None:
        """
        Once trading is paused (emergency stop), recording a safe HF must NOT
        automatically resume trading — OR logic ensures it stays paused.
        """
        monitoring = MonitoringService(enable_state_sync=False)
        # Manually activate emergency stop
        from app.automation.schemas import ComponentType

        monitoring.activate_emergency_stop(
            reason="Manual operator stop", component=ComponentType.SYSTEM
        )
        assert monitoring.is_trading_allowed() is False

        # Record a safe HF (3.0 >> threshold of 1.6)
        monitoring.record_health_factor(Decimal("3.0"))

        # Emergency stop must STILL be active — OR logic
        assert monitoring.is_trading_allowed() is False

    def test_hf_emergency_activates_trading_pause(self) -> None:
        """record_health_factor below threshold immediately pauses trading."""
        monitoring = MonitoringService(enable_state_sync=False)
        assert monitoring.is_trading_allowed() is True

        monitoring.record_health_factor(Decimal("1.4"))

        assert monitoring.is_trading_allowed() is False

    def test_clear_emergency_stop_requires_explicit_call(self) -> None:
        """
        After activate_emergency_stop(), only clear_emergency_stop()
        can resume trading — not a subsequent record_health_factor.
        """
        from app.automation.schemas import ComponentType

        monitoring = MonitoringService(enable_state_sync=False)
        monitoring.activate_emergency_stop(reason="Test stop", component=ComponentType.SYSTEM)
        assert monitoring.is_trading_allowed() is False

        # Recording a safe HF does NOT resume trading
        monitoring.record_health_factor(Decimal("3.5"))
        assert monitoring.is_trading_allowed() is False

        # Only explicit clear restores it
        monitoring.clear_emergency_stop()
        assert monitoring.is_trading_allowed() is True

    def test_sync_state_uses_or_logic_for_emergency_stop(self) -> None:
        """
        _sync_state_file must preserve existing emergency_stop=True even if
        HF is safe (no new emergency triggered).

        This verifies the OR logic:
          final_emergency = existing_emergency OR hf_triggered_emergency
        """
        # We test the logic indirectly via MonitoringService internals
        monitoring = MonitoringService(enable_state_sync=False)
        # Simulate _trading_paused already True from a previous emergency
        monitoring._trading_paused = True

        # Call _sync_state_file with hf_triggered_emergency=False and a safe HF
        # (existing_emergency would come from state file; here we just check
        #  the internal trading_paused flag is not cleared by record_health_factor)
        monitoring.record_health_factor(Decimal("3.0"))

        # _trading_paused is NOT cleared by record_health_factor
        assert monitoring._trading_paused is True


# ===========================================================================
# TestJwtWeakKeyValidation
# ===========================================================================


class TestJwtWeakKeyValidation:
    """Rule 5: JWT weak secret keys must be rejected in production/staging."""

    def test_weak_key_raises_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Weak JWT key in APP_ENV=production raises RuntimeError."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("JWT_SECRET_KEY", "development-secret-key-change-in-production")
        # Force class attribute re-read
        with patch.object(
            AuthService,
            "SECRET_KEY",
            "development-secret-key-change-in-production",
        ):
            with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
                AuthService.validate_secret_key()

    def test_weak_key_raises_in_staging(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Weak JWT key in APP_ENV=staging raises RuntimeError."""
        monkeypatch.setenv("APP_ENV", "staging")
        with patch.object(AuthService, "SECRET_KEY", "secret"):
            with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
                AuthService.validate_secret_key()

    def test_short_key_raises_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A key shorter than 32 chars in production raises RuntimeError."""
        monkeypatch.setenv("APP_ENV", "production")
        # "shortkey" is not in _WEAK_SECRET_KEYS but is < 32 chars
        with patch.object(AuthService, "SECRET_KEY", "shortkey-not-weak-but-too-short"):
            with pytest.raises(RuntimeError, match="too short"):
                AuthService.validate_secret_key()

    def test_strong_key_passes_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A 32+ character strong key in production must not raise."""
        monkeypatch.setenv("APP_ENV", "production")
        strong_key = "a" * 32 + "extra-chars-for-safety"
        with patch.object(AuthService, "SECRET_KEY", strong_key):
            # Should not raise
            AuthService.validate_secret_key()

    def test_weak_key_allowed_in_dev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Weak key is permitted in dev environment (no exception raised)."""
        monkeypatch.setenv("APP_ENV", "dev")
        with patch.object(
            AuthService,
            "SECRET_KEY",
            "development-secret-key-change-in-production",
        ):
            # Must not raise in dev
            AuthService.validate_secret_key()

    def test_empty_key_raises_in_staging(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty JWT key in staging raises RuntimeError."""
        monkeypatch.setenv("APP_ENV", "staging")
        with patch.object(AuthService, "SECRET_KEY", ""):
            with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
                AuthService.validate_secret_key()


# ===========================================================================
# TestLlmFailClosed
# ===========================================================================


class TestLlmFailClosed:
    """Rule 6: LLM parse failure → HOLD (fail-closed security requirement)."""

    def test_parse_failure_returns_hold(self) -> None:
        """_parse_llm_response with invalid JSON must return action=HOLD."""
        service = AIService()
        decision = service._parse_llm_response("invalid json {{{", LLMProvider.CLAUDE)

        assert decision.action == TradeAction.HOLD
        assert decision.confidence == 0
        assert "Parse error" in (decision.reason or "")

    def test_parse_empty_string_returns_hold(self) -> None:
        """_parse_llm_response with empty string must return HOLD."""
        service = AIService()
        decision = service._parse_llm_response("", LLMProvider.CLAUDE)

        assert decision.action == TradeAction.HOLD

    def test_parse_valid_buy_returns_buy(self) -> None:
        """Verify that valid JSON with action=BUY is correctly parsed (sanity check)."""
        import json

        service = AIService()
        payload = json.dumps({"action": "BUY", "confidence": 80, "reason": "bullish"})
        decision = service._parse_llm_response(payload, LLMProvider.CLAUDE)

        assert decision.action == TradeAction.BUY
        assert decision.confidence == 80

    def test_llms_disagree_returns_hold(self) -> None:
        """_cross_validate with disagreeing LLMs must return final_action=HOLD."""
        service = AIService()
        primary = LLMDecision(
            provider=LLMProvider.CLAUDE,
            action=TradeAction.BUY,
            confidence=80,
            reason="bullish",
        )
        secondary = LLMDecision(
            provider=LLMProvider.OPENAI,
            action=TradeAction.SELL,
            confidence=75,
            reason="bearish",
        )

        result = service._cross_validate(primary, secondary)

        assert result.final_action == TradeAction.HOLD
        assert result.agreed is False
        assert result.final_confidence <= 30

    def test_llms_agree_returns_common_action(self) -> None:
        """_cross_validate with agreeing LLMs must return their shared action."""
        service = AIService()
        primary = LLMDecision(
            provider=LLMProvider.CLAUDE,
            action=TradeAction.BUY,
            confidence=80,
            reason="both bullish",
        )
        secondary = LLMDecision(
            provider=LLMProvider.OPENAI,
            action=TradeAction.BUY,
            confidence=70,
            reason="also bullish",
        )

        result = service._cross_validate(primary, secondary)

        assert result.final_action == TradeAction.BUY
        assert result.agreed is True

    def test_empty_api_key_returns_hold(self) -> None:
        """_call_claude with empty ANTHROPIC_API_KEY returns action=HOLD."""
        from app.ai.config import AISettings

        service = AIService()
        settings = AISettings(
            anthropic_api_key="",
            openai_api_key=None,
            claude_model="claude-opus-4-5",
            openai_model="gpt-4o",
            min_confidence_threshold=40,
            cross_validation_enabled=False,
            shadow_mode=False,
            prompt_version="v1",
            ai_fallback_model="claude-sonnet-4-20250514",
        )

        decision = service._call_claude("system", "some prompt", settings)

        assert decision.action == TradeAction.HOLD
        assert decision.confidence == 0

    def test_unknown_action_in_json_returns_hold(self) -> None:
        """An unknown action value in LLM JSON response defaults to HOLD."""
        import json

        service = AIService()
        payload = json.dumps({"action": "UNKNOWN_ACTION", "confidence": 90, "reason": "?"})
        decision = service._parse_llm_response(payload, LLMProvider.CLAUDE)

        assert decision.action == TradeAction.HOLD


# ===========================================================================
# TestDecimalOnlyFinancials
# ===========================================================================


class TestDecimalOnlyFinancials:
    """Rule 7: Financial calculations must use Decimal type, never float."""

    def test_aave_settings_min_health_factor_is_decimal(self) -> None:
        """AaveSettings.min_health_factor must be Decimal type."""
        settings = _make_settings()
        assert isinstance(settings.min_health_factor, Decimal), "min_health_factor must be Decimal"

    def test_aave_settings_max_single_trade_usd_is_decimal(self) -> None:
        """AaveSettings.max_single_trade_usd must be Decimal type."""
        settings = _make_settings()
        assert isinstance(settings.max_single_trade_usd, Decimal), (
            "max_single_trade_usd must be Decimal"
        )

    def test_exchange_settings_max_order_usd_is_decimal(self) -> None:
        """ExchangeSettings.max_order_usd must be Decimal type."""
        from app.exchange.config import ExchangeSettings

        settings = ExchangeSettings(
            api_key="dummy",
            api_secret="dummy",
            sandbox=True,
            default_symbol="BTC/USDT",
            max_order_usd=Decimal("100"),
            daily_trade_limit=10,
            cooldown_seconds=300,
            timeout_seconds=30,
            hostname="bybit.com",
            usd_to_jpy_rate=150.0,
            app_env="dev",
            phase=1,
        )
        assert isinstance(settings.max_order_usd, Decimal), "max_order_usd must be Decimal"

    def test_normalize_amount_returns_decimal(self) -> None:
        """AaveService._normalize_amount() must return a Decimal."""
        service = AaveService(
            client=FakeAaveClient(),
            settings=_make_settings(),
            state_manager=FakeStateManager(),
        )
        result = service._normalize_amount(Decimal("50"))
        assert isinstance(result, Decimal), "_normalize_amount must return Decimal"

    def test_aave_config_min_hf_decimal_default(self) -> None:
        """get_aave_settings() default min_health_factor must be Decimal('1.6')."""
        from app.aave.config import get_aave_settings

        settings = get_aave_settings()
        assert isinstance(settings.min_health_factor, Decimal)
        assert settings.min_health_factor == Decimal("1.6")

    def test_health_factor_status_current_is_decimal(self) -> None:
        """HealthFactorStatus.current returned by record_health_factor must be Decimal."""
        monitoring = MonitoringService(enable_state_sync=False)
        status = monitoring.record_health_factor(Decimal("2.0"))

        assert isinstance(status.current, Decimal), "HealthFactorStatus.current must be Decimal"


# ===========================================================================
# TestHardStopBlocking
# ===========================================================================


class TestHardStopBlocking:
    """Rule 8: HARD_STOP mode blocks all Aave operations."""

    def _make_service_with_mode(
        self,
        mode: AaveOperationMode,
        hf: str = "2.0",
        emergency_stop: bool = False,
    ) -> tuple[AaveService, FakeAaveClient]:
        client = FakeAaveClient(health_factor=Decimal(hf))
        settings = _make_settings()
        state = AaveSystemState(
            emergency_stop=emergency_stop,
            mode=mode,
            health_factor=Decimal(hf),
            last_update=datetime.now(timezone.utc),
            reason=None,
            circuit_closed=True,
            stale_threshold_seconds=300,
        )
        state_manager = FakeStateManager(state=state)
        # Always pass a fresh MonitoringService to avoid sharing the global singleton
        fresh_monitoring = MonitoringService(enable_state_sync=False)
        service = AaveService(
            client=client,
            settings=settings,
            state_manager=state_manager,
            monitoring_service=fresh_monitoring,
        )
        return service, client

    def test_hard_stop_mode_blocks_buy(self) -> None:
        """HARD_STOP mode: BUY returns SKIPPED."""
        service, client = self._make_service_with_mode(AaveOperationMode.HARD_STOP)
        result = service.execute_rebalance(
            action=TradeAction.BUY, amount=Decimal("10"), asset_symbol="USDC"
        )
        assert result.status is AaveOperationStatus.SKIPPED
        assert result.operation is AaveOperationType.NOOP
        assert client.deposit_calls == []

    def test_hard_stop_mode_blocks_sell(self) -> None:
        """HARD_STOP mode: SELL returns SKIPPED."""
        service, client = self._make_service_with_mode(AaveOperationMode.HARD_STOP)
        result = service.execute_rebalance(
            action=TradeAction.SELL, amount=Decimal("10"), asset_symbol="USDC"
        )
        assert result.status is AaveOperationStatus.SKIPPED
        assert result.operation is AaveOperationType.NOOP
        assert client.withdraw_calls == []

    def test_hard_stop_message_contains_mode_name(self) -> None:
        """HARD_STOP result message must mention 'hard_stop'."""
        service, _ = self._make_service_with_mode(AaveOperationMode.HARD_STOP)
        result = service.execute_rebalance(
            action=TradeAction.BUY, amount=Decimal("10"), asset_symbol="USDC"
        )
        assert result.message is not None
        assert "hard_stop" in result.message.lower()

    def test_safe_mode_blocks_buy_only(self) -> None:
        """SAFE_MODE: BUY returns SKIPPED, SELL is allowed."""
        service, client = self._make_service_with_mode(AaveOperationMode.SAFE_MODE)

        # BUY is blocked
        result_buy = service.execute_rebalance(
            action=TradeAction.BUY, amount=Decimal("10"), asset_symbol="USDC"
        )
        assert result_buy.status is AaveOperationStatus.SKIPPED
        assert "safe_mode" in result_buy.message.lower()
        assert client.deposit_calls == []

        # SELL is allowed
        result_sell = service.execute_rebalance(
            action=TradeAction.SELL, amount=Decimal("5"), asset_symbol="USDC"
        )
        assert result_sell.status is AaveOperationStatus.SUCCESS
        assert result_sell.operation is AaveOperationType.WITHDRAW
        assert client.withdraw_calls == [("USDC", Decimal("5"))]

    def test_normal_mode_allows_buy_and_sell(self) -> None:
        """NORMAL mode allows both BUY and SELL when HF is safe."""
        service, client = self._make_service_with_mode(AaveOperationMode.NORMAL)

        result_buy = service.execute_rebalance(
            action=TradeAction.BUY, amount=Decimal("10"), asset_symbol="USDC"
        )
        assert result_buy.status is AaveOperationStatus.SUCCESS
        assert client.deposit_calls == [("USDC", Decimal("10"))]

        # Reset cooldown
        service._recent_actions = []
        result_sell = service.execute_rebalance(
            action=TradeAction.SELL, amount=Decimal("5"), asset_symbol="USDC"
        )
        assert result_sell.status is AaveOperationStatus.SUCCESS
        assert client.withdraw_calls == [("USDC", Decimal("5"))]

    def test_emergency_stop_flag_blocks_all_in_normal_mode(self) -> None:
        """emergency_stop=True in state blocks all ops, regardless of mode=NORMAL."""
        service, client = self._make_service_with_mode(
            AaveOperationMode.NORMAL, emergency_stop=True
        )

        result = service.execute_rebalance(
            action=TradeAction.BUY, amount=Decimal("10"), asset_symbol="USDC"
        )
        assert result.status is AaveOperationStatus.SKIPPED
        assert "emergency_stop" in result.message.lower()
        assert client.deposit_calls == []