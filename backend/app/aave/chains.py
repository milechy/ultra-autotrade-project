# backend/app/aave/chains.py
"""
Aave V3 マルチチェーン対応のチェーンレジストリモジュール。

サポートするチェーン: Arbitrum One, Optimism, Base, Ethereum Mainnet
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
