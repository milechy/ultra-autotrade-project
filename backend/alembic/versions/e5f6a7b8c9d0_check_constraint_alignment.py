"""fee_v10_check_constraint_alignment

Update fee_transactions.risk_mode CHECK constraint from v10-spec values
('LOW','MIDDLE','HIGH') to F-3 RiskMode internal values
('conservative','balanced','aggressive').

Equivalent raw SQL: backend/alembic/sql/046_fee_v10_check_constraint_alignment.sql

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-25 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace risk_mode CHECK with F-3 internal values."""
    op.drop_constraint("chk_fee_tx_risk_mode", "fee_transactions", type_="check")
    op.create_check_constraint(
        "chk_fee_tx_risk_mode",
        "fee_transactions",
        "risk_mode IN ('conservative', 'balanced', 'aggressive')",
    )


def downgrade() -> None:
    """Restore v10-spec values CHECK ('LOW','MIDDLE','HIGH')."""
    op.drop_constraint("chk_fee_tx_risk_mode", "fee_transactions", type_="check")
    op.create_check_constraint(
        "chk_fee_tx_risk_mode",
        "fee_transactions",
        "risk_mode IN ('LOW', 'MIDDLE', 'HIGH')",
    )
