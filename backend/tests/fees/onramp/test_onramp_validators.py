# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/tests/fees/onramp/test_onramp_validators.py
"""フィアット オンランプ 純粋バリデータ テスト。

テスト対象:
- validate_fiat_amount  : 最小/最大境界 (下限未満 / 上限超過 / 境界ちょうど)
- validate_fiat_currency: 許可通貨 / 非許可通貨
- validate_target_crypto: 許可暗号資産 / 非許可暗号資産
- validate_wallet_address: 正常形式 / 異常形式 (長さ / プレフィックス / 非16進数)
- is_valid_transition / validate_transition: 全 valid/invalid ペア

外部 API / DB / 秘密情報は一切使用しない。
webhook signature / HMAC / secret は一切テストしない (フェーズ B スコープ)。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.fees.onramp.schemas import OnrampStatus
from app.fees.onramp.validators import (
    ALLOWED_FIAT_CURRENCIES,
    ALLOWED_TARGET_CRYPTOS,
    MAX_FIAT_AMOUNT,
    MIN_FIAT_AMOUNT,
    is_valid_transition,
    validate_fiat_amount,
    validate_fiat_currency,
    validate_target_crypto,
    validate_transition,
    validate_wallet_address,
)

# ---------------------------------------------------------------------------
# validate_fiat_amount
# ---------------------------------------------------------------------------


class TestValidateFiatAmount:
    """フィアット金額バリデータのテスト。"""

    def test_minimum_amount_ok(self) -> None:
        """最小額ちょうど (MIN_FIAT_AMOUNT) は正常。"""
        validate_fiat_amount(MIN_FIAT_AMOUNT)  # 例外なし

    def test_maximum_amount_ok(self) -> None:
        """最大額ちょうど (MAX_FIAT_AMOUNT) は正常。"""
        validate_fiat_amount(MAX_FIAT_AMOUNT)  # 例外なし

    def test_middle_amount_ok(self) -> None:
        """中間値は正常。"""
        validate_fiat_amount(Decimal("500.00"))

    def test_below_minimum_raises(self) -> None:
        """MIN_FIAT_AMOUNT 未満は ValueError。"""
        below = MIN_FIAT_AMOUNT - Decimal("0.01")
        with pytest.raises(ValueError, match="最小オンランプ額"):
            validate_fiat_amount(below)

    def test_zero_raises(self) -> None:
        """0 は MIN_FIAT_AMOUNT 未満で ValueError。"""
        with pytest.raises(ValueError, match="最小オンランプ額"):
            validate_fiat_amount(Decimal("0"))

    def test_negative_raises(self) -> None:
        """負値は ValueError。"""
        with pytest.raises(ValueError, match="最小オンランプ額"):
            validate_fiat_amount(Decimal("-1.00"))

    def test_above_maximum_raises(self) -> None:
        """MAX_FIAT_AMOUNT 超過は ValueError。"""
        above = MAX_FIAT_AMOUNT + Decimal("0.01")
        with pytest.raises(ValueError, match="最大オンランプ額"):
            validate_fiat_amount(above)

    def test_float_raises_type_error(self) -> None:
        """float を渡すと TypeError (Rule 11: float 禁止)。"""
        with pytest.raises(TypeError, match="Decimal"):
            validate_fiat_amount(100.0)  # type: ignore[arg-type]

    def test_int_raises_type_error(self) -> None:
        """int を渡すと TypeError (Decimal 以外禁止)。"""
        with pytest.raises(TypeError, match="Decimal"):
            validate_fiat_amount(100)  # type: ignore[arg-type]

    def test_just_above_minimum_ok(self) -> None:
        """MIN_FIAT_AMOUNT + 0.01 は正常。"""
        validate_fiat_amount(MIN_FIAT_AMOUNT + Decimal("0.01"))

    def test_just_below_maximum_ok(self) -> None:
        """MAX_FIAT_AMOUNT - 0.01 は正常。"""
        validate_fiat_amount(MAX_FIAT_AMOUNT - Decimal("0.01"))


# ---------------------------------------------------------------------------
# validate_fiat_currency
# ---------------------------------------------------------------------------


class TestValidateFiatCurrency:
    """フィアット通貨許可リスト検証テスト。"""

    @pytest.mark.parametrize("currency", sorted(ALLOWED_FIAT_CURRENCIES))
    def test_allowed_currencies_ok(self, currency: str) -> None:
        """許可リスト内の通貨は正常。"""
        validate_fiat_currency(currency)  # 例外なし

    def test_unknown_currency_raises(self) -> None:
        """許可リスト外の通貨は ValueError。"""
        with pytest.raises(ValueError, match="許可リスト外"):
            validate_fiat_currency("BTC")

    def test_lowercase_raises(self) -> None:
        """小文字の通貨コードは許可リスト外として ValueError。"""
        with pytest.raises(ValueError, match="許可リスト外"):
            validate_fiat_currency("usd")

    def test_empty_string_raises(self) -> None:
        """空文字列は ValueError。"""
        with pytest.raises(ValueError, match="許可リスト外"):
            validate_fiat_currency("")

    def test_krw_raises(self) -> None:
        """許可リストにない KRW は ValueError。"""
        with pytest.raises(ValueError, match="許可リスト外"):
            validate_fiat_currency("KRW")

    def test_gbp_raises(self) -> None:
        """許可リストにない GBP は ValueError。"""
        with pytest.raises(ValueError, match="許可リスト外"):
            validate_fiat_currency("GBP")


# ---------------------------------------------------------------------------
# validate_target_crypto
# ---------------------------------------------------------------------------


class TestValidateTargetCrypto:
    """対象暗号資産許可リスト検証テスト。"""

    @pytest.mark.parametrize("crypto", sorted(ALLOWED_TARGET_CRYPTOS))
    def test_allowed_cryptos_ok(self, crypto: str) -> None:
        """許可リスト内の暗号資産は正常。"""
        validate_target_crypto(crypto)  # 例外なし

    def test_btc_raises(self) -> None:
        """許可リストにない BTC は ValueError。"""
        with pytest.raises(ValueError, match="許可リスト外"):
            validate_target_crypto("BTC")

    def test_lowercase_raises(self) -> None:
        """小文字の暗号資産シンボルは ValueError。"""
        with pytest.raises(ValueError, match="許可リスト外"):
            validate_target_crypto("eth")

    def test_empty_string_raises(self) -> None:
        """空文字列は ValueError。"""
        with pytest.raises(ValueError, match="許可リスト外"):
            validate_target_crypto("")

    def test_sol_raises(self) -> None:
        """許可リストにない SOL は ValueError。"""
        with pytest.raises(ValueError, match="許可リスト外"):
            validate_target_crypto("SOL")


# ---------------------------------------------------------------------------
# validate_wallet_address
# ---------------------------------------------------------------------------


class TestValidateWalletAddress:
    """EVM ウォレットアドレス形式検証テスト。"""

    def test_valid_lowercase_hex(self) -> None:
        """0x + 40 文字小文字16進数は正常。"""
        validate_wallet_address("0x" + "a" * 40)

    def test_valid_uppercase_hex(self) -> None:
        """0x + 40 文字大文字16進数は正常。"""
        validate_wallet_address("0x" + "A" * 40)

    def test_valid_mixed_hex(self) -> None:
        """0x + 40 文字混合16進数は正常。"""
        validate_wallet_address("0xAbCdEf0123456789AbCdEf0123456789AbCdEf01")

    def test_valid_all_zeros(self) -> None:
        """ゼロアドレス (0x000...000) は形式として正常。"""
        validate_wallet_address("0x" + "0" * 40)

    def test_too_short_raises(self) -> None:
        """41 文字 (0x + 39 hex) は ValueError。"""
        with pytest.raises(ValueError, match="不正な EVM アドレス形式"):
            validate_wallet_address("0x" + "a" * 39)

    def test_too_long_raises(self) -> None:
        """43 文字 (0x + 41 hex) は ValueError。"""
        with pytest.raises(ValueError, match="不正な EVM アドレス形式"):
            validate_wallet_address("0x" + "a" * 41)

    def test_missing_0x_prefix_raises(self) -> None:
        """0x プレフィックスなしの 40 文字は ValueError。"""
        with pytest.raises(ValueError, match="不正な EVM アドレス形式"):
            validate_wallet_address("a" * 40)

    def test_wrong_prefix_raises(self) -> None:
        """0X (大文字 X) プレフィックスは ValueError。"""
        with pytest.raises(ValueError, match="不正な EVM アドレス形式"):
            validate_wallet_address("0X" + "a" * 40)

    def test_non_hex_characters_raises(self) -> None:
        """非16進数文字 (g, z 等) は ValueError。"""
        with pytest.raises(ValueError, match="不正な EVM アドレス形式"):
            validate_wallet_address("0x" + "g" * 40)

    def test_empty_string_raises(self) -> None:
        """空文字列は ValueError。"""
        with pytest.raises(ValueError, match="不正な EVM アドレス形式"):
            validate_wallet_address("")

    def test_spaces_raises(self) -> None:
        """スペースを含む場合は ValueError。"""
        with pytest.raises(ValueError, match="不正な EVM アドレス形式"):
            validate_wallet_address("0x" + " " * 40)

    def test_exactly_42_chars_valid(self) -> None:
        """正確に 42 文字 (0x + 40 hex) = auth/schemas.py の min/max 42 制約と一致。"""
        addr = "0x" + "1234567890abcdef" * 2 + "12345678"
        assert len(addr) == 42
        validate_wallet_address(addr)


# ---------------------------------------------------------------------------
# is_valid_transition / validate_transition
# ---------------------------------------------------------------------------


VALID_TRANSITION_PAIRS = [
    (OnrampStatus.CREATED, OnrampStatus.PENDING),
    (OnrampStatus.CREATED, OnrampStatus.FAILED),
    (OnrampStatus.PENDING, OnrampStatus.SETTLED),
    (OnrampStatus.PENDING, OnrampStatus.FAILED),
]

# 全状態ペアから有効ペアを除いた無効ペア (自己遷移も含む)
ALL_STATUSES = list(OnrampStatus)
INVALID_TRANSITION_PAIRS = [
    (f, t) for f in ALL_STATUSES for t in ALL_STATUSES if (f, t) not in VALID_TRANSITION_PAIRS
]


class TestIsValidTransition:
    """is_valid_transition の全 valid / invalid ペアテスト。"""

    @pytest.mark.parametrize("from_s,to_s", VALID_TRANSITION_PAIRS)
    def test_valid_transitions(self, from_s: OnrampStatus, to_s: OnrampStatus) -> None:
        """有効な遷移ペアは True を返す。"""
        assert is_valid_transition(from_s, to_s) is True

    @pytest.mark.parametrize("from_s,to_s", INVALID_TRANSITION_PAIRS)
    def test_invalid_transitions(self, from_s: OnrampStatus, to_s: OnrampStatus) -> None:
        """無効な遷移ペアは False を返す (後退・終端・スキップ・自己遷移)。"""
        assert is_valid_transition(from_s, to_s) is False

    def test_settled_is_terminal(self) -> None:
        """SETTLED から他への遷移はすべて無効 (終端)。"""
        for to_s in OnrampStatus:
            assert is_valid_transition(OnrampStatus.SETTLED, to_s) is False

    def test_failed_is_terminal(self) -> None:
        """FAILED から他への遷移はすべて無効 (終端)。"""
        for to_s in OnrampStatus:
            assert is_valid_transition(OnrampStatus.FAILED, to_s) is False

    def test_pending_to_created_is_invalid(self) -> None:
        """PENDING → CREATED は後退で無効。"""
        assert is_valid_transition(OnrampStatus.PENDING, OnrampStatus.CREATED) is False

    def test_created_to_settled_is_invalid(self) -> None:
        """CREATED → SETTLED は PENDING をスキップするため無効。"""
        assert is_valid_transition(OnrampStatus.CREATED, OnrampStatus.SETTLED) is False


class TestValidateTransition:
    """validate_transition の例外送出テスト。"""

    @pytest.mark.parametrize("from_s,to_s", VALID_TRANSITION_PAIRS)
    def test_valid_transitions_no_exception(self, from_s: OnrampStatus, to_s: OnrampStatus) -> None:
        """有効な遷移では例外が送出されない。"""
        validate_transition(from_s, to_s)  # 例外なし

    def test_settled_to_pending_raises(self) -> None:
        """SETTLED → PENDING は ValueError。"""
        with pytest.raises(ValueError, match="無効な状態遷移"):
            validate_transition(OnrampStatus.SETTLED, OnrampStatus.PENDING)

    def test_failed_to_settled_raises(self) -> None:
        """FAILED → SETTLED は ValueError。"""
        with pytest.raises(ValueError, match="無効な状態遷移"):
            validate_transition(OnrampStatus.FAILED, OnrampStatus.SETTLED)

    def test_created_to_settled_raises(self) -> None:
        """CREATED → SETTLED は PENDING スキップで ValueError。"""
        with pytest.raises(ValueError, match="無効な状態遷移"):
            validate_transition(OnrampStatus.CREATED, OnrampStatus.SETTLED)

    def test_pending_to_created_raises(self) -> None:
        """PENDING → CREATED は後退で ValueError。"""
        with pytest.raises(ValueError, match="無効な状態遷移"):
            validate_transition(OnrampStatus.PENDING, OnrampStatus.CREATED)

    @pytest.mark.parametrize("from_s,to_s", INVALID_TRANSITION_PAIRS)
    def test_all_invalid_pairs_raise(self, from_s: OnrampStatus, to_s: OnrampStatus) -> None:
        """全無効ペアで ValueError が送出されること。"""
        with pytest.raises(ValueError, match="無効な状態遷移"):
            validate_transition(from_s, to_s)
