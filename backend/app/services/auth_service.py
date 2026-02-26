import secrets
import os
import pyotp
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy import select, or_
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.config import settings
from app.models.user import User, RefreshToken, UserTypeEnum
from app.models.auth_models import PasswordHistory, PasswordResetToken
from app.schemas.user import (
    UserCreate, 
    UserInDB, 
    Token, 
    TokenData, 
    PasswordResetRequest,
    PasswordResetConfirm,
    MFASetupResponse,
    MFAVerifyRequest
)
from app.core.security import get_password_hash, verify_password, oauth2_scheme, verify_password_strength, create_access_token, create_refresh_token
from app.db.deps import get_db
from app.core.config import settings
from app.repositories.users import get_user_by_id

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    """Service for handling authentication and user management."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_user(self, user_create: UserCreate) -> User:
        """Create a new user with hashed password and security features."""
        # Check if user already exists
        db_user = self.get_user_by_email(user_create.email)
        if db_user:
            raise ValueError("Email already registered")
            
        # Check password strength
        if not verify_password_strength(user_create.password):
            raise ValueError("Password does not meet complexity requirements")
            
        # Create new user
        hashed_password = get_password_hash(user_create.password)
        now = datetime.utcnow()
        db_user = User(
            username=user_create.username,
            email=user_create.email,
            hashed_password=hashed_password,
            full_name=user_create.full_name,
            is_active=True,
            last_password_change=now,
            failed_login_attempts=0,
            is_locked=False,
            mfa_enabled=False
        )
        
        # Add initial password to history
        self._add_to_password_history(db_user.id, hashed_password)
        
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user
    
    async def authenticate_user(
        self,
        username: str,
        password: str,
        mfa_code: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[User]:
        """Authenticate a user by username/email and password.

        This method only verifies credentials and MFA. Token creation is
        handled separately to keep concerns separated.

        Args:
            username: The username or email of the user
            password: The user's password
            mfa_code: Optional MFA code if MFA is enabled
            client_ip: Client IP address for audit logging (unused currently)
            user_agent: User agent string for audit logging (unused currently)

        Returns:
            The authenticated ``User`` instance or ``None`` if authentication fails.

        Raises:
            HTTPException: If authentication fails due to lockout or invalid MFA.
        """
        systemadmin_email = (
            os.getenv("SYSTEMADMIN_EMAIL")
            or os.getenv("SUPERADMIN_EMAIL")
            or "systemadmin@autonomy.ai"
        )

        # First, try to find the user by username or email
        stmt = select(User).where(
            or_(User.username == username, User.email == username)
        )
        result = await self.db.execute(stmt)
        user = result.scalars().first()
        
        if not user:
            # User not found - perform dummy hash to maintain timing consistency
            get_password_hash("dummy_password")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "user_not_found",
                    "message": (
                        "We couldn't find an account with that email. "
                        "Please contact your system administrator to request login credentials."
                    ),
                    "contact_role": "systemadmin",
                    "systemadmin_email": systemadmin_email,
                    "show_contact_form": True,
                },
            )

        user_type = getattr(user, "user_type", None)
        if isinstance(user_type, str):
            try:
                user_type = UserTypeEnum(user_type)
            except ValueError:
                user_type = None
        if user_type is None:
            user_type = UserTypeEnum.SYSTEM_ADMIN if user.is_superuser else UserTypeEnum.USER

        is_system_admin = bool(user.is_superuser or user_type == UserTypeEnum.SYSTEM_ADMIN)
        is_tenant_admin = user_type == UserTypeEnum.TENANT_ADMIN
        is_scenario_user = user_type == UserTypeEnum.USER

        # Check if the account is locked
        if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS and \
           user.last_failed_login and \
           (datetime.utcnow() - user.last_failed_login).total_seconds() < settings.LOGIN_LOCKOUT_MINUTES * 60:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account locked. Please try again in {settings.LOGIN_LOCKOUT_MINUTES} minutes or reset your password."
            )
            
        # Verify the password
        if not verify_password(password, user.hashed_password):
            # Update failed login attempts
            user.failed_login_attempts += 1
            user.last_failed_login = datetime.utcnow()
            await self.db.commit()

            if is_tenant_admin:
                message = (
                    "Incorrect password. Please contact your system administrator for assistance."
                )
                contact_role = "systemadmin"
            elif is_scenario_user:
                message = (
                    "Incorrect password. Please contact your tenant admin for assistance."
                )
                contact_role = "tenantadmin"
            elif is_system_admin:
                message = (
                    "Incorrect password. Please verify your credentials or reach out to a fellow system administrator for support."
                )
                contact_role = "systemadmin"
            else:
                message = (
                    "Incorrect password. Please contact your administrator for assistance."
                )
                contact_role = "administrator"

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "incorrect_password",
                    "message": message,
                    "contact_role": contact_role,
                    "systemadmin_email": systemadmin_email,
                },
            )
            
        # If we get here, the password is correct
        # Reset failed login attempts
        if user.failed_login_attempts > 0:
            user.failed_login_attempts = 0
            await self.db.commit()
            
        # If MFA is enabled, verify the MFA code
        if user.mfa_enabled:
            if not mfa_code:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="MFA code is required"
                )
                
            if not await self.verify_mfa_code(user, mfa_code):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid MFA code"
                )
        
        # Successful authentication returns the user object
        return user
        
    async def create_refresh_token_record(
        self,
        user_id: int,
        token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> RefreshToken:
        """Create a new refresh token record in the database."""
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        expires_at = datetime.utcnow() + expires_delta
        
        refresh_token = RefreshToken(
            token=token,
            user_id=user_id,
            expires_at=expires_at,
        )
        
        self.db.add(refresh_token)
        await self.db.commit()
        await self.db.refresh(refresh_token)
        
        return refresh_token
    
    async def create_refresh_token(self, user_id: int) -> str:
        """Create a new refresh token for the given user ID."""
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        return create_refresh_token(user_id, expires_delta=expires_delta)
        
    async def verify_mfa_code(self, user: User, code: str) -> bool:
        """Verify an MFA code for the given user."""
        if not user.mfa_secret:
            return False
            
        totp = pyotp.TOTP(user.mfa_secret)
        return totp.verify(code)
    
    async def create_tokens(
        self,
        user: User,
        mfa_verified: bool = False,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Token:
        """Create access and refresh tokens for a user."""

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        user_type_value: Optional[str] = None
        user_type = getattr(user, "user_type", None)
        if isinstance(user_type, UserTypeEnum):
            user_type_value = user_type.value
        elif isinstance(user_type, str):
            try:
                user_type_value = UserTypeEnum(user_type).value
            except ValueError:
                user_type_value = None
        if user_type_value is None and user.is_superuser:
            user_type_value = UserTypeEnum.SYSTEM_ADMIN.value

        subject_identifier = user.email or str(user.id)

        access_token = create_access_token(
            subject=subject_identifier,
            user_type=user_type_value,
            expires_delta=access_token_expires,
        )

        refresh_token = await self.create_refresh_token(user.id)
        await self.create_refresh_token_record(
            user_id=user.id,
            token=refresh_token,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )
    
    async def refresh_access_token(self, refresh_token: str) -> Token:
        """Refresh an access token using a refresh token."""
        stmt = select(RefreshToken).where(
            RefreshToken.token == refresh_token,
            RefreshToken.expires_at > datetime.utcnow()
        )
        result = await self.db.execute(stmt)
        db_token = result.scalars().first()
        
        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )
            
        if db_token.is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked"
            )
            
        # Create new access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        user = await get_user_by_id(self.db, db_token.user_id)
        user_type_value: Optional[str] = None
        if user:
            utype = getattr(user, "user_type", None)
            if isinstance(utype, UserTypeEnum):
                user_type_value = utype.value
            elif isinstance(utype, str):
                try:
                    user_type_value = UserTypeEnum(utype).value
                except ValueError:
                    user_type_value = None
            if user_type_value is None and user.is_superuser:
                user_type_value = UserTypeEnum.SYSTEM_ADMIN.value

        subject_identifier = user.email if user else str(db_token.user_id)

        access_token = create_access_token(
            subject=subject_identifier,
            user_type=user_type_value,
            expires_delta=access_token_expires,
        )
        
        # Create new refresh token
        new_refresh_token = await self.create_refresh_token(db_token.user_id)
        
        # Revoke the old refresh token
        db_token.is_revoked = True
        db_token.revoked_at = datetime.utcnow()
        self.db.add(db_token)
        
        try:
            await self.db.commit()
            await self.db.refresh(db_token)
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to refresh access token"
            )
            
        # Create a new refresh token record
        await self.create_refresh_token_record(
            user_id=db_token.user_id,
            token=new_refresh_token
        )
        
        # Return the new tokens
        return Token(
            access_token=access_token,
            token_type="bearer",
            refresh_token=new_refresh_token
        )
        
    async def get_current_user(self, token: str = Depends(oauth2_scheme)) -> User:
        """Get the current user from a JWT token."""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        try:
            payload = jwt.decode(
                token, 
                settings.SECRET_KEY, 
                algorithms=[settings.ALGORITHM]
            )
            user_id = payload.get("sub")
            
            if user_id is None:
                raise credentials_exception
                
            stmt = select(User).where(User.id == int(user_id))
            result = await self.db.execute(stmt)
            user = result.scalars().first()
            
            if user is None:
                raise credentials_exception
                
            return user
            
        except JWTError:
            raise credentials_exception
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username."""
        stmt = select(User).where(User.username == username)
        result = await self.db.execute(stmt)
        return result.scalars().first()
        
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        from sqlalchemy.future import select
        
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalars().first()
        
    async def _create_refresh_token(self, user_id: int, expires_delta: timedelta, jti: str = None) -> RefreshToken:
        """Create and store a refresh token in the database."""
        expires = datetime.utcnow() + expires_delta
        token = secrets.token_urlsafe(64)  # Longer token for refresh tokens
        db_token = RefreshToken(
            token=token,
            user_id=user_id,
            expires_at=expires,
            created_at=datetime.utcnow()
        )
        self.db.add(db_token)
        await self.db.commit()
        await self.db.refresh(db_token)
        return db_token
        
    async def _add_to_password_history(self, user_id: int, hashed_password: str) -> None:
        """
        Add a password to the user's password history.
        
        Args:
            user_id: The ID of the user
            hashed_password: The hashed password to add to history
        """
        from sqlalchemy.future import select
        from sqlalchemy import func, delete
        
        # Get the current time
        now = datetime.utcnow()
        
        # Create a new password history record
        password_history = PasswordHistory(
            user_id=user_id,
            hashed_password=hashed_password,
            created_at=now
        )
        
        self.db.add(password_history)
        
        # Get the count of password history records for this user
        stmt = select(func.count(PasswordHistory.id)).where(
            PasswordHistory.user_id == user_id
        )
        result = await self.db.execute(stmt)
        count = result.scalar_one()
        
        # If we have more than the allowed history, delete the oldest ones
        if count > settings.PASSWORD_HISTORY_LIMIT:
            # Get the ID of the oldest record to keep
            subq = select(PasswordHistory.id).where(
                PasswordHistory.user_id == user_id
            ).order_by(PasswordHistory.created_at.desc()).offset(
                settings.PASSWORD_HISTORY_LIMIT - 1
            ).limit(1).subquery()
            
            # Delete all records older than the one we want to keep
            stmt = delete(PasswordHistory).where(
                PasswordHistory.user_id == user_id,
                PasswordHistory.id < select(subq.c.id).scalar_subquery()
            )
            await self.db.execute(stmt)
        
        await self.db.commit()
        
    async def is_password_in_history(self, user_id: int, password: str) -> bool:
        """
        Check if the given password is in the user's password history.
        
        Args:
            user_id: The ID of the user
            password: The password to check
            
        Returns:
            bool: True if password is in history, False otherwise
        """
        from sqlalchemy.future import select
        
        # Get the user's password history (most recent first)
        stmt = select(PasswordHistory).where(
            PasswordHistory.user_id == user_id
        ).order_by(PasswordHistory.created_at.desc()).limit(
            settings.PASSWORD_HISTORY_LIMIT
        )
        
        result = await self.db.execute(stmt)
        history = result.scalars().all()
        
        # Check if the password matches any in the history
        for record in history:
            if verify_password(password, record.hashed_password):
                return True
                
        return False
            
    async def change_password(self, user: User, current_password: str, new_password: str) -> bool:
        """
        Change a user's password with security checks.
        
        Args:
            user: The user changing their password
            current_password: The user's current password
            new_password: The new password
            
        Returns:
            bool: True if password was changed successfully, False otherwise
            
        Raises:
            ValueError: If the current password is incorrect or new password is invalid
        """
        # Verify current password
        if not verify_password(current_password, user.hashed_password):
            raise ValueError("Current password is incorrect")
            
        # Check if new password is the same as current
        if verify_password(new_password, user.hashed_password):
            raise ValueError("New password must be different from current password")
            
        # Check password strength
        if not verify_password_strength(new_password):
            raise ValueError("New password does not meet complexity requirements")
            
        # Check if password was used before
        if await self.is_password_in_history(user.id, new_password):
            raise ValueError("You have used this password before. Please choose a different one.")
            
        # Hash the new password
        hashed_password = get_password_hash(new_password)
        
        # Update the user's password
        user.hashed_password = hashed_password
        user.password_changed_at = datetime.utcnow()
        
        # Add the new password to history
        await self._add_to_password_history(user.id, hashed_password)
        
        # Save changes
        await self.db.commit()
        
        return True
        if self.is_password_in_history(user.id, new_password):
            raise ValueError("You cannot reuse a previous password")
            
        # Update password and add to history
        new_hashed_password = get_password_hash(new_password)
        user.hashed_password = new_hashed_password
        user.last_password_change = datetime.utcnow()
        
        # Add to password history
        self._add_to_password_history(user.id, new_hashed_password)
        
    async def generate_mfa_secret(self, user: User) -> str:
        """Generate a new MFA secret for a user.
        
        Args:
            user: The user to generate the MFA secret for
            
        Returns:
            str: The generated MFA secret
        """
        # Generate a new secret
        secret = pyotp.random_base32()
        
        # Update the user's MFA secret
        user.mfa_secret = secret
        user.mfa_enabled = False  # Not enabled until verified
        
        await self.db.commit()
        
        return secret
        
    async def generate_mfa_uri(self, user: User, secret: str) -> str:
        """
        Generate a provisioning URI for the MFA app.
        
        Args:
            user: The user to generate the URI for
            secret: The MFA secret
            
        Returns:
            str: The provisioning URI
        """
        return pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=settings.PROJECT_NAME
        )
        
    async def verify_mfa_code(self, user: User, code: str) -> bool:
        """
        Verify an MFA code for a user.
        
        Args:
            user: The user to verify the code for
            code: The MFA code to verify
            
        Returns:
            bool: True if the code is valid, False otherwise
        """
        if not user.mfa_secret:
            return False
            
        totp = pyotp.TOTP(user.mfa_secret)
        return totp.verify(code, valid_window=1)  # Allow 30s before/after for clock skew
        
    async def enable_mfa(self, user: User, code: str) -> bool:
        """
        Enable MFA for a user after verifying their first code.
        
        Args:
            user: The user to enable MFA for
            code: The MFA code to verify
            
        Returns:
            bool: True if MFA was enabled, False if the code was invalid
        """
        if not user.mfa_secret:
            return False
            
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(code):
            return False
            
        user.mfa_enabled = True
        await self.db.commit()
        
        return True
        
    async def disable_mfa(self, user: User) -> None:
        """
        Disable MFA for a user.
        
        Args:
            user: The user to disable MFA for
        """
        user.mfa_enabled = False
        user.mfa_secret = None
        await self.db.commit()
        
    async def generate_recovery_codes(self, user: User, count: int = 10) -> List[str]:
        """
        Generate recovery codes for MFA.
        
        Args:
            user: The user to generate recovery codes for
            count: Number of recovery codes to generate (default: 10)
            
        Returns:
            List[str]: List of recovery codes
        """
        # Generate new recovery codes
        codes = [secrets.token_urlsafe(16) for _ in range(count)]
        
        # Hash the codes before storing them
        hashed_codes = [get_password_hash(code) for code in codes]
        
        # Store the hashed codes in the database
        user.mfa_recovery_codes = hashed_codes
        await self.db.commit()
        
        # Return the plaintext codes (only shown once!)
        return codes
        
    async def verify_recovery_code(self, user: User, code: str) -> bool:
        """
        Verify a recovery code and remove it if valid.
        
        Args:
            user: The user to verify the recovery code for
            code: The recovery code to verify
            
        Returns:
            bool: True if the recovery code was valid, False otherwise
        """
        if not user.mfa_recovery_codes:
            return False
            
        if code in user.mfa_recovery_codes:
            # Remove the used code
            user.mfa_recovery_codes = [c for c in user.mfa_recovery_codes if c != code]
            self.db.commit()
            return True
            
        return False

# Dependency to get an AuthService instance
def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """Dependency that returns an instance of AuthService with a database session.
    
    Args:
        db: The database session
        
    Returns:
        An instance of AuthService
    """
    return AuthService(db)

# Dependency to get the current active user
def get_current_active_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service)
):
    return auth_service.get_current_user(token)
