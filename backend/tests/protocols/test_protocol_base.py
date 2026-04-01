# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""BaseProtocolClient インターフェースのテスト。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.protocols.base import (
    BaseProtocolClient,
    ProtocolHealthMetrics,
    ProtocolPosition,
    TransactionResult,
)

# --- テスト用の具象実装 ---


class ConcreteProtocolClient(BaseProtocolClient):
    """テスト用の最小限の具象実装。"""

    def get_protocol_name(self) -> str:
        return "test_protocol"

    def get_supported_assets(self) -> list[str]:
        return ["USDC", "ETH"]

    async def get_current_apy(self) -> Decimal:
        return Decimal("5.0")

    async def supply(self, amount: Decimal, asset: str) -> TransactionResult:
        return TransactionResult(
            success=True,
            tx_hash="0x" + "aa" * 32,
            amount=amount,
        )

    async def withdraw(self, amount: Decimal, asset: str) -> TransactionResult:
        return TransactionResult(
            success=True,
            tx_hash="0x" + "bb" * 32,
            amount=amount,
        )

    async def get_position(self) -> ProtocolPosition:
        return ProtocolPosition(
            protocol_name="test_protocol",
            asset="USDC",
            balance=Decimal("1000"),
            value_usd=Decimal("1000"),
        )

    async def get_health_metrics(self) -> ProtocolHealthMetrics:
        return ProtocolHealthMetrics(
            protocol_name="test_protocol",
            is_healthy=True,
            risk_score=Decimal("0.1"),
            details={"note": "test"},
        )


class TestBaseProtocolClientAbstract:
    """BaseProtocolClient の抽象クラス動作テスト。"""

    def test_cannot_instantiate_base_directly(self) -> None:
        """BaseProtocolClient は直接インスタンス化できないこと。"""
        with pytest.raises(TypeError):
            BaseProtocolClient()  # type: ignore[abstract]

    def test_cannot_instantiate_partial_implementation(self) -> None:
        """抽象メソッドを一部しか実装しないクラスはインスタンス化できないこと。"""

        class PartialClient(BaseProtocolClient):
            def get_protocol_name(self) -> str:
                return "partial"

            # 他の抽象メソッドは未実装

        with pytest.raises(TypeError):
            PartialClient()  # type: ignore[abstract]

    def test_concrete_implementation_can_be_instantiated(self) -> None:
        """全抽象メソッドを実装した具象クラスはインスタンス化できること。"""
        client = ConcreteProtocolClient()
        assert client is not None

    def test_is_subclass_of_base(self) -> None:
        """ConcreteProtocolClient が BaseProtocolClient のサブクラスであること。"""
        assert issubclass(ConcreteProtocolClient, BaseProtocolClient)


class TestConcreteProtocolClient:
    """具象実装クラスの全メソッド動作テスト。"""

    @pytest.fixture
    def client(self) -> ConcreteProtocolClient:
        return ConcreteProtocolClient()

    def test_get_protocol_name(self, client: ConcreteProtocolClient) -> None:
        """get_protocol_name が文字列を返すこと。"""
        name = client.get_protocol_name()
        assert isinstance(name, str)
        assert name == "test_protocol"

    def test_get_supported_assets(self, client: ConcreteProtocolClient) -> None:
        """get_supported_assets がリストを返すこと。"""
        assets = client.get_supported_assets()
        assert isinstance(assets, list)
        assert len(assets) > 0
        assert all(isinstance(a, str) for a in assets)

    @pytest.mark.asyncio
    async def test_get_current_apy(self, client: ConcreteProtocolClient) -> None:
        """get_current_apy が Decimal を返すこと。"""
        apy = await client.get_current_apy()
        assert isinstance(apy, Decimal)
        assert apy >= Decimal("0")

    @pytest.mark.asyncio
    async def test_supply_returns_transaction_result(self, client: ConcreteProtocolClient) -> None:
        """supply が TransactionResult を返すこと。"""
        result = await client.supply(Decimal("100"), "USDC")
        assert isinstance(result, TransactionResult)
        assert result.success is True
        assert isinstance(result.amount, Decimal)
        assert result.amount == Decimal("100")
        assert result.tx_hash is not None

    @pytest.mark.asyncio
    async def test_withdraw_returns_transaction_result(
        self, client: ConcreteProtocolClient
    ) -> None:
        """withdraw が TransactionResult を返すこと。"""
        result = await client.withdraw(Decimal("50"), "USDC")
        assert isinstance(result, TransactionResult)
        assert result.success is True
        assert isinstance(result.amount, Decimal)
        assert result.amount == Decimal("50")

    @pytest.mark.asyncio
    async def test_get_position_returns_protocol_position(
        self, client: ConcreteProtocolClient
    ) -> None:
        """get_position が ProtocolPosition を返すこと。"""
        position = await client.get_position()
        assert isinstance(position, ProtocolPosition)
        assert position.protocol_name == "test_protocol"
        assert isinstance(position.balance, Decimal)
        assert isinstance(position.value_usd, Decimal)

    @pytest.mark.asyncio
    async def test_get_health_metrics_returns_protocol_health_metrics(
        self, client: ConcreteProtocolClient
    ) -> None:
        """get_health_metrics が ProtocolHealthMetrics を返すこと。"""
        metrics = await client.get_health_metrics()
        assert isinstance(metrics, ProtocolHealthMetrics)
        assert metrics.protocol_name == "test_protocol"
        assert isinstance(metrics.is_healthy, bool)
        assert isinstance(metrics.risk_score, Decimal)
        assert Decimal("0") <= metrics.risk_score <= Decimal("1")
        assert isinstance(metrics.details, dict)


