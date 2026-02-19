"""add groups table and group relationships

Revision ID: 20240912120000
Revises: 20240910152000
Create Date: 2025-09-12 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


def _is_sqlite(op_obj) -> bool:
    bind = op_obj.get_bind()
    return bind.dialect.name == 'sqlite'

# revision identifiers, used by Alembic.
revision = '20240912120000'
down_revision = '20240910152000'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('logo', sa.String(length=255), nullable=True),
        sa.Column('admin_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('admin_id')
    )

    if _is_sqlite(op):
        with op.batch_alter_table('users') as batch_op:
            batch_op.add_column(sa.Column('group_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_users_group', 'groups', ['group_id'], ['id'], ondelete='CASCADE'
            )

        with op.batch_alter_table('supply_chain_configs') as batch_op:
            batch_op.add_column(sa.Column('group_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_scc_group', 'groups', ['group_id'], ['id'], ondelete='CASCADE'
            )

        with op.batch_alter_table('games') as batch_op:
            batch_op.add_column(sa.Column('group_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_games_group', 'groups', ['group_id'], ['id'], ondelete='CASCADE'
            )
    else:
        op.add_column('users', sa.Column('group_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_users_group', 'users', 'groups', ['group_id'], ['id'], ondelete='CASCADE')

        op.add_column('supply_chain_configs', sa.Column('group_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_scc_group', 'supply_chain_configs', 'groups', ['group_id'], ['id'], ondelete='CASCADE')

        op.add_column('games', sa.Column('group_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_games_group', 'games', 'groups', ['group_id'], ['id'], ondelete='CASCADE')

def downgrade():
    if _is_sqlite(op):
        with op.batch_alter_table('games') as batch_op:
            batch_op.drop_constraint('fk_games_group', type_='foreignkey')
            batch_op.drop_column('group_id')

        with op.batch_alter_table('supply_chain_configs') as batch_op:
            batch_op.drop_constraint('fk_scc_group', type_='foreignkey')
            batch_op.drop_column('group_id')

        with op.batch_alter_table('users') as batch_op:
            batch_op.drop_constraint('fk_users_group', type_='foreignkey')
            batch_op.drop_column('group_id')
    else:
        op.drop_constraint('fk_games_group', 'games', type_='foreignkey')
        op.drop_column('games', 'group_id')

        op.drop_constraint('fk_scc_group', 'supply_chain_configs', type_='foreignkey')
        op.drop_column('supply_chain_configs', 'group_id')

        op.drop_constraint('fk_users_group', 'users', type_='foreignkey')
        op.drop_column('users', 'group_id')

    op.drop_table('groups')
