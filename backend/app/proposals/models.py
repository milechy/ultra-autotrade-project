# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/proposals/models.py
"""提案モデル定義。"""
#
# DB マイグレーション:
#   fee_rate / fee_amount / error_message: c3d4e5f6a7b8 / d4e5f6a7b8c9 ほかで alembic 化済み。
#   execution_attempts: h8i9j0k1l2m3_add_proposals_execution_attempts.py で alembic 化
#                       (launch_gate L0 schema sync, 2026-05-27)。
#                       適用前は本ファイル先頭のコメント記載通り手動 ALTER で先行投入されていた。
#   expected_from / expected_to: non-custodial method2 submit-tx on-chain receipt 検証用 (2026-06-01)。
#   ALTER TABLE proposals ADD COLUMN IF NOT EXISTS expected_from VARCHAR(42);
#   ALTER TABLE proposals ADD COLUMN IF NOT EXISTS expected_to VARCHAR(42);

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Integer, Numeric, String, Text, event
from sqlalchemy.orm import NO_VALUE, Mapped, mapped_column

from app.database import Base

from .execution_route import DEFAULT_EXECUTION_ROUTE, ExecutionRoute


class Proposal(Base):
    """提案テーブル。"""

    __tablename__ = "proposals"
    # execution_route の有効値は ExecutionRoute (models.py が唯一の真実源)。
    # migration / DB CHECK 制約は本 enum の values() を文字通り使う
    # (CLAUDE.md「CHECK制約と migration の二重管理ルール」遵守)。
    __table_args__ = (
        CheckConstraint(
            "execution_route IN (" + ", ".join(f"'{v}'" for v in ExecutionRoute.values()) + ")",
            name="ck_proposals_execution_route",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ai_decision_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    asset: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=36, scale=18), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expected_hf_after: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    estimated_gas_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=6), nullable=True
    )
    fee_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=6), nullable=True
    )
    fee_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=2), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    # execution_attempts: Aave 実行試行回数 (2026-05-21 P0 デッドレター化対策)
    # MAX_EXECUTION_ATTEMPTS (= 3) 超過で status を 'failed' に強制遷移させ再試行を停止する。
    # server_default='0' は alembic h8i9j0k1l2m3 migration (launch_gate L0 schema sync) と同期。
    execution_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # submit-tx receipt 検証: partner が送信した tx の from/to アドレスを保存して照合する
    expected_from: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    expected_to: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    # P0-2 (2026-06-03): 執行経路分岐 (CEX 本線 / on-chain Aave opt-in)。
    # 作成時に確定し immutable (下部 _prevent_execution_route_mutation で強制)。
    # 値の正は app.proposals.execution_route.ExecutionRoute。
    execution_route: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_EXECUTION_ROUTE,
        server_default=DEFAULT_EXECUTION_ROUTE,
        index=True,
    )
    # CEX 経路の執行証跡: CEX API order_id (= tx_id) と生レスポンス。
    # on-chain 経路では NULL のまま (basescan の tx_hash 側に記録される)。
    cex_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cex_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


@event.listens_for(Proposal.execution_route, "set", propagate=True)
def _prevent_execution_route_mutation(
    target: Proposal, value: object, oldvalue: object, initiator: object
) -> object:
    """execution_route の作成後変更を構造的に禁止する (P0-2 DoD: immutable)。

    初回設定 (oldvalue が未設定 / None) は許可。以後、別値への変更は ValueError。
    同値の再代入 (db.refresh 等) は no-op で許可する。

    「経路の後から変更を許す実装」は P0-2 で明示的に禁止されているため、
    application 層で物理的に弾く。
    """
    if oldvalue is NO_VALUE or oldvalue is None:
        return value
    if value != oldvalue:
        raise ValueError(
            f"execution_route is immutable (proposal id={getattr(target, 'id', None)}): "
            f"cannot change {oldvalue!r} -> {value!r}"
        )
    return value
