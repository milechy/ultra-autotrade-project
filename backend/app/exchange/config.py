# backend/app/exchange/config.py

"""
Exchange（Bybit Sandbox / bitFlyer）関連の設定値読み出しモジュール。

- 環境変数から API キーやリスク管理パラメータを取得する
- デフォルト値は「安全側（小さく・保守的）」に倒す
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.utils.config import get_env


@dataclass
class ExchangeSettings:
    """
    Bybit Sandbox / bitFlyer 取引に関する設定値のまとまり。

    NOTE:
    - sandbox=True がデフォルトであり、本番環境への誤送信を防止する
    - max_order_usd は安全側に小さく設定する
    - usd_to_jpy_rate は bitFlyer（BTC/JPY）使用時に amount_usd を JPY 換算するレート
    """

    api_key: str
    api_secret: str
    sandbox: bool
    default_symbol: str
    max_order_usd: Decimal
    daily_trade_limit: int
    cooldown_seconds: int
    timeout_seconds: int
    hostname: str
    usd_to_jpy_rate: float  # USD/JPY 換算レート（bitFlyer 使用時）
    app_env: str
    phase: int  # 段階的資金投入フェーズ (1=マイクロテスト, 2=小規模本番, 3=本格運用)


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
      - EXCHANGE_API_KEY（未設定時は BYBIT_API_KEY → BITFLYER_API_KEY にフォールバック）
      - EXCHANGE_API_SECRET（未設定時は BYBIT_API_SECRET → BITFLYER_API_SECRET にフォールバック）

    任意（デフォルト値あり）:
      - EXCHANGE_SANDBOX（未設定時は BYBIT_SANDBOX にフォールバック、デフォルト: True）
      - EXCHANGE_DEFAULT_SYMBOL（デフォルト: "BTC/USDT"）
      - EXCHANGE_MAX_ORDER_USD（デフォルト: 100）
      - EXCHANGE_DAILY_TRADE_LIMIT（デフォルト: 10）
      - EXCHANGE_COOLDOWN_SECONDS（デフォルト: 300 = 5分）
      - EXCHANGE_TIMEOUT_SECONDS（デフォルト: 30）
      - BYBIT_HOSTNAME（デフォルト: "bybit.com"、EU テストネットは "bybit.eu"）
      - USD_TO_JPY_RATE（デフォルト: 150.0、bitFlyer 使用時の JPY 換算レート）
    """
    # EXCHANGE_API_KEY が未設定の場合は BYBIT_API_KEY → BITFLYER_API_KEY にフォールバック
    api_key = (
        get_env("EXCHANGE_API_KEY", required=False)
        or get_env("BYBIT_API_KEY", required=False)
        or get_env("BITFLYER_API_KEY", required=False)
        or ""
    )
    api_secret = (
        get_env("EXCHANGE_API_SECRET", required=False)
        or get_env("BYBIT_API_SECRET", required=False)
        or get_env("BITFLYER_API_SECRET", required=False)
        or ""
    )

    # APP_ENV=prod → 強制的に本番モード（sandbox=False）
    app_env = get_env("APP_ENV", required=False) or "local"

    # EXCHANGE_SANDBOX が未設定の場合は BYBIT_SANDBOX にフォールバック
    if app_env == "prod":
        sandbox = False
    else:
        raw_sandbox = get_env("EXCHANGE_SANDBOX", required=False) or get_env(
            "BYBIT_SANDBOX", required=False
        )
        sandbox = raw_sandbox.lower() in ("true", "1", "yes") if raw_sandbox else True
    default_symbol = get_env("EXCHANGE_DEFAULT_SYMBOL", required=False) or "BTC/USDT"

    phase = _get_env_int("EXCHANGE_PHASE", default=1)
    # フェーズに基づいてmax_order_usdの上限を設定
    phase_limits = {1: Decimal("50"), 2: Decimal("100"), 3: Decimal("1000")}
    phase_max = phase_limits.get(phase, Decimal("50"))

    max_order_usd = _get_env_decimal(
        "EXCHANGE_MAX_ORDER_USD",
        default="100",  # 1注文あたり 100 USD 相当を上限にする（デフォルト）
    )
    if max_order_usd > phase_max:
        max_order_usd = phase_max
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
    hostname = get_env("BYBIT_HOSTNAME", required=False) or "bybit.com"
    usd_to_jpy_rate = float(get_env("USD_TO_JPY_RATE", required=False) or "150.0")

    return ExchangeSettings(
        api_key=api_key,
        api_secret=api_secret,
        sandbox=sandbox,
        default_symbol=default_symbol,
        max_order_usd=max_order_usd,
        daily_trade_limit=daily_trade_limit,
        cooldown_seconds=cooldown_seconds,
        timeout_seconds=timeout_seconds,
        hostname=hostname,
        usd_to_jpy_rate=usd_to_jpy_rate,
        app_env=app_env,
        phase=phase,
    )


def get_bitflyer_settings() -> ExchangeSettings:
    """
    bitFlyer 専用の ExchangeSettings を構築して返す。

    - BITFLYER_API_KEY / BITFLYER_API_SECRET を直接使用する（フォールバックチェーンなし）
    - default_symbol は "BTC/JPY"（bitFlyer は USDT 建てなし）
    - sandbox は常に True（bitFlyer にサンドボックスなし、dry_run で安全動作）
    """
    api_key = get_env("BITFLYER_API_KEY", required=False) or ""
    api_secret = get_env("BITFLYER_API_SECRET", required=False) or ""
    app_env = get_env("APP_ENV", required=False) or "local"
    default_symbol = get_env("EXCHANGE_DEFAULT_SYMBOL", required=False) or "BTC/JPY"

    phase = _get_env_int("EXCHANGE_PHASE", default=1)
    phase_limits = {1: Decimal("50"), 2: Decimal("100"), 3: Decimal("1000")}
    phase_max = phase_limits.get(phase, Decimal("50"))

    max_order_usd = _get_env_decimal("EXCHANGE_MAX_ORDER_USD", default="100")
    if max_order_usd > phase_max:
        max_order_usd = phase_max
    daily_trade_limit = _get_env_int("EXCHANGE_DAILY_TRADE_LIMIT", default=10)
    cooldown_seconds = _get_env_int("EXCHANGE_COOLDOWN_SECONDS", default=300)
    timeout_seconds = _get_env_int("EXCHANGE_TIMEOUT_SECONDS", default=30)
    usd_to_jpy_rate = float(get_env("USD_TO_JPY_RATE", required=False) or "150.0")

    return ExchangeSettings(
        api_key=api_key,
        api_secret=api_secret,
        sandbox=True,  # bitFlyer にサンドボックスなし → 常に dry_run で安全動作
        default_symbol=default_symbol,
        max_order_usd=max_order_usd,
        daily_trade_limit=daily_trade_limit,
        cooldown_seconds=cooldown_seconds,
        timeout_seconds=timeout_seconds,
        hostname="bitflyer.com",
        usd_to_jpy_rate=usd_to_jpy_rate,
        app_env=app_env,
        phase=phase,
    )
