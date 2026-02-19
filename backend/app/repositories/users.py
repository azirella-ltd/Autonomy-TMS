from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from app.models.user import User, UserTypeEnum

async def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Get a user by email.
    
    Args:
        db: Database session
        email: User's email address
        
    Returns:
        User or None: The user if found, else None
    """
    result = await db.execute(select(User).filter(User.email == email))
    return result.scalars().first()

async def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """
    Get a user by ID.
    
    Args:
        db: Database session
        user_id: User's ID
        
    Returns:
        User or None: The user if found, else None
    """
    result = await db.execute(select(User).filter(User.id == user_id))
    return result.scalars().first()

async def create_user(
    db: Session,
    email: str,
    hashed_password: str,
    name: Optional[str] = None,
    user_type: Optional[UserTypeEnum] = None,
) -> User:
    """
    Create a new user.
    
    Args:
        db: Database session
        email: User's email address
        hashed_password: Hashed password
        name: User's name (optional)
        user_type: Enumerated user type (optional)
        
    Returns:
        User: The created user
    """
    normalized_type = user_type or UserTypeEnum.USER
    user = User(
        email=email,
        hashed_password=hashed_password,
        full_name=name,
        user_type=normalized_type,
        is_superuser=normalized_type == UserTypeEnum.SYSTEM_ADMIN,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def update_user(
    db: Session, 
    user: User, 
    **kwargs
) -> User:
    """
    Update a user's attributes.
    
    Args:
        db: Database session
        user: The user to update
        **kwargs: Attributes to update
        
    Returns:
        User: The updated user
    """
    for key, value in kwargs.items():
        if hasattr(user, key):
            setattr(user, key, value)
    
    await db.commit()
    await db.refresh(user)
    return user

async def delete_user(db: Session, user: User) -> bool:
    """
    Delete a user.
    
    Args:
        db: Database session
        user: The user to delete
        
    Returns:
        bool: True if the user was deleted, False otherwise
    """
    await db.delete(user)
    await db.commit()
    return True
