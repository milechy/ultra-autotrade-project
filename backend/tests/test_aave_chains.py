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

    def test_registry_has_six_chains(self) -> None:
        assert len(CHAIN_REGISTRY) == 6
        assert set(CHAIN_REGISTRY.keys()) == {
            "arbitrum",
            "optimism",
            "base",
            "ethereum",
            "arbitrum_sepolia",
            "base_sepolia",
        }

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

    def test_base_tokens_exact_set(self) -> None:
        """Base トークンマップは Aave V3 実上場 15 銘柄のみ含む。"""
        config = CHAIN_REGISTRY["base"]
        expected = {
            "WETH",
            "cbETH",
            "USDbC",
            "wstETH",
            "USDC",
            "weETH",
            "cbBTC",
            "ezETH",
            "GHO",
            "wrsETH",
            "LBTC",
            "EURC",
            "AAVE",
            "tBTC",
            "syrupUSDC",
        }
        assert set(config.tokens.keys()) == expected
        assert len(config.tokens) == 15

    def test_base_tokens_no_unsupported(self) -> None:
        """Base Aave V3 に上場していない WBTC / USDT / DAI は含まない。"""
        config = CHAIN_REGISTRY["base"]
        for unsupported in ("WBTC", "USDT", "DAI"):
            assert unsupported not in config.tokens, f"{unsupported} は Base Aave V3 非上場"

    def test_base_tokens_cbbtc_address(self) -> None:
        config = CHAIN_REGISTRY["base"]
        assert config.tokens["cbBTC"] == "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"

    def test_base_tokens_usdc_address(self) -> None:
        config = CHAIN_REGISTRY["base"]
        assert config.tokens["USDC"] == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

    def test_ethereum_config(self) -> None:
        config = CHAIN_REGISTRY["ethereum"]
        assert config.chain_id == 1
        assert config.pool_address == "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
        assert config.flashbots_rpc_env_var == "AAVE_FLASHBOTS_RPC_URL"

    def test_arbitrum_sepolia_config(self) -> None:
        config = CHAIN_REGISTRY["arbitrum_sepolia"]
        assert config.chain_id == 421614
        assert config.pool_address == "0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff"
        assert config.data_provider_address == "0x29F1d9A68B77D0e8BefE6D2Cb3eE8cB4Ad6FADE0"
        assert config.oracle_address == "0x3E17d8C99b6e73Dc2bBe30AAC4A0C5Bd0e0D261B"
        assert config.is_testnet is True

    def test_base_sepolia_config(self) -> None:
        config = CHAIN_REGISTRY["base_sepolia"]
        assert config.chain_id == 84532
        assert config.pool_address == "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"
        assert config.is_testnet is True

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
    def test_env_not_set_defaults_to_base(self) -> None:
        """AAVE_ACTIVE_CHAINS 未設定時は base をデフォルトとする（本番は Base Mainnet 運用）。

        2026-05-21 変更: 旧デフォルト "arbitrum" → "base"。
        AAVE_RPC_URL_ARBITRUM 未設定の本番環境で ValueError が発生していた根本対策。
        """
        import os

        os.environ.pop("AAVE_ACTIVE_CHAINS", None)
        chains = get_active_chains()
        assert len(chains) == 1
        assert chains[0].chain_name == "base"


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

    def test_base_rpc_url_from_env(self) -> None:
        """本番環境想定: AAVE_RPC_URL_BASE が設定されていれば base RPC URL を返す。"""
        config = get_chain_config("base")
        with patch.dict("os.environ", {"AAVE_RPC_URL_BASE": "https://base-rpc.example.com"}):
            url = get_rpc_url_for_chain(config)
            assert url == "https://base-rpc.example.com"

    def test_arbitrum_rpc_not_set_raises(self) -> None:
        """AAVE_RPC_URL_ARBITRUM 未設定時は ValueError（本番インシデント P0 の再現テスト）。"""
        config = get_chain_config("arbitrum")
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="AAVE_RPC_URL_ARBITRUM"):
                get_rpc_url_for_chain(config)


