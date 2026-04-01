# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""Protocol共通基底クラス（OCP準拠）。

全プロトコルクライアントはこのインターフェースを実装すること。
新プロトコル追加時は BaseProtocolClient を継承するだけでよい（拡張に開放、変更に閉鎖）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ProtocolPosition:
    """プロトコル上のポジション情報。"""

    protocol_name: str
    asset: str
    balance: Decimal
    value_usd: Decimal


@dataclass
class ProtocolHealthMetrics:
    """プロトコルのヘルスメトリクス。"""

    protocol_name: str
    is_healthy: bool
    risk_score: Decimal  # 0.0 (safe) to 1.0 (critical)
    details: dict[str, str] = field(default_factory=dict)  # プロトコル固有の追加情報


@dataclass
class TransactionResult:
    """トランザクション実行結果。"""

    success: bool
    tx_hash: str | None
    amount: Decimal
    error: str | None = None


class BaseProtocolClient(ABC):
    """全プロトコルクライアントの共通インターフェース。

    新プロトコルを追加する場合はこのクラスを継承して全抽象メソッドを実装すること。
    既存クライアントへの変更は不要（OCP: Open/Closed Principle）。
    """

    @abstractmethod
    def get_protocol_name(self) -> str:
        """プロトコル名を返す。"""
        ...

    @abstractmethod
    def get_supported_assets(self) -> list[str]:
        """サポートするアセット一覧を返す。"""
        ...

    @abstractmethod
    async def get_current_apy(self) -> Decimal:
        """現在の APY（年率、%単位）を返す。"""
        ...

    @abstractmethod
    async def supply(self, amount: Decimal, asset: str) -> TransactionResult:
        """アセットを預け入れる。

        Args:
            amount: 預け入れ量
            asset: アセット識別子（例: "ETH", "USDC"）

        Returns:
            TransactionResult: トランザクション結果
        """
        ...

    @abstractmethod
    async def withdraw(self, amount: Decimal, asset: str) -> TransactionResult:
        """アセットを引き出す。

        Args:
            amount: 引き出し量
            asset: アセット識別子（例: "ETH", "USDC"）

        Returns:
            TransactionResult: トランザクション結果
        """
        ...

    @abstractmethod
    async def get_position(self) -> ProtocolPosition:
        """現在のポジション情報を返す。"""
        ...

    @abstractmethod
    async def get_health_metrics(self) -> ProtocolHealthMetrics:
        """プロトコルのヘルスメトリクスを返す。"""
        ...
