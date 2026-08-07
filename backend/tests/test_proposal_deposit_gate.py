# Copyright (c) Ultra AutoTrade. All rights reserved.
"""提案生成側の入金ゲート（_resolve_proposal_amount）の単体テスト。

A-2: deposit が運用開始の最低入金額 (MIN_DEPOSIT_USD=$1000) 未満なら、custodial /
非カストディアル いずれの経路でも Decimal("0")（= 呼び出し側で skip）を返すことを検証。
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.automation.ai_judgment_scheduler import _resolve_proposal_amount


def _db_with_allocation(total) -> MagicMock:  # type: ignore[no-untyped-def]
    """db.get は既定で「SCW を持たない custodial ユーザー」を返す。

    素の MagicMock だと smart_wallet_address が truthy になり、SCW 保有ユーザー扱いで
    allocation が sizing の分母から外れる（uses_custodial_allocation / 2026-08-06）。
    """
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = total
    # allocation 帳簿の有無判定 (_has_active_allocation) は .first() を見る。
    # 素の MagicMock だと truthy になり「帳簿あり」と誤判定され、入金ファネルが
    # 適用対象外になってしまう。total で明示的に切り替える。
    db.query.return_value.filter.return_value.first.return_value = MagicMock() if total else None
    db.get.return_value = MagicMock(smart_wallet_address=None, wallet_address=None)
    return db


def test_custodial_below_gate_skipped() -> None:
    """custodial allocation $150 (<$1000) は提案 0（skip）。"""
    db = _db_with_allocation(Decimal("150"))
    assert _resolve_proposal_amount(db, user_id=11) == Decimal("0")


def test_custodial_at_gate_generates() -> None:
    """custodial allocation $5000 (>=$1000) は提案 > 0。"""
    db = _db_with_allocation(Decimal("5000"))
    amount = _resolve_proposal_amount(db, user_id=11)
    assert amount > Decimal("0")


def test_consumer_wallet_below_gate_uses_funding_funnel() -> None:
    """非カストディアル wallet 残高 $150 (<$1000) は推奨運用額ベースの提案を出す。

    2026-08-07 仕様変更 (docs/62 承認→入金→署名ファネル): 以前は $0 で skip していたが、
    それでは「提案を見て入金する」導線が非カストディアル経路で成立しなかった。
    custodial allocation 経路 (上の test_custodial_below_gate_skipped) は台帳額が
    入金意思の裏付けなので skip のまま据え置き、**非対称は意図的**。

    残高 $150 に対し提案額が上回るが、実行は着金検知が MIN_DEPOSIT_USD を再検証して
    止める (tests/automation/test_funding_funnel_sizing.py)。
    """
    db = _db_with_allocation(0)
    db.get.return_value = MagicMock(smart_wallet_address=None, wallet_address="0xabc")
    with patch(
        "app.automation.ai_judgment_scheduler._read_wallet_usdc_balance",
        return_value=Decimal("150"),
    ):
        assert _resolve_proposal_amount(db, user_id=9) > Decimal("0")


def test_consumer_wallet_above_gate_generates() -> None:
    """非カストディアル wallet 残高 $2500 (>=$1000) は提案 > 0。"""
    db = _db_with_allocation(0)
    db.get.return_value = MagicMock(smart_wallet_address=None, wallet_address="0xabc")
    with patch(
        "app.automation.ai_judgment_scheduler._read_wallet_usdc_balance",
        return_value=Decimal("2500"),
    ):
        assert _resolve_proposal_amount(db, user_id=9) > Decimal("0")
