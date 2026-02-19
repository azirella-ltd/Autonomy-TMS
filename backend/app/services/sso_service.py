"""
SSO Service

Handles authentication with external SSO providers:
- OAuth 2.0 (Google, Microsoft, Okta, Azure AD)
- SAML 2.0
- LDAP/Active Directory
"""

from typing import Optional, Dict, Any, Tuple
from datetime import datetime
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

# OAuth2
from authlib.integrations.starlette_client import OAuth
from authlib.integrations.base_client import OAuthError

# LDAP
try:
    import ldap3
    from ldap3.core.exceptions import LDAPException
    LDAP_AVAILABLE = True
except ImportError:
    LDAP_AVAILABLE = False

# SAML (optional - can be added later)
try:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from onelogin.saml2.utils import OneLogin_Saml2_Utils
    SAML_AVAILABLE = True
except ImportError:
    SAML_AVAILABLE = False

from app.models.sso_provider import SSOProvider, UserSSOMapping, SSOLoginAttempt, SSOProviderType
from app.models.user import User, UserTypeEnum
from app.core.config import settings
from app.services.auth_service import get_password_hash

logger = logging.getLogger(__name__)


class SSOService:
    """
    Service for handling SSO authentication across multiple providers
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.oauth = OAuth()

    async def get_provider(self, provider_id: int) -> Optional[SSOProvider]:
        """Get SSO provider by ID"""
        result = await self.db.execute(
            select(SSOProvider).where(
                SSOProvider.id == provider_id,
                SSOProvider.enabled == True
            )
        )
        return result.scalar_one_or_none()

    async def get_provider_by_slug(self, slug: str) -> Optional[SSOProvider]:
        """Get SSO provider by slug"""
        result = await self.db.execute(
            select(SSOProvider).where(
                SSOProvider.slug == slug,
                SSOProvider.enabled == True
            )
        )
        return result.scalar_one_or_none()

    async def list_providers(self) -> list[SSOProvider]:
        """List all enabled SSO providers"""
        result = await self.db.execute(
            select(SSOProvider).where(SSOProvider.enabled == True)
        )
        return result.scalars().all()

    # ==================== OAuth 2.0 ====================

    def register_oauth_provider(self, provider: SSOProvider):
        """Register OAuth provider with authlib"""
        config = provider.config

        self.oauth.register(
            name=provider.slug,
            client_id=config.get('client_id'),
            client_secret=config.get('client_secret'),
            authorize_url=config.get('authorization_url'),
            authorize_params=None,
            access_token_url=config.get('token_url'),
            access_token_params=None,
            refresh_token_url=None,
            client_kwargs={'scope': config.get('scope', 'openid email profile')},
        )

    async def get_oauth_authorization_url(
        self,
        provider: SSOProvider,
        redirect_uri: str
    ) -> str:
        """
        Get OAuth2 authorization URL to redirect user to

        Args:
            provider: SSO provider configuration
            redirect_uri: Where to redirect after authentication

        Returns:
            Authorization URL
        """
        if provider.type != SSOProviderType.OAUTH2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider {provider.name} is not an OAuth2 provider"
            )

        self.register_oauth_provider(provider)

        client = self.oauth.create_client(provider.slug)
        return await client.authorize_redirect_url(redirect_uri)

    async def authenticate_oauth2(
        self,
        provider: SSOProvider,
        code: str,
        redirect_uri: str,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[User, bool]:
        """
        Authenticate user via OAuth2

        Args:
            provider: SSO provider configuration
            code: Authorization code from provider
            redirect_uri: Redirect URI used in authorization
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Tuple of (User, is_new_user)
        """
        if provider.type != SSOProviderType.OAUTH2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider {provider.name} is not an OAuth2 provider"
            )

        try:
            self.register_oauth_provider(provider)
            client = self.oauth.create_client(provider.slug)

            # Exchange code for token
            token = await client.fetch_access_token(code=code, redirect_uri=redirect_uri)

            # Fetch user info
            userinfo_url = provider.config.get('userinfo_url')
            if not userinfo_url:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="userinfo_url not configured for provider"
                )

            resp = await client.get(userinfo_url, token=token)
            userinfo = resp.json()

            # Extract user attributes
            external_id = userinfo.get('sub') or userinfo.get('id')
            email = userinfo.get('email')
            name = userinfo.get('name') or userinfo.get('given_name', '') + ' ' + userinfo.get('family_name', '')

            if not external_id or not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Provider did not return required user information (sub/id and email)"
                )

            # Check domain restrictions
            if provider.allowed_domains:
                email_domain = email.split('@')[1] if '@' in email else ''
                if email_domain not in provider.allowed_domains:
                    await self._log_attempt(
                        provider_id=provider.id,
                        external_id=external_id,
                        external_email=email,
                        success=False,
                        failure_reason=f"Email domain {email_domain} not allowed",
                        ip_address=ip_address,
                        user_agent=user_agent
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Email domain not allowed for this provider"
                    )

            # Find or create user
            user, is_new = await self._find_or_create_user(
                provider=provider,
                external_id=external_id,
                email=email,
                name=name,
                external_attributes=userinfo
            )

            # Log successful attempt
            await self._log_attempt(
                provider_id=provider.id,
                external_id=external_id,
                external_email=email,
                user_id=user.id,
                success=True,
                ip_address=ip_address,
                user_agent=user_agent
            )

            # Update last login
            user.last_login = datetime.utcnow()
            await self.db.commit()

            return user, is_new

        except OAuthError as e:
            logger.error(f"OAuth error for provider {provider.name}: {str(e)}")
            await self._log_attempt(
                provider_id=provider.id,
                external_id=None,
                external_email=None,
                success=False,
                failure_reason=f"OAuth error: {str(e)}",
                ip_address=ip_address,
                user_agent=user_agent
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"OAuth authentication failed: {str(e)}"
            )

    # ==================== LDAP ====================

    async def authenticate_ldap(
        self,
        provider: SSOProvider,
        username: str,
        password: str,
        ip_address: str = None,
        user_agent: str = None
    ) -> Tuple[User, bool]:
        """
        Authenticate user via LDAP

        Args:
            provider: SSO provider configuration
            username: LDAP username
            password: User password
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Tuple of (User, is_new_user)
        """
        if not LDAP_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="LDAP support not available (install python-ldap3)"
            )

        if provider.type != SSOProviderType.LDAP:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider {provider.name} is not an LDAP provider"
            )

        config = provider.config

        try:
            # Connect to LDAP server
            server = ldap3.Server(
                host=config.get('server'),
                port=config.get('port', 389),
                use_ssl=config.get('use_ssl', False),
                get_info=ldap3.ALL
            )

            # Build user DN
            user_dn_template = config.get('user_dn_template', 'uid={},{}')
            base_dn = config.get('base_dn')
            user_dn = user_dn_template.format(username, base_dn)

            # Attempt bind with user credentials
            conn = ldap3.Connection(
                server,
                user=user_dn,
                password=password,
                auto_bind=True,
                raise_exceptions=True
            )

            if not conn.bind():
                await self._log_attempt(
                    provider_id=provider.id,
                    external_id=username,
                    external_email=None,
                    success=False,
                    failure_reason="LDAP bind failed",
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )

            # Fetch user attributes
            search_filter = f"(uid={username})"
            conn.search(
                search_base=base_dn,
                search_filter=search_filter,
                attributes=['uid', 'mail', 'cn', 'displayName', 'givenName', 'sn']
            )

            if not conn.entries:
                await self._log_attempt(
                    provider_id=provider.id,
                    external_id=username,
                    external_email=None,
                    success=False,
                    failure_reason="User not found in LDAP",
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            entry = conn.entries[0]

            # Extract attributes
            external_id = str(entry.uid.value) if hasattr(entry, 'uid') else username
            email = str(entry.mail.value) if hasattr(entry, 'mail') else f"{username}@{config.get('default_domain', 'local')}"
            name = (str(entry.displayName.value) if hasattr(entry, 'displayName')
                   else str(entry.cn.value) if hasattr(entry, 'cn')
                   else username)

            # Check domain restrictions
            if provider.allowed_domains:
                email_domain = email.split('@')[1] if '@' in email else ''
                if email_domain not in provider.allowed_domains:
                    await self._log_attempt(
                        provider_id=provider.id,
                        external_id=external_id,
                        external_email=email,
                        success=False,
                        failure_reason=f"Email domain {email_domain} not allowed",
                        ip_address=ip_address,
                        user_agent=user_agent
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Email domain not allowed for this provider"
                    )

            # Find or create user
            user, is_new = await self._find_or_create_user(
                provider=provider,
                external_id=external_id,
                email=email,
                name=name,
                external_attributes=entry.entry_attributes_as_dict
            )

            # Log successful attempt
            await self._log_attempt(
                provider_id=provider.id,
                external_id=external_id,
                external_email=email,
                user_id=user.id,
                success=True,
                ip_address=ip_address,
                user_agent=user_agent
            )

            # Update last login
            user.last_login = datetime.utcnow()
            await self.db.commit()

            conn.unbind()

            return user, is_new

        except LDAPException as e:
            logger.error(f"LDAP error for provider {provider.name}: {str(e)}")
            await self._log_attempt(
                provider_id=provider.id,
                external_id=username,
                external_email=None,
                success=False,
                failure_reason=f"LDAP error: {str(e)}",
                ip_address=ip_address,
                user_agent=user_agent
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"LDAP authentication failed"
            )

    # ==================== Helper Methods ====================

    async def _find_or_create_user(
        self,
        provider: SSOProvider,
        external_id: str,
        email: str,
        name: str,
        external_attributes: Dict[str, Any]
    ) -> Tuple[User, bool]:
        """
        Find existing user or create new one

        Returns:
            Tuple of (User, is_new_user)
        """
        # Check if mapping already exists
        result = await self.db.execute(
            select(UserSSOMapping).where(
                UserSSOMapping.provider_id == provider.id,
                UserSSOMapping.external_id == external_id
            )
        )
        mapping = result.scalar_one_or_none()

        if mapping:
            # Existing mapping - update and return user
            mapping.external_email = email
            mapping.external_name = name
            mapping.external_attributes = external_attributes
            mapping.last_sync = datetime.utcnow()
            mapping.last_login = datetime.utcnow()
            await self.db.commit()

            # Fetch user
            result = await self.db.execute(
                select(User).where(User.id == mapping.user_id)
            )
            user = result.scalar_one()
            return user, False

        # Check if user exists by email
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            # Create mapping for existing user
            new_mapping = UserSSOMapping(
                user_id=existing_user.id,
                provider_id=provider.id,
                external_id=external_id,
                external_email=email,
                external_name=name,
                external_attributes=external_attributes,
                last_login=datetime.utcnow()
            )
            self.db.add(new_mapping)
            await self.db.commit()
            return existing_user, False

        # Auto-create user if enabled
        if not provider.auto_create_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not exist and auto-provisioning is disabled"
            )

        # Create new user
        new_user = User(
            email=email,
            username=email.split('@')[0],  # Use email prefix as username
            full_name=name,
            hashed_password=get_password_hash(external_id),  # Random password (user can't use it)
            is_active=True,
            user_type=UserTypeEnum[provider.default_user_type] if provider.default_user_type else UserTypeEnum.USER,
            group_id=provider.default_group_id,
            created_at=datetime.utcnow()
        )

        self.db.add(new_user)
        await self.db.flush()

        # Create mapping
        new_mapping = UserSSOMapping(
            user_id=new_user.id,
            provider_id=provider.id,
            external_id=external_id,
            external_email=email,
            external_name=name,
            external_attributes=external_attributes,
            last_login=datetime.utcnow()
        )
        self.db.add(new_mapping)

        await self.db.commit()
        await self.db.refresh(new_user)

        logger.info(f"Auto-created user {new_user.email} from SSO provider {provider.name}")

        return new_user, True

    async def _log_attempt(
        self,
        provider_id: int,
        external_id: Optional[str],
        external_email: Optional[str],
        user_id: Optional[int] = None,
        success: bool = False,
        failure_reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Log SSO login attempt"""
        attempt = SSOLoginAttempt(
            provider_id=provider_id,
            external_id=external_id,
            external_email=external_email,
            user_id=user_id,
            success=success,
            failure_reason=failure_reason,
            ip_address=ip_address,
            user_agent=user_agent,
            attempted_at=datetime.utcnow()
        )
        self.db.add(attempt)
        await self.db.commit()
