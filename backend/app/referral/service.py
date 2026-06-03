# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/referral/service.py
"""RAS Lane 2 サービス層。

partner ロール用に以下を提供する:
  - 紹介コードの取得 / 自動発行
  - 紹介経由で登録された配下ユーザー一覧
  - 配下ユーザーの取引履歴 (deposit / withdraw / borrow / repay のみ、wallet/tx は除外)
  - 紹介キャンペーン ウィンドウ管理 (新規紹介時のウィンドウ開閉)
"""

from __future__ import annotations

import logging
import os
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.auth.models import User
from app.fees.models import FeeConfigV10, FeeTransaction, ReferralCampaign
from app.transactions.models import Transaction

from .code_generator import generate_referral_code

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# /referral/users/{id}/transactions が返す operation 値のホワイトリスト。
_ALLOWED_TX_TYPES = ("deposit", "withdraw", "borrow", "repay")


def _share_base_url() -> str:
    """招待 URL の base host を環境変数から取得する。"""
    return os.getenv("PUBLIC_FRONTEND_URL", "https://app.ultra-auto-trade.com").rstrip("/")


def get_or_create_code(db: Session, partner_user: User) -> str:
    """partner の紹介コードを取得 (未発行なら自動発行)。

    Args:
        db: DB セッション。
        partner_user: 紹介コードを発行する partner ユーザー。

    Returns:
        partner に紐づく 8 桁紹介コード。
    """
    if partner_user.referral_code:
        return partner_user.referral_code

    code = generate_referral_code(db)
    partner_user.referral_code = code
    db.commit()
    db.refresh(partner_user)
    logger.info("Issued referral_code partner_id=%d code=%s", partner_user.id, code)
    return code


def build_share_url(referral_code: str) -> str:
    """紹介コードから招待 URL を組み立てる。"""
    return f"{_share_base_url()}/register?ref={referral_code}"


def list_referred_users(db: Session, partner_id: int) -> list[User]:
    """``referrer_id == partner_id`` のユーザー一覧 (新しい順)。"""
    return (
        db.query(User).filter(User.referrer_id == partner_id).order_by(User.created_at.desc()).all()
    )


def list_transactions(db: Session, partner_id: int, referred_user_id: int) -> list[Transaction]:
    """配下ユーザーの取引履歴を返す (RBAC 込み)。

    Args:
        db: DB セッション。
        partner_id: 呼び出し元 partner の id。
        referred_user_id: 取引を取得したい配下ユーザーの id。

    Returns:
        operation が deposit/withdraw/borrow/repay の Transaction 一覧 (新しい順)。

    Raises:
        HTTPException: 対象ユーザーが存在しない、または partner 配下でない場合 (403/404)。
    """
    referred = db.query(User).filter(User.id == referred_user_id).first()
    if referred is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referred user not found",
        )
    if referred.referrer_id != partner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your referred user",
        )

    return (
        db.query(Transaction)
        .filter(
            Transaction.user_id == referred_user_id,
            Transaction.operation.in_(_ALLOWED_TX_TYPES),
        )
        .order_by(Transaction.created_at.desc())
        .all()
    )


def mask_email(email: str) -> str:
    """``y***@example.com`` 形式へマスクする。"""
    if "@" not in email:
        return email[:1] + "***"
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def handle_new_referral(db: Session, partner_id: int, referree_id: int) -> ReferralCampaign:
    """新規紹介登録時に紹介キャンペーン ウィンドウを更新する。

    1. 同一パートナーの既存アクティブ ウィンドウを今月で終了。
    2. 新しい 12ヶ月ウィンドウを作成 (来月スタート)。

    Args:
        db: DB セッション (呼び出し元が commit を担当)。
        partner_id: 紹介したパートナーの user id。
        referree_id: 新規登録したユーザーの user id。

    Returns:
        作成した ReferralCampaign レコード。
    """
    today = date.today()
    current_month = date(today.year, today.month, 1)

    # 既存のアクティブ ウィンドウを今月で閉じる
    existing_active = db.scalars(
        select(ReferralCampaign).where(
            ReferralCampaign.partner_id == partner_id,
            ReferralCampaign.ended_early_month.is_(None),
            ReferralCampaign.reward_expires_month >= current_month,
        )
    ).all()
    for old_campaign in existing_active:
        old_campaign.ended_early_month = current_month
        logger.info(
            "Closed referral campaign id=%d partner=%d (new referral in month=%s)",
            old_campaign.id,
            partner_id,
            current_month,
        )

    # 新ウィンドウ: 来月スタート、12ヶ月間
    reward_start_month = _add_months(current_month, 1)
    reward_expires_month = _add_months(reward_start_month, 11)

    campaign = ReferralCampaign(
        partner_id=partner_id,
        referree_id=referree_id,
        reward_start_month=reward_start_month,
        reward_expires_month=reward_expires_month,
    )
    db.add(campaign)
    logger.info(
        "Created referral campaign partner=%d referree=%d start=%s expires=%s",
        partner_id,
        referree_id,
        reward_start_month,
        reward_expires_month,
    )
    return campaign


def _add_months(d: date, months: int) -> date:
    """月初 date に n ヶ月を加算して月初 date を返す (日は常に 1 日)。"""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, 1)


def get_referral_earnings(db: Session, partner_id: int) -> dict:
    """紹介キャンペーン収益サマリーを返す。

    - referral_count: referrer_id == partner_id のユーザー数
    - current_month_reward_jpy: 今月の affiliate_amount_jpy 合計
    - total_payout_jpy: finalized 済みの affiliate_amount_jpy 累計
    - campaign_rate: active FeeConfigV10 の affiliate_rate (デフォルト 0.10)
    - campaign_expires_month: アクティブ ウィンドウの reward_expires_month (None = ウィンドウなし)
    """
    referral_count: int = (
        db.query(func.count(User.id)).filter(User.referrer_id == partner_id).scalar() or 0
    )

    today = date.today()
    current_month = date(today.year, today.month, 1)

    current_month_raw = (
        db.query(func.sum(FeeTransaction.affiliate_amount_jpy))
        .filter(
            FeeTransaction.affiliate_id == partner_id,
            FeeTransaction.calculation_month == current_month,
        )
        .scalar()
    )
    current_month_reward = current_month_raw if current_month_raw is not None else Decimal("0")

    total_payout_raw = (
        db.query(func.sum(FeeTransaction.affiliate_amount_jpy))
        .filter(
            FeeTransaction.affiliate_id == partner_id,
            FeeTransaction.finalized_at.isnot(None),
        )
        .scalar()
    )
    total_payout = total_payout_raw if total_payout_raw is not None else Decimal("0")

    active_config = (
        db.query(FeeConfigV10)
        .filter(FeeConfigV10.is_active.is_(True))
        .order_by(FeeConfigV10.effective_from.desc())
        .first()
    )
    campaign_rate = active_config.affiliate_rate if active_config else Decimal("0.10")

    # アクティブ ウィンドウを探して期限月を返す
    active_campaign = db.scalar(
        select(ReferralCampaign).where(
            ReferralCampaign.partner_id == partner_id,
            ReferralCampaign.ended_early_month.is_(None),
            ReferralCampaign.reward_expires_month >= current_month,
            ReferralCampaign.reward_start_month <= current_month,
        )
    )
    campaign_expires_month: str | None = (
        str(active_campaign.reward_expires_month) if active_campaign else None
    )

    return {
        "referral_count": referral_count,
        "current_month_reward_jpy": str(current_month_reward),
        "total_payout_jpy": str(total_payout),
        "campaign_rate": str(campaign_rate),
        "campaign_expires_month": campaign_expires_month,
    }
