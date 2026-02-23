"""Create edge agent management tables

Revision ID: 20260223_edge
Revises: None
Create Date: 2026-02-23

13 tables for PicoClaw fleet, OpenClaw gateway, signal ingestion,
and security audit:
  - edge_picoclaw_instances
  - edge_picoclaw_heartbeats
  - edge_picoclaw_alerts
  - edge_service_accounts
  - edge_openclaw_config
  - edge_openclaw_channels
  - edge_openclaw_skills
  - edge_openclaw_sessions
  - edge_ingested_signals
  - edge_signal_correlations
  - edge_source_reliability
  - edge_security_checklist
  - edge_activity_log
"""
from alembic import op
import sqlalchemy as sa

revision = '20260223_edge'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # PicoClaw Fleet
    op.create_table(
        'edge_picoclaw_instances',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('site_key', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('site_name', sa.String(200), nullable=True),
        sa.Column('site_type', sa.String(50), nullable=True),
        sa.Column('region', sa.String(100), nullable=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=True),
        sa.Column('mode', sa.String(50), nullable=False, server_default='deterministic'),
        sa.Column('heartbeat_interval_min', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('digest_interval_min', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('alert_channel', sa.String(50), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='STALE'),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('uptime_pct', sa.Float(), nullable=True),
        sa.Column('memory_mb', sa.Float(), nullable=True),
        sa.Column('inventory_ratio', sa.Float(), nullable=True),
        sa.Column('service_level', sa.Float(), nullable=True),
        sa.Column('demand_deviation', sa.Float(), nullable=True),
        sa.Column('capacity_utilization', sa.Float(), nullable=True),
        sa.Column('orders_past_due', sa.Integer(), nullable=True),
        sa.Column('forecast_mape', sa.Float(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('registered_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_pico_status', 'edge_picoclaw_instances', ['status'])
    op.create_index('idx_pico_group', 'edge_picoclaw_instances', ['group_id'])

    op.create_table(
        'edge_picoclaw_heartbeats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('site_key', sa.String(100), sa.ForeignKey('edge_picoclaw_instances.site_key', ondelete='CASCADE'), nullable=False),
        sa.Column('memory_mb', sa.Float(), nullable=True),
        sa.Column('cpu_pct', sa.Float(), nullable=True),
        sa.Column('uptime_seconds', sa.Integer(), nullable=True),
        sa.Column('conditions', sa.JSON(), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_heartbeat_site', 'edge_picoclaw_heartbeats', ['site_key'])
    op.create_index('idx_heartbeat_time', 'edge_picoclaw_heartbeats', ['received_at'])

    op.create_table(
        'edge_picoclaw_alerts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('alert_id', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('site_key', sa.String(100), sa.ForeignKey('edge_picoclaw_instances.site_key', ondelete='CASCADE'), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('condition', sa.String(100), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=True),
        sa.Column('threshold_value', sa.Float(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('acknowledged', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('acknowledged_by', sa.String(100), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_alert_site', 'edge_picoclaw_alerts', ['site_key'])
    op.create_index('idx_alert_severity', 'edge_picoclaw_alerts', ['severity'])
    op.create_index('idx_alert_created', 'edge_picoclaw_alerts', ['created_at'])

    op.create_table(
        'edge_service_accounts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('scope', sa.String(20), nullable=False, server_default='site'),
        sa.Column('site_key', sa.String(100), nullable=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=True),
        sa.Column('token_hash', sa.String(256), nullable=True),
        sa.Column('token_masked', sa.String(50), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_sa_scope', 'edge_service_accounts', ['scope'])
    op.create_index('idx_sa_status', 'edge_service_accounts', ['status'])

    # OpenClaw Gateway
    op.create_table(
        'edge_openclaw_config',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=True, unique=True),
        sa.Column('provider', sa.String(50), nullable=False, server_default='vllm'),
        sa.Column('model', sa.String(100), nullable=False, server_default='qwen3-8b'),
        sa.Column('api_base', sa.String(500), nullable=True, server_default='http://localhost:8001/v1'),
        sa.Column('api_key_masked', sa.String(50), nullable=True),
        sa.Column('max_tokens', sa.Integer(), nullable=False, server_default='4096'),
        sa.Column('temperature', sa.Float(), nullable=False, server_default='0.1'),
        sa.Column('gateway_port', sa.Integer(), nullable=False, server_default='3100'),
        sa.Column('gateway_binding', sa.String(100), nullable=False, server_default='127.0.0.1'),
        sa.Column('workspace_path', sa.String(500), nullable=True, server_default='/opt/openclaw/workspace'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'edge_openclaw_channels',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('channel_id', sa.String(50), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('channel_type', sa.String(50), nullable=False),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='disconnected'),
        sa.Column('configured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('warning', sa.Text(), nullable=True),
        sa.Column('last_tested_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'edge_openclaw_skills',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('skill_id', sa.String(50), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'edge_openclaw_sessions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('session_id', sa.String(64), nullable=False, index=True),
        sa.Column('channel', sa.String(50), nullable=False),
        sa.Column('user_identifier', sa.String(200), nullable=True),
        sa.Column('skill_used', sa.String(50), nullable=True),
        sa.Column('query_text', sa.Text(), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('signal_captured', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('signal_id', sa.String(64), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_session_channel', 'edge_openclaw_sessions', ['channel'])
    op.create_index('idx_session_created', 'edge_openclaw_sessions', ['created_at'])

    # Signal Ingestion
    op.create_table(
        'edge_ingested_signals',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('signal_id', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=True),
        sa.Column('channel', sa.String(50), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('signal_type', sa.String(50), nullable=False),
        sa.Column('direction', sa.String(20), nullable=True),
        sa.Column('product_id', sa.String(100), nullable=True),
        sa.Column('site_id', sa.String(100), nullable=True),
        sa.Column('base_confidence', sa.Float(), nullable=True),
        sa.Column('source_reliability', sa.Float(), nullable=True),
        sa.Column('time_decay', sa.Float(), nullable=True, server_default='1.0'),
        sa.Column('final_confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('magnitude_hint', sa.Float(), nullable=True),
        sa.Column('magnitude_applied', sa.Float(), nullable=True),
        sa.Column('reviewed_by', sa.String(100), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('review_reason', sa.Text(), nullable=True),
        sa.Column('adjustment_id', sa.Integer(), nullable=True),
        sa.Column('correlation_group_id', sa.String(64), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_signal_status', 'edge_ingested_signals', ['status'])
    op.create_index('idx_signal_source', 'edge_ingested_signals', ['source'])
    op.create_index('idx_signal_type', 'edge_ingested_signals', ['signal_type'])
    op.create_index('idx_signal_product_site', 'edge_ingested_signals', ['product_id', 'site_id'])
    op.create_index('idx_signal_created', 'edge_ingested_signals', ['created_at'])

    op.create_table(
        'edge_signal_correlations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('correlation_id', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('product_id', sa.String(100), nullable=True),
        sa.Column('site_id', sa.String(100), nullable=True),
        sa.Column('direction', sa.String(20), nullable=True),
        sa.Column('signal_ids', sa.JSON(), nullable=False),
        sa.Column('signal_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('combined_confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_corr_product_site', 'edge_signal_correlations', ['product_id', 'site_id'])

    op.create_table(
        'edge_source_reliability',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(50), nullable=False, unique=True, index=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=True),
        sa.Column('default_weight', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('learned_weight', sa.Float(), nullable=True),
        sa.Column('manual_weight', sa.Float(), nullable=True),
        sa.Column('signals_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('signals_correct', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('accuracy', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Security & Audit
    op.create_table(
        'edge_security_checklist',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('item_id', sa.String(50), nullable=False, unique=True, index=True),
        sa.Column('section', sa.String(100), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('checked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('checked_by', sa.String(100), nullable=True),
        sa.Column('checked_at', sa.DateTime(), nullable=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=True),
    )

    op.create_table(
        'edge_activity_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('component', sa.String(50), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('site_key', sa.String(100), nullable=True),
        sa.Column('severity', sa.String(20), nullable=False, server_default='info'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_activity_component', 'edge_activity_log', ['component'])
    op.create_index('idx_activity_created', 'edge_activity_log', ['created_at'])


def downgrade():
    op.drop_table('edge_activity_log')
    op.drop_table('edge_security_checklist')
    op.drop_table('edge_source_reliability')
    op.drop_table('edge_signal_correlations')
    op.drop_table('edge_ingested_signals')
    op.drop_table('edge_openclaw_sessions')
    op.drop_table('edge_openclaw_skills')
    op.drop_table('edge_openclaw_channels')
    op.drop_table('edge_openclaw_config')
    op.drop_table('edge_service_accounts')
    op.drop_table('edge_picoclaw_alerts')
    op.drop_table('edge_picoclaw_heartbeats')
    op.drop_table('edge_picoclaw_instances')
