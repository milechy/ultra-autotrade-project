# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
# backend/app/auth/models.py
"""
ユーザーモデル定義。

docs/13_security_design.md に準拠したセキュリティ要件を満たす。

ALTER TABLE users ADD COLUMN tier VARCHAR(20) NOT NULL DEFAULT 'LOWER';
ALTER TABLE users ADD COLUMN last_judgment_at TIMESTAMP WITH TIME ZONE NULL;
-- 注: F-2 で DEFAULT を 'GENERAL' から 'LOWER' に変更。本番 DB の DEFAULT 切替は
-- F-16 マイグレーションで実施 (docs/46_users_tier_migration_plan.md 参照)。

ALTER TABLE users ADD COLUMN IF NOT EXISTS privy_did VARCHAR(255) NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_privy_did ON users (privy_did) WHERE privy_did IS NOT NULL;

-- GID 1214176344039867 (P1): execution_policy CHECK + server_default 強化
-- DB default は a1b2c3d4e5f6 で 'auto_execute' 設定済み。
-- CheckConstraint と SQLAlchemy 側 server_default を Alembic migration で同期する。
ALTER TABLE users ADD CONSTRAINT users_execution_policy_check
    CHECK (execution_policy IN ('auto_execute', 'require_approval', 'proposal_only'));

-- P0 GID 1214993061793196 (P3-1): execution_policy safe default 変更
-- 新規ユーザーの DB default を auto_execute → require_approval に変更。
-- 既存 auto_execute 行の UPDATE は別途 P0 対応で実施する (本 PR 対象外)。
ALTER TABLE users ALTER COLUMN execution_policy SET DEFAULT 'require_approval';

-- RAS (Referral / Partner Affiliate System) Lane 1 schema. Lane 1 が DB schema 本体を
-- 所有するが、Lane 2 (本ファイル) でも型解決のため同一定義を先行追加している。
-- Lane 1 マージ時は同一定義のため conflict 解消は trivial。
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(16) NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_referral_code ON users (referral_code) WHERE referral_code IS NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS referrer_id INTEGER NULL REFERENCES users(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_consent_at TIMESTAMP WITH TIME ZONE NULL;

-- Lane P: LINE 月次レポート通知 opt-in
ALTER TABLE users ADD COLUMN IF NOT EXISTS line_monthly_opt_in BOOLEAN NOT NULL DEFAULT FALSE;

-- corporate-CSV [2/4]: 法人決算月 (1-12, NULL=個人)。TAX & REPORTS 法人モードのアンロック条件。
ALTER TABLE users ADD COLUMN IF NOT EXISTS corporate_fiscal_month SMALLINT NULL;
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.constants import ExecutionPolicy
from app.database import Base

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """ユーザーロール。"""

    ADMIN = "admin"
    PARTNER = "partner"
    EDITOR = "editor"
    VIEWER = "viewer"


class InvestmentTier(str, Enum):
    """投資ティア。v10 (F-2 2026-04-25 〜): LOWER / MIDDLE / UPPER の 3 層

    - LOWER:  〜1,000,000 円
    - MIDDLE: 1,000,001 〜 10,000,000 円
    - UPPER:  10,000,001 円 〜
    """

    LOWER = "LOWER"
    MIDDLE = "MIDDLE"
    UPPER = "UPPER"


#: tier 値 → 日本語ラベル。フロント表示および通知文言で使用。
TIER_JP_LABELS: dict[InvestmentTier, str] = {
    InvestmentTier.LOWER: "一般",
    InvestmentTier.MIDDLE: "ミドル",
    InvestmentTier.UPPER: "アッパー",
}


#: v10 tier 判定の境界値 (JPY)。
TIER_BOUNDARY_LOWER_JPY = 1_000_000  # LOWER / MIDDLE 境界
TIER_BOUNDARY_UPPER_JPY = 10_000_000  # MIDDLE / UPPER 境界


class RiskMode(str, Enum):
    """リスクモード。

    内部値は v9 から継続使用 (conservative / balanced / aggressive)。
    Aave MDD / Optimizer Allocator / Aave Risk Profile が文字列リテラルで直参照しているため
    **値のリネームは禁止** (F-13 でも維持)。表示は ``RISK_MODE_JP_LABELS`` 経由で日本語化する。

    F-3 (2026-04-25): 本 enum を新規作成 (従来は str リテラル直書き)。
    """

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


#: risk_mode → 日本語表示ラベル (v10 spec)。1:1 マッピング。
RISK_MODE_JP_LABELS: dict[RiskMode, str] = {
    RiskMode.CONSERVATIVE: "ローリスク",
    RiskMode.BALANCED: "ミドルリスク",
    RiskMode.AGGRESSIVE: "ハイリスク",
}

#: Phase 1 で選択許可されているモード。
#: Phase 2 で BALANCED / AGGRESSIVE を解禁する想定 (DB 側の制約ではなく API 層で強制)。
PHASE_1_ALLOWED_RISK_MODES: frozenset[RiskMode] = frozenset({RiskMode.CONSERVATIVE})

#: 各 risk_mode の解禁 Phase (Phase 2-3 の段階解禁を見据えた設計)。
RISK_MODE_PHASE: dict[RiskMode, int] = {
    RiskMode.CONSERVATIVE: 1,
    RiskMode.BALANCED: 2,
    RiskMode.AGGRESSIVE: 2,
}

#: リスクモード別月額サブスク率 (v10 spec §1)。
#: F-1 で fee_configs.subscription_rates JSONB に投入する想定値と一致する。
RISK_MODE_SUBSCRIPTION_RATES: dict[RiskMode, Decimal] = {
    RiskMode.CONSERVATIVE: Decimal("0"),  # ローリスク 0%
    RiskMode.BALANCED: Decimal("0.003"),  # ミドルリスク 0.3%/月
    RiskMode.AGGRESSIVE: Decimal("0.010"),  # ハイリスク 1.0%/月
}

#: リスクモードごとに利用可能なプロトコル (v10 spec §1)。
#: BALANCED / AGGRESSIVE は Phase 2 解禁時に Lido / Pendle を併用する。
RISK_MODE_PROTOCOLS: dict[RiskMode, frozenset[str]] = {
    RiskMode.CONSERVATIVE: frozenset({"aave"}),
    RiskMode.BALANCED: frozenset({"aave", "lido"}),
    RiskMode.AGGRESSIVE: frozenset({"aave", "lido", "pendle"}),
}


def get_risk_mode_label(value: str | None) -> str:
    """``users.risk_mode`` の DB 値から日本語ラベルを取得する。

    NULL / 不明値は CONSERVATIVE のラベル ("ローリスク") にフォールバックする
    (Phase 1 デフォルト)。F-16 で NULL を 'conservative' に物理 UPDATE 後はフォールバック不要。
    """
    if not value:
        return RISK_MODE_JP_LABELS[RiskMode.CONSERVATIVE]
    try:
        mode = RiskMode(value)
    except ValueError:
        return RISK_MODE_JP_LABELS[RiskMode.CONSERVATIVE]
    return RISK_MODE_JP_LABELS[mode]


def normalize_tier(raw_tier: str | None, *, user_id: int | None = None) -> InvestmentTier:
    """``users.tier`` の DB 値 (str) を ``InvestmentTier`` enum に正規化する。

    F-6 で導入。``workflow.py`` / ``ai_judgment_scheduler.py`` の trade-time フィー計算
    経路で、``user.tier`` を ``calculate_fee_by_market`` に渡す前の正規化に使う。

    優先順:
      1. ``InvestmentTier`` の有効値 (LOWER/MIDDLE/UPPER) → そのまま enum で返す
      2. それ以外 (None / 不明値) → WARNING ログ + ``InvestmentTier.LOWER`` フォールバック

    フォールバック時に ``ValueError`` は raise しない (フィー計算は継続、HOLD 転換させない)。
    """
    if raw_tier is not None:
        try:
            return InvestmentTier(raw_tier)
        except ValueError:
            pass
    logger.warning(
        "tier_normalize_fallback",
        extra={
            "user_id": user_id,
            "received_tier": raw_tier,
            "fallback_to": InvestmentTier.LOWER.value,
        },
    )
    return InvestmentTier.LOWER


class User(Base):
    """
    ユーザーテーブル。

    Attributes:
        id: プライマリキー
        email: メールアドレス（ユニーク）
        username: ユーザー名（ユニーク）
        hashed_password: bcrypt ハッシュ化されたパスワード
        role: ユーザーロール（admin / viewer）
        is_active: アクティブ状態
        created_at: 作成日時
        updated_at: 更新日時
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "execution_policy IN ("
            + ", ".join(f"'{value}'" for value in ExecutionPolicy.values())
            + ")",
            name="users_execution_policy_check",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRole.VIEWER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    terms_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default=None)
    risk_mode: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default="conservative"
    )
    notification_email: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
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
    user_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="managed")
    execution_policy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ExecutionPolicy.REQUIRE_APPROVAL.value,
        server_default=ExecutionPolicy.REQUIRE_APPROVAL.value,
    )
    wallet_address: Mapped[Optional[str]] = mapped_column(
        String(42), unique=True, nullable=True, index=True, default=None
    )
    privy_did: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, index=True, default=None
    )
    invited_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, default=None
    )
    tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InvestmentTier.LOWER.value
    )
    last_judgment_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    # RAS Lane 1 schema (Lane 2 先行定義 / 同一定義のため Lane 1 merge 時 conflict は trivial)
    referral_code: Mapped[Optional[str]] = mapped_column(
        String(16), unique=True, nullable=True, index=True, default=None
    )
    referrer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, default=None
    )
    referred_consent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    line_monthly_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # notification_settings_json: チャネル/種別別通知設定 (JSON テキスト、NULL=デフォルト適用)
    # ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_settings_json TEXT NULL;
    notification_settings_json: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, default=None
    )
    # corporate_fiscal_month: 法人決算月 (1-12)。NULL=個人ユーザー(法人モード未設定)。
    # TAX & REPORTS の法人モード (freee/弥生 CSV) のアンロック条件に使用する。
    # ALTER TABLE users ADD COLUMN IF NOT EXISTS corporate_fiscal_month SMALLINT NULL;
    corporate_fiscal_month: Mapped[Optional[int]] = mapped_column(
        SmallInteger, nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"

    @property
    def is_admin(self) -> bool:
        """管理者かどうか。"""
        return self.role == UserRole.ADMIN.value