class TestMakeMultiChainClientsRpcGuard:
    """make_multi_chain_clients の RPC 未設定チェーンスキップ動作を検証する。

    P0 GID 1214993061793196: AAVE_ACTIVE_CHAINS に arbitrum が含まれ
    AAVE_RPC_URL_ARBITRUM が未設定の場合、起動 ValueError を防ぐためスキップする。
    """

    def test_skips_chain_without_rpc_in_web3_mode(self) -> None:
        """web3 モードで RPC 未設定チェーンはスキップされ、結果に含まれない。"""
        from unittest.mock import patch

        from app.aave.client import make_multi_chain_clients

        # AAVE_ACTIVE_CHAINS=arbitrum, RPC 未設定 → arbitrum はスキップ
        with patch.dict(
            "os.environ",
            {"AAVE_ACTIVE_CHAINS": "arbitrum", "AAVE_CLIENT_TYPE": "web3"},
            clear=False,
        ):
            # AAVE_RPC_URL_ARBITRUM を確実に未設定にする
            import os

            os.environ.pop("AAVE_RPC_URL_ARBITRUM", None)
            clients = make_multi_chain_clients(client_type="web3")
            # RPC 未設定 → スキップ → 空
            assert "arbitrum" not in clients

    def test_includes_chain_with_rpc_set_in_web3_mode(self) -> None:
        """web3 モードで RPC 設定済みチェーンは結果に含まれる。"""
        from unittest.mock import MagicMock, patch

        from app.aave.client import make_multi_chain_clients

        with patch.dict(
            "os.environ",
            {
                "AAVE_ACTIVE_CHAINS": "base",
                "AAVE_RPC_URL_BASE": "https://base-rpc.example.com",
                "AAVE_CLIENT_TYPE": "web3",
            },
            clear=False,
        ):
            with patch("app.aave.client.make_aave_client") as mock_factory:
                mock_factory.return_value = MagicMock()
                clients = make_multi_chain_clients(client_type="web3")
                assert "base" in clients

    def test_dummy_mode_includes_all_chains_regardless_of_rpc(self) -> None:
        """dummy モードでは RPC 未設定でもスキップしない（テスト環境で動くため）。"""
        import os
        from unittest.mock import MagicMock, patch

        from app.aave.client import make_multi_chain_clients

        os.environ.pop("AAVE_RPC_URL_ARBITRUM", None)

        with patch.dict(
            "os.environ",
            {"AAVE_ACTIVE_CHAINS": "arbitrum"},
            clear=False,
        ):
            with patch("app.aave.client.make_aave_client") as mock_factory:
                mock_factory.return_value = MagicMock()
                clients = make_multi_chain_clients(client_type="dummy")
                assert "arbitrum" in clients


class TestGetPrimaryChainDefault:
    """proposals/router.py の _get_primary_chain() のデフォルト挙動を検証する。

    P0 GID 1214993061793196: 旧デフォルト "arbitrum_sepolia" / "arbitrum" → "base" に統一。
    """

    def test_default_chain_is_base_when_env_not_set(self) -> None:
        """AAVE_ACTIVE_CHAINS 未設定時は "base" が返る。"""
        import os

        from app.proposals.router import _get_primary_chain

        os.environ.pop("AAVE_ACTIVE_CHAINS", None)
        chain = _get_primary_chain()
        assert chain == "base"

    def test_returns_first_chain_from_env(self) -> None:
        """AAVE_ACTIVE_CHAINS=base,arbitrum → "base" が返る（先頭チェーン）。"""
        with patch.dict("os.environ", {"AAVE_ACTIVE_CHAINS": "base,arbitrum"}):
            from app.proposals.router import _get_primary_chain

            chain = _get_primary_chain()
            assert chain == "base"

    def test_base_only_env_returns_base(self) -> None:
        """本番環境想定: AAVE_ACTIVE_CHAINS=base → "base" が返る。"""
        with patch.dict("os.environ", {"AAVE_ACTIVE_CHAINS": "base"}):
            from app.proposals.router import _get_primary_chain

            chain = _get_primary_chain()
            assert chain == "base"
