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
