# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/auth/service.py
"""
認証サービス。

パスワードハッシュ化、JWT トークン生成・検証を担当。
docs/13_security_design.md に準拠。
"""

import logging
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt as pyjwt
from eth_account.messages import encode_defunct
from fastapi import HTTPException, status
from jwt import InvalidTokenError as JWTError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from web3 import Web3

from .models import User, UserRole
from .schemas import (
    OpenRegisterRequest,
    RegisterRequest,
    RegisterWithReferralRequest,
    UserCreateRequest,
)

logger = logging.getLogger(__name__)


class AuthService:
    """認証サービス。"""

    # JWT 設定
    SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-secret-key-change-in-production")
    ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
    )  # 24時間

    # bcrypt 設定
    BCRYPT_ROUNDS = 12

    # 本番環境で使用禁止の弱いシークレットキー
    _WEAK_SECRET_KEYS = {
        "development-secret-key-change-in-production",
        "secret",
        "changeme",
        "password",
        "test",
        "",
    }

    @classmethod
    def validate_secret_key(cls) -> None:
        """
        JWT シークレットキーの強度を検証する。

        本番環境（APP_ENV が production または staging）では、
        弱いシークレットキーの使用を禁止する。

        Raises:
            RuntimeError: 弱いシークレットキーが本番環境で使用されている場合
        """
        app_env = os.getenv("APP_ENV", "dev").lower()

        # 本番環境チェック
        if app_env in ("production", "staging"):
            if cls.SECRET_KEY in cls._WEAK_SECRET_KEYS:
                raise RuntimeError(
                    "JWT_SECRET_KEY is not set or using a weak default. "
                    "Please set a strong secret key for production/staging environment."
                )
            if len(cls.SECRET_KEY) < 32:
                raise RuntimeError(
                    "JWT_SECRET_KEY is too short. "
                    "Please use a secret key with at least 32 characters."
                )

    @classmethod
    def hash_password(cls, password: str) -> str:
        """
        パスワードを bcrypt でハッシュ化する。

        Args:
            password: 平文パスワード

        Returns:
            ハッシュ化されたパスワード
        """
        salt = bcrypt.gensalt(rounds=cls.BCRYPT_ROUNDS)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        """
        パスワードを検証する。

        Args:
            plain_password: 平文パスワード
            hashed_password: ハッシュ化されたパスワード

        Returns:
            パスワードが一致すれば True
        """
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )

    @classmethod
    def create_access_token(
        cls,
        user_id: int,
        email: str,
        role: str,
        expires_delta: Optional[timedelta] = None,
    ) -> tuple[str, int]:
        """
        JWT アクセストークンを生成する。

        Args:
            user_id: ユーザー ID
            email: メールアドレス
            role: ユーザーロール
            expires_delta: 有効期限（省略時はデフォルト）

        Returns:
            (トークン, 有効期限秒数) のタプル
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=cls.ACCESS_TOKEN_EXPIRE_MINUTES)

        expire = datetime.now(timezone.utc) + expires_delta
        to_encode = {
            "sub": str(user_id),
            "email": email,
            "role": role,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }

        token = pyjwt.encode(to_encode, cls.SECRET_KEY, algorithm=cls.ALGORITHM)
        expires_in = int(expires_delta.total_seconds())

        return token, expires_in

    @classmethod
    def decode_token(cls, token: str) -> Optional[dict[str, Any]]:
        """
        JWT トークンをデコードする。

        Args:
            token: JWT トークン

        Returns:
            ペイロード辞書、または無効な場合は None
        """
        try:
            payload: dict[str, Any] = pyjwt.decode(
                token, cls.SECRET_KEY, algorithms=[cls.ALGORITHM]
            )
            return payload
        except JWTError as e:
            logger.warning("JWT decode error: %s", e)
            return None

    @classmethod
    def get_user_by_email(cls, db: Session, email: str) -> Optional[User]:
        """メールアドレスでユーザーを取得する。"""
        return db.query(User).filter(User.email == email).first()

    @classmethod
    def get_user_by_id(cls, db: Session, user_id: int) -> Optional[User]:
        """ID でユーザーを取得する。"""
        return db.query(User).filter(User.id == user_id).first()

    @classmethod
    def get_user_by_username(cls, db: Session, username: str) -> Optional[User]:
        """ユーザー名でユーザーを取得する。"""
        return db.query(User).filter(User.username == username).first()

    @classmethod
    def user_exists(cls, db: Session) -> bool:
        """ユーザーが1人以上存在するか確認する。"""
        return db.query(User).first() is not None

    @classmethod
    def authenticate_user(
        cls,
        db: Session,
        email: str,
        password: str,
    ) -> Optional[User]:
        """
        ユーザーを認証する。

        Args:
            db: データベースセッション
            email: メールアドレス
            password: 平文パスワード

        Returns:
            認証成功時は User、失敗時は None
        """
        user = cls.get_user_by_email(db, email)
        if user is None:
            return None
        if not user.is_active:
            return None
        if not cls.verify_password(password, user.hashed_password):
            return None
        return user

    @classmethod
    def create_user(
        cls,
        db: Session,
        request: RegisterRequest
        | RegisterWithReferralRequest
        | UserCreateRequest
        | OpenRegisterRequest,
        role: str = UserRole.VIEWER.value,
    ) -> User:
        """
        ユーザーを作成する。

        Args:
            db: データベースセッション
            request: 登録リクエスト
            role: ユーザーロール

        Returns:
            作成されたユーザー

        Raises:
            ValueError: メールまたはユーザー名が既に使用されている場合
        """
        # 重複チェック
        if cls.get_user_by_email(db, request.email):
            raise ValueError(f"Email already registered: {request.email}")
        if cls.get_user_by_username(db, request.username):
            raise ValueError(f"Username already taken: {request.username}")

        # UserCreateRequest の場合はロールを取得
        if isinstance(request, UserCreateRequest):
            role = request.role.value

        user = User(
            email=request.email,
            username=request.username.lower(),
            hashed_password=cls.hash_password(request.password),
            role=role,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        logger.info("Created user: %s (role=%s)", user.email, user.role)
        return user

    @classmethod
    def update_user(
        cls,
        db: Session,
        user: User,
        email: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> User:
        """
        ユーザーを更新する。

        Args:
            db: データベースセッション
            user: 更新対象のユーザー
            email: 新しいメールアドレス（任意）
            username: 新しいユーザー名（任意）
            password: 新しいパスワード（任意）
            role: 新しいロール（任意）
            is_active: 新しいアクティブ状態（任意）

        Returns:
            更新されたユーザー

        Raises:
            ValueError: メールまたはユーザー名が既に使用されている場合
        """
        if email and email != user.email:
            if cls.get_user_by_email(db, email):
                raise ValueError(f"Email already registered: {email}")
            user.email = email

        if username and username != user.username:
            if cls.get_user_by_username(db, username.lower()):
                raise ValueError(f"Username already taken: {username}")
            user.username = username.lower()

        if password:
            user.hashed_password = cls.hash_password(password)

        if role is not None:
            user.role = role

        if is_active is not None:
            user.is_active = is_active

        db.commit()
        db.refresh(user)

        logger.info("Updated user: %s", user.email)
        return user

    @classmethod
    def delete_user(cls, db: Session, user: User) -> None:
        """
        ユーザーを削除する。

        Args:
            db: データベースセッション
            user: 削除対象のユーザー
        """
        logger.info("Deleting user: %s", user.email)
        db.delete(user)
        db.commit()

    @classmethod
    def get_all_users(cls, db: Session) -> list[User]:
        """全ユーザーを取得する。"""
        return db.query(User).order_by(User.created_at.desc()).all()

    @classmethod
    def count_admins(cls, db: Session) -> int:
        """管理者の数を取得する。"""
        return db.query(User).filter(User.role == UserRole.ADMIN.value).count()

    @classmethod
    def get_user_by_wallet(cls, db: Session, wallet_address: str) -> Optional[User]:
        """ウォレットアドレスでユーザーを取得する。"""
        return db.query(User).filter(User.wallet_address == wallet_address.lower()).first()

    @classmethod
    def get_user_by_smart_wallet(cls, db: Session, smart_wallet_address: str) -> Optional[User]:
        """Smart Wallet (ERC-4337 SCW) アドレスでユーザーを取得する (slice4b)。"""
        return (
            db.query(User).filter(User.smart_wallet_address == smart_wallet_address.lower()).first()
        )

    @classmethod
    def verify_wallet_signature(cls, wallet_address: str, message: str, signature: str) -> bool:
        """
        ウォレット署名を検証する。

        - eth_account.messages.encode_defunct でメッセージをエンコード
        - Account.recover_message で署名者アドレスを復元
        - 復元アドレスが wallet_address と一致するか確認
        """
        try:
            w3 = Web3()
            encoded_message = encode_defunct(text=message)
            recovered_address: str = w3.eth.account.recover_message(
                encoded_message, signature=signature
            )
            return recovered_address.lower() == wallet_address.lower()
        except Exception as e:
            logger.warning("Wallet signature verification failed: %s", e)
            return False

    @classmethod
    def create_wallet_user(
        cls, db: Session, wallet_address: str, privy_did: Optional[str] = None
    ) -> tuple[User, bool]:
        """
        ウォレットアドレスからユーザーを自動作成する。

        - role = viewer
        - risk_mode = conservative
        - terms_accepted_at = None
        - email / username は wallet_ プレフィックス + アドレス先頭8文字（衝突時はランダム4桁追加）
        - privy_did: Privy固有のDID（任意、後追い更新も可能）

        Returns:
            (User, is_newly_created) のタプル。
            - is_newly_created=True: この呼び出しでユーザーを新規作成した
            - is_newly_created=False: 並行 first-login race を吸収して既存ユーザーを返した
              (router の is_new_user フラグはこの値を信頼すべき)
        """
        base_slug = wallet_address[2:10].lower()
        base_email = f"wallet_{base_slug}@wallet.local"
        base_username = f"wallet_{base_slug}"

        # 衝突回避
        email = base_email
        username = base_username
        if cls.get_user_by_email(db, email):
            suffix = "".join(secrets.choice(string.digits) for _ in range(4))
            email = f"wallet_{base_slug}{suffix}@wallet.local"
        if cls.get_user_by_username(db, username):
            suffix = "".join(secrets.choice(string.digits) for _ in range(4))
            username = f"wallet_{base_slug}{suffix}"

        # 使用しないランダムパスワードをハッシュ化
        alphabet = string.ascii_letters + string.digits
        random_password = "".join(secrets.choice(alphabet) for _ in range(64))
        hashed = cls.hash_password(random_password)

        user = User(
            email=email,
            username=username,
            hashed_password=hashed,
            role=UserRole.VIEWER.value,
            risk_mode="conservative",
            terms_accepted_at=None,
            wallet_address=wallet_address.lower(),
            privy_did=privy_did,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError as exc:
            # IntegrityError の原因 (privy_did 衝突 / wallet_address 並行作成) を
            # constraint 名で判別する。privy_did 衝突 → 409、wallet_address 衝突は
            # 並行 first-login の可能性が高いので既存ユーザーを取得して返す。
            db.rollback()
            constraint_name = cls._extract_constraint_name(exc)
            logger.warning(
                "Wallet user creation IntegrityError (wallet=%s..., privy_did=%s, "
                "constraint=%s): %s",
                wallet_address[:10],
                (privy_did[:20] + "...") if privy_did else None,
                constraint_name or "<unknown>",
                exc.orig if hasattr(exc, "orig") else exc,
            )

            if constraint_name and "privy_did" in constraint_name:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="DID already in use",
                ) from exc

            if constraint_name and "wallet_address" in constraint_name:
                # 並行 first-login: 別リクエストが先に同じ wallet_address で作成済み。
                # 既存ユーザーを取得して返すことで race を吸収する。
                existing = cls.get_user_by_wallet(db, wallet_address)
                if existing is not None:
                    logger.info(
                        "Resolved concurrent wallet creation race: wallet=%s..., user_id=%s",
                        wallet_address[:10],
                        existing.id,
                    )
                    return existing, False
                # 取得できない場合は不整合 → 500
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Concurrent wallet insert race not resolvable",
                ) from exc

            # 想定外の constraint (email / username 等) は呼び出し元で再 raise。
            logger.exception(
                "Unexpected IntegrityError on wallet user creation (constraint=%s)",
                constraint_name or "<unknown>",
            )
            raise
        db.refresh(user)

        logger.info("Created wallet user: %s (wallet=%s...)", user.email, wallet_address[:10])
        return user, True

    @staticmethod
    def _extract_constraint_name(exc: IntegrityError) -> str:
        """IntegrityError から違反した constraint 名を抽出する。

        PostgreSQL (psycopg2 / psycopg3) は ``exc.orig.diag.constraint_name`` で
        constraint 名を提供する。SQLite 等の他ドライバーは diag を持たないため
        フォールバックとして orig の文字列表現に含まれる constraint 名を文字列
        マッチで判定する (本関数は呼び出し側で部分一致 ``in`` で使うことを前提)。
        """
        orig = getattr(exc, "orig", None)
        if orig is None:
            return ""
        diag = getattr(orig, "diag", None)
        if diag is not None:
            constraint = getattr(diag, "constraint_name", None)
            if isinstance(constraint, str) and constraint:
                return constraint
        return str(orig)

    @classmethod
    def update_privy_did(cls, db: Session, user: User, privy_did: str) -> None:
        """既存ユーザーの privy_did を後追い保存する。

        既に同じ privy_did が設定されている場合はスキップ。
        別ユーザーが同じ privy_did を持つ場合は IntegrityError が発生するため呼び出し元でハンドリングする。
        """
        if user.privy_did == privy_did:
            return
        user.privy_did = privy_did
        db.commit()
