# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/aave/config.py

"""
Aave 関連の設定値読み出しモジュール。

- 環境変数からネットワークやリスク関連パラメータを取得する
- デフォルト値は「安全側（小さく・保守的）」に倒す
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.utils.config import get_env

from .risk_limiter import get_effective_limits

# 2026年4-5月 rsETH/srsETH エクスプロイト再発防止のためブラックリスト登録。
# deposit() / build_deposit_txs() はこのセットに含まれるシンボルを受け付けない。
# 追加するときは必ずここを編集し、test_blocklist.py のテストも更新すること。
# wrsETH は chains.py:90 に登録されており同エクスプロイト対象のため同時追加。
BLOCKLISTED_COLLATERAL: frozenset[str] = frozenset({"rsETH", "srsETH", "wrsETH"})

# 大文字小文字非依存の比較用セット（rseth / RSETH 等も確実にブロック）。
# チェック側は asset.upper() と本セットを比較する。
BLOCKLISTED_COLLATERAL_UPPER: frozenset[str] = frozenset(s.upper() for s in BLOCKLISTED_COLLATERAL)


@dataclass
class AaveSettings:
    """
    Aave 運用に関する設定値のまとまり。

    NOTE:
    - Phase4 ではテストネット／ダミークライアント前提のため、
      RPC URL や秘密鍵はまだ必須にはしない。
    - Web3AaveClient を使用する場合は rpc_url, wallet_private_key,
      pool_address, usdc_address が必要。
    """

    network: str
    default_asset_symbol: str
    max_single_trade_usd: Decimal
    min_health_factor: Decimal
    warn_health_factor: Decimal
    trade_cooldown_seconds: int
    rpc_url: Optional[str]
    private_key: Optional[str]
    operation_mode: str
    state_file_path: str
    state_stale_threshold_seconds: int
    pool_addresses_provider: str

    # Web3 クライアント用フィールド
    pool_address: Optional[str] = None
    pool_data_provider_address: Optional[str] = None
    wallet_private_key: Optional[str] = None
    usdc_address: Optional[str] = None
    flashbots_rpc_url: Optional[str] = None
    rpc_url_secondary: Optional[str] = None
    chain_name: Optional[str] = None
    max_price_deviation_pct: Decimal = Decimal("2.0")


def _get_env_int(name: str, default: int) -> int:
    """
    整数値の環境変数を取得するヘルパー。

    不正な値が入っていた場合は RuntimeError にする。
    """
    # ★ Aave 関連の env は必須ではないので required=False
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        return default

    try:
        return int(raw)
    except ValueError as exc:  # noqa: TRY003
        raise RuntimeError(f"Invalid integer value for env var {name}: {raw!r}") from exc


def _get_env_decimal(name: str, default: str) -> Decimal:
    """
    Decimal 値の環境変数を取得するヘルパー。

    :param name: 環境変数名
    :param default: パースに失敗した場合や未設定時に使用する文字列表現
    """
    # ★ こちらも required=False
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        raw = default

    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:  # noqa: TRY003
        # 不正な値が入っていた場合も「安全側」のデフォルトに倒す。
        raise RuntimeError(f"Invalid decimal value for env var {name}: {raw!r}") from exc


def get_aave_settings() -> AaveSettings:
    """
    AaveSettings を構築して返す。

    デフォルト値は「小さく・安全側」に設定している。
    """
    # ★ ここも required=False にして、未設定なら安全側デフォルトへ
    network = get_env("AAVE_NETWORK", required=False) or "polygon-mumbai"
    default_asset_symbol = get_env("AAVE_DEFAULT_ASSET_SYMBOL", required=False) or "USDC"

    max_single_trade_usd = _get_env_decimal(
        "AAVE_MAX_SINGLE_TRADE_USD",
        default="100.0",  # 1トレードあたり 100 USD 相当を上限にする（デフォルト）
    )

    _limits = get_effective_limits()
    min_health_factor = _get_env_decimal(
        "AAVE_MIN_HEALTH_FACTOR",
        default=str(_limits.hf_min),
    )
    warn_health_factor = _get_env_decimal(
        "AAVE_WARN_HEALTH_FACTOR",
        default="1.8",  # SAFE_MODE 遷移閾値
    )
    trade_cooldown_seconds = _get_env_int(
        "AAVE_TRADE_COOLDOWN_SECONDS",
        default=_limits.cooldown_seconds,
    )

    # RPC URL と秘密鍵は任意（staging 環境用）
    rpc_url = get_env("AAVE_RPC_URL", required=False)
    rpc_url_secondary = get_env("AAVE_RPC_URL_SECONDARY", required=False)
    private_key = get_env("AAVE_PRIVATE_KEY_STAGING", required=False)

    # 動作モードと状態ファイル設定
    operation_mode = get_env("AAVE_OPERATION_MODE", required=False) or "NORMAL"
    state_file_path = get_env("AAVE_STATE_FILE_PATH", required=False) or "/var/run/ultra/state.json"
    state_stale_threshold_seconds = _get_env_int(
        "AAVE_STATE_STALE_THRESHOLD_SECONDS",
        default=300,  # 5分
    )

    # Aave V3 Addresses (polygon-mumbai)
    pool_addresses_provider = (
        get_env("AAVE_POOL_ADDRESSES_PROVIDER", required=False)
        or "0x5343b5bA672Ae99d627A1C87866b8E53F47Db2E6"
    )

    # Web3 クライアント用設定
    pool_address = get_env("AAVE_POOL_ADDRESS", required=False)
    pool_data_provider_address = get_env("AAVE_POOL_DATA_PROVIDER_ADDRESS", required=False)
    wallet_private_key = get_env("AAVE_WALLET_PRIVATE_KEY", required=False)
    usdc_address = get_env("AAVE_USDC_ADDRESS", required=False)
    flashbots_rpc_url = get_env("AAVE_FLASHBOTS_RPC_URL", required=False)
    max_price_deviation_pct = _get_env_decimal(
        "AAVE_MAX_PRICE_DEVIATION_PCT",
        default="2.0",
    )

    return AaveSettings(
        network=network,
        default_asset_symbol=default_asset_symbol,
        max_single_trade_usd=max_single_trade_usd,
        min_health_factor=min_health_factor,
        warn_health_factor=warn_health_factor,
        trade_cooldown_seconds=trade_cooldown_seconds,
        rpc_url=rpc_url,
        private_key=private_key,
        operation_mode=operation_mode,
        state_file_path=state_file_path,
        state_stale_threshold_seconds=state_stale_threshold_seconds,
        pool_addresses_provider=pool_addresses_provider,
        pool_address=pool_address,
        pool_data_provider_address=pool_data_provider_address,
        wallet_private_key=wallet_private_key,
        usdc_address=usdc_address,
        flashbots_rpc_url=flashbots_rpc_url,
        rpc_url_secondary=rpc_url_secondary,
        max_price_deviation_pct=max_price_deviation_pct,
    )


def get_multi_chain_settings() -> dict[str, AaveSettings]:
    """
    アクティブな全チェーンの AaveSettings を構築して返す。

    - チェーン共通の設定（リスクパラメータ・秘密鍵等）は get_aave_settings() と
      同じ環境変数から読み込む。
    - チェーン固有の設定（network, rpc_url, pool_address, usdc_address,
      flashbots_rpc_url, chain_name）は各 ChainConfig から取得する。
    - chains.py が存在しない環境でもファイルレベルの import を壊さないよう、
      import は関数スコープ内に閉じ込める。

    :returns: chain_name -> AaveSettings のマッピング
    """
    import os  # noqa: PLC0415

    # chains モジュールは stream-x ブランチで追加予定のため遅延 import する
    from .chains import get_active_chains, get_rpc_url_for_chain  # noqa: PLC0415

    # --- チェーン共通設定（環境変数から取得）---
    min_health_factor = _get_env_decimal("AAVE_MIN_HEALTH_FACTOR", default="1.6")
    warn_health_factor = _get_env_decimal("AAVE_WARN_HEALTH_FACTOR", default="1.8")
    trade_cooldown_seconds = _get_env_int("AAVE_TRADE_COOLDOWN_SECONDS", default=600)
    max_single_trade_usd = _get_env_decimal("AAVE_MAX_SINGLE_TRADE_USD", default="100.0")
    default_asset_symbol = get_env("AAVE_DEFAULT_ASSET_SYMBOL", required=False) or "USDC"
    operation_mode = get_env("AAVE_OPERATION_MODE", required=False) or "NORMAL"
    state_file_path = get_env("AAVE_STATE_FILE_PATH", required=False) or "/var/run/ultra/state.json"
    state_stale_threshold_seconds = _get_env_int("AAVE_STATE_STALE_THRESHOLD_SECONDS", default=300)
    pool_addresses_provider = (
        get_env("AAVE_POOL_ADDRESSES_PROVIDER", required=False)
        or "0x5343b5bA672Ae99d627A1C87866b8E53F47Db2E6"
    )
    private_key = get_env("AAVE_PRIVATE_KEY_STAGING", required=False)
    wallet_private_key = get_env("AAVE_WALLET_PRIVATE_KEY", required=False)

    # --- チェーンごとに AaveSettings を組み立て ---
    result: dict[str, AaveSettings] = {}
    for chain in get_active_chains():
        # Flashbots RPC URL（Ethereum のみ、chains.py の設定に従う）
        flashbots_rpc_url = (
            os.getenv(chain.flashbots_rpc_env_var) if chain.flashbots_rpc_env_var else None
        )

        result[chain.chain_name] = AaveSettings(
            network=chain.chain_name,
            rpc_url=get_rpc_url_for_chain(chain),
            pool_address=chain.pool_address,
            usdc_address=chain.tokens.get("USDC"),
            flashbots_rpc_url=flashbots_rpc_url,
            chain_name=chain.chain_name,
            # 共通設定
            min_health_factor=min_health_factor,
            warn_health_factor=warn_health_factor,
            trade_cooldown_seconds=trade_cooldown_seconds,
            max_single_trade_usd=max_single_trade_usd,
            default_asset_symbol=default_asset_symbol,
            operation_mode=operation_mode,
            state_file_path=state_file_path,
            state_stale_threshold_seconds=state_stale_threshold_seconds,
            pool_addresses_provider=pool_addresses_provider,
            private_key=private_key,
            wallet_private_key=wallet_private_key,
        )

    return result
