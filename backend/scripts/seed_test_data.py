#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# Unauthorized copying or distribution is strictly prohibited.
"""
テスト用データ投入スクリプト

使い方（staging サーバー上）:
  cd /opt/ultra-autotrade/backend
  python scripts/seed_test_data.py

投入データ:
  - AI判定:   BUY/SELL/HOLD 各3件 = 9件
  - 取引提案: pending 2件
  - 取引履歴: completed 5件
  - ポートフォリオスナップショット: 30日分
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# backend/ をパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.ai.models import AIDecision
from app.database import SessionLocal, init_db
from app.portfolio.models import PortfolioSnapshot
from app.proposals.models import Proposal
from app.transactions.models import Transaction


def _now(offset_hours: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=offset_hours)


def seed_ai_decisions(db, user_id: int) -> list[int]:
    """BUY/SELL/HOLD 各3件を投入し、IDリストを返す。"""
    records = [
        # BUY x 3
        dict(
            user_id=user_id,
            query="Arbitrum USDC supply opportunity",
            action="BUY",
            confidence=82,
            reason="Health Factor is stable at 2.1. Market conditions favorable for USDC supply. TVL increasing on Arbitrum.",
            primary_provider="claude-sonnet-4-6",
            primary_action="BUY",
            primary_confidence=82,
            secondary_provider="gpt-4o",
            secondary_action="BUY",
            secondary_confidence=78,
            agreed=True,
        ),
        dict(
            user_id=user_id,
            query="WETH collateral analysis",
            action="BUY",
            confidence=75,
            reason="WETH price stable. Supply rate at 3.2% APY. Risk within acceptable bounds.",
            primary_provider="claude-sonnet-4-6",
            primary_action="BUY",
            primary_confidence=75,
            secondary_provider="gpt-4o",
            secondary_action="HOLD",
            secondary_confidence=60,
            agreed=False,
        ),
        dict(
            user_id=user_id,
            query="Portfolio rebalance check",
            action="BUY",
            confidence=88,
            reason="Strong upward momentum. Confidence high. Aave V3 safety score: 92.",
            primary_provider="claude-sonnet-4-6",
            primary_action="BUY",
            primary_confidence=88,
            secondary_provider="gpt-4o",
            secondary_action="BUY",
            secondary_confidence=85,
            agreed=True,
        ),
        # SELL x 3
        dict(
            user_id=user_id,
            query="USDC withdraw signal",
            action="SELL",
            confidence=71,
            reason="Health Factor dropped to 1.8. Recommend partial withdrawal to restore safety margin.",
            primary_provider="claude-sonnet-4-6",
            primary_action="SELL",
            primary_confidence=71,
            secondary_provider="gpt-4o",
            secondary_action="SELL",
            secondary_confidence=68,
            agreed=True,
        ),
        dict(
            user_id=user_id,
            query="Liquidation risk assessment",
            action="SELL",
            confidence=65,
            reason="Market volatility elevated. Conservative withdrawal advised to protect collateral.",
            primary_provider="claude-sonnet-4-6",
            primary_action="SELL",
            primary_confidence=65,
            secondary_provider=None,
            secondary_action=None,
            secondary_confidence=None,
            agreed=False,
        ),
        dict(
            user_id=user_id,
            query="Risk rebalance — HF 1.75",
            action="SELL",
            confidence=79,
            reason="HF below safe threshold. Immediate USDC withdrawal recommended.",
            primary_provider="claude-sonnet-4-6",
            primary_action="SELL",
            primary_confidence=79,
            secondary_provider="gpt-4o",
            secondary_action="SELL",
            secondary_confidence=77,
            agreed=True,
        ),
        # HOLD x 3
        dict(
            user_id=user_id,
            query="Market conditions check",
            action="HOLD",
            confidence=55,
            reason="Mixed signals. Gas fees elevated. No action recommended until conditions improve.",
            primary_provider="claude-sonnet-4-6",
            primary_action="HOLD",
            primary_confidence=55,
            secondary_provider="gpt-4o",
            secondary_action="HOLD",
            secondary_confidence=62,
            agreed=True,
        ),
        dict(
            user_id=user_id,
            query="Weekly portfolio review",
            action="HOLD",
            confidence=60,
            reason="Portfolio balanced. Current yield acceptable. No rebalancing needed.",
            primary_provider="claude-sonnet-4-6",
            primary_action="HOLD",
            primary_confidence=60,
            secondary_provider=None,
            secondary_action=None,
            secondary_confidence=None,
            agreed=False,
        ),
        dict(
            user_id=user_id,
            query="Pre-market open assessment",
            action="HOLD",
            confidence=58,
            reason="Insufficient signal strength. Waiting for clearer trend confirmation.",
            primary_provider="claude-sonnet-4-6",
            primary_action="HOLD",
            primary_confidence=58,
            secondary_provider="gpt-4o",
            secondary_action="BUY",
            secondary_confidence=55,
            agreed=False,
        ),
    ]

    ids = []
    for i, r in enumerate(records):
        obj = AIDecision(
            created_at=_now(offset_hours=(len(records) - i) * 3),
            **r,
        )
        db.add(obj)
        db.flush()
        ids.append(obj.id)

    print(f"  ✓ AI判定 {len(ids)} 件投入")
    return ids


def seed_proposals(db, user_id: int, ai_decision_ids: list[int]) -> None:
    """pending 提案 2件を投入。"""
    proposals = [
        Proposal(
            user_id=user_id,
            ai_decision_id=ai_decision_ids[0] if ai_decision_ids else None,
            operation="SUPPLY",
            asset="USDC",
            amount=Decimal("500.000000000000000000"),
            amount_usd=Decimal("500.00"),
            reason="AI recommended SUPPLY: Health Factor stable at 2.1. USDC supply APY 3.4%.",
            expected_hf_after=Decimal("2.3500"),
            estimated_gas_usd=Decimal("0.850000"),
            status="pending",
            expires_at=_now(offset_hours=-24),  # expires 24h from now
            created_at=_now(offset_hours=1),
        ),
        Proposal(
            user_id=user_id,
            ai_decision_id=ai_decision_ids[2] if len(ai_decision_ids) > 2 else None,
            operation="WITHDRAW",
            asset="USDC",
            amount=Decimal("200.000000000000000000"),
            amount_usd=Decimal("200.00"),
            reason="Partial withdrawal to improve Health Factor margin. Current HF 1.8 → target 2.2.",
            expected_hf_after=Decimal("2.2000"),
            estimated_gas_usd=Decimal("0.720000"),
            status="pending",
            expires_at=_now(offset_hours=-24),
            created_at=_now(offset_hours=2),
        ),
    ]

    for p in proposals:
        db.add(p)

    print(f"  ✓ 提案 {len(proposals)} 件投入 (pending)")


def seed_transactions(db, user_id: int, ai_decision_ids: list[int]) -> None:
    """completed 取引 5件を投入。"""
    txs = [
        Transaction(
            user_id=user_id,
            wallet_address="0xTestWallet1234567890abcdef1234567890ab",
            operation="SUPPLY",
            asset="USDC",
            amount=Decimal("1000.000000000000000000"),
            amount_usd=Decimal("1000.00"),
            tx_hash="0xabc123def456789012345678901234567890abcdef1234567890abcdef123456",
            chain="arbitrum_sepolia",
            status="completed",
            ai_decision_id=ai_decision_ids[0] if ai_decision_ids else None,
            gas_used=Decimal("150000"),
            gas_price_gwei=Decimal("0.100000000"),
            is_dry_run=False,
            created_at=_now(offset_hours=72),
        ),
        Transaction(
            user_id=user_id,
            wallet_address="0xTestWallet1234567890abcdef1234567890ab",
            operation="SUPPLY",
            asset="WETH",
            amount=Decimal("0.500000000000000000"),
            amount_usd=Decimal("1800.00"),
            tx_hash="0xdef456abc789012345678901234567890abcdef1234567890abcdef456789012",
            chain="arbitrum_sepolia",
            status="completed",
            ai_decision_id=ai_decision_ids[2] if len(ai_decision_ids) > 2 else None,
            gas_used=Decimal("160000"),
            gas_price_gwei=Decimal("0.100000000"),
            is_dry_run=False,
            created_at=_now(offset_hours=48),
        ),
        Transaction(
            user_id=user_id,
            wallet_address="0xTestWallet1234567890abcdef1234567890ab",
            operation="WITHDRAW",
            asset="USDC",
            amount=Decimal("300.000000000000000000"),
            amount_usd=Decimal("300.00"),
            tx_hash="0x789abc012def345678901234567890abcdef1234567890abcdef789012345678",
            chain="arbitrum_sepolia",
            status="completed",
            ai_decision_id=ai_decision_ids[3] if len(ai_decision_ids) > 3 else None,
            gas_used=Decimal("140000"),
            gas_price_gwei=Decimal("0.100000000"),
            is_dry_run=False,
            created_at=_now(offset_hours=36),
        ),
        Transaction(
            user_id=user_id,
            wallet_address="0xTestWallet1234567890abcdef1234567890ab",
            operation="SUPPLY",
            asset="USDC",
            amount=Decimal("500.000000000000000000"),
            amount_usd=Decimal("500.00"),
            tx_hash="0x012def345678901234567890abcdef1234567890abcdef012345678901234567",
            chain="arbitrum_sepolia",
            status="completed",
            ai_decision_id=ai_decision_ids[5] if len(ai_decision_ids) > 5 else None,
            gas_used=Decimal("155000"),
            gas_price_gwei=Decimal("0.100000000"),
            is_dry_run=False,
            created_at=_now(offset_hours=24),
        ),
        Transaction(
            user_id=user_id,
            wallet_address="0xTestWallet1234567890abcdef1234567890ab",
            operation="WITHDRAW",
            asset="WETH",
            amount=Decimal("0.200000000000000000"),
            amount_usd=Decimal("720.00"),
            tx_hash="0x345678901234567890abcdef1234567890abcdef3456789012345678901234ab",
            chain="arbitrum_sepolia",
            status="completed",
            ai_decision_id=ai_decision_ids[4] if len(ai_decision_ids) > 4 else None,
            gas_used=Decimal("148000"),
            gas_price_gwei=Decimal("0.100000000"),
            is_dry_run=False,
            created_at=_now(offset_hours=12),
        ),
    ]

    for tx in txs:
        db.add(tx)

    print(f"  ✓ 取引履歴 {len(txs)} 件投入 (completed)")


def seed_portfolio_snapshots(db, user_id: int) -> None:
    """30日分のポートフォリオスナップショットを投入（チャート用）。"""
    import random

    random.seed(42)

    base_value = Decimal("8500.00")
    base_hf = Decimal("2.10")
    snapshots = []

    for i in range(30, -1, -1):
        # ±3% の変動をシミュレート
        drift = Decimal(str(random.uniform(-0.03, 0.04)))  # noqa: S311
        total_value = (base_value * (1 + drift)).quantize(Decimal("0.01"))
        supply = (total_value * Decimal("0.75")).quantize(Decimal("0.01"))
        borrow = (total_value * Decimal("0.20")).quantize(Decimal("0.01"))
        hf = (base_hf + Decimal(str(random.uniform(-0.15, 0.15)))).quantize(Decimal("0.0001"))  # noqa: S311
        hf = max(Decimal("1.5"), min(Decimal("3.0"), hf))

        snapshots.append(
            PortfolioSnapshot(
                user_id=user_id,
                total_value_usd=total_value,
                total_supply_usd=supply,
                total_borrow_usd=borrow,
                health_factor=hf,
                positions_json=[
                    {
                        "symbol": "USDC",
                        "supplied": float(supply * Decimal("0.6")),
                        "borrowed": float(borrow * Decimal("0.5")),
                        "supplyApr": 3.4,
                        "usdValue": float(supply * Decimal("0.6")),
                    },
                    {
                        "symbol": "WETH",
                        "supplied": float(supply * Decimal("0.4")),
                        "borrowed": float(borrow * Decimal("0.5")),
                        "supplyApr": 1.8,
                        "usdValue": float(supply * Decimal("0.4")),
                    },
                ],
                recorded_at=_now(offset_hours=i * 24),
            )
        )
        base_value = total_value  # drift forward

    for s in snapshots:
        db.add(s)

    print(f"  ✓ ポートフォリオスナップショット {len(snapshots)} 件投入 (30日分)")


def get_or_create_admin_user(db):
    """最初のユーザーを取得する（seedは認証不要で直接DB操作）。"""
    from app.auth.models import User

    user = db.scalars(select(User).order_by(User.id.asc()).limit(1)).first()
    if user is None:
        print("  ⚠️  ユーザーが存在しません。先に /auth/register でadminを登録してください。")
        sys.exit(1)
    print(f"  ✓ ユーザー取得: {user.email} (id={user.id})")
    return user


def main() -> None:
    print("=== Ultra AutoTrade テストデータ投入 ===")
    init_db()

    with SessionLocal() as db:
        user = get_or_create_admin_user(db)

        # AI判定
        ai_ids = seed_ai_decisions(db, user.id)

        # 取引提案（pending）
        seed_proposals(db, user.id, ai_ids)

        # 取引履歴（completed）
        seed_transactions(db, user.id, ai_ids)

        # ポートフォリオスナップショット（チャート用）
        seed_portfolio_snapshots(db, user.id)

        db.commit()
        print("\n✅ 投入完了")


if __name__ == "__main__":
    main()
