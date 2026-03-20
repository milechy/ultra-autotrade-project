# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
get_multi_chain_settings() のテスト。
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from app.aave.config import AaveSettings, get_multi_chain_settings


class TestGetMultiChainSettings:
    @patch.dict(
        "os.environ",
        {
            "AAVE_ACTIVE_CHAINS": "arbitrum",
            "AAVE_RPC_URL_ARBITRUM": "https://arb-rpc.example.com",
        },
    )
    def test_single_chain_returns_one_settings(self) -> None:
        result = get_multi_chain_settings()
        assert len(result) == 1
        assert "arbitrum" in result
        settings = result["arbitrum"]
        assert isinstance(settings, AaveSettings)
        assert settings.chain_name == "arbitrum"
        assert settings.network == "arbitrum"
        assert settings.rpc_url == "https://arb-rpc.example.com"
        assert settings.pool_address == "0x794a61358D6845594F94dc1DB02A252b5b4814aD"

    @patch.dict(
        "os.environ",
        {
            "AAVE_ACTIVE_CHAINS": "arbitrum,optimism",
            "AAVE_RPC_URL_ARBITRUM": "https://arb-rpc.example.com",
            "AAVE_RPC_URL_OPTIMISM": "https://opt-rpc.example.com",
        },
    )
    def test_multiple_chains(self) -> None:
        result = get_multi_chain_settings()
        assert len(result) == 2
        assert set(result.keys()) == {"arbitrum", "optimism"}
        assert result["optimism"].rpc_url == "https://opt-rpc.example.com"
        assert result["optimism"].chain_name == "optimism"

    @patch.dict(
        "os.environ",
        {
            "AAVE_ACTIVE_CHAINS": "arbitrum",
            "AAVE_RPC_URL_ARBITRUM": "https://arb-rpc.example.com",
        },
    )
    def test_shared_settings_from_env(self) -> None:
        """共通設定が正しく適用されることを確認。"""
        result = get_multi_chain_settings()
        settings = result["arbitrum"]
        # デフォルト値の確認
        assert settings.min_health_factor == Decimal("1.6")
        assert settings.warn_health_factor == Decimal("1.8")
        assert settings.trade_cooldown_seconds == 600
        assert settings.default_asset_symbol == "USDC"

    @patch.dict(
        "os.environ",
        {
            "AAVE_ACTIVE_CHAINS": "arbitrum",
            "AAVE_RPC_URL_ARBITRUM": "https://arb-rpc.example.com",
        },
    )
    def test_usdc_address_from_chain_registry(self) -> None:
        result = get_multi_chain_settings()
        settings = result["arbitrum"]
        assert settings.usdc_address == "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"

    @patch.dict(
        "os.environ",
        {
            "AAVE_ACTIVE_CHAINS": "ethereum",
            "AAVE_RPC_URL_ETHEREUM": "https://eth-rpc.example.com",
            "AAVE_FLASHBOTS_RPC_URL": "https://flashbots.example.com",
        },
    )
    def test_ethereum_flashbots_rpc_url(self) -> None:
        """Ethereum チェーンの Flashbots RPC URL が設定される。"""
        result = get_multi_chain_settings()
        settings = result["ethereum"]
        assert settings.flashbots_rpc_url == "https://flashbots.example.com"

    @patch.dict(
        "os.environ",
        {
            "AAVE_ACTIVE_CHAINS": "arbitrum",
            "AAVE_RPC_URL_ARBITRUM": "https://arb-rpc.example.com",
        },
    )
    def test_non_ethereum_no_flashbots(self) -> None:
        """非 Ethereum チェーンには Flashbots RPC URL が設定されない。"""
        result = get_multi_chain_settings()
        settings = result["arbitrum"]
        assert settings.flashbots_rpc_url is None

    @patch.dict(
        "os.environ",
        {
            "AAVE_ACTIVE_CHAINS": "arbitrum",
            # RPC URL missing
        },
    )
    def test_missing_rpc_url_raises(self) -> None:
        with pytest.raises(ValueError, match="RPC URL"):
            get_multi_chain_settings()
