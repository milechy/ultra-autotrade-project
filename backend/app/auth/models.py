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
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(str, Enum):
    """ユーザーロール。"""

    ADMIN = "admin"
    PARTNER = "partner"
    EDITOR = "editor"
    VIEWER = "viewer"


class InvestmentTier(str, Enum):
    """投資ティア。

    v10 (F-2 2026-04-25 〜): LOWER / MIDDLE / UPPER の 3 層
      - LOWER:  〜1,000,000 円
      - MIDDLE: 1,000,001 〜 10,000,000 円
      - UPPER:  10,000,001 円 〜

    GENERAL は v9 過渡期互換値 (DEPRECATED)。F-16 で users.tier の
    全 GENERAL レコードを LOWER/MIDDLE/UPPER に再判定後、F-13 で本 enum から削除。
    """

    LOWER = "LOWER"
    MIDDLE = "MIDDLE"
    UPPER = "UPPER"
    GENERAL = "GENERAL"  # DEPRECATED (v9). 削除は F-13 (F-16 マイグレーション完了後)


#: v9 GENERAL → v10 デフォルト変換マップ (read-time fallback)。
#: F-16 マイグレーションで DB から GENERAL が消失した時点で参照箇所も削除可能。
LEGACY_TIER_MAP: dict[str, "InvestmentTier"] = {
    "GENERAL": InvestmentTier.LOWER,
}

#: tier 値 → 日本語ラベル。フロント表示および通知文言で使用。
TIER_JP_LABELS: dict[InvestmentTier, str] = {
    InvestmentTier.LOWER: "一般",
    InvestmentTier.MIDDLE: "ミドル",
    InvestmentTier.UPPER: "アッパー",
    InvestmentTier.GENERAL: "一般",  # GENERAL は LOWER と同じラベル (過渡期)
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
        String(20), nullable=False, default="auto_execute"
    )
    wallet_address: Mapped[Optional[str]] = mapped_column(
        String(42), unique=True, nullable=True, index=True, default=None
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

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"

    @property
    def is_admin(self) -> bool:
        """管理者かどうか。"""
        return self.role == UserRole.ADMIN.value
