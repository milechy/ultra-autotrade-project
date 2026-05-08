# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/referral/code_generator.py
"""紹介コード生成器。

8 桁英数字 (大文字 + 数字、混同しやすい I/O/0/1 は除外) で生成し、
DB ユニーク衝突時は最大 5 回リトライする。
"""

from __future__ import annotations

import logging
import secrets

from sqlalchemy.orm import Session

from app.auth.models import User

logger = logging.getLogger(__name__)

# 混同しやすい I/O/0/1 を除外したアルファベット (28 文字)。
_REFERRAL_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REFERRAL_CODE_LENGTH = 8
MAX_RETRY = 5


def _random_code() -> str:
    """暗号学的乱数で 8 桁の紹介コード候補を返す。"""
    return "".join(secrets.choice(_REFERRAL_ALPHABET) for _ in range(REFERRAL_CODE_LENGTH))


def generate_referral_code(db: Session) -> str:
    """DB ユニーク衝突を考慮しながら 8 桁紹介コードを生成する。

    Args:
        db: 衝突確認に使う DB セッション。

    Returns:
        DB 上で未使用の 8 桁英数字コード。

    Raises:
        RuntimeError: ``MAX_RETRY`` 回連続で衝突した場合 (運用上ほぼ起こらない)。
    """
    for attempt in range(1, MAX_RETRY + 1):
        candidate = _random_code()
        existing = db.query(User).filter(User.referral_code == candidate).first()
        if existing is None:
            if attempt > 1:
                logger.info("referral_code generated after %d retries", attempt)
            return candidate
        logger.warning("referral_code collision on attempt=%d (candidate=%s)", attempt, candidate)

    logger.error("referral_code generation exhausted retries (max=%d)", MAX_RETRY)
    raise RuntimeError("Failed to generate unique referral_code after retries")
