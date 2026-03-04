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
    min_health_factor = _get_env_decimal(
        "AAVE_MIN_HEALTH_FACTOR",
        default="1.6",  # docs/07_aave_operation_logic.md / 15_rollback_procedures.md を意識した値
    )
    warn_health_factor = _get_env_decimal(
        "AAVE_WARN_HEALTH_FACTOR",
        default="1.8",  # SAFE_MODE 遷移閾値
    )
    trade_cooldown_seconds = _get_env_int(
        "AAVE_TRADE_COOLDOWN_SECONDS",
        default=600,  # 10分
    )

    # RPC URL と秘密鍵は任意（staging 環境用）
    rpc_url = get_env("AAVE_RPC_URL", required=False)
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
    )
