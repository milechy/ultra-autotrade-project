# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_aave_chains.py
"""
Aave V3 マルチチェーン設定レジストリのテスト。
"""

from unittest.mock import patch

import pytest

from app.aave.chains import (
    CHAIN_REGISTRY,
    AaveChainConfig,
    get_active_chains,
    get_chain_config,
    get_rpc_url_for_chain,
)


class TestChainRegistry:
    """CHAIN_REGISTRY の静的データを検証する。"""

    def test_registry_has_four_chains(self) -> None:
        assert len(CHAIN_REGISTRY) == 4
        assert set(CHAIN_REGISTRY.keys()) == {"arbitrum", "optimism", "base", "ethereum"}

    def test_arbitrum_config(self) -> None:
        config = CHAIN_REGISTRY["arbitrum"]
        assert config.chain_id == 42161
        assert config.display_name == "Arbitrum One"
        assert config.pool_address == "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
        assert "USDC" in config.tokens
        assert "WETH" in config.tokens
        assert "WBTC" in config.tokens
        assert config.flashbots_rpc_env_var is None

    def test_optimism_config(self) -> None:
        config = CHAIN_REGISTRY["optimism"]
        assert config.chain_id == 10
        assert config.pool_address == "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
        assert config.flashbots_rpc_env_var is None

    def test_base_config(self) -> None:
        config = CHAIN_REGISTRY["base"]
        assert config.chain_id == 8453
        assert config.pool_address == "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
        assert config.flashbots_rpc_env_var is None

    def test_ethereum_config(self) -> None:
        config = CHAIN_REGISTRY["ethereum"]
        assert config.chain_id == 1
        assert config.pool_address == "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
        assert config.flashbots_rpc_env_var == "AAVE_FLASHBOTS_RPC_URL"

    def test_all_configs_are_frozen(self) -> None:
        for config in CHAIN_REGISTRY.values():
            assert isinstance(config, AaveChainConfig)
            with pytest.raises(AttributeError):
                config.chain_id = 999  # type: ignore[misc]


class TestGetChainConfig:
    def test_known_chain(self) -> None:
        config = get_chain_config("arbitrum")
        assert config.chain_name == "arbitrum"

    def test_unknown_chain_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="未知のチェーン名"):
            get_chain_config("polygon")


class TestGetActiveChains:
    @patch.dict("os.environ", {"AAVE_ACTIVE_CHAINS": "arbitrum"})
    def test_default_single_chain(self) -> None:
        chains = get_active_chains()
        assert len(chains) == 1
        assert chains[0].chain_name == "arbitrum"

    @patch.dict("os.environ", {"AAVE_ACTIVE_CHAINS": "arbitrum,optimism"})
    def test_multiple_chains(self) -> None:
        chains = get_active_chains()
        assert len(chains) == 2
        names = [c.chain_name for c in chains]
        assert names == ["arbitrum", "optimism"]

    @patch.dict("os.environ", {"AAVE_ACTIVE_CHAINS": "arbitrum, optimism , base"})
    def test_whitespace_handling(self) -> None:
        chains = get_active_chains()
        assert len(chains) == 3

    @patch.dict("os.environ", {"AAVE_ACTIVE_CHAINS": "unknown"})
    def test_unknown_chain_raises(self) -> None:
        with pytest.raises(ValueError, match="未知のチェーン名"):
            get_active_chains()

    @patch.dict("os.environ", {}, clear=False)
    def test_env_not_set_defaults_to_arbitrum(self) -> None:
        """AAVE_ACTIVE_CHAINS 未設定時は arbitrum をデフォルトとする。"""
        import os

        os.environ.pop("AAVE_ACTIVE_CHAINS", None)
        chains = get_active_chains()
        assert len(chains) == 1
        assert chains[0].chain_name == "arbitrum"


class TestGetRpcUrlForChain:
    def test_returns_rpc_url_from_env(self) -> None:
        config = get_chain_config("arbitrum")
        with patch.dict("os.environ", {"AAVE_RPC_URL_ARBITRUM": "https://arb-rpc.example.com"}):
            url = get_rpc_url_for_chain(config)
            assert url == "https://arb-rpc.example.com"

    def test_raises_when_env_not_set(self) -> None:
        config = get_chain_config("optimism")
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="RPC URL"):
                get_rpc_url_for_chain(config)
