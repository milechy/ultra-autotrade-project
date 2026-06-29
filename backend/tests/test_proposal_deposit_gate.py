# Copyright (c) Ultra AutoTrade. All rights reserved.
"""提案生成側の入金ゲート（_resolve_proposal_amount）の単体テスト。

A-2: deposit が運用開始の最低入金額 (MIN_DEPOSIT_USD=$200) 未満なら、custodial /
非カストディアル いずれの経路でも Decimal("0")（= 呼び出し側で skip）を返すことを検証。
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.automation.ai_judgment_scheduler import _resolve_proposal_amount


def _db_with_allocation(total) -> MagicMock:  # type: ignore[no-untyped-def]
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = total
    return db


def test_custodial_below_gate_skipped() -> None:
    """custodial allocation $150 (<$200) は提案 0（skip）。"""
    db = _db_with_allocation(Decimal("150"))
    assert _resolve_proposal_amount(db, user_id=11) == Decimal("0")


def test_custodial_at_gate_generates() -> None:
    """custodial allocation $5000 (>=$200) は提案 > 0。"""
    db = _db_with_allocation(Decimal("5000"))
    amount = _resolve_proposal_amount(db, user_id=11)
    assert amount > Decimal("0")


def test_consumer_wallet_below_gate_skipped() -> None:
    """非カストディアル wallet 残高 $150 (<$200) は提案 0（skip）。"""
    db = _db_with_allocation(0)
    db.get.return_value = MagicMock(smart_wallet_address=None, wallet_address="0xabc")
    with patch(
        "app.automation.ai_judgment_scheduler._read_wallet_usdc_balance",
        return_value=Decimal("150"),
    ):
        assert _resolve_proposal_amount(db, user_id=9) == Decimal("0")


def test_consumer_wallet_above_gate_generates() -> None:
    """非カストディアル wallet 残高 $2500 (>=$200) は提案 > 0。"""
    db = _db_with_allocation(0)
    db.get.return_value = MagicMock(smart_wallet_address=None, wallet_address="0xabc")
    with patch(
        "app.automation.ai_judgment_scheduler._read_wallet_usdc_balance",
        return_value=Decimal("2500"),
    ):
        assert _resolve_proposal_amount(db, user_id=9) > Decimal("0")
