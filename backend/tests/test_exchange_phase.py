# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_exchange_phase.py
"""段階的資金投入フェーズ設定のテスト。

対象モジュール:
- app.exchange.config.get_exchange_settings（phase フィールド・フェーズ別上限）
"""

from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import patch


class TestExchangePhaseConfig:
    """ExchangeSettings の phase フィールドとフェーズ別上限のテスト。"""

    def test_default_phase_is_1(self):
        """EXCHANGE_PHASE 未設定のとき phase=1 であること。"""
        from app.exchange.config import get_exchange_settings

        env = {k: v for k, v in os.environ.items() if k != "EXCHANGE_PHASE"}
        with patch.dict(os.environ, env, clear=True):
            settings = get_exchange_settings()
        assert settings.phase == 1

    def test_phase_1_max_order_limit(self):
        """Phase 1 では max_order_usd が $50 に制限されること。"""
        from app.exchange.config import get_exchange_settings

        with patch.dict(
            os.environ,
            {
                "EXCHANGE_PHASE": "1",
                "EXCHANGE_MAX_ORDER_USD": "50",
            },
        ):
            settings = get_exchange_settings()
        assert settings.phase == 1
        assert settings.max_order_usd == Decimal("50")

    def test_phase_2_max_order_limit(self):
        """Phase 2 では max_order_usd が $100 に制限されること。"""
        from app.exchange.config import get_exchange_settings

        with patch.dict(
            os.environ,
            {
                "EXCHANGE_PHASE": "2",
                "EXCHANGE_MAX_ORDER_USD": "100",
            },
        ):
            settings = get_exchange_settings()
        assert settings.phase == 2
        assert settings.max_order_usd == Decimal("100")

    def test_phase_3_max_order_limit(self):
        """Phase 3 では max_order_usd が $1000 に制限されること。"""
        from app.exchange.config import get_exchange_settings

        with patch.dict(
            os.environ,
            {
                "EXCHANGE_PHASE": "3",
                "EXCHANGE_MAX_ORDER_USD": "1000",
            },
        ):
            settings = get_exchange_settings()
        assert settings.phase == 3
        assert settings.max_order_usd == Decimal("1000")

    def test_phase_overrides_higher_env_value(self):
        """環境変数で $200 を設定しても Phase 1 なら $50 に制限されること。"""
        from app.exchange.config import get_exchange_settings

        with patch.dict(
            os.environ,
            {
                "EXCHANGE_PHASE": "1",
                "EXCHANGE_MAX_ORDER_USD": "200",
            },
        ):
            settings = get_exchange_settings()
        assert settings.phase == 1
        assert settings.max_order_usd == Decimal("50")

    def test_phase_2_overrides_higher_env_value(self):
        """環境変数で $500 を設定しても Phase 2 なら $100 に制限されること。"""
        from app.exchange.config import get_exchange_settings

        with patch.dict(
            os.environ,
            {
                "EXCHANGE_PHASE": "2",
                "EXCHANGE_MAX_ORDER_USD": "500",
            },
        ):
            settings = get_exchange_settings()
        assert settings.phase == 2
        assert settings.max_order_usd == Decimal("100")

    def test_phase_1_does_not_override_lower_env_value(self):
        """環境変数が Phase 上限より低い場合、環境変数の値が使われること。"""
        from app.exchange.config import get_exchange_settings

        with patch.dict(
            os.environ,
            {
                "EXCHANGE_PHASE": "1",
                "EXCHANGE_MAX_ORDER_USD": "30",  # Phase 1 上限 $50 より低い
            },
        ):
            settings = get_exchange_settings()
        assert settings.phase == 1
        assert settings.max_order_usd == Decimal("30")
