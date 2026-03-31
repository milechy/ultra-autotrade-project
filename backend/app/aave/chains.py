# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/chains.py
"""
Aave V3 マルチチェーン対応のチェーンレジストリモジュール。

サポートするチェーン: Arbitrum One, Optimism, Base, Ethereum Mainnet
                    Arbitrum Sepolia (testnet), Base Sepolia (testnet)
各チェーンの Pool アドレス・トークンアドレス・RPC URL 環境変数名を一元管理する。

NOTE: 新しいチェーンを追加する場合は、必ずテストネットで動作確認してから本番に反映すること。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AaveChainConfig:
    """
    Aave V3 チェーン設定のデータクラス。

    各チェーン固有のコントラクトアドレスと環境変数名を保持する。
    frozen=True により不変オブジェクトとして扱う。
    """

    chain_id: int
    chain_name: str
    display_name: str
    pool_address: str
    rpc_url_env_var: str
    tokens: dict[str, str]
    flashbots_rpc_env_var: Optional[str]
    data_provider_address: Optional[str] = None
    oracle_address: Optional[str] = None
    pool_addresses_provider: Optional[str] = None
    is_testnet: bool = False


# チェーンレジストリ
# NOTE: 新しいチェーンを追加する場合は必ずテストネットで動作確認してから本番に反映すること。
CHAIN_REGISTRY: dict[str, AaveChainConfig] = {
    "arbitrum": AaveChainConfig(
        chain_id=42161,
        chain_name="arbitrum",
        display_name="Arbitrum One",
        pool_address="0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        rpc_url_env_var="AAVE_RPC_URL_ARBITRUM",
        tokens={
            "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            "WBTC": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
        },
        flashbots_rpc_env_var=None,
    ),
    "optimism": AaveChainConfig(
        chain_id=10,
        chain_name="optimism",
        display_name="Optimism",
        pool_address="0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        rpc_url_env_var="AAVE_RPC_URL_OPTIMISM",
        tokens={
            "USDC": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
            "WETH": "0x4200000000000000000000000000000000000006",
            "WBTC": "0x68f180fcCe6836688e9084f035309E29Bf0A2095",
        },
        flashbots_rpc_env_var=None,
    ),
    "base": AaveChainConfig(
        chain_id=8453,
        chain_name="base",
        display_name="Base",
        pool_address="0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
        rpc_url_env_var="AAVE_RPC_URL_BASE",
        tokens={
            "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "WETH": "0x4200000000000000000000000000000000000006",
            # Base では cbBTC を使用。API 一貫性のためキーは "WBTC" とする。
            "WBTC": "0x0555E30da8f98308EdB960aa94C0Db47230d2B9c",
        },
        flashbots_rpc_env_var=None,
    ),
    "ethereum": AaveChainConfig(
        chain_id=1,
        chain_name="ethereum",
        display_name="Ethereum Mainnet",
        pool_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
        rpc_url_env_var="AAVE_RPC_URL_ETHEREUM",
        tokens={
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "WETH": "0xC02aaA39b223FE8D0A0e5FD4e76e7d7C7baE0C55",
            "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        },
        flashbots_rpc_env_var="AAVE_FLASHBOTS_RPC_URL",
    ),
    # --- テストネット ---
    "arbitrum_sepolia": AaveChainConfig(
        chain_id=421614,
        chain_name="arbitrum_sepolia",
        display_name="Arbitrum Sepolia (Testnet)",
        pool_address="0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff",
        rpc_url_env_var="ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA",
        tokens={
            "USDC": "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
            "WETH": "0x980B62Da83eFf3D4576C647993b0c1D7faf17c73",
        },
        flashbots_rpc_env_var=None,
        pool_addresses_provider="0xd8f12BCDe1d1775D09a9e053C33ccAE7a53fE08c",
        data_provider_address="0x29F1d9A68B77D0e8BefE6D2Cb3eE8cB4Ad6FADE0",
        oracle_address="0x3E17d8C99b6e73Dc2bBe30AAC4A0C5Bd0e0D261B",
        is_testnet=True,
    ),
    "base_sepolia": AaveChainConfig(
        chain_id=84532,
        chain_name="base_sepolia",
        display_name="Base Sepolia (Testnet)",
        pool_address="0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27",
        rpc_url_env_var="ALCHEMY_RPC_URL_BASE_SEPOLIA",
        tokens={
            "USDC": "0xba50cd2a20f6da35d788639e581bca8d0b5d4d5f",
            "WETH": "0x4200000000000000000000000000000000000006",
        },
        flashbots_rpc_env_var=None,
        pool_addresses_provider="0xd449FeD49d9C443688d6816fE6872F21402e41de",
        data_provider_address="0xBc9f5b7E248451CdD7cA54e717a2BFe1F32b566b",
        oracle_address="0x943b0dE18d4abf4eF02A85912F8fc07684C141dF",
        is_testnet=True,
    ),
}


def get_chain_config(chain_name: str) -> AaveChainConfig:
    """
    チェーン名からチェーン設定を取得する。

    :param chain_name: チェーン名（例: "arbitrum", "optimism", "base", "ethereum"）
    :return: 対応する AaveChainConfig
    :raises ValueError: 未知のチェーン名が指定された場合
    """
    config = CHAIN_REGISTRY.get(chain_name)
    if config is None:
        known = ", ".join(sorted(CHAIN_REGISTRY.keys()))
        raise ValueError(f"未知のチェーン名: {chain_name!r}。有効なチェーン: {known}")
    return config


def get_active_chains() -> list[AaveChainConfig]:
    """
    環境変数 AAVE_ACTIVE_CHAINS からアクティブなチェーン一覧を取得する。

    カンマ区切りで複数チェーンを指定可能（例: "arbitrum,optimism"）。
    未設定の場合は "arbitrum" をデフォルトとする。

    :return: アクティブなチェーンの AaveChainConfig リスト
    :raises ValueError: 未知のチェーン名が含まれる場合
    """
    raw = os.getenv("AAVE_ACTIVE_CHAINS", "arbitrum")
    chain_names = [name.strip() for name in raw.split(",") if name.strip()]
    return [get_chain_config(name) for name in chain_names]


def get_rpc_url_for_chain(chain: AaveChainConfig) -> str:
    """
    チェーン設定に対応する RPC URL を環境変数から取得する。

    :param chain: 対象チェーンの AaveChainConfig
    :return: RPC URL 文字列
    :raises ValueError: 環境変数が未設定の場合
    """
    rpc_url = os.getenv(chain.rpc_url_env_var)
    if not rpc_url:
        raise ValueError(
            f"RPC URL が設定されていません。環境変数 {chain.rpc_url_env_var!r} を設定してください。"
            f"（チェーン: {chain.display_name}）"
        )
    return rpc_url
