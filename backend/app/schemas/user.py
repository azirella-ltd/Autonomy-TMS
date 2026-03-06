from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, validator

try:  # pragma: no cover - optional dependency shim for email validation
    from email_validator import validate_email  # type: ignore
except ImportError:  # pragma: no cover
    validate_email = None  # type: ignore

if validate_email is not None:
    from pydantic import EmailStr  # type: ignore
else:
    class EmailStr(str):  # type: ignore
        @classmethod
        def __get_validators__(cls):
            yield cls.validate

        @classmethod
        def validate(cls, value):
            if not isinstance(value, str):
                raise TypeError("string required")
            return value
from app.models.user import UserTypeEnum

class UserBase(BaseModel):
    """Base user schema with common fields."""
    # username is optional for backwards compat with existing users that have null username
    username: Optional[str] = Field(None, min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=100)
    tenant_id: Optional[int] = None
    user_type: UserTypeEnum = Field(default=UserTypeEnum.USER)

class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(..., min_length=8, max_length=50)
    is_superuser: Optional[bool] = False
    user_type: Optional[UserTypeEnum] = None

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v

    @validator('user_type', pre=True)
    def normalize_user_type(cls, value):
        if value is None or isinstance(value, UserTypeEnum):
            return value
        token = ''.join(ch for ch in str(value).strip().lower() if ch.isalnum())
        mapping = {
            'systemadmin': UserTypeEnum.SYSTEM_ADMIN,
            'superadmin': UserTypeEnum.SYSTEM_ADMIN,
            'systemadministrator': UserTypeEnum.SYSTEM_ADMIN,
            'tenantadmin': UserTypeEnum.TENANT_ADMIN,
            'tenantadministrator': UserTypeEnum.TENANT_ADMIN,
            'admin': UserTypeEnum.TENANT_ADMIN,
            'player': UserTypeEnum.USER,
            'user': UserTypeEnum.USER,
        }
        if token in mapping:
            return mapping[token]
        raise ValueError('Invalid user type')

class UserUpdate(BaseModel):
    """Schema for updating user information."""
    username: Optional[str] = Field(None, min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=100)
    password: Optional[str] = Field(None, min_length=8, max_length=50)
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    tenant_id: Optional[int] = None
    user_type: Optional[UserTypeEnum] = None

    @validator('user_type', pre=True)
    def normalize_user_type(cls, value):
        if value is None or isinstance(value, UserTypeEnum):
            return value
        token = ''.join(ch for ch in str(value).strip().lower() if ch.isalnum())
        mapping = {
            'systemadmin': UserTypeEnum.SYSTEM_ADMIN,
            'superadmin': UserTypeEnum.SYSTEM_ADMIN,
            'systemadministrator': UserTypeEnum.SYSTEM_ADMIN,
            'tenantadmin': UserTypeEnum.TENANT_ADMIN,
            'tenantadministrator': UserTypeEnum.TENANT_ADMIN,
            'admin': UserTypeEnum.TENANT_ADMIN,
            'player': UserTypeEnum.USER,
            'user': UserTypeEnum.USER,
        }
        if token in mapping:
            return mapping[token]
        raise ValueError('Invalid user type')

class UserInDBBase(UserBase):
    """Base schema for user data in the database."""
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

class User(UserInDBBase):
    """Schema for returning user data (without sensitive information)."""
    pass

class UserInDB(UserInDBBase):
    """Schema for user data stored in the database (includes hashed password)."""
    hashed_password: str

class Token(BaseModel):
    """Schema for authentication tokens."""
    access_token: str
    refresh_token: str
    token_type: str

class TokenData(BaseModel):
    """Schema for token payload data."""
    username: Optional[str] = None

class UserWithGames(User):
    """Schema for user data including their games."""
    games: List[dict] = []

class UserPasswordChange(BaseModel):
    """Schema for changing a user's password."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=50)
    
    @validator('new_password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v


class PasswordResetRequest(BaseModel):
    """Schema for requesting a password reset."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schema for confirming a password reset."""
    token: str
    new_password: str = Field(..., min_length=8, max_length=50)
    
    @validator('new_password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v


class MFASetupResponse(BaseModel):
    """Response schema for MFA setup."""
    secret: str
    qr_code_uri: str
    recovery_codes: List[str]


class MFAVerifyRequest(BaseModel):
    """Request schema for MFA verification."""
    code: str


class MFARecoveryCodes(BaseModel):
    """Schema for MFA recovery codes."""
    recovery_codes: List[str]
