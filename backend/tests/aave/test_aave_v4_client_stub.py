# backend/tests/aave/test_aave_v4_client_stub.py
"""
Aave V4 クライアント scaffold の単体テスト。

検証項目:
  (1) DummyAaveV4Client の read メソッドが期待 Decimal を返す
  (2) 本体スタブ (AaveV4EthereumHubClient) が NotImplementedError を raise
  (3) client に write/tx メソッド (deposit/withdraw/supply/approve) が
      テスト外から安全に呼び出せない (NotImplementedError で保護されている) ことを確認
  (4) schemas (AaveV4HubConfig / V4AccountData) のインスタンス化
  (5) import app.aave_v4 が既存 V3 モジュールに副作用を与えない独立性
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.aave.client import AccountData
from app.aave_v4.client import AaveV4EthereumHubClient, DummyAaveV4Client
from app.aave_v4.schemas import AaveV4HubConfig, V4AccountData  # noqa: F401

# --------------------------------------------------------------------------- #
# (1) DummyAaveV4Client — read メソッドが期待 Decimal を返す
# --------------------------------------------------------------------------- #


class TestDummyAaveV4ClientReadMethods:
    """DummyAaveV4Client の read-only メソッドが正しい Decimal を返すことを検証。"""

    def setup_method(self) -> None:
        self.client = DummyAaveV4Client()

    def test_get_health_factor_returns_decimal(self) -> None:
        """get_health_factor が Decimal("2.5") を返すこと。"""
        result = self.client.get_health_factor()
        assert isinstance(result, Decimal), f"期待 Decimal, 実際: {type(result)}"
        assert result == Decimal("2.5")

    def test_get_health_factor_with_wallet_address(self) -> None:
        """wallet_address を渡しても同じ Decimal を返すこと。"""
        result = self.client.get_health_factor("0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF")
        assert isinstance(result, Decimal)
        assert result == Decimal("2.5")

    def test_get_account_data_returns_account_data(self) -> None:
        """get_account_data が V3 互換 AccountData を返すこと。"""
        result = self.client.get_account_data()
        assert isinstance(result, AccountData)

    def test_get_account_data_fields_are_decimal(self) -> None:
        """AccountData の全金融フィールドが Decimal 型であること (float 禁止 Rule 11)。"""
        result = self.client.get_account_data()
        assert isinstance(result.total_collateral_usd, Decimal)
        assert isinstance(result.total_debt_usd, Decimal)
        assert isinstance(result.available_borrows_usd, Decimal)
        assert isinstance(result.health_factor, Decimal)

    def test_get_account_data_expected_values(self) -> None:
        """AccountData が期待固定値を持つこと。"""
        result = self.client.get_account_data()
        assert result.total_collateral_usd == Decimal("10000")
        assert result.total_debt_usd == Decimal("3000")
        assert result.available_borrows_usd == Decimal("5000")
        assert result.health_factor == Decimal("2.5")

    def test_get_pool_utilization_returns_decimal(self) -> None:
        """get_pool_utilization が Decimal を返すこと。"""
        result = self.client.get_pool_utilization("USDC")
        assert isinstance(result, Decimal)
        assert result == Decimal("75.0")

    def test_get_pool_utilization_no_float(self) -> None:
        """get_pool_utilization が float を返さないこと (Rule 11)。"""
        result = self.client.get_pool_utilization("WETH")
        assert not isinstance(result, float)

    def test_get_v4_account_data_returns_v4_schema(self) -> None:
        """get_v4_account_data が V4AccountData スキーマを返すこと。"""
        result = self.client.get_v4_account_data()
        assert isinstance(result, V4AccountData)
        assert isinstance(result.health_factor, Decimal)
        assert result.health_factor == Decimal("2.5")


# --------------------------------------------------------------------------- #
# (2) 本体スタブが NotImplementedError を raise
# --------------------------------------------------------------------------- #


class TestAaveV4EthereumHubClientStub:
    """AaveV4EthereumHubClient が Phase 0 で NotImplementedError を raise することを検証。"""

    def setup_method(self) -> None:
        self.client = AaveV4EthereumHubClient()

    def test_get_health_factor_raises_not_implemented(self) -> None:
        """get_health_factor が NotImplementedError を raise すること。"""
        with pytest.raises(NotImplementedError) as exc_info:
            self.client.get_health_factor("0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF")
        assert "docs/55" in str(exc_info.value), "エラーメッセージに docs/55 への参照がないこと"

    def test_get_account_data_raises_not_implemented(self) -> None:
        """get_account_data が NotImplementedError を raise すること。"""
        with pytest.raises(NotImplementedError) as exc_info:
            self.client.get_account_data("0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF")
        assert "docs/55" in str(exc_info.value)

    def test_get_pool_utilization_returns_none(self) -> None:
        """get_pool_utilization は基底クラスの fail-open 実装 (None) を返すこと。"""
        # AaveV4ClientBase の get_pool_utilization は具象実装あり (None 返却)
        result = self.client.get_pool_utilization("USDC")
        assert result is None

    def test_deposit_raises_not_implemented(self) -> None:
        """deposit が NotImplementedError を raise すること (Phase 3 以降実装)。"""
        with pytest.raises(NotImplementedError) as exc_info:
            self.client.deposit()
        assert "Phase 3" in str(exc_info.value)

    def test_withdraw_raises_not_implemented(self) -> None:
        """withdraw が NotImplementedError を raise すること (Phase 3 以降実装)。"""
        with pytest.raises(NotImplementedError) as exc_info:
            self.client.withdraw()
        assert "Phase 3" in str(exc_info.value)

    def test_error_message_references_docs55(self) -> None:
        """全 stub の NotImplementedError メッセージが docs/55 を参照すること。"""
        for method_name, call in [
            ("get_health_factor", lambda: self.client.get_health_factor("")),
            ("get_account_data", lambda: self.client.get_account_data("")),
            ("deposit", lambda: self.client.deposit()),
            ("withdraw", lambda: self.client.withdraw()),
        ]:
            with pytest.raises(NotImplementedError) as exc_info:
                call()
            assert "docs/55" in str(exc_info.value), (
                f"{method_name} の NotImplementedError に docs/55 参照がない"
            )


# --------------------------------------------------------------------------- #
# (3) write/tx メソッドが存在しないか、存在しても保護されていることを確認
# --------------------------------------------------------------------------- #


class TestNoWriteMethodsOnDummy:
    """DummyAaveV4Client に意図しない write API が露出していないことを検証。"""

    def setup_method(self) -> None:
        self.client = DummyAaveV4Client()

    def test_approve_method_does_not_exist(self) -> None:
        """approve メソッドが存在しないこと。"""
        assert not hasattr(self.client, "approve"), (
            "approve メソッドは Phase 0 に存在してはならない"
        )

    def test_supply_method_does_not_exist(self) -> None:
        """supply メソッドが存在しないこと (deposit が AaveClientBase 由来名)。"""
        assert not hasattr(self.client, "supply"), "supply メソッドは Phase 0 に存在してはならない"

    def test_send_transaction_method_does_not_exist(self) -> None:
        """send_transaction メソッドが存在しないこと。"""
        assert not hasattr(self.client, "send_transaction"), (
            "send_transaction は Phase 0 に存在してはならない"
        )

    def test_sign_transaction_method_does_not_exist(self) -> None:
        """sign_transaction メソッドが存在しないこと。"""
        assert not hasattr(self.client, "sign_transaction"), (
            "sign_transaction は Phase 0 に存在してはならない"
        )

    def test_deposit_raises_not_implemented_on_dummy(self) -> None:
        """DummyAaveV4Client.deposit は NotImplementedError を raise すること。"""
        with pytest.raises(NotImplementedError):
            self.client.deposit()

    def test_withdraw_raises_not_implemented_on_dummy(self) -> None:
        """DummyAaveV4Client.withdraw は NotImplementedError を raise すること。"""
        with pytest.raises(NotImplementedError):
            self.client.withdraw()


class TestNoWriteMethodsOnStub:
    """AaveV4EthereumHubClient に意図しない write API が露出していないことを検証。"""

    def setup_method(self) -> None:
        self.client = AaveV4EthereumHubClient()

    def test_approve_method_does_not_exist(self) -> None:
        """approve メソッドが存在しないこと。"""
        assert not hasattr(self.client, "approve")

    def test_supply_method_does_not_exist(self) -> None:
        """supply メソッドが存在しないこと。"""
        assert not hasattr(self.client, "supply")

    def test_send_transaction_method_does_not_exist(self) -> None:
        """send_transaction メソッドが存在しないこと。"""
        assert not hasattr(self.client, "send_transaction")


# --------------------------------------------------------------------------- #
# (4) schemas のインスタンス化
# --------------------------------------------------------------------------- #


class TestSchemas:
    """AaveV4HubConfig / V4AccountData が正しくインスタンス化できることを検証。"""

    def test_aave_v4_hub_config_default(self) -> None:
        """AaveV4HubConfig がデフォルト値でインスタンス化できること。"""
        config = AaveV4HubConfig()
        assert config.hub_address == ""
        assert config.rpc_url == ""
        assert config.chain_id == 0
        assert config.timeout_sec == 10

    def test_aave_v4_hub_config_custom(self) -> None:
        """AaveV4HubConfig にカスタム値を設定できること。"""
        config = AaveV4HubConfig(
            hub_address="0xDeaDbeefdEAdbeefdEadbEEFdeadbeEFdEaDbeeF",
            rpc_url="https://rpc.example.com",
            chain_id=8453,
            timeout_sec=30,
        )
        assert config.chain_id == 8453
        assert config.timeout_sec == 30

    def test_v4_account_data_default(self) -> None:
        """V4AccountData がデフォルト値でインスタンス化できること。"""
        data = V4AccountData()
        assert data.total_collateral_usd == Decimal("0")
        assert data.health_factor == Decimal("0")

    def test_v4_account_data_fields_are_decimal(self) -> None:
        """V4AccountData の全金融フィールドが Decimal 型であること。"""
        data = V4AccountData(
            total_collateral_usd=Decimal("5000"),
            total_debt_usd=Decimal("1000"),
            available_borrows_usd=Decimal("2000"),
            health_factor=Decimal("3.0"),
        )
        assert isinstance(data.total_collateral_usd, Decimal)
        assert isinstance(data.total_debt_usd, Decimal)
        assert isinstance(data.available_borrows_usd, Decimal)
        assert isinstance(data.health_factor, Decimal)

    def test_v4_account_data_no_float(self) -> None:
        """V4AccountData のフィールドに float が入らないこと (Rule 11)。"""
        data = V4AccountData(
            total_collateral_usd=Decimal("5000"),
            total_debt_usd=Decimal("1000"),
            available_borrows_usd=Decimal("2000"),
            health_factor=Decimal("3.0"),
        )
        for field_name in (
            "total_collateral_usd",
            "total_debt_usd",
            "available_borrows_usd",
            "health_factor",
        ):
            value = getattr(data, field_name)
            assert not isinstance(value, float), f"{field_name} が float になっている"


# --------------------------------------------------------------------------- #
# (5) V3 モジュールへの副作用なし (独立性)
# --------------------------------------------------------------------------- #


class TestV3Independence:
    """app.aave_v4 のインポートが既存 V3 モジュールに副作用を与えないことを検証。"""

    def test_v3_module_import_unaffected(self) -> None:
        """app.aave.client を import しても V3 AccountData が変わらないこと。"""
        from app.aave.client import AccountData as V3AccountData
        from app.aave.client import DummyAaveClient as V3DummyClient

        v3_client = V3DummyClient()
        result = v3_client.get_account_data("")
        assert isinstance(result, V3AccountData)
        assert isinstance(result.health_factor, Decimal)

    def test_v4_dummy_does_not_affect_v3_dummy(self) -> None:
        """DummyAaveV4Client と DummyAaveClient が独立したインスタンスであること。"""
        from app.aave.client import DummyAaveClient

        v3 = DummyAaveClient()
        v4 = DummyAaveV4Client()

        # 両方の read メソッドが独立して動作すること
        assert v3.get_health_factor() == v4.get_health_factor()  # 同じ固定値
        assert type(v3) is not type(v4)  # 異なるクラス

    def test_aave_v4_module_exports(self) -> None:
        """app.aave_v4 の __all__ に期待クラスが含まれること。"""
        import app.aave_v4 as aave_v4_module

        assert "AaveV4ClientBase" in aave_v4_module.__all__
        assert "DummyAaveV4Client" in aave_v4_module.__all__
        assert "AaveV4HubConfig" in aave_v4_module.__all__
        assert "V4AccountData" in aave_v4_module.__all__

    def test_v3_class_hierarchy_unaffected(self) -> None:
        """V4 クラス追加後も V3 AaveClientBase のサブクラス関係が変わらないこと。"""
        from app.aave.client import AaveClientBase, DummyAaveClient

        assert issubclass(DummyAaveClient, AaveClientBase)
        # V4 クラスも AaveClientBase を継承していることを確認
        assert issubclass(DummyAaveV4Client, AaveClientBase)
        assert issubclass(AaveV4EthereumHubClient, AaveClientBase)
