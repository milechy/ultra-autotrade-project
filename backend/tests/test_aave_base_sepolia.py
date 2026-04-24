# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_aave_base_sepolia.py
"""
Aave V3 Base Sepolia テストネット設定の単体テスト。

実際の RPC 呼び出しは行わず、チェーンレジストリの設定値のみを検証する。
"""

from unittest.mock import patch

from app.aave.chains import (
    CHAIN_REGISTRY,
    AaveChainConfig,
    get_active_chains,
    get_chain_config,
    get_rpc_url_for_chain,
)

_CHAIN_KEY = "base_sepolia"
_EXPECTED_POOL = "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"
_EXPECTED_USDC = "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f"
_EXPECTED_DATA_PROVIDER = "0xBc9f5b7E248451CdD7cA54e717a2BFe1F32b566b"
_EXPECTED_ORACLE = "0x943b0dE18d4abf4eF02A85912F8fc07684C141dF"
_EXPECTED_RPC_ENV_VAR = "ALCHEMY_RPC_URL_BASE_SEPOLIA"
_EXPECTED_CHAIN_ID = 84532


class TestBaseSepoliaInRegistry:
    def test_base_sepolia_in_chain_registry(self) -> None:
        """base_sepolia キーが CHAIN_REGISTRY に存在すること。"""
        assert _CHAIN_KEY in CHAIN_REGISTRY

    def test_base_sepolia_pool_address_correct(self) -> None:
        """Pool アドレスが Aave 公式ドキュメントと一致すること。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.pool_address == _EXPECTED_POOL

    def test_base_sepolia_usdc_address_correct(self) -> None:
        """USDC アドレスが Aave Base Sepolia の公式アドレスと一致すること。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.tokens["USDC"] == _EXPECTED_USDC

    def test_base_sepolia_data_provider_not_none(self) -> None:
        """data_provider_address が設定済みであること。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.data_provider_address is not None
        assert config.data_provider_address == _EXPECTED_DATA_PROVIDER

    def test_base_sepolia_oracle_not_none(self) -> None:
        """oracle_address が設定済みであること。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.oracle_address is not None
        assert config.oracle_address == _EXPECTED_ORACLE

    def test_base_sepolia_rpc_env_var(self) -> None:
        """rpc_url_env_var が Alchemy 用の正しい環境変数名であること。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.rpc_url_env_var == _EXPECTED_RPC_ENV_VAR

    def test_get_chain_config_base_sepolia(self) -> None:
        """get_chain_config() が base_sepolia の AaveChainConfig を返すこと。"""
        config = get_chain_config(_CHAIN_KEY)
        assert isinstance(config, AaveChainConfig)
        assert config.chain_name == _CHAIN_KEY
        assert config.chain_id == _EXPECTED_CHAIN_ID

    def test_active_chains_includes_base_sepolia(self) -> None:
        """AAVE_ACTIVE_CHAINS=base_sepolia 設定時に正しく解決されること。"""
        with patch.dict("os.environ", {"AAVE_ACTIVE_CHAINS": "base_sepolia"}):
            chains = get_active_chains()
        assert len(chains) == 1
        assert chains[0].chain_name == _CHAIN_KEY

    def test_rpc_url_uses_alchemy_env_var(self) -> None:
        """get_rpc_url_for_chain() が ALCHEMY_RPC_URL_BASE_SEPOLIA から URL を取得すること。"""
        config = get_chain_config(_CHAIN_KEY)
        fake_url = "https://base-sepolia.g.alchemy.com/v2/TEST_KEY"
        with patch.dict("os.environ", {_EXPECTED_RPC_ENV_VAR: fake_url}):
            url = get_rpc_url_for_chain(config)
        assert url == fake_url

    def test_base_sepolia_is_testnet_flag(self) -> None:
        """is_testnet フラグが True であること（本番チェーンと区別するため）。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.is_testnet is True
