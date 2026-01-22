# backend/app/aave/client.py

"""
Aave とのやり取りを行うクライアント層。

Phase4 では「実ネットアクセスは行わず、ダミークライアントのみ」を提供する。
将来的に本番用の AaveClient 実装を追加することを想定。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .config import AaveSettings, get_aave_settings


class AaveClientError(Exception):
    """Aave クライアント全般の基底例外。"""


class AaveClient(Protocol):
    """
    Aave クライアントのインターフェース。

    deposit / withdraw / get_health_factor を備えた実装であれば差し替え可能。
    """

    def get_health_factor(self) -> Decimal:
        """現在のポジションのヘルスファクターを返す。"""

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        """
        指定したトークンを Aave に deposit する。

        :return: トランザクションハッシュ
        """

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        """
        指定したトークンを Aave から withdraw する。

        :return: トランザクションハッシュ
        """


@dataclass
class DummyAaveClient:
    """
    テスト・開発用のダミー Aave クライアント。

    - 実ネットワークには一切アクセスしない
    - ヘルスファクターは常に安全側の値（例: 2.0）を返す
    - deposit / withdraw は tx_hash 風の文字列を返すだけ
    """

    settings: AaveSettings

    def get_health_factor(self) -> Decimal:
        # 安全側の固定値。実装時にはここを本物の値に差し替える。
        return Decimal("2.0")

    def deposit(self, asset_symbol: str, amount: Decimal) -> str:
        return f"dummy-deposit-{asset_symbol}-{amount}"

    def withdraw(self, asset_symbol: str, amount: Decimal) -> str:
        return f"dummy-withdraw-{asset_symbol}-{amount}"


def get_default_aave_client() -> AaveClient:
    """
    デフォルトの Aave クライアントを返す。

    Phase4 現時点では DummyAaveClient のみを提供し、
    実運用時に明示的に差し替える前提とする。
    """
    settings = get_aave_settings()
    return DummyAaveClient(settings=settings)