class TestTransactionResult:
    """TransactionResult データクラスのテスト。"""

    def test_success_result(self) -> None:
        """成功結果が正しく作成されること。"""
        result = TransactionResult(
            success=True,
            tx_hash="0xabc123",
            amount=Decimal("1.5"),
        )
        assert result.success is True
        assert result.tx_hash == "0xabc123"
        assert result.amount == Decimal("1.5")
        assert result.error is None

    def test_failure_result(self) -> None:
        """失敗結果が正しく作成されること。"""
        result = TransactionResult(
            success=False,
            tx_hash=None,
            amount=Decimal("1.0"),
            error="ネットワークエラー",
        )
        assert result.success is False
        assert result.tx_hash is None
        assert result.error == "ネットワークエラー"

    def test_amount_is_decimal(self) -> None:
        """amount が Decimal 型であること（float 禁止）。"""
        result = TransactionResult(
            success=True,
            tx_hash=None,
            amount=Decimal("100"),
        )
        assert isinstance(result.amount, Decimal)


class TestProtocolPosition:
    """ProtocolPosition データクラスのテスト。"""

    def test_position_fields(self) -> None:
        """ProtocolPosition の全フィールドが正しく設定されること。"""
        pos = ProtocolPosition(
            protocol_name="aave",
            asset="USDC",
            balance=Decimal("500"),
            value_usd=Decimal("500"),
        )
        assert pos.protocol_name == "aave"
        assert pos.asset == "USDC"
        assert isinstance(pos.balance, Decimal)
        assert isinstance(pos.value_usd, Decimal)


class TestProtocolHealthMetrics:
    """ProtocolHealthMetrics データクラスのテスト。"""

    def test_healthy_metrics(self) -> None:
        """ヘルシーなメトリクスが正しく作成されること。"""
        metrics = ProtocolHealthMetrics(
            protocol_name="lido",
            is_healthy=True,
            risk_score=Decimal("0.05"),
        )
        assert metrics.is_healthy is True
        assert metrics.risk_score == Decimal("0.05")
        assert metrics.details == {}

    def test_unhealthy_metrics_with_details(self) -> None:
        """アンヘルシーなメトリクスが詳細付きで正しく作成されること。"""
        metrics = ProtocolHealthMetrics(
            protocol_name="pendle",
            is_healthy=False,
            risk_score=Decimal("0.9"),
            details={"error": "TVL が低下しています"},
        )
        assert metrics.is_healthy is False
        assert metrics.risk_score == Decimal("0.9")
        assert "error" in metrics.details


