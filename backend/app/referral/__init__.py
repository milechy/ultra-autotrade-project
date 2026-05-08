# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/referral/__init__.py
"""RAS (Referral / Partner Affiliate System) Lane 2 module.

partner ロール用の紹介コード API と、register エンドポイントから参照される
紹介コード処理を提供する。
"""

from .router import router as router

__all__ = ["router"]
