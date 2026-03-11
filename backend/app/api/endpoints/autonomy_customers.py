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

from app.api.deps import get_current_user, get_current_active_user, require_tenant_admin
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


class CustomerCreateRequest(BaseModel):
    name: str = Field(..., description="Customer name")
    description: Optional[str] = None


@router.get("", response_model=List[CustomerResponse], tags=["customers"])
async def list_customers(
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all Autonomy platform customers with their tenants and admins."""
    result = await db.execute(text("""
        SELECT c.id, c.name, c.description,
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
        ORDER BY c.id
    """))
    rows = result.mappings().all()
    return [CustomerResponse(**dict(r)) for r in rows]


@router.get("/{customer_id}", response_model=CustomerResponse, tags=["customers"])
async def get_customer(
    customer_id: int,
    current_user: User = Depends(require_system_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific customer."""
    result = await db.execute(text("""
        SELECT c.id, c.name, c.description,
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
        WHERE c.id = :cid
    """), {"cid": customer_id})
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerResponse(**dict(row))
