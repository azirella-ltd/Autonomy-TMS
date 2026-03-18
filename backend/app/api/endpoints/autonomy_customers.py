"""
Autonomy Customer Registry API

System admin endpoint for managing platform customers, their tenants, and admins.
Only accessible by SYSTEM_ADMIN users.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.user import User


async def require_system_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure user is a system admin (superuser or SYSTEM_ADMIN type)."""
    if current_user.user_type != "SYSTEM_ADMIN" and not getattr(current_user, "is_superuser", False):
        raise HTTPException(
            status_code=403,
            detail="Requires system admin privileges",
        )
    return current_user

logger = logging.getLogger(__name__)

router = APIRouter()


class CustomerResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    contract_notes: Optional[str] = None
    production_tenant_id: Optional[int] = None
    production_tenant_name: Optional[str] = None
    production_admin_id: Optional[int] = None
    production_admin_email: Optional[str] = None
    learning_tenant_id: Optional[int] = None
    learning_tenant_name: Optional[str] = None
    learning_admin_id: Optional[int] = None
    learning_admin_email: Optional[str] = None
    has_learning_tenant: bool = False
    is_active: bool = True


class CustomerUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    contract_notes: Optional[str] = None


_CUSTOMER_SELECT = """
    SELECT c.id, c.name, c.description,
           c.contact_name, c.contact_email, c.contact_phone,
           c.industry, c.website,
           c.contract_start_date::text, c.contract_end_date::text,
           c.contract_notes,
           c.production_tenant_id, pt.name as production_tenant_name,
           c.production_admin_id, pu.email as production_admin_email,
           c.learning_tenant_id, lt.name as learning_tenant_name,
           c.learning_admin_id, lu.email as learning_admin_email,
           c.has_learning_tenant, c.is_active
    FROM autonomy_customers c
    LEFT JOIN tenants pt ON pt.id = c.production_tenant_id
    LEFT JOIN tenants lt ON lt.id = c.learning_tenant_id
    LEFT JOIN users pu ON pu.id = c.production_admin_id
    LEFT JOIN users lu ON lu.id = c.learning_admin_id
"""


@router.get("", response_model=List[CustomerResponse], tags=["customers"])
async def list_customers(
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all Autonomy platform customers with their tenants and admins."""
    result = await db.execute(text(f"{_CUSTOMER_SELECT} ORDER BY c.name"))
    rows = result.mappings().all()
    return [CustomerResponse(**dict(r)) for r in rows]


@router.get("/{customer_id}", response_model=CustomerResponse, tags=["customers"])
async def get_customer(
    customer_id: int,
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific customer."""
    result = await db.execute(
        text(f"{_CUSTOMER_SELECT} WHERE c.id = :cid"),
        {"cid": customer_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerResponse(**dict(row))


@router.delete("/{customer_id}", tags=["customers"])
async def delete_customer(
    customer_id: int,
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a customer and all its linked tenants.

    Deletes linked production and learning tenants first (via TenantService),
    then removes the autonomy_customers record.
    """
    result = await db.execute(
        text("SELECT id, name, production_tenant_id, learning_tenant_id FROM autonomy_customers WHERE id = :cid"),
        {"cid": customer_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")

    from app.db.session import sync_session_factory
    from app.services.tenant_service import TenantService

    tenant_ids = [
        tid for tid in (row["production_tenant_id"], row["learning_tenant_id"])
        if tid is not None
    ]

    deleted_tenants = []
    for tid in tenant_ids:
        try:
            sync_db = sync_session_factory()
            try:
                svc = TenantService(sync_db)
                svc.delete_tenant(tid)
                deleted_tenants.append(tid)
            finally:
                sync_db.close()
        except Exception as e:
            logger.warning("Failed to delete tenant %d for customer %d: %s", tid, customer_id, e)

    await db.execute(text("DELETE FROM autonomy_customers WHERE id = :cid"), {"cid": customer_id})
    await db.commit()
    return {"success": True, "deleted_id": customer_id, "deleted_tenants": deleted_tenants}


@router.put("/{customer_id}", response_model=CustomerResponse, tags=["customers"])
async def update_customer(
    customer_id: int,
    body: CustomerUpdateRequest,
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update customer contact and contract details."""
    updates = body.dict(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    params = {"cid": customer_id}
    for field, value in updates.items():
        set_clauses.append(f"{field} = :{field}")
        params[field] = value

    set_clauses.append("updated_at = now()")
    sql = f"UPDATE autonomy_customers SET {', '.join(set_clauses)} WHERE id = :cid"
    await db.execute(text(sql), params)
    await db.commit()

    # Return updated record
    result = await db.execute(
        text(f"{_CUSTOMER_SELECT} WHERE c.id = :cid"),
        {"cid": customer_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerResponse(**dict(row))
