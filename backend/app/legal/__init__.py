# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/legal/__init__.py
"""Legal / ToS / consent log データモデル。

P0-14 (ToS active consent UI + 同意ログ永続化) の backend 永続化層。
UI は W3-23 の別 PR、本 module は schema と pure dataclass のみ。
"""

from app.legal.models import TosConsent

__all__ = ["TosConsent"]
