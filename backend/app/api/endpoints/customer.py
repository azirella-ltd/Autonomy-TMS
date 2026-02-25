from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...models import User
from ...models.user import UserTypeEnum
from ...schemas.customer import Customer as CustomerSchema, CustomerCreate, CustomerUpdate, CustomerSummary
from ...services.customer_service import CustomerService
from ...services.rbac_service import RBACService
from ...core.security import get_current_active_user

router = APIRouter()

def get_customer_service(db: Session = Depends(get_db)) -> CustomerService:
    return CustomerService(db)

@router.get("/my", response_model=Optional[CustomerSummary])
async def get_my_customer(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the current user's customer with mode information.

    Returns None if the user is not assigned to a customer.
    This endpoint is used by the frontend to determine navigation mode.
    """
    from ...models.customer import Customer

    if not current_user.customer_id:
        return None

    stmt = select(Customer).filter(Customer.id == current_user.customer_id)
    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()

    return customer


@router.get("/", response_model=List[CustomerSchema])
async def list_customers(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    from ...models.customer import Customer

    user_type = getattr(current_user, "user_type", None)
    if isinstance(user_type, str):
        try:
            user_type = UserTypeEnum(user_type)
        except ValueError:
            user_type = None

    # Only SYSTEM_ADMIN sees all customers; GROUP_ADMIN sees only their customer
    if user_type == UserTypeEnum.SYSTEM_ADMIN:
        stmt = select(Customer).options(joinedload(Customer.admin))
        result = await db.execute(stmt)
        return result.scalars().unique().all()

    is_customer_admin = user_type == UserTypeEnum.GROUP_ADMIN

    if is_customer_admin and current_user.customer_id:
        stmt = select(Customer).options(joinedload(Customer.admin)).filter(Customer.id == current_user.customer_id)
        result = await db.execute(stmt)
        customer = result.scalar_one_or_none()
        if customer:
            return [customer]
        raise HTTPException(status_code=404, detail="Customer not found")

    # Regular users can see their own customer if assigned
    if current_user.customer_id:
        stmt = select(Customer).options(joinedload(Customer.admin)).filter(Customer.id == current_user.customer_id)
        result = await db.execute(stmt)
        customer = result.scalar_one_or_none()
        if customer:
            return [customer]

    raise HTTPException(status_code=403, detail="Not enough permissions")

@router.post("/", response_model=CustomerSchema, status_code=status.HTTP_201_CREATED)
def create_customer(customer_in: CustomerCreate, customer_service: CustomerService = Depends(get_customer_service), current_user: User = Depends(get_current_active_user)):
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return customer_service.create_customer(customer_in)

@router.put("/{customer_id}", response_model=CustomerSchema)
def update_customer(customer_id: int, customer_update: CustomerUpdate, customer_service: CustomerService = Depends(get_customer_service), current_user: User = Depends(get_current_active_user)):
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return customer_service.update_customer(customer_id, customer_update)

@router.delete("/{customer_id}", response_model=dict)
def delete_customer(customer_id: int, customer_service: CustomerService = Depends(get_customer_service), current_user: User = Depends(get_current_active_user)):
    if current_user.user_type != UserTypeEnum.SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return customer_service.delete_customer(customer_id)

@router.get("/{customer_id}/users")
async def get_customer_users(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all users in a specific customer.

    Customer admins can only view their own customer's users.
    System admins can view any customer's users.
    """
    user_type = getattr(current_user, "user_type", None)
    if isinstance(user_type, str):
        try:
            user_type = UserTypeEnum(user_type)
        except ValueError:
            user_type = None

    # Check permissions
    is_system_admin = user_type == UserTypeEnum.SYSTEM_ADMIN
    is_customer_admin = user_type == UserTypeEnum.GROUP_ADMIN

    if not is_system_admin and not is_customer_admin:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Customer admins can only view their own customer
    if is_customer_admin and current_user.customer_id != customer_id:
        raise HTTPException(status_code=403, detail="You can only view users in your own customer")

    # Query users in the customer
    stmt = select(User).filter(User.customer_id == customer_id)
    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "user_type": user.user_type.value if hasattr(user.user_type, 'value') else user.user_type,
            "is_active": user.is_active,
            "customer_id": user.customer_id,
        }
        for user in users
    ]
