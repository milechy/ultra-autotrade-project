# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/auth/schemas.py
"""
認証関連の Pydantic スキーマ。
"""

import re
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


# InvestmentTier は app.auth.models で定義 (v10 3 層: LOWER / MIDDLE / UPPER)。
# F-2 までは本ファイルでも重複定義していたが、単一情報源 (auth/models.py) に統合した。
from app.auth.models import InvestmentTier as InvestmentTier  # noqa: E402, F401
from app.auth.models import normalize_tier  # noqa: E402


class RegisterRequest(BaseModel):
    """初回管理者登録または招待コード登録リクエスト。"""

    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)
    invitation_code: Optional[str] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ユーザー名は空白のみにできません")
        if not (v[0].isalpha() or v[0].isdigit()):
            raise ValueError(
                "ユーザー名は文字か数字で始まる必要があります (must start with a letter or number)"
            )
        if not re.match(r"^[\w\s\-]+$", v):
            raise ValueError("ユーザー名には文字・数字・スペース・_・- のみ使用できます")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class RegisterWithReferralRequest(BaseModel):
    """紹介コード経由ユーザー登録リクエスト (RAS Lane 2.1)。"""

    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)
    referral_code: str
    referred_consent: bool

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ユーザー名は空白のみにできません")
        if not (v[0].isalpha() or v[0].isdigit()):
            raise ValueError(
                "ユーザー名は文字か数字で始まる必要があります (must start with a letter or number)"
            )
        if not re.match(r"^[\w\s\-]+$", v):
            raise ValueError("ユーザー名には文字・数字・スペース・_・- のみ使用できます")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("referral_code")
    @classmethod
    def validate_referral_code_format(cls, v: str) -> str:
        if len(v) != 8 or not v.isalnum():
            raise ValueError("invalid referral code format")
        return v.upper()


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
    execution_policy: str = "require_approval"
    wallet_address: Optional[str] = None
    smart_wallet_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tier", mode="before")
    @classmethod
    def normalize_tier_value(cls, v: object) -> InvestmentTier:
        """DB に残存する 'standard' 等の不明値を normalize_tier で LOWER に正規化する。"""
        raw = str(v) if v is not None else None
        return normalize_tier(raw)

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
        if not v.strip():
            raise ValueError("ユーザー名は空白のみにできません")
        if not (v[0].isalpha() or v[0].isdigit()):
            raise ValueError(
                "ユーザー名は文字か数字で始まる必要があります (must start with a letter or number)"
            )
        if not re.match(r"^[\w\s\-]+$", v):
            raise ValueError("ユーザー名には文字・数字・スペース・_・- のみ使用できます")
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
        if not v.strip():
            raise ValueError("ユーザー名は空白のみにできません")
        if not (v[0].isalpha() or v[0].isdigit()):
            raise ValueError(
                "ユーザー名は文字か数字で始まる必要があります (must start with a letter or number)"
            )
        if not re.match(r"^[\w\s\-]+$", v):
            raise ValueError("ユーザー名には文字・数字・スペース・_・- のみ使用できます")
        return v.lower()


class OpenRegisterRequest(BaseModel):
    """一般登録（open）リクエスト。partner 招待不要で自己申請。

    terms_consent == True が必須。KYC ゲートは別 Lane で実装予定。
    """

    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)
    terms_consent: bool = Field(..., description="利用規約への同意（必須）")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ユーザー名は空白のみにできません")
        if not (v[0].isalpha() or v[0].isdigit()):
            raise ValueError(
                "ユーザー名は文字か数字で始まる必要があります (must start with a letter or number)"
            )
        if not re.match(r"^[\w\s\-]+$", v):
            raise ValueError("ユーザー名には文字・数字・スペース・_・- のみ使用できます")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("terms_consent")
    @classmethod
    def consent_must_be_true(cls, v: bool) -> bool:
        if not v:
            raise ValueError("利用規約への同意が必要です (terms_consent must be True)")
        return v


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
    privy_did: Optional[str] = Field(None, max_length=255, description="Privy DID (did:privy:...)")
    # Privy ID Token (JWT) — 提供された場合はサーバー側で署名検証し、
    # sub claim と privy_did の一致を強制する (Codex Review P1 対応)。
    privy_id_token: Optional[str] = Field(
        None,
        max_length=4096,
        description="Privy ID token (JWT). 提供時はサーバーで検証し sub == privy_did を確認する。",
    )


class WalletConnectResponse(BaseModel):
    """WalletConnect認証レスポンス。"""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    is_new_user: bool
    needs_terms_acceptance: bool

    model_config = ConfigDict(from_attributes=True)


class WalletLinkRequest(BaseModel):
    """認証済みユーザーへのウォレット紐付けリクエスト (POST /auth/wallet/link)。"""

    address: str = Field(
        ..., min_length=42, max_length=42, description="EVM wallet address (0x...)"
    )
    signature: str = Field(..., description="ECDSA signature (0x...)")
    message: str = Field(..., description="Signed message (must contain timestamp)")


class WalletLinkResponse(BaseModel):
    """ウォレット紐付けレスポンス。"""

    user_id: int
    wallet_address: str
    linked_at: str  # ISO8601 文字列

    model_config = ConfigDict(from_attributes=True)


class SmartWalletLinkRequest(BaseModel):
    """認証済みユーザーへの Smart Wallet (ERC-4337 SCW) アドレス登録 (POST /auth/wallet/smart-link)。

    SCW はコントラクトのため EOA 署名による所有証明ができない。非カストディアル設計
    (submit-tx の UserOp sender==登録SCW 検証 / unique 制約 / VIEWER は自己提案のみ) により、
    JWT 認証済みユーザーが自分の SCW を登録する方式で安全 (slice4b 案a)。
    """

    smart_wallet_address: str = Field(
        ..., min_length=42, max_length=42, description="Smart Wallet contract address (0x...)"
    )


class SmartWalletLinkResponse(BaseModel):
    """Smart Wallet 登録レスポンス。"""

    user_id: int
    smart_wallet_address: str

    model_config = ConfigDict(from_attributes=True)
