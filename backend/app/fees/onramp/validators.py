# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/fees/onramp/validators.py
"""フィアット オンランプ 純粋バリデータ (Phase A)。

全関数は副作用なし / I/O なし / 秘密情報なしの純粋関数。
既存 backend/app/fees/ の規約 (frozen dataclass + Decimal, I/O 禁止) に準拠。

禁止事項 (本モジュールに絶対含めない):
- webhook signature 検証 / HMAC / secret 比較
- Stripe SDK import / Stripe API 呼出
- DB アクセス / HTTP リクエスト
- float による金額計算 (Rule 11: Decimal のみ)

バリデーション対象:
1. フィアット金額の最小/最大チェック (Decimal)
2. フィアット通貨許可リスト検証
3. 対象暗号資産許可リスト検証
4. ウォレットアドレス形式検証 (EVM 0x + 40 hex 文字)
5. 状態遷移バリデータ (docs/60_stripe_privy_fiat_onramp_design.md §5 と一致)

金額境界値 (暫定値 / 【要確認】フェーズ B 実装前に Stripe 公式ドキュメントで確認):
    MIN_FIAT_AMOUNT = Decimal("10.00")     -- 最小オンランプ額 (USD 基準, 暫定)
    MAX_FIAT_AMOUNT = Decimal("10000.00")  -- 最大オンランプ額 (USD 基準, 暫定)

通貨許可リスト (暫定値 / 【要確認】Stripe Crypto Onramp 対応通貨を公式ドキュメントで確認):
    ALLOWED_FIAT_CURRENCIES = {"USD", "EUR", "JPY"}

暗号資産許可リスト (暫定値 / 【要確認】Stripe Crypto Onramp 対応資産を公式ドキュメントで確認):
    ALLOWED_TARGET_CRYPTOS = {"ETH", "USDC"}
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final

from .schemas import OnrampStatus

# ---------------------------------------------------------------------------
# モジュール定数 (許可リスト / 境界値)
# 【要確認】: 以下の値はすべて暫定。フェーズ B 実装前に Stripe 公式ドキュメントで確認すること。
# docs/60_stripe_privy_fiat_onramp_design.md §7 / §8 参照。
# ---------------------------------------------------------------------------

#: 最小オンランプ額 (暫定: USD 10.00 相当)。
#: float 禁止 (Rule 11)。Decimal 文字列リテラルで定義。
MIN_FIAT_AMOUNT: Final[Decimal] = Decimal("10.00")

#: 最大オンランプ額 (暫定: USD 10,000.00 相当)。
#: float 禁止 (Rule 11)。
MAX_FIAT_AMOUNT: Final[Decimal] = Decimal("10000.00")

#: 対応フィアット通貨許可リスト (ISO 4217, 暫定)。
#: 【要確認】Stripe Crypto Onramp の実際の対応通貨を確認して更新すること。
ALLOWED_FIAT_CURRENCIES: Final[frozenset[str]] = frozenset({"USD", "EUR", "JPY"})

#: 対応暗号資産許可リスト (暫定)。
#: 【要確認】Stripe Crypto Onramp の実際の対応資産を確認して更新すること。
ALLOWED_TARGET_CRYPTOS: Final[frozenset[str]] = frozenset({"ETH", "USDC"})

#: EVM ウォレットアドレスの正規表現。
#: "0x" プレフィックス + 40 文字の16進数 = 計 42 文字。
#: backend/app/auth/schemas.py WalletConnectRequest(min_length=42, max_length=42) 準拠。
_EVM_ADDRESS_RE: Final[re.Pattern[str]] = re.compile(r"^0x[0-9a-fA-F]{40}$")

#: 有効な状態遷移セット (from_status, to_status) のペア。
#: docs/60_stripe_privy_fiat_onramp_design.md §5 状態遷移図と一致させること。
_VALID_TRANSITIONS: Final[frozenset[tuple[OnrampStatus, OnrampStatus]]] = frozenset(
    {
        (OnrampStatus.CREATED, OnrampStatus.PENDING),  # セッション開始
        (OnrampStatus.CREATED, OnrampStatus.FAILED),  # 即時失敗
        (OnrampStatus.PENDING, OnrampStatus.SETTLED),  # 着金完了
        (OnrampStatus.PENDING, OnrampStatus.FAILED),  # タイムアウト / 失敗
    }
)


# ---------------------------------------------------------------------------
# 純粋バリデータ関数
# ---------------------------------------------------------------------------


def validate_fiat_amount(amount: Decimal) -> None:
    """フィアット金額が最小/最大オンランプ額の範囲内か検証する。

    副作用なし / I/O なし / 純粋関数。
    float 禁止 (Rule 11): 引数は必ず Decimal で渡すこと。

    Args:
        amount: 検証対象のフィアット金額 (Decimal)。

    Raises:
        ValueError: amount が MIN_FIAT_AMOUNT 未満、または MAX_FIAT_AMOUNT 超過の場合。
        TypeError: amount が Decimal 型でない場合。

    Examples:
        >>> from decimal import Decimal
        >>> validate_fiat_amount(Decimal("100.00"))  # OK
        >>> validate_fiat_amount(Decimal("9.99"))    # ValueError
    """
    if not isinstance(amount, Decimal):
        raise TypeError(
            f"fiat_amount must be Decimal, got {type(amount).__name__}. "
            "float は金融計算に使用禁止 (Security Rules Rule 11)。"
        )
    if amount < MIN_FIAT_AMOUNT:
        raise ValueError(
            f"fiat_amount {amount} は最小オンランプ額 {MIN_FIAT_AMOUNT} を下回っています。"
        )
    if amount > MAX_FIAT_AMOUNT:
        raise ValueError(
            f"fiat_amount {amount} は最大オンランプ額 {MAX_FIAT_AMOUNT} を超過しています。"
        )


def validate_fiat_currency(currency: str) -> None:
    """フィアット通貨が許可リスト内か検証する。

    副作用なし / I/O なし / 純粋関数。

    Args:
        currency: ISO 4217 通貨コード (例: "USD", "EUR", "JPY")。

    Raises:
        ValueError: currency が ALLOWED_FIAT_CURRENCIES に含まれない場合。

    Examples:
        >>> validate_fiat_currency("USD")  # OK
        >>> validate_fiat_currency("BTC")  # ValueError
    """
    if currency not in ALLOWED_FIAT_CURRENCIES:
        raise ValueError(
            f"fiat_currency '{currency}' は許可リスト外です。"
            f"許可: {sorted(ALLOWED_FIAT_CURRENCIES)}"
        )


def validate_target_crypto(crypto: str) -> None:
    """対象暗号資産が許可リスト内か検証する。

    副作用なし / I/O なし / 純粋関数。

    Args:
        crypto: 暗号資産シンボル (例: "ETH", "USDC")。

    Raises:
        ValueError: crypto が ALLOWED_TARGET_CRYPTOS に含まれない場合。

    Examples:
        >>> validate_target_crypto("ETH")   # OK
        >>> validate_target_crypto("BTC")   # ValueError
    """
    if crypto not in ALLOWED_TARGET_CRYPTOS:
        raise ValueError(
            f"target_crypto '{crypto}' は許可リスト外です。許可: {sorted(ALLOWED_TARGET_CRYPTOS)}"
        )


def validate_wallet_address(address: str) -> None:
    """EVM ウォレットアドレスの形式を検証する。

    副作用なし / I/O なし / 純粋関数。
    "0x" プレフィックス + 40 文字の16進数 = 計 42 文字の形式を要求する。
    backend/app/auth/schemas.py WalletConnectRequest の min_length=42, max_length=42 制約と一致。

    Args:
        address: 検証対象の EVM ウォレットアドレス。

    Raises:
        ValueError: address が EVM アドレス形式でない場合。

    Examples:
        >>> validate_wallet_address("0x" + "a" * 40)  # OK
        >>> validate_wallet_address("0x1234")          # ValueError
    """
    if not _EVM_ADDRESS_RE.match(address):
        raise ValueError(
            f"wallet_address '{address}' は不正な EVM アドレス形式です。"
            "期待: '0x' + 40文字の16進数 (計42文字)。"
        )


def is_valid_transition(from_status: OnrampStatus, to_status: OnrampStatus) -> bool:
    """オンランプ状態遷移が有効か検証する。

    副作用なし / I/O なし / 純粋関数。
    有効な遷移は _VALID_TRANSITIONS で定義し、
    docs/60_stripe_privy_fiat_onramp_design.md §5 状態遷移図と一致させる。

    Args:
        from_status: 現在の状態。
        to_status: 遷移先の状態。

    Returns:
        True if the transition is valid, False otherwise.

    Examples:
        >>> is_valid_transition(OnrampStatus.CREATED, OnrampStatus.PENDING)  # True
        >>> is_valid_transition(OnrampStatus.SETTLED, OnrampStatus.PENDING)  # False
    """
    return (from_status, to_status) in _VALID_TRANSITIONS


def validate_transition(from_status: OnrampStatus, to_status: OnrampStatus) -> None:
    """オンランプ状態遷移が有効か検証し、不正な場合は ValueError を送出する。

    副作用なし / I/O なし / 純粋関数。
    ``is_valid_transition`` の例外送出ラッパー。

    Args:
        from_status: 現在の状態。
        to_status: 遷移先の状態。

    Raises:
        ValueError: 状態遷移が無効な場合。

    Examples:
        >>> validate_transition(OnrampStatus.CREATED, OnrampStatus.PENDING)  # OK
        >>> validate_transition(OnrampStatus.SETTLED, OnrampStatus.PENDING)  # ValueError
    """
    if not is_valid_transition(from_status, to_status):
        raise ValueError(
            f"無効な状態遷移: {from_status.value!r} → {to_status.value!r}。"
            "docs/60_stripe_privy_fiat_onramp_design.md §5 参照。"
        )
