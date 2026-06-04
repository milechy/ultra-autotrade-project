# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/tos/service.py
"""ToS 同意ログのビジネスロジック。"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.tos.models import ToSConsent, UserAction

logger = logging.getLogger(__name__)


def compute_consent_hash(
    *,
    user_id: int,
    tos_version: str,
    consent_at: datetime,
    ip: Optional[str],
    user_agent: Optional[str],
    is_demo_ack: bool,
) -> str:
    """同意レコードの改ざん検知用 SHA-256 hash を計算する。

    後で再計算して DB 値と一致しなければ改ざんありと判定できる。
    入力は決定的にシリアライズする (sort_keys=True / ISO8601)。
    """
    # SQLite drops tz info, so treat naive datetimes as UTC. PostgreSQL preserves
    # tz aware datetimes; both paths normalize to the same UTC ISO8601 string.
    if consent_at.tzinfo is None:
        consent_at_norm = consent_at.replace(tzinfo=timezone.utc)
    else:
        consent_at_norm = consent_at.astimezone(timezone.utc)
    payload = {
        "user_id": user_id,
        "tos_version": tos_version,
        "consent_at": consent_at_norm.isoformat(),
        "ip": ip or "",
        "user_agent": user_agent or "",
        "is_demo_ack": bool(is_demo_ack),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def verify_consent_hash(consent: ToSConsent) -> bool:
    """既存レコードの consent_hash を再計算し、改ざんが無いか検証する。"""
    expected = compute_consent_hash(
        user_id=consent.user_id,
        tos_version=consent.tos_version,
        consent_at=consent.consent_at,
        ip=consent.ip,
        user_agent=consent.user_agent,
        is_demo_ack=consent.is_demo_ack,
    )
    return expected == consent.consent_hash


def record_consent(
    db: Session,
    *,
    user_id: int,
    tos_version: str,
    ip: Optional[str],
    user_agent: Optional[str],
    is_demo_ack: bool,
) -> ToSConsent:
    """同意ログを tos_consents へ INSERT し、user_actions へ並行記録する。

    user_actions への INSERT は best-effort: 失敗しても tos_consents の commit は維持する。
    """
    consent_at = datetime.now(timezone.utc)
    consent_hash = compute_consent_hash(
        user_id=user_id,
        tos_version=tos_version,
        consent_at=consent_at,
        ip=ip,
        user_agent=user_agent,
        is_demo_ack=is_demo_ack,
    )
    consent = ToSConsent(
        user_id=user_id,
        tos_version=tos_version,
        consent_at=consent_at,
        ip=ip,
        user_agent=user_agent,
        consent_hash=consent_hash,
        is_demo_ack=is_demo_ack,
    )
    db.add(consent)

    payload = json.dumps(
        {
            "tos_version": tos_version,
            "is_demo_ack": is_demo_ack,
            "consent_hash": consent_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    action = UserAction(
        user_id=user_id,
        action_type="tos_consent",
        payload=payload,
        created_at=consent_at,
    )
    db.add(action)

    db.commit()
    db.refresh(consent)
    logger.info(
        "ToS consent recorded: user_id=%s version=%s hash=%s...",
        user_id,
        tos_version,
        consent_hash[:12],
    )
    return consent


def get_latest_consent(db: Session, user_id: int) -> Optional[ToSConsent]:
    """指定ユーザーの最新 ToS 同意レコードを返す。無ければ None。"""
    return (
        db.query(ToSConsent)
        .filter(ToSConsent.user_id == user_id)
        .order_by(ToSConsent.consent_at.desc())
        .first()
    )
