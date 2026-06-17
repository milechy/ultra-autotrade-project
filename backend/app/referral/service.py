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

# get_api_referral_info で返す referred_users の status 値 ("active" | "registered")
_STATUS_ACTIVE = "active"
_STATUS_REGISTERED = "registered"


def _share_base_url() -> str:
    """招待 URL の base host を環境変数から取得する。"""
    return os.getenv("PUBLIC_FRONTEND_URL", "https://app.ultra-auto-trade.com").rstrip("/")


def get_or_create_code(db: Session, user: User) -> str:
    """ユーザーの紹介コードを取得 (未発行なら自動発行)。

    partner / viewer を問わず全 active user に対して利用できる。

    Args:
        db: DB セッション。
        user: 紹介コードを発行するユーザー。

    Returns:
        ユーザーに紐づく 8 桁紹介コード。
    """
    if user.referral_code:
        return user.referral_code

    code = generate_referral_code(db)
    user.referral_code = code
    db.commit()
    db.refresh(user)
    logger.info("Issued referral_code user_id=%d code=%s", user.id, code)
    return code


def build_share_url(referral_code: str) -> str:
    """紹介コードから招待 URL を組み立てる。"""
    return f"{_share_base_url()}/auth/register?ref={referral_code}"


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

    1. 同一パートナーの既存アクティブ ウィンドウを今月で終了 (シングルスロット・ローリング)。
    2. 新しいウィンドウを作成 (来月スタート、末 = 最後に紹介した月 + 13ヶ月)。

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

    # 新ウィンドウ: 来月スタート、末 = 最後に紹介した月(current_month) + 13ヶ月。
    # reward_start_month = current_month + 1、expires = start + 12 (= current_month + 13)。
    reward_start_month = _add_months(current_month, 1)
    reward_expires_month = _add_months(reward_start_month, 12)

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


def get_referral_earnings(db: Session, partner_id: int) -> dict[str, str | int | None]:
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

    # finalized_at はオンチェーン送金時のみ。バッチ処理済み全件を集計する
    total_payout_raw = (
        db.query(func.sum(FeeTransaction.affiliate_amount_jpy))
        .filter(
            FeeTransaction.affiliate_id == partner_id,
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
    # affiliate_rate の正本 = 製品仕様 (Asana 1215467015333283 / 2026-06-06 確定):
    # 紹介友達の月次 user_takehome_jpy の 10%。calculator Step6 が takehome×rate で算定する。
    # active fee_config が無い場合の fallback は 0.10 (FeeConfigV10.affiliate_rate server_default と一致)。
    campaign_rate = active_config.affiliate_rate if active_config else Decimal("0.10")

    # アクティブ ウィンドウ (報酬発生中) を優先で探す
    active_campaign = db.scalar(
        select(ReferralCampaign).where(
            ReferralCampaign.partner_id == partner_id,
            ReferralCampaign.ended_early_month.is_(None),
            ReferralCampaign.reward_expires_month >= current_month,
            ReferralCampaign.reward_start_month <= current_month,
        )
    )
    # PL10: 紹介登録直後の月は reward_start_month が翌月 (current_month 未満を満たさない) ため
    # アクティブ判定に乗らない。この「開始待ち (pending)」ウィンドウも拾って expires を埋め、
    # UI で「キャンペーンなし」と誤表示されないようにする (campaign_status で active と区別)。
    pending_campaign = (
        None
        if active_campaign
        else db.scalar(
            select(ReferralCampaign).where(
                ReferralCampaign.partner_id == partner_id,
                ReferralCampaign.ended_early_month.is_(None),
                ReferralCampaign.reward_expires_month >= current_month,
                ReferralCampaign.reward_start_month > current_month,
            )
        )
    )
    campaign = active_campaign or pending_campaign
    campaign_expires_month: str | None = str(campaign.reward_expires_month) if campaign else None
    campaign_status: str | None = (
        "active" if active_campaign else "pending" if pending_campaign else None
    )

    return {
        "referral_count": referral_count,
        "current_month_reward_jpy": str(current_month_reward),
        "total_payout_jpy": str(total_payout),
        "campaign_rate": str(campaign_rate),
        "campaign_expires_month": campaign_expires_month,
        "campaign_status": campaign_status,
    }


def get_api_referral_info(db: Session, user: User) -> dict[str, object]:
    """LIFF 紹介パネル用: /api/referral/earnings のデータを組み立てる。

    partner 専用の ``get_referral_earnings`` と異なり、全 active user が対象。
    紹介報酬は「紹介友達の実受取利益 × affiliate_rate(10%)」で、当月分は
    ``current_month_reward_jpy`` / 累計は ``total_payout_jpy`` に集約する。
    友達ごとの内訳 ``reward_jpy`` は未集計のため "0" を返す (集計は別タスク)。

    Args:
        db: DB セッション。
        user: リクエスト元の active user。

    Returns:
        ``ReferralInfoResponse`` に渡せる dict。
    """
    today = date.today()
    current_month = date(today.year, today.month, 1)

    referred = list_referred_users(db, user.id)
    referral_count = len(referred)

    ref_ids = [u.id for u in referred]
    confirmed_user_ids: set[int] = (
        {
            row.user_id
            for row in db.query(Transaction.user_id)
            .filter(Transaction.user_id.in_(ref_ids), Transaction.status == "confirmed")
            .distinct()
            .all()
        }
        if ref_ids
        else set()
    )

    referred_user_details = [
        {
            "name": ref_user.username,
            "joined_at": ref_user.created_at,
            "status": _STATUS_ACTIVE if ref_user.id in confirmed_user_ids else _STATUS_REGISTERED,
            "reward_jpy": "0",
        }
        for ref_user in referred
    ]

    current_month_raw = (
        db.query(func.sum(FeeTransaction.affiliate_amount_jpy))
        .filter(
            FeeTransaction.affiliate_id == user.id,
            FeeTransaction.calculation_month == current_month,
        )
        .scalar()
    )
    current_month_reward = current_month_raw if current_month_raw is not None else Decimal("0")

    # finalized_at はオンチェーン送金時のみ。バッチ処理済み全件を集計する
    total_payout_raw = (
        db.query(func.sum(FeeTransaction.affiliate_amount_jpy))
        .filter(
            FeeTransaction.affiliate_id == user.id,
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

    return {
        "referral_count": referral_count,
        "current_month_reward_jpy": str(current_month_reward),
        "total_payout_jpy": str(total_payout),
        "campaign_rate": str(campaign_rate),
        "referral_code": user.referral_code or "",
        "referred_users": referred_user_details,
    }
