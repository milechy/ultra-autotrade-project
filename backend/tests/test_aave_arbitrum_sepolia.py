# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/test_aave_arbitrum_sepolia.py
"""
Aave V3 Arbitrum Sepolia テストネット設定の単体テスト。

テストネット接続 PoC の初期検証を目的とする。
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

_CHAIN_KEY = "arbitrum_sepolia"
_EXPECTED_POOL = "0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff"
_EXPECTED_USDC = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"
_EXPECTED_DATA_PROVIDER = "0x29F1d9A68B77D0e8BefE6D2Cb3eE8cB4Ad6FADE0"
_EXPECTED_ORACLE = "0x3E17d8C99b6e73Dc2bBe30AAC4A0C5Bd0e0D261B"
_EXPECTED_RPC_ENV_VAR = "ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA"


class TestArbitrumSepoliaInRegistry:
    def test_arbitrum_sepolia_in_chain_registry(self) -> None:
        """arbitrum_sepolia キーが CHAIN_REGISTRY に存在すること。"""
        assert _CHAIN_KEY in CHAIN_REGISTRY

    def test_arbitrum_sepolia_pool_address_correct(self) -> None:
        """Pool アドレスが Aave 公式ドキュメントと一致すること。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.pool_address == _EXPECTED_POOL

    def test_arbitrum_sepolia_usdc_address_correct(self) -> None:
        """USDC アドレスが Aave Arbitrum Sepolia の公式アドレスと一致すること。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.tokens["USDC"] == _EXPECTED_USDC

    def test_arbitrum_sepolia_data_provider_not_none(self) -> None:
        """data_provider_address が設定済みであること（Arbitrum Sepolia は確認済み）。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.data_provider_address is not None
        assert config.data_provider_address == _EXPECTED_DATA_PROVIDER

    def test_arbitrum_sepolia_oracle_not_none(self) -> None:
        """oracle_address が設定済みであること（Arbitrum Sepolia は確認済み）。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.oracle_address is not None
        assert config.oracle_address == _EXPECTED_ORACLE

    def test_arbitrum_sepolia_rpc_env_var(self) -> None:
        """rpc_url_env_var が Alchemy 用の正しい環境変数名であること。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.rpc_url_env_var == _EXPECTED_RPC_ENV_VAR

    def test_get_chain_config_arbitrum_sepolia(self) -> None:
        """get_chain_config() が arbitrum_sepolia の AaveChainConfig を返すこと。"""
        config = get_chain_config(_CHAIN_KEY)
        assert isinstance(config, AaveChainConfig)
        assert config.chain_name == _CHAIN_KEY
        assert config.chain_id == 421614

    def test_active_chains_includes_arbitrum_sepolia(self) -> None:
        """AAVE_ACTIVE_CHAINS=arbitrum_sepolia 設定時に正しく解決されること。"""
        with patch.dict("os.environ", {"AAVE_ACTIVE_CHAINS": "arbitrum_sepolia"}):
            chains = get_active_chains()
        assert len(chains) == 1
        assert chains[0].chain_name == _CHAIN_KEY

    def test_rpc_url_uses_alchemy_env_var(self) -> None:
        """get_rpc_url_for_chain() が ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA から URL を取得すること。"""
        config = get_chain_config(_CHAIN_KEY)
        fake_url = "https://arb-sepolia.g.alchemy.com/v2/TEST_KEY"
        with patch.dict("os.environ", {_EXPECTED_RPC_ENV_VAR: fake_url}):
            url = get_rpc_url_for_chain(config)
        assert url == fake_url

    def test_arbitrum_sepolia_is_testnet_flag(self) -> None:
        """is_testnet フラグが True であること（本番チェーンと区別するため）。"""
        config = CHAIN_REGISTRY[_CHAIN_KEY]
        assert config.is_testnet is True
