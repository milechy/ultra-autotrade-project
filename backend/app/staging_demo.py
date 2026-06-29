# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/staging_demo.py

"""staging / 審査用デモデータのシード（本番では絶対に無効）。

LINE ミニアプリ審査担当者は毎回「自分の LINE アカウント」でログインするため、
初期状態が「残高 $0・提案なし・データなし」になり、サービス内容をハンズオンで
確認できない（crypto 系は実機確認されるため却下リスク）。

本モジュールは **staging 限定**で、新規ユーザー作成時にサンプルの AI 判定と
保留中提案を 1 件投入し、審査担当者がホームで「AI が運用提案を出す」挙動を
即座に確認できるようにする。実行（on-chain tx）はサンプルのため発生しない。

二重ガード（`ai.service._staging_demo_force_directional_enabled` と同方式で
本番混入を防ぐ）:
  1. APP_ENV=production なら常に無効（フラグ値に関わらず）
  2. それ以外で STAGING_REVIEW_DEMO_SEED=true のときのみ有効（既定 false）

失敗してもユーザー作成は壊さない（best-effort / 例外は握って rollback）。
金融計算は Decimal のみ（CLAUDE.md [CRITICAL] 11）。
"""

import logging
import os

logger = logging.getLogger(__name__)


def review_demo_seed_enabled() -> bool:
    """審査用デモシードの有効判定（本番では常に False）。"""
    if os.getenv("APP_ENV", "").strip().lower() == "production":
        return False
    return os.getenv("STAGING_REVIEW_DEMO_SEED", "false").strip().lower() == "true"


def maybe_seed_review_demo(db, user) -> None:  # type: ignore[no-untyped-def]
    """新規ユーザーに審査用デモの AI 判定 + 保留中提案を 1 件投入する。

    - staging 限定（`review_demo_seed_enabled()` が False の本番では no-op）。
    - 冪等: すでに提案を持つユーザーは skip。
    - best-effort: 失敗してもユーザー作成フローを壊さない。

    Args:
        db: SQLAlchemy セッション。
        user: 作成直後の User（id 確定済み）。
    """
    if not review_demo_seed_enabled():
        return

    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415

    from app.ai.models import AIDecision  # noqa: PLC0415
    from app.proposals.models import Proposal  # noqa: PLC0415

    try:
        existing = db.query(Proposal).filter(Proposal.user_id == user.id).first()
        if existing is not None:
            return

        now = datetime.now(timezone.utc)
        decision = AIDecision(
            user_id=user.id,
            query="[審査デモ] USDC 相場分析",
            action="BUY",
            confidence=86,
            reason=(
                "（審査用サンプル）RSI と移動平均が上昇トレンドを示し、複数モデルが "
                "BUY で一致したため買い判定。これは LINE 審査用に表示しているサンプルです。"
            ),
            primary_provider="claude",
            primary_action="BUY",
            primary_confidence=86,
            secondary_provider="gpt-4o",
            secondary_action="BUY",
            secondary_confidence=82,
            agreed=True,
            prompt_version="demo",
        )
        db.add(decision)
        db.flush()  # decision.id を確定

        proposal = Proposal(
            user_id=user.id,
            ai_decision_id=decision.id,
            operation="SUPPLY",
            asset="USDC",
            protocol="aave",
            amount=Decimal("1000"),
            amount_usd=Decimal("1000.00"),
            reason=(
                "（審査用サンプル）AI が USDC を Aave に供給する提案です。承認すると "
                "ご自身のウォレットで実行されます（審査用サンプルのため実行はされません）。"
            ),
            status="pending",
            expires_at=now + timedelta(hours=72),
        )
        db.add(proposal)
        db.commit()
        logger.info(
            "[review-demo] seeded sample AI decision + pending proposal for user_id=%d",
            user.id,
        )
    except Exception as exc:  # noqa: BLE001 — デモ失敗でユーザー作成を壊さない
        db.rollback()
        logger.warning("[review-demo] seed failed for user_id=%d: %s", user.id, exc)
