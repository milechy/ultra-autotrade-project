# backend/app/auth/__init__.py
"""認証モジュール。"""

from .dependencies import get_current_user, require_active_user, require_admin
from .models import User
from .router import router
from .schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    UserRole,
)
from .service import AuthService

__all__ = [
    "User",
    "LoginRequest",
    "RegisterRequest",
    "TokenResponse",
    "UserResponse",
    "UserRole",
    "AuthService",
    "get_current_user",
    "require_admin",
    "require_active_user",
    "router",
]
