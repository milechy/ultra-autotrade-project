from dataclasses import dataclass
from typing import Optional

from app.utils.config import get_env


@dataclass
class OctoBotSettings:
    """
    OctoBot 外部シグナル API 関連の設定値。
    """
    base_url: str
    api_key: str
    timeout_seconds: int = 10


def _get_env_int(name: str, default: int) -> int:
    """
    整数の環境変数を取得するユーティリティ。

    - 未設定 or パース不能の場合は default を返す。
    """
    raw: Optional[str] = get_env(
        name,
        default=str(default),
        required=False,
    )
    if raw is None:
        return default

    try:
        return int(raw)
    except (TypeError, ValueError):
        # TODO: ログに warning を出すなど（現時点では黙って default を使う）
        return default


def get_octobot_settings() -> OctoBotSettings:
    """
    OctoBot 設定値を環境変数から読み出す。

    必須:
      - OCTOBOT_API_BASE_URL
      - OCTOBOT_API_KEY

    任意:
      - OCTOBOT_TIMEOUT_SECONDS（デフォルト 10秒）
    """
    base_url = get_env("OCTOBOT_API_BASE_URL")
    api_key = get_env("OCTOBOT_API_KEY")

    if not base_url or not api_key:
        raise RuntimeError(
            "OctoBot settings are not configured. "
            "Please set OCTOBOT_API_BASE_URL and OCTOBOT_API_KEY."
        )

    timeout_seconds = _get_env_int("OCTOBOT_TIMEOUT_SECONDS", default=10)

    return OctoBotSettings(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
