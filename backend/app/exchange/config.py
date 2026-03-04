# backend/app/exchange/config.py

"""
Exchange（Bybit Sandbox）関連の設定値読み出しモジュール。

- 環境変数から API キーやリスク管理パラメータを取得する
- デフォルト値は「安全側（小さく・保守的）」に倒す
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.utils.config import get_env


@dataclass
class ExchangeSettings:
    """
    Bybit Sandbox 取引に関する設定値のまとまり。

    NOTE:
    - sandbox=True がデフォルトであり、本番環境への誤送信を防止する
    - max_order_usd は安全側に小さく設定する
    """

    api_key: str
    api_secret: str
    sandbox: bool
    default_symbol: str
    max_order_usd: Decimal
    daily_trade_limit: int
    cooldown_seconds: int
    timeout_seconds: int


def _get_env_int(name: str, default: int) -> int:
    """
    整数値の環境変数を取得するヘルパー。

    不正な値が入っていた場合は RuntimeError にする。
    """
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        return default

    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer value for env var {name}: {raw!r}") from exc


def _get_env_decimal(name: str, default: str) -> Decimal:
    """
    Decimal 値の環境変数を取得するヘルパー。

    :param name: 環境変数名
    :param default: パースに失敗した場合や未設定時に使用する文字列表現
    """
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        raw = default

    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError(f"Invalid decimal value for env var {name}: {raw!r}") from exc


def _get_env_bool(name: str, default: bool) -> bool:
    """
    真偽値の環境変数を取得するヘルパー。

    "true" / "1" / "yes" を True として扱い、それ以外は False とする。
    """
    raw = get_env(name, required=False)
    if raw is None or raw == "":
        return default

    return raw.lower() in ("true", "1", "yes")


def get_exchange_settings() -> ExchangeSettings:
    """
    ExchangeSettings を構築して返す。

    必須:
      - EXCHANGE_API_KEY
      - EXCHANGE_API_SECRET

    任意（デフォルト値あり）:
      - EXCHANGE_SANDBOX（デフォルト: True）
      - EXCHANGE_DEFAULT_SYMBOL（デフォルト: "BTC/USDT"）
      - EXCHANGE_MAX_ORDER_USD（デフォルト: 100）
      - EXCHANGE_DAILY_TRADE_LIMIT（デフォルト: 10）
      - EXCHANGE_COOLDOWN_SECONDS（デフォルト: 300 = 5分）
      - EXCHANGE_TIMEOUT_SECONDS（デフォルト: 30）
    """
    api_key = get_env("EXCHANGE_API_KEY", required=False) or ""
    api_secret = get_env("EXCHANGE_API_SECRET", required=False) or ""

    sandbox = _get_env_bool("EXCHANGE_SANDBOX", default=True)
    default_symbol = get_env("EXCHANGE_DEFAULT_SYMBOL", required=False) or "BTC/USDT"

    max_order_usd = _get_env_decimal(
        "EXCHANGE_MAX_ORDER_USD",
        default="100",  # 1注文あたり 100 USD 相当を上限にする（デフォルト）
    )
    daily_trade_limit = _get_env_int(
        "EXCHANGE_DAILY_TRADE_LIMIT",
        default=10,
    )
    cooldown_seconds = _get_env_int(
        "EXCHANGE_COOLDOWN_SECONDS",
        default=300,  # 5分
    )
    timeout_seconds = _get_env_int(
        "EXCHANGE_TIMEOUT_SECONDS",
        default=30,
    )

    return ExchangeSettings(
        api_key=api_key,
        api_secret=api_secret,
        sandbox=sandbox,
        default_symbol=default_symbol,
        max_order_usd=max_order_usd,
        daily_trade_limit=daily_trade_limit,
        cooldown_seconds=cooldown_seconds,
        timeout_seconds=timeout_seconds,
    )
