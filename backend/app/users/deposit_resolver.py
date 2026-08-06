# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/users/deposit_resolver.py

"""ユーザーの「運用に充てられる入金額（deposit, USD）」を解決する共有ヘルパー。

A-2 の実行時ゲート（提案承認 / モード切替）が「残高が最低入金額 `MIN_DEPOSIT_USD`
を満たすか」を判定するために使う。提案生成側 (`ai_judgment_scheduler`) は hot path で
allocation/wallet を既に計算しているためインラインでゲートし、本ヘルパーは
ユーザー操作起点の cold path（承認・設定）から呼ぶ。

解決順（`_resolve_proposal_amount` の deposit 部分と一致させる / docs/61 案C）:
  0. smart_wallet_address を持つユーザーは 1 を飛ばして 2 へ（`uses_custodial_allocation`）
  1. active fund_allocations 合計（custodial パートナー/テスター枠）
  2. 非カストディアル消費者: 本人 wallet の on-chain USDC 残高
  3. どちらも無い: None（判定不能）

[2026-08-06] 0 を追加した理由: `fund_allocations` は **custodial プールの持分を表す帳簿行**で
あり、オンチェーンの裏付けを持たない。SCW を持つユーザーの執行は本人 SCW から行われる
（`_should_use_scw_route` → `_execute_supply_via_scw`）ため、帳簿額でゲートを通すと
「$200 ゲートは通過するが SCW 残高 0 で on-chain revert」になる。実際、本番の user 11 は
allocation $4,600 / SCW 実残高 $0 で、この形の失敗が確定する状態だった。ブロックされる側
（安全側）に倒すため、SCW 保有ユーザーは実残高のみを資金源とみなす。

戻り値:
  - Decimal: 解決できた deposit（USD）
  - None: allocation も wallet も無い、または on-chain 残高取得失敗（判定不能）

呼び出し側は「None=判定不能」と「Decimal で MIN 未満」を区別すること。
ユーザー操作起点のゲートは None を fail-open（インフラ起因で正規操作を止めない）、
確定した不足のみブロックする方針。金融計算は Decimal のみ（CLAUDE.md [CRITICAL] 11）。
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.models import User


def uses_custodial_allocation(user: Optional[User]) -> bool:
    """このユーザーの資金源として `fund_allocations`（custodial 枠）を使ってよいか。

    smart_wallet_address を持つユーザーは執行が本人 SCW から行われるため、プールの
    持分帳簿である `fund_allocations` を資金源に使わない（モジュール docstring の 0 参照）。

    Args:
        user: 対象ユーザー。None は「判別不能」なので従来どおり allocation を許可する。

    Returns:
        allocation を資金源として使ってよいなら True。
    """
    return not (user is not None and user.smart_wallet_address)


def resolve_user_deposit_usd(db: Session, user_id: int) -> Optional[Decimal]:
    """ユーザーの deposit（運用に充てられる入金額・USD）を解決する。

    Args:
        db: SQLAlchemy セッション。
        user_id: 対象ユーザー ID。

    Returns:
        deposit（USD）。判定不能なら None。
    """
    from app.partner.allocation_models import FundAllocation  # noqa: PLC0415

    user = db.get(User, user_id)

    # ── 1. fund_allocation 優先（custodial 枠 / SCW 保有ユーザーは対象外） ──
    if uses_custodial_allocation(user):
        raw = (
            db.query(func.sum(FundAllocation.allocated_amount_usd))
            .filter(
                FundAllocation.tester_user_id == user_id,
                FundAllocation.status == "active",
            )
            .scalar()
        )
        allocated = Decimal(str(raw)) if raw else Decimal("0")
        if allocated > Decimal("0"):
            return allocated

    # ── 2. fallback: 非カストディアル消費者の wallet USDC 残高 ──
    wallet = (user.smart_wallet_address or user.wallet_address) if user else None
    if wallet:
        from app.aave.balance import read_wallet_usdc_balance  # noqa: PLC0415

        # web3 失敗時は None（判定不能）。呼び出し側で fail-open。
        return read_wallet_usdc_balance(wallet)

    # ── 3. allocation も wallet も無い → 判定不能 ──
    return None
