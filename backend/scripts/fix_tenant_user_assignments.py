#!/usr/bin/env python3
"""Fix tenant/user/config assignments.

1. Create TBG_admin as tenant admin for Tenant 1 (The Beer Game learning tenant)
2. Detach systemadmin from tenant ownership (set tenant_id=NULL, default_config_id=NULL)
3. Ensure each production tenant has its own admin user
4. Verify decision stream scoping per tenant

Run inside Docker: docker compose exec backend python scripts/fix_tenant_user_assignments.py
"""

import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select, update, text
from sqlalchemy.orm import Session

from app.db.base_class import SessionLocal
from app.models.user import User, UserTypeEnum
from app.models.tenant import Tenant, TenantMode
from app.models.supply_chain_config import SupplyChainConfig
from app.core.security import get_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_PASSWORD = os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2026")


def run(db: Session):
    # ── 1. Inventory current state ──────────────────────────────────────
    tenants = db.query(Tenant).order_by(Tenant.id).all()
    users = db.query(User).order_by(User.id).all()
    configs = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.is_active == True
    ).order_by(SupplyChainConfig.id).all()

    logger.info("=== Current State ===")
    for t in tenants:
        mode = getattr(t, "mode", "unknown")
        logger.info(f"  Tenant {t.id}: {t.name!r} (mode={mode})")

    for u in users:
        logger.info(f"  User {u.id}: {u.email} type={u.user_type} tenant={u.tenant_id} default_config={u.default_config_id}")

    for c in configs:
        logger.info(f"  Config {c.id}: {c.name!r} tenant={c.tenant_id} active={c.is_active}")

    # ── 2. Create TBG_admin for Tenant 1 ────────────────────────────────
    tenant_1 = db.query(Tenant).filter(Tenant.id == 1).first()
    if not tenant_1:
        logger.error("Tenant 1 not found!")
        return

    tbg_admin = db.query(User).filter(User.email == "tbg_admin@autonomy.com").first()
    if not tbg_admin:
        tbg_admin = User(
            username="tbg_admin",
            email="tbg_admin@autonomy.com",
            full_name="TBG Learning Admin",
            hashed_password=get_password_hash(DEFAULT_PASSWORD),
            is_superuser=False,
            is_active=True,
            user_type=UserTypeEnum.TENANT_ADMIN,
            tenant_id=tenant_1.id,
        )
        db.add(tbg_admin)
        db.flush()
        logger.info(f"Created TBG_admin (id={tbg_admin.id}) for Tenant 1")
    else:
        tbg_admin.tenant_id = tenant_1.id
        tbg_admin.user_type = UserTypeEnum.TENANT_ADMIN
        logger.info(f"TBG_admin already exists (id={tbg_admin.id}), ensured assignment to Tenant 1")

    # Set TBG_admin's default config to the Default TBG config
    tbg_config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.tenant_id == tenant_1.id,
        SupplyChainConfig.is_active == True,
    ).first()
    if tbg_config:
        tbg_admin.default_config_id = tbg_config.id
        logger.info(f"Set TBG_admin default_config_id={tbg_config.id} ({tbg_config.name!r})")

    # ── 3. Detach systemadmin from tenant ownership ─────────────────────
    sysadmin = db.query(User).filter(
        User.user_type == UserTypeEnum.SYSTEM_ADMIN
    ).first()
    if sysadmin:
        old_tenant = sysadmin.tenant_id
        old_config = sysadmin.default_config_id
        sysadmin.tenant_id = None
        sysadmin.default_config_id = None
        logger.info(
            f"Detached systemadmin (id={sysadmin.id}) from tenant "
            f"(was tenant_id={old_tenant}, default_config={old_config}) → NULL/NULL"
        )
    else:
        logger.warning("No SYSTEM_ADMIN user found!")

    # ── 4. Verify production tenant admins exist ────────────────────────
    for t in tenants:
        if t.id == 1:
            continue  # TBG handled above
        admin = db.query(User).filter(
            User.tenant_id == t.id,
            User.user_type == UserTypeEnum.TENANT_ADMIN,
        ).first()
        if admin:
            logger.info(f"Tenant {t.id} ({t.name!r}) has admin: {admin.email}")
        else:
            logger.warning(f"Tenant {t.id} ({t.name!r}) has NO tenant admin!")

    # ── 5. Summary ──────────────────────────────────────────────────────
    db.commit()
    logger.info("=== Done ===")
    logger.info("systemadmin@autonomy.com is now tenant-agnostic (tenant_id=NULL)")
    logger.info("tbg_admin@autonomy.com owns Tenant 1 (The Beer Game)")
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Update frontend config resolution for SYSTEM_ADMIN with NULL tenant_id")
    logger.info("  2. Run provisioning for each production config")
    logger.info("  3. Add Default TBG learning configs to production tenants")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        run(db)
    finally:
        db.close()