class TestLidoClientInheritance:
    """Lido クライアントの BaseProtocolClient 継承テスト。"""

    def test_dummy_lido_is_base_protocol_client(self) -> None:
        """DummyLidoClient が BaseProtocolClient のサブクラスであること。"""
        from app.protocols.lido.client import DummyLidoClient

        assert issubclass(DummyLidoClient, BaseProtocolClient)

    def test_abstract_lido_is_base_protocol_client(self) -> None:
        """AbstractLidoClient が BaseProtocolClient のサブクラスであること。"""
        from app.protocols.lido.client import AbstractLidoClient

        assert issubclass(AbstractLidoClient, BaseProtocolClient)

    def test_dummy_lido_get_protocol_name(self) -> None:
        """DummyLidoClient.get_protocol_name が 'lido' を返すこと。"""
        from app.protocols.lido.client import DummyLidoClient
        from app.protocols.lido.config import get_lido_config

        client = DummyLidoClient(get_lido_config())
        assert client.get_protocol_name() == "lido"

    def test_dummy_lido_get_supported_assets(self) -> None:
        """DummyLidoClient.get_supported_assets がアセットリストを返すこと。"""
        from app.protocols.lido.client import DummyLidoClient
        from app.protocols.lido.config import get_lido_config

        client = DummyLidoClient(get_lido_config())
        assets = client.get_supported_assets()
        assert "ETH" in assets

    @pytest.mark.asyncio
    async def test_dummy_lido_supply(self) -> None:
        """DummyLidoClient.supply が TransactionResult を返すこと。"""
        from app.protocols.lido.client import DummyLidoClient
        from app.protocols.lido.config import get_lido_config

        client = DummyLidoClient(get_lido_config())
        result = await client.supply(Decimal("1"), "ETH")
        assert isinstance(result, TransactionResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dummy_lido_supply_unsupported_asset(self) -> None:
        """DummyLidoClient.supply に ETH 以外を渡すと失敗すること。"""
        from app.protocols.lido.client import DummyLidoClient
        from app.protocols.lido.config import get_lido_config

        client = DummyLidoClient(get_lido_config())
        result = await client.supply(Decimal("1"), "USDC")
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_dummy_lido_get_health_metrics(self) -> None:
        """DummyLidoClient.get_health_metrics が ProtocolHealthMetrics を返すこと。"""
        from app.protocols.lido.client import DummyLidoClient
        from app.protocols.lido.config import get_lido_config

        client = DummyLidoClient(get_lido_config())
        metrics = await client.get_health_metrics()
        assert isinstance(metrics, ProtocolHealthMetrics)
        assert metrics.protocol_name == "lido"
        assert isinstance(metrics.risk_score, Decimal)


class TestPendleClientInheritance:
    """Pendle クライアントの BaseProtocolClient 継承テスト。"""

    def test_dummy_pendle_is_base_protocol_client(self) -> None:
        """DummyPendleClient が BaseProtocolClient のサブクラスであること。"""
        from app.protocols.pendle.client import DummyPendleClient

        assert issubclass(DummyPendleClient, BaseProtocolClient)

    def test_abstract_pendle_is_base_protocol_client(self) -> None:
        """AbstractPendleClient が BaseProtocolClient のサブクラスであること。"""
        from app.protocols.pendle.client import AbstractPendleClient

        assert issubclass(AbstractPendleClient, BaseProtocolClient)

    def test_dummy_pendle_get_protocol_name(self) -> None:
        """DummyPendleClient.get_protocol_name が 'pendle' を返すこと。"""
        from app.protocols.pendle.client import DummyPendleClient
        from app.protocols.pendle.config import get_pendle_config

        client = DummyPendleClient(get_pendle_config())
        assert client.get_protocol_name() == "pendle"

    def test_dummy_pendle_get_supported_assets(self) -> None:
        """DummyPendleClient.get_supported_assets がアセットリストを返すこと。"""
        from app.protocols.pendle.client import DummyPendleClient
        from app.protocols.pendle.config import get_pendle_config

        client = DummyPendleClient(get_pendle_config())
        assets = client.get_supported_assets()
        assert len(assets) > 0

    @pytest.mark.asyncio
    async def test_dummy_pendle_supply(self) -> None:
        """DummyPendleClient.supply が TransactionResult を返すこと。"""
        from app.protocols.pendle.client import DummyPendleClient
        from app.protocols.pendle.config import get_pendle_config

        client = DummyPendleClient(get_pendle_config())
        result = await client.supply(Decimal("10"), "stETH")
        assert isinstance(result, TransactionResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dummy_pendle_get_health_metrics(self) -> None:
        """DummyPendleClient.get_health_metrics が ProtocolHealthMetrics を返すこと。"""
        from app.protocols.pendle.client import DummyPendleClient
        from app.protocols.pendle.config import get_pendle_config

        client = DummyPendleClient(get_pendle_config())
        metrics = await client.get_health_metrics()
        assert isinstance(metrics, ProtocolHealthMetrics)
        assert metrics.protocol_name == "pendle"
        assert isinstance(metrics.risk_score, Decimal)
        assert Decimal("0") <= metrics.risk_score <= Decimal("1")
