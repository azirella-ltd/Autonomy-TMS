"""Expand nodetype enum to cover market nodes

Revision ID: 20250226090000
Revises: 20241101090000
Create Date: 2025-09-26 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250226090000"
down_revision = "20241101090000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind and bind.dialect.name == "sqlite":
        # Recreate table with a plain string column to allow new node types.
        with op.batch_alter_table("nodes", recreate="always") as batch_op:
            batch_op.alter_column(
                "type",
                existing_type=sa.String(length=100),
                type_=sa.String(length=32),
                nullable=False,
            )
        return
    op.execute(
        """
        ALTER TABLE nodes
        MODIFY COLUMN type ENUM(
            'RETAILER',
            'WHOLESALER',
            'DISTRIBUTOR',
            'MANUFACTURER',
            'MARKET_SUPPLY',
            'MARKET_DEMAND'
        ) NOT NULL
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind and bind.dialect.name == "sqlite":
        return
    op.execute(
        """
        ALTER TABLE nodes
        MODIFY COLUMN type ENUM(
            'RETAILER',
            'WHOLESALER',
            'DISTRIBUTOR',
            'MANUFACTURER'
        ) NOT NULL
        """
    )
