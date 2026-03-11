import logging
import re

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from ..models import (
    Tenant,
    User,
    SupplyChainConfig,
    Scenario as Game,
    ScenarioStatus as GameStatus,
    ScenarioUser as ScenarioUser,
    ScenarioUserRole as ScenarioUserRole,
    ScenarioUserType as ScenarioUserType,
    ScenarioUserStrategy as ScenarioUserStrategy,
)
from ..models.user import UserTypeEnum
from ..models.tenant import TenantMode
from ..models.supply_chain_config import (
    Node,
    TransportationLane,
    Market,
    MarketDemand,
    NodeType,
)
from ..models.sc_entities import Product, ProductBom
from ..models.autonomy_customer import AutonomyCustomer
from ..schemas.tenant import TenantCreate, TenantUpdate
from ..core.security import get_password_hash
from app.core.time_buckets import TimeBucket
from .supply_chain_config_service import SupplyChainConfigService
from .bootstrap import DEFAULT_ADMIN_PASSWORD
# Product imported from sc_entities (line 26)

logger = logging.getLogger(__name__)

DEFAULT_SITE_TYPE_DEFINITIONS = [
    {
        "type": "factory",
        "label": "Factory",
        "order": 4,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "distributor",
        "label": "Distributor",
        "order": 3,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "wholesaler",
        "label": "Wholesaler",
        "order": 2,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "retailer",
        "label": "Retailer",
        "order": 1,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "market_supply",
        "label": "Market Supply",
        "order": 5,
        "is_required": True,
        "master_type": "market_supply",
    },
    {
        "type": "market_demand",
        "label": "Market Demand",
        "order": 0,
        "is_required": True,
        "master_type": "market_demand",
    },
]


