# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/transactions/models.py
"""取引履歴モデル定義。"""
#
# DB マイグレーション（Alembic未使用 — 手動ALTER）:
#   ALTER TABLE transactions ADD COLUMN IF NOT EXISTS error_message TEXT;
#   ALTER TABLE transactions ADD COLUMN IF NOT EXISTS gas_sponsored BOOLEAN;
#   -- gas_sponsored: ERC-4337 UserOp の paymaster がガス代を全額負担したか。
#   --   True=paymasterがスポンサー（ユーザー負担分は実質0） / False=Smart Wallet自己負担
#   --   （gas_used * gas_price_gwei が実費用） / NULL=bundlerがpaymasterフィールドを
#   --   返さない・EOA直接送信 tx 等で判別不能。部分スポンサー（一部だけ負担）は
#   --   bundler が返す actualGasCost が既に合算済みのため区別できない（all-or-nothing扱い）。
#   -- gas_used / gas_price_gwei は本カラム追加と同時に、bundler の
#   --   eth_getUserOperationReceipt (actualGasUsed / actualGasCost) 由来の実績値で
#   --   埋まるようになった（旧: 常にNULL、費目は $0.27/トレード固定値のみ）。

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Transaction(Base):
    """取引履歴テーブル。"""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    wallet_address: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    operation: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=36, scale=18), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=2), nullable=False)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    chain: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    ai_decision_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gas_used: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=0), nullable=True
    )
    gas_price_gwei: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=9), nullable=True
    )
    is_dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gas_sponsored: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
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
