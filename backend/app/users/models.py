# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/users/models.py
"""ユーザー設定モデル定義。

本モジュールは main.py から `from app.users.models import UserSettings  # noqa: F401`
でインポートされ、Base.metadata.create_all() 時にテーブルが自動作成される。
Alembic 不使用プロジェクトのため、下記 SQL は手動実行が必要なバックアップとして保持する。

手動 CREATE TABLE SQL (新規環境・DB 再構築時):
    CREATE TABLE IF NOT EXISTS user_settings (
        id              SERIAL PRIMARY KEY,
        user_id         INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        notification_email      VARCHAR(255),
        notification_frequency  VARCHAR(20)  NOT NULL DEFAULT 'important',
        max_single_trade_usd    NUMERIC(20,2),
        max_daily_trade_usd     NUMERIC(20,2),
        risk_mode       VARCHAR(20)  NOT NULL DEFAULT 'conservative',
        dark_mode       BOOLEAN      NOT NULL DEFAULT TRUE,
        language        VARCHAR(10)  NOT NULL DEFAULT 'ja',
        two_factor_enabled BOOLEAN  NOT NULL DEFAULT FALSE,
        created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS ix_user_settings_user_id ON user_settings (user_id);
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.security.sqlalchemy_types import EncryptedString


class UserSettings(Base):
    """
    ユーザー設定テーブル。

    ユーザーごとの通知設定・取引上限・リスクモード等を格納する。
    users テーブルとは 1:1 の関係。

    Attributes:
        id: プライマリキー
        user_id: ユーザー ID（users.id への外部キー、ユニーク）
        notification_email: 通知用メールアドレス
        notification_frequency: 通知頻度 (all / important / none)
        max_single_trade_usd: 単一取引の上限金額（USD）
        max_daily_trade_usd: 日次取引の上限金額（USD）
        risk_mode: リスクモード (conservative / balanced / aggressive)
        dark_mode: ダークモード有効化フラグ
        language: 言語設定 (ja / en)
        two_factor_enabled: 二段階認証有効化フラグ
        created_at: 作成日時
        updated_at: 更新日時
    """

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Track 2 / 層2: 実 PII のためフィールドレベル暗号化(AES-256-GCM)。
    # ALTER TABLE user_settings ALTER COLUMN notification_email TYPE VARCHAR(512);
    notification_email: Mapped[Optional[str]] = mapped_column(
        EncryptedString(512), nullable=True, default=None
    )
    notification_frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="important"
    )
    max_single_trade_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=2), nullable=True, default=None
    )
    max_daily_trade_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=2), nullable=True, default=None
    )
    risk_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="conservative")
    dark_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="ja")
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<UserSettings(user_id={self.user_id}, risk_mode={self.risk_mode})>"


# アカウント削除申請の status 値（models.py を唯一の真実源とする / CHECK は migration 内で独自定義しない）
ACCOUNT_DELETION_STATUS_PENDING = "pending"
ACCOUNT_DELETION_STATUS_PROCESSED = "processed"
ACCOUNT_DELETION_STATUS_CANCELLED = "cancelled"


class AccountDeletionRequest(Base):
    """アカウント削除申請テーブル。

    ユーザーからの削除申請を耐久的に記録する（APPI / 個人情報保護法対応）。
    本モジュールは main.py から import され、Base.metadata.create_all() 時に
    テーブルが自動作成される。status は application-layer で制御する
    （'pending' / 'processed' / 'cancelled'）。CHECK 制約を migration 内で
    独自定義しない（models.py が唯一の真実源）。

    手動 CREATE TABLE SQL (新規環境・DB 再構築時):
        CREATE TABLE IF NOT EXISTS account_deletion_requests (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status       VARCHAR(20) NOT NULL DEFAULT 'pending',
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processed_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS ix_account_deletion_requests_user_id
            ON account_deletion_requests (user_id);
    """

    __tablename__ = "account_deletion_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ACCOUNT_DELETION_STATUS_PENDING
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<AccountDeletionRequest(user_id={self.user_id}, status={self.status})>"


# 委譲枠 (delegation grant) の status 値（models.py を唯一の真実源とする /
# CHECK 制約は migration 内で独自定義しない）。
DELEGATION_STATUS_ACTIVE = "active"
DELEGATION_STATUS_REVOKED = "revoked"
DELEGATION_STATUS_EXPIRED = "expired"


class DelegationGrant(Base):
    """事前枠承認（委譲枠）テーブル。

    v4 完全おまかせ自動運用（Phase 0 / スライス0-C）の事前枠承認を耐久記録する。
    ユーザーが「この枠・このリスクで任せる」と1回 consent した内容を保持し、
    AUTO 執行時に有効な grant が無ければ fail-closed で拒否するための真実源になる。

    - 上限は **%** で保持し、実行時に総資産 × risk_limiter ハード上限（単一≤10% /
      日次≤30% / HF≥1.6）で二重クランプする（DB 値が緩くてもハードが勝つ）。
    - status は application-layer で制御（active / revoked / expired）。CHECK 制約を
      migration 内で独自定義しない（models.py が唯一の真実源）。
    - 1 ユーザーが複数 grant を持ち得る（履歴を残す）。有効判定は get_active_grant() で行う。
    - 本モジュールは main.py から import され Base.metadata.create_all() でテーブル自動作成。
      production は alembic migration（down_revision=swa20260618）で適用する。

    手動 CREATE TABLE SQL (新規環境・DB 再構築時):
        CREATE TABLE IF NOT EXISTS delegation_grants (
            id                    SERIAL PRIMARY KEY,
            user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            wallet_address        VARCHAR(42),
            status                VARCHAR(16) NOT NULL DEFAULT 'active',
            max_single_trade_pct  NUMERIC(5,2) NOT NULL,
            max_daily_trade_pct   NUMERIC(5,2) NOT NULL,
            hf_floor              NUMERIC(6,3) NOT NULL,
            allowed_protocols     JSON NOT NULL,
            allowed_assets        JSON NOT NULL,
            consent_at            TIMESTAMPTZ NOT NULL,
            expires_at            TIMESTAMPTZ NOT NULL,
            revoked_at            TIMESTAMPTZ,
            privy_policy_id       VARCHAR(255),
            privy_signer_id       VARCHAR(255),
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_delegation_grants_user_id
            ON delegation_grants (user_id);
    """

    __tablename__ = "delegation_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 委譲対象ウォレット（smart_wallet_address 優先。consent 時点の値を固定保持）
    wallet_address: Mapped[Optional[str]] = mapped_column(String(42), nullable=True, default=None)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DELEGATION_STATUS_ACTIVE
    )
    # 上限は % で保持（実行時に risk_limiter ハード上限へクランプ）
    max_single_trade_pct: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2), nullable=False
    )
    max_daily_trade_pct: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2), nullable=False
    )
    hf_floor: Mapped[Decimal] = mapped_column(Numeric(precision=6, scale=3), nullable=False)
    allowed_protocols: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    allowed_assets: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    privy_policy_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    privy_signer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<DelegationGrant(user_id={self.user_id}, status={self.status})>"


def get_active_grant(user_id: int, db: object) -> "Optional[DelegationGrant]":
    """ユーザーの現在有効な委譲枠を返す。無ければ None（fail-closed の判定に使う）。

    有効条件: status='active' かつ revoked_at IS NULL かつ expires_at > 現在時刻。
    複数該当する場合は最新（created_at 降順）の 1 件。

    Note:
        expires_at が過去でも DB の status は 'active' のまま残り得る（遅延 expire）。
        本関数は expires_at を実時刻で必ず再判定するため、status だけに依存しない。
    """
    from sqlalchemy import select  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    stmt = (
        select(DelegationGrant)
        .where(
            DelegationGrant.user_id == user_id,
            DelegationGrant.status == DELEGATION_STATUS_ACTIVE,
            DelegationGrant.revoked_at.is_(None),
            DelegationGrant.expires_at > now,
        )
        .order_by(DelegationGrant.created_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)  # type: ignore[attr-defined,no-any-return]
