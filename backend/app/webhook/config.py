from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_webhook_secret() -> Optional[str]:
    """環境変数 WEBHOOK_SECRET を取得する。未設定時は None を返す。"""
    secret = os.environ.get("WEBHOOK_SECRET")
    if not secret:
        logger.warning("WEBHOOK_SECRET が未設定です。認証をスキップします。")
    return secret
