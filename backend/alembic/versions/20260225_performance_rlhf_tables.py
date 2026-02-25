"""Create agent performance and RLHF feedback tables

Revision ID: 20260225_perf
Revises: 20260223_edge
Create Date: 2026-02-25

2 tables for Phase 4 agent benchmarking and RLHF training:
  - agent_performance_logs
  - rlhf_feedback
"""
from alembic import op
import sqlalchemy as sa

revision = '20260225_perf'
down_revision = '20260223_edge'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_performance_logs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('scenario_user_id', sa.Integer(),
                  sa.ForeignKey('scenario_users.id'), nullable=False, index=True),
        sa.Column('scenario_id', sa.Integer(),
                  sa.ForeignKey('scenarios.id'), nullable=False, index=True),
        sa.Column('round_number', sa.Integer(), nullable=False, index=True),
        sa.Column('agent_type', sa.String(20), nullable=False, index=True),
        sa.Column('agent_mode', sa.String(20), nullable=False),
        sa.Column('total_cost', sa.Float(), nullable=False),
        sa.Column('holding_cost', sa.Float(), nullable=False),
        sa.Column('shortage_cost', sa.Float(), nullable=False),
        sa.Column('service_level', sa.Float(), nullable=False),
        sa.Column('stockout_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('backlog', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_inventory', sa.Float(), nullable=False),
        sa.Column('inventory_variance', sa.Float(), nullable=True),
        sa.Column('demand_amplification', sa.Float(), nullable=True),
        sa.Column('order_variance', sa.Float(), nullable=True),
        sa.Column('order_quantity', sa.Integer(), nullable=True),
        sa.Column('optimal_order', sa.Integer(), nullable=True),
        sa.Column('decision_error', sa.Float(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, index=True),
    )

    op.create_table(
        'rlhf_feedback',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('scenario_user_id', sa.Integer(),
                  sa.ForeignKey('scenario_users.id'), nullable=False, index=True),
        sa.Column('scenario_id', sa.Integer(),
                  sa.ForeignKey('scenarios.id'), nullable=False, index=True),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('agent_type', sa.String(20), nullable=False, index=True),
        sa.Column('game_state', sa.JSON(), nullable=False),
        sa.Column('ai_suggestion', sa.Integer(), nullable=False),
        sa.Column('ai_reasoning', sa.Text(), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('human_decision', sa.Integer(), nullable=False),
        sa.Column('feedback_action', sa.String(20), nullable=False, index=True),
        sa.Column('modification_delta', sa.Integer(), nullable=True),
        sa.Column('ai_outcome', sa.JSON(), nullable=True),
        sa.Column('human_outcome', sa.JSON(), nullable=True),
        sa.Column('preference_label', sa.String(20), nullable=False,
                  server_default='unknown', index=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table('rlhf_feedback')
    op.drop_table('agent_performance_logs')
