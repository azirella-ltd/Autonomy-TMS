"""add supplier node type

Revision ID: 20250308094500_add_supplier_node_type
Revises: 20250306090000
Create Date: 2025-03-08 09:45:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250308094500_add_supplier_node_type"
down_revision = "20250306090000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Ensure alembic_version can store longer revision identifiers on MySQL.
    if bind.dialect.name == "mysql":
        op.execute("ALTER TABLE alembic_version MODIFY COLUMN version_num VARCHAR(64)")

    op.execute(
        """
        ALTER TABLE nodes
        MODIFY COLUMN type ENUM(
            'RETAILER',
            'WHOLESALER',
            'DISTRIBUTOR',
            'MANUFACTURER',
            'SUPPLIER',
            'MARKET_SUPPLY',
            'MARKET_DEMAND'
        ) NOT NULL
        """
    )
    op.execute(
        """
        UPDATE nodes
        SET
            type = 'SUPPLIER',
            name = CONCAT(
                'Component Supplier ',
                SUBSTRING_INDEX(SUBSTRING_INDEX(name, ' ', -1), '-', 1),
                '-',
                LPAD(SUBSTRING_INDEX(name, '-', -1), 2, '0')
            )
        WHERE type = 'MARKET_SUPPLY'
          AND name LIKE 'Supplier %'
        """
    )
    node_defs = (
        '[{"type":"market_demand","label":"Market Demand","order":0,"is_required":true},'
        '{"type":"distributor","label":"Distributor","order":1,"is_required":false},'
        '{"type":"manufacturer","label":"Manufacturer","order":2,"is_required":false},'
        '{"type":"wholesaler","label":"Wholesaler","order":3,"is_required":false},'
        '{"type":"market_demand","label":"Market Demand","order":4,"is_required":true}]'
    )
    op.execute(
        sa.text(
            "UPDATE supply_chain_configs "
            "SET node_type_definitions = :defs "
            "WHERE name = 'Complex_SC'"
        ).bindparams(defs=node_defs)
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE nodes
        SET type = 'MARKET_SUPPLY'
        WHERE type = 'SUPPLIER'
        """
    )
    op.execute(
        """
        UPDATE nodes
        SET name = CONCAT(
                'Supplier ',
                SUBSTRING_INDEX(SUBSTRING_INDEX(name, ' ', -1), '-', 1),
                '-',
                CAST(SUBSTRING_INDEX(name, '-', -1) AS UNSIGNED)
            )
        WHERE name LIKE 'Component Supplier %'
        """
    )
    op.execute(
        """
        UPDATE supply_chain_configs
        SET node_type_definitions = '[{"type":"market_supply","label":"Market Supply","order":0,"is_required":true},{"type":"manufacturer","label":"Manufacturer","order":1,"is_required":false},{"type":"distributor","label":"Distributor","order":2,"is_required":false},{"type":"wholesaler","label":"Wholesaler","order":3,"is_required":false},{"type":"retailer","label":"Retailer","order":4,"is_required":false},{"type":"market_demand","label":"Market Demand","order":5,"is_required":true}]'
        WHERE name = 'Complex_SC'
        """
    )
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
