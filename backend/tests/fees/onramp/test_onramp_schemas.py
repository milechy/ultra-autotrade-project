# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/fees/onramp/test_onramp_schemas.py
"""OnrampSessionIntent / OnrampSettlementEvent / OnrampStatus スキーマ テスト。

テスト対象:
- OnrampStatus: enum 値の正当性
- OnrampSessionIntent: 正常構築 / frozen (不変) / Decimal 型強制
- OnrampSettlementEvent: 正常構築 / Optional フィールド / frozen (不変)

外部 API / DB / 秘密情報は一切使用しない。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.fees.onramp.schemas import (
    OnrampSessionIntent,
    OnrampSettlementEvent,
    OnrampStatus,
)

# ---------------------------------------------------------------------------
# OnrampStatus
# ---------------------------------------------------------------------------


class TestOnrampStatus:
    def test_values_match_design_doc(self) -> None:
        """状態値が設計書 §5 の状態遷移図と一致していること。"""
        assert OnrampStatus.CREATED.value == "created"
        assert OnrampStatus.PENDING.value == "pending"
        assert OnrampStatus.SETTLED.value == "settled"
        assert OnrampStatus.FAILED.value == "failed"

    def test_str_enum_is_string(self) -> None:
        """OnrampStatus は str のサブクラスであること (JSON シリアライズ対応)。"""
        assert isinstance(OnrampStatus.CREATED, str)
        assert OnrampStatus.CREATED == "created"

    def test_all_four_statuses_defined(self) -> None:
        """4 状態すべてが定義されていること。"""
        members = {s.value for s in OnrampStatus}
        assert members == {"created", "pending", "settled", "failed"}

    def test_from_string(self) -> None:
        """文字列から OnrampStatus を生成できること。"""
        assert OnrampStatus("settled") is OnrampStatus.SETTLED
        assert OnrampStatus("failed") is OnrampStatus.FAILED


# ---------------------------------------------------------------------------
# OnrampSessionIntent
# ---------------------------------------------------------------------------


class TestOnrampSessionIntent:
    """OnrampSessionIntent の正常系・型検証テスト。"""

    def _make_intent(
        self,
        *,
        user_id: int = 1,
        fiat_amount: Decimal = Decimal("100.00"),
        fiat_currency: str = "USD",
        target_crypto: str = "ETH",
        destination_wallet_address: str = "0x" + "a" * 40,
    ) -> OnrampSessionIntent:
        return OnrampSessionIntent(
            user_id=user_id,
            fiat_amount=fiat_amount,
            fiat_currency=fiat_currency,
            target_crypto=target_crypto,
            destination_wallet_address=destination_wallet_address,
        )

    def test_normal_construction(self) -> None:
        """正常値でインスタンスが構築できること。"""
        intent = self._make_intent()
        assert intent.user_id == 1
        assert intent.fiat_amount == Decimal("100.00")
        assert intent.fiat_currency == "USD"
        assert intent.target_crypto == "ETH"
        assert intent.destination_wallet_address == "0x" + "a" * 40

    def test_frozen_immutable(self) -> None:
        """frozen=True で属性が変更不可であること。"""
        intent = self._make_intent()
        with pytest.raises(FrozenInstanceError):
            intent.fiat_amount = Decimal("200.00")  # type: ignore[misc]

    def test_fiat_amount_is_decimal(self) -> None:
        """fiat_amount が Decimal として保持されること。"""
        intent = self._make_intent(fiat_amount=Decimal("9999.99"))
        assert isinstance(intent.fiat_amount, Decimal)
        assert intent.fiat_amount == Decimal("9999.99")

    def test_large_user_id(self) -> None:
        """user_id に大きな整数を指定できること。"""
        intent = self._make_intent(user_id=999999)
        assert intent.user_id == 999999

    def test_various_fiat_currencies(self) -> None:
        """fiat_currency に任意の文字列を格納できること (許可リスト検証は validators 担当)。"""
        for currency in ("USD", "EUR", "JPY"):
            intent = self._make_intent(fiat_currency=currency)
            assert intent.fiat_currency == currency

    def test_various_target_cryptos(self) -> None:
        """target_crypto に任意の文字列を格納できること (許可リスト検証は validators 担当)。"""
        for crypto in ("ETH", "USDC"):
            intent = self._make_intent(target_crypto=crypto)
            assert intent.target_crypto == crypto

    def test_wallet_address_stored_as_is(self) -> None:
        """destination_wallet_address は文字列のまま保持されること。"""
        addr = "0x" + "f" * 40
        intent = self._make_intent(destination_wallet_address=addr)
        assert intent.destination_wallet_address == addr

    def test_equality(self) -> None:
        """同じ値の OnrampSessionIntent は等しいこと (frozen dataclass)。"""
        a = self._make_intent()
        b = self._make_intent()
        assert a == b

    def test_inequality_on_different_amount(self) -> None:
        """fiat_amount が異なる場合は不等であること。"""
        a = self._make_intent(fiat_amount=Decimal("100.00"))
        b = self._make_intent(fiat_amount=Decimal("200.00"))
        assert a != b


# ---------------------------------------------------------------------------
# OnrampSettlementEvent
# ---------------------------------------------------------------------------


class TestOnrampSettlementEvent:
    """OnrampSettlementEvent の正常系・Optional フィールド・型検証テスト。"""

    def test_normal_construction_settled(self) -> None:
        """SETTLED 状態で crypto_amount_received ありの正常構築。"""
        event = OnrampSettlementEvent(
            intent_id="intent-001",
            status=OnrampStatus.SETTLED,
            crypto_amount_received=Decimal("0.05"),
            vendor_reference_id="stripe-session-abc123",
        )
        assert event.intent_id == "intent-001"
        assert event.status is OnrampStatus.SETTLED
        assert event.crypto_amount_received == Decimal("0.05")
        assert event.vendor_reference_id == "stripe-session-abc123"

    def test_normal_construction_failed(self) -> None:
        """FAILED 状態で crypto_amount_received なしの正常構築。"""
        event = OnrampSettlementEvent(
            intent_id="intent-002",
            status=OnrampStatus.FAILED,
        )
        assert event.status is OnrampStatus.FAILED
        assert event.crypto_amount_received is None
        assert event.vendor_reference_id is None

    def test_optional_fields_default_to_none(self) -> None:
        """crypto_amount_received / vendor_reference_id はデフォルト None。"""
        event = OnrampSettlementEvent(
            intent_id="intent-003",
            status=OnrampStatus.PENDING,
        )
        assert event.crypto_amount_received is None
        assert event.vendor_reference_id is None

    def test_frozen_immutable(self) -> None:
        """frozen=True で属性が変更不可であること。"""
        event = OnrampSettlementEvent(
            intent_id="intent-004",
            status=OnrampStatus.CREATED,
        )
        with pytest.raises(FrozenInstanceError):
            event.status = OnrampStatus.SETTLED  # type: ignore[misc]

    def test_crypto_amount_is_decimal(self) -> None:
        """crypto_amount_received が Decimal として保持されること。"""
        amount = Decimal("1.234567890123456789")
        event = OnrampSettlementEvent(
            intent_id="intent-005",
            status=OnrampStatus.SETTLED,
            crypto_amount_received=amount,
        )
        assert isinstance(event.crypto_amount_received, Decimal)
        assert event.crypto_amount_received == amount

    def test_status_enum_assignment(self) -> None:
        """status に OnrampStatus enum を直接代入できること。"""
        for status in OnrampStatus:
            event = OnrampSettlementEvent(
                intent_id="intent-x",
                status=status,
            )
            assert event.status is status

    def test_no_secret_fields(self) -> None:
        """スキーマに秘密情報フィールドが存在しないこと。"""
        event = OnrampSettlementEvent(
            intent_id="test",
            status=OnrampStatus.CREATED,
        )
        prohibited = {
            "stripe_signature",
            "webhook_secret",
            "api_key",
            "secret",
            "hmac",
        }
        actual_fields = {f.name for f in event.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        assert not prohibited.intersection(actual_fields), (
            f"秘密情報フィールドが含まれています: {prohibited.intersection(actual_fields)}"
        )

    def test_equality(self) -> None:
        """同じ値の OnrampSettlementEvent は等しいこと。"""
        a = OnrampSettlementEvent(
            intent_id="intent-eq",
            status=OnrampStatus.SETTLED,
            crypto_amount_received=Decimal("0.1"),
        )
        b = OnrampSettlementEvent(
            intent_id="intent-eq",
            status=OnrampStatus.SETTLED,
            crypto_amount_received=Decimal("0.1"),
        )
        assert a == b
