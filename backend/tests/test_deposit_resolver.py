# Copyright (c) Ultra AutoTrade. All rights reserved.
"""resolve_user_deposit_usd（deposit 解決ヘルパー）の単体テスト。

custodial allocation / 非カストディアル wallet fallback / 判定不能(None) の
3 経路を mock セッションで検証する。
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.users.deposit_resolver import resolve_user_deposit_usd


def _db_with_allocation(total) -> MagicMock:  # type: ignore[no-untyped-def]
    """db.query(...).filter(...).scalar() が total を返す mock セッション。"""
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = total
    return db


def test_custodial_allocation_returned() -> None:
    """active fund_allocations 合計が deposit として返る。"""
    db = _db_with_allocation(Decimal("5000"))
    assert resolve_user_deposit_usd(db, user_id=11) == Decimal("5000")


def test_falls_back_to_wallet_when_no_allocation() -> None:
    """allocation 0 → wallet USDC 残高に fallback する。"""
    db = _db_with_allocation(0)
    user = MagicMock(smart_wallet_address=None, wallet_address="0xabc")
    db.get.return_value = user
    with patch("app.aave.balance.read_wallet_usdc_balance", return_value=Decimal("150")):
        assert resolve_user_deposit_usd(db, user_id=9) == Decimal("150")


def test_smart_wallet_preferred_over_eoa() -> None:
    """smart_wallet_address があればそれを優先して残高を読む。"""
    db = _db_with_allocation(None)
    user = MagicMock(smart_wallet_address="0xSCW", wallet_address="0xEOA")
    db.get.return_value = user
    with patch("app.aave.balance.read_wallet_usdc_balance", return_value=Decimal("250")) as reader:
        assert resolve_user_deposit_usd(db, user_id=9) == Decimal("250")
        reader.assert_called_once_with("0xSCW")


def test_none_when_no_allocation_and_no_wallet() -> None:
    """allocation も wallet も無ければ判定不能 (None)。"""
    db = _db_with_allocation(0)
    db.get.return_value = MagicMock(smart_wallet_address=None, wallet_address=None)
    assert resolve_user_deposit_usd(db, user_id=42) is None


def test_none_when_wallet_balance_unavailable() -> None:
    """wallet はあるが on-chain 残高取得失敗 → None（判定不能 / fail-open は呼び出し側）。"""
    db = _db_with_allocation(0)
    db.get.return_value = MagicMock(smart_wallet_address=None, wallet_address="0xabc")
    with patch("app.aave.balance.read_wallet_usdc_balance", return_value=None):
        assert resolve_user_deposit_usd(db, user_id=9) is None