class TenantService:
    """Service for managing Autonomy tenants (organization isolation boundary)."""

    def __init__(self, db: Session):
        self.db = db

    def get_tenants(self):
        """Return all tenants."""
        return self.db.query(Tenant).all()

    def get_tenant(self, tenant_id: int) -> Tenant:
        """Return a single tenant by ID, or raise 404."""
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return tenant

    def _generate_unique_slug(self, name: str) -> str:
        """Generate a URL-safe unique slug from a tenant name."""
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        base_slug = slug
        counter = 1
        while self.db.query(Tenant).filter(Tenant.slug == slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug

    @staticmethod
    def _derive_learning_email(email: str) -> str:
        """Derive learning tenant admin email from production admin email.

        Example: admin@company.com -> admin_learn@company.com
        """
        local, domain = email.rsplit("@", 1)
        return f"{local}_learn@{domain}"

    @staticmethod
    def _derive_learning_username(username: str) -> str:
        """Derive learning tenant admin username from production admin username."""
        return f"{username}_learn"

    def create_tenant(self, tenant_in: TenantCreate) -> Tenant:
        """Create a paired Production + Learning organization.

        Every organization gets two tenants:
        - Production tenant (mode=production): Real supply chain data and planning
        - Learning tenant (mode=learning): Training, simulation, agent validation

        Each tenant gets its own admin user. The learning admin email is derived
        from the production admin email: user@domain.com -> user_learn@domain.com
        """
        admin_data = tenant_in.admin
        hashed_password = get_password_hash(admin_data.password)
        try:
            # ── Production tenant + admin ──────────────────────────────
            prod_admin = User(
                username=admin_data.username,
                email=admin_data.email,
                full_name=admin_data.full_name,
                hashed_password=hashed_password,
                user_type=UserTypeEnum.TENANT_ADMIN,
                is_active=True,
                is_superuser=False,
            )
            self.db.add(prod_admin)
            self.db.flush()

            prod_slug = self._generate_unique_slug(tenant_in.name)
            prod_tenant = Tenant(
                name=tenant_in.name,
                slug=prod_slug,
                subdomain=prod_slug[:50],
                description=tenant_in.description,
                logo=tenant_in.logo,
                admin_id=prod_admin.id,
                mode=TenantMode.PRODUCTION,
            )
            self.db.add(prod_tenant)
            self.db.flush()

            prod_admin.tenant_id = prod_tenant.id
            self.db.add(prod_admin)

            prod_sc_config = SupplyChainConfig(
                name="Default Supply Chain",
                description="Default supply chain configuration",
                created_by=prod_admin.id,
                tenant_id=prod_tenant.id,
                is_active=True,
                time_bucket=TimeBucket.WEEK,
                site_type_definitions=DEFAULT_SITE_TYPE_DEFINITIONS,
            )
            self.db.add(prod_sc_config)
            self.db.flush()

            # ── Learning tenant + admin ────────────────────────────────
            learn_email = self._derive_learning_email(admin_data.email)
            learn_username = self._derive_learning_username(admin_data.username)

            learn_admin = User(
                username=learn_username,
                email=learn_email,
                full_name=f"{admin_data.full_name} (Learning)",
                hashed_password=hashed_password,  # same password
                user_type=UserTypeEnum.TENANT_ADMIN,
                is_active=True,
                is_superuser=False,
            )
            self.db.add(learn_admin)
            self.db.flush()

            learn_name = f"{tenant_in.name} (Learning)"
            learn_slug = self._generate_unique_slug(learn_name)
            learn_tenant = Tenant(
                name=learn_name,
                slug=learn_slug,
                subdomain=learn_slug[:50],
                description=f"Learning tenant for {tenant_in.name}",
                logo=tenant_in.logo,
                admin_id=learn_admin.id,
                mode=TenantMode.LEARNING,
            )
            self.db.add(learn_tenant)
            self.db.flush()

            learn_admin.tenant_id = learn_tenant.id
            self.db.add(learn_admin)

            learn_sc_config = SupplyChainConfig(
                name="Default Learning Config",
                description="Default learning supply chain configuration",
                created_by=learn_admin.id,
                tenant_id=learn_tenant.id,
                is_active=True,
                time_bucket=TimeBucket.WEEK,
                site_type_definitions=DEFAULT_SITE_TYPE_DEFINITIONS,
            )
            self.db.add(learn_sc_config)
            self.db.flush()

            # Register in autonomy_customers registry
            customer = AutonomyCustomer(
                name=tenant_in.name,
                description=tenant_in.description,
                production_tenant_id=prod_tenant.id,
                production_admin_id=prod_admin.id,
                learning_tenant_id=learn_tenant.id,
                learning_admin_id=learn_admin.id,
                has_learning_tenant=True,
            )
            self.db.add(customer)
            self.db.flush()

            self.db.commit()
            self.db.refresh(prod_tenant)
            return prod_tenant
        except Exception:
            self.db.rollback()
            logger.exception("Failed to create tenant %s", tenant_in.name)
            raise HTTPException(status_code=500, detail="Error creating tenant")

    def update_tenant(self, tenant_id: int, tenant_update: TenantUpdate) -> Tenant:
        """Update an existing tenant."""
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        update_data = tenant_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tenant, field, value)

        # Sync name changes to autonomy_customers registry
        if "name" in update_data:
            customer = (
                self.db.query(AutonomyCustomer)
                .filter(
                    (AutonomyCustomer.production_tenant_id == tenant_id)
                    | (AutonomyCustomer.learning_tenant_id == tenant_id)
                )
                .first()
            )
            if customer and customer.production_tenant_id == tenant_id:
                customer.name = update_data["name"]
                if "description" in update_data:
                    customer.description = update_data["description"]

        self.db.commit()
        self.db.refresh(tenant)
        return tenant

    def delete_tenant(self, tenant_id: int):
        """Delete a tenant and all associated data.

        Uses explicit SQL with savepoints to avoid ORM cascade issues with
        models whose tables may not exist (e.g. templates, tutorial_progress).
        """
        from sqlalchemy import text

        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        # Get user IDs belonging to this tenant
        user_ids = [u.id for u in self.db.query(User.id).filter(User.tenant_id == tenant_id).all()]

        def _safe_execute(sql_str, params=None):
            """Execute SQL inside a savepoint so failures don't abort the transaction."""
            savepoint = self.db.begin_nested()
            try:
                self.db.execute(text(sql_str), params or {})
                savepoint.commit()
            except Exception:
                savepoint.rollback()

        # Delete user-FK dependent rows
        user_fk_tables = [
            "scenario_user_periods", "scenario_user_actions", "scenario_user_achievements",
            "scenario_user_badges", "scenario_user_stats", "scenario_user_inventory",
            "scenario_users", "user_sessions", "refresh_tokens", "token_blacklist",
            "password_reset_tokens", "password_history", "push_tokens",
            "notification_preferences", "notification_logs",
            "user_role_assignments", "user_roles", "user_sso_mappings",
            "audit_logs", "chat_messages", "comments", "comment_mentions",
            "decision_comments", "decision_history", "planning_decisions",
            "agent_suggestions", "supervisor_actions",
            "leaderboard_entries", "achievement_notifications",
            "team_channel_members", "team_messages",
            "override_effectiveness_posteriors", "override_causal_match_pairs",
            "approval_actions", "approval_requests",
            "forecast_adjustments", "consensus_plan_votes", "consensus_plan_comments",
            "briefing_followups", "executive_briefings", "briefing_schedules",
            "watchlists", "sop_worklist_items",
        ]
        if user_ids:
            id_list = ",".join(str(uid) for uid in user_ids)
            for tbl in user_fk_tables:
                _safe_execute(f"DELETE FROM {tbl} WHERE user_id IN ({id_list})")
            # Nullify created_by FKs that reference these users
            created_by_tables = [
                "forecast_versions", "supply_plan", "mps_plans",
                "supply_chain_configs", "scenarios", "agent_configs",
                "approval_templates", "consensus_plans",
            ]
            for tbl in created_by_tables:
                _safe_execute(f"UPDATE {tbl} SET created_by = NULL WHERE created_by IN ({id_list})")

        # Break the circular tenant.admin_id → users FK before deleting users
        _safe_execute(
            "UPDATE tenants SET admin_id = NULL WHERE id = :tid",
            {"tid": tenant_id}
        )

        # Delete tenant-scoped data (order matters: children before parents)
        tenant_fk_tables = [
            # Planning & workflow
            "planning_cycles", "workflow_step_executions", "workflow_executions",
            "workflow_templates", "sync_table_results", "sync_job_executions",
            "sync_job_configs", "sap_connections",
            "planning_feedback_signal", "planning_policy_envelope",
            "condition_alerts", "guardrail_directives",
            "decision_governance_policies", "authority_definitions",
            # Supply chain config children (sites, lanes, products, markets)
            "markets", "market_demands", "transportation_lane", "product_bom",
            "product", "site", "supply_chain_configs",
        ]
        for tbl in tenant_fk_tables:
            _safe_execute(f"DELETE FROM {tbl} WHERE tenant_id = :tid", {"tid": tenant_id})

        # Delete scenarios and their children
        _safe_execute(
            "DELETE FROM scenarios WHERE tenant_id = :tid",
            {"tid": tenant_id}
        )

        # Deactivate autonomy_customers records that reference this tenant
        # (before user/tenant deletion to avoid dangling FK references)
        _safe_execute(
            "UPDATE autonomy_customers SET is_active = false, "
            "production_tenant_id = CASE WHEN production_tenant_id = :tid THEN NULL ELSE production_tenant_id END, "
            "production_admin_id = CASE WHEN production_tenant_id = :tid THEN NULL ELSE production_admin_id END, "
            "learning_tenant_id = CASE WHEN learning_tenant_id = :tid THEN NULL ELSE learning_tenant_id END, "
            "learning_admin_id = CASE WHEN learning_tenant_id = :tid THEN NULL ELSE learning_admin_id END "
            "WHERE production_tenant_id = :tid OR learning_tenant_id = :tid",
            {"tid": tenant_id}
        )

        # Delete users (backrefs to non-existent tables removed in template.py)
        self.db.query(User).filter(User.tenant_id == tenant_id).delete(synchronize_session=False)

        # Delete the tenant
        self.db.query(Tenant).filter(Tenant.id == tenant_id).delete(synchronize_session=False)
        self.db.commit()
        return {"message": "Tenant deleted"}


# Backward compatibility aliases
CustomerService = TenantService
