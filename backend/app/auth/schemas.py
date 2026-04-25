# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/auth/schemas.py
"""
認証関連の Pydantic スキーマ。
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator


class UserRole(str, Enum):
    """ユーザーロール。"""

    ADMIN = "admin"
    PARTNER = "partner"
    EDITOR = "editor"
    VIEWER = "viewer"


# InvestmentTier は app.auth.models で定義 (v10 3 層 + GENERAL 過渡期互換)。
# F-2 までは本ファイルでも重複定義していたが、単一情報源 (auth/models.py) に統合した。
from app.auth.models import InvestmentTier as InvestmentTier  # noqa: E402, F401


class RegisterRequest(BaseModel):
    """初回管理者登録リクエスト（招待コードがある場合は招待登録）。"""

    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)
    invitation_code: Optional[str] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        # アンダースコアとハイフンを除去した後、英数字のみかチェック
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username must be alphanumeric (with _ or - allowed)")
        # 先頭は英数字のみ許可（_や-で始まることを禁止）
        if not v[0].isalnum():
            raise ValueError("Username must start with a letter or number")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    """ログインリクエスト。"""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """トークンレスポンス。"""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int  # 秒数


class UserResponse(BaseModel):
    """ユーザー情報レスポンス。"""

    id: int
    email: str
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    terms_accepted_at: Optional[datetime] = None
    terms_version: Optional[str] = None
    risk_mode: Optional[str] = "conservative"
    invited_by: Optional[int] = None
    tier: InvestmentTier = InvestmentTier.LOWER

    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def risk_mode_label(self) -> str:
        """日本語表示ラベル (フロントエンドが直接利用可能)。

        F-3 (2026-04-25): 内部値 (conservative/balanced/aggressive) は維持しつつ、
        表示用の日本語ラベルを computed field として追加。NULL / 不明値は
        "ローリスク" にフォールバック。
        """
        from app.auth.models import get_risk_mode_label  # noqa: PLC0415

        return get_risk_mode_label(self.risk_mode)


class RegisterResponse(UserResponse):
    """登録レスポンス（トークン含む、自動ログイン用）。"""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class TermsAcceptRequest(BaseModel):
    """利用規約同意リクエスト。"""

    version: str = Field(
        ..., description="Terms version being accepted (e.g. '2.0')", max_length=20
    )


class TermsStatusResponse(BaseModel):
    """利用規約同意状態レスポンス。"""

    accepted: bool
    terms_version: Optional[str] = None
    terms_accepted_at: Optional[datetime] = None
    current_version: str = "2.0"
    needs_acceptance: bool = True


class UserCreateRequest(BaseModel):
    """ユーザー作成リクエスト（管理者用）。"""

    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)
    role: UserRole = UserRole.VIEWER

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        # アンダースコアとハイフンを除去した後、英数字のみかチェック
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username must be alphanumeric (with _ or - allowed)")
        # 先頭は英数字のみ許可（_や-で始まることを禁止）
        if not v[0].isalnum():
            raise ValueError("Username must start with a letter or number")
        return v.lower()


class UserUpdateRequest(BaseModel):
    """ユーザー更新リクエスト。"""

    email: Optional[EmailStr] = None
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)
    password: Optional[str] = Field(default=None, min_length=8, max_length=100)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        # アンダースコアとハイフンを除去した後、英数字のみかチェック
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username must be alphanumeric (with _ or - allowed)")
        # 先頭は英数字のみ許可（_や-で始まることを禁止）
        if not v[0].isalnum():
            raise ValueError("Username must start with a letter or number")
        return v.lower()


class PasswordChangeRequest(BaseModel):
    """パスワード変更リクエスト。"""

    current_password: str
    new_password: str = Field(min_length=8, max_length=100)


class RiskModeUpdateRequest(BaseModel):
    """リスクモード変更リクエスト。"""

    mode: str = Field(
        ...,
        description="conservative / balanced / aggressive",
        pattern="^(conservative|balanced|aggressive)$",
    )


class WalletConnectRequest(BaseModel):
    """WalletConnect認証リクエスト。"""

    wallet_address: str = Field(
        ..., min_length=42, max_length=42, description="EVM wallet address (0x...)"
    )
    message: str = Field(..., description="Signed message (must contain timestamp)")
    signature: str = Field(..., description="ECDSA signature (0x...)")


class WalletConnectResponse(BaseModel):
    """WalletConnect認証レスポンス。"""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    is_new_user: bool
    needs_terms_acceptance: bool

    model_config = ConfigDict(from_attributes=True)
