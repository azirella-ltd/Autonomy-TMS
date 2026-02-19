"""Add training metadata columns to supply chain configs

Revision ID: 20240920160000
Revises: 20240915120000
Create Date: 2025-09-20 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


def _is_sqlite(op_obj) -> bool:
    bind = op_obj.get_bind()
    return bind.dialect.name == 'sqlite'


# revision identifiers, used by Alembic.
revision = '20240920160000'
down_revision = '20240915120000'
branch_labels = None
depends_on = None


def upgrade():
    columns = [
        sa.Column('needs_training', sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column('training_status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('trained_at', sa.DateTime(), nullable=True),
        sa.Column('trained_model_path', sa.String(length=255), nullable=True),
        sa.Column('last_trained_config_hash', sa.String(length=128), nullable=True),
    ]

    if _is_sqlite(op):
        with op.batch_alter_table('supply_chain_configs') as batch_op:
            for column in columns:
                batch_op.add_column(column.copy())
            batch_op.alter_column('needs_training', server_default=None)
            batch_op.alter_column('training_status', server_default=None)
    else:
        op.add_column('supply_chain_configs', columns[0])
        op.add_column('supply_chain_configs', columns[1])
        op.add_column('supply_chain_configs', columns[2])
        op.add_column('supply_chain_configs', columns[3])
        op.add_column('supply_chain_configs', columns[4])

        # Remove server defaults now that existing rows have been initialised
        op.alter_column('supply_chain_configs', 'needs_training', server_default=None)
        op.alter_column('supply_chain_configs', 'training_status', server_default=None)


def downgrade():
    if _is_sqlite(op):
        with op.batch_alter_table('supply_chain_configs') as batch_op:
            batch_op.drop_column('last_trained_config_hash')
            batch_op.drop_column('trained_model_path')
            batch_op.drop_column('trained_at')
            batch_op.drop_column('training_status')
            batch_op.drop_column('needs_training')
    else:
        op.drop_column('supply_chain_configs', 'last_trained_config_hash')
        op.drop_column('supply_chain_configs', 'trained_model_path')
        op.drop_column('supply_chain_configs', 'trained_at')
        op.drop_column('supply_chain_configs', 'training_status')
        op.drop_column('supply_chain_configs', 'needs_training')
