"""
SSO Provider Models

Supports multiple authentication providers:
- SAML 2.0
- OAuth 2.0 (Google, Microsoft, Okta)
- LDAP/Active Directory
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .base import Base


class SSOProviderType(str, enum.Enum):
    """SSO provider type enumeration"""
    SAML = "saml"
    OAUTH2 = "oauth2"
    LDAP = "ldap"


class SSOProvider(Base):
    """
    SSO Provider configuration

    Stores configuration for external authentication providers
    """
    __tablename__ = "sso_providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # Display name (e.g., "Corporate Okta")
    slug = Column(String(50), unique=True, nullable=False, index=True)  # URL-safe identifier
    type = Column(Enum(SSOProviderType, name="sso_provider_type"), nullable=False)

    # Provider-specific configuration (JSON)
    # OAuth2: client_id, client_secret, authorization_url, token_url, userinfo_url
    # SAML: entity_id, sso_url, x509_cert, metadata_url
    # LDAP: server, port, base_dn, user_dn_template, bind_dn, bind_password
    config = Column(JSON, nullable=False)

    enabled = Column(Boolean, default=True, nullable=False)

    # Domain restrictions (optional) - only allow users from these email domains
    allowed_domains = Column(JSON)  # List of allowed email domains, e.g., ["company.com", "subsidiary.com"]

    # Auto-provisioning settings
    auto_create_users = Column(Boolean, default=True)  # Auto-create users on first SSO login
    default_user_type = Column(String(50), default="USER")  # Default role for new users
    default_tenant_id = Column(Integer, ForeignKey('tenants.id'), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)

    # Tenant (multi-tenancy)
    tenant_id = Column(Integer, ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True)

    # Relationships
    user_mappings = relationship("UserSSOMapping", back_populates="provider", cascade="all, delete-orphan")
    default_tenant = relationship("Tenant", foreign_keys=[default_tenant_id])
    tenant = relationship("Tenant", back_populates="sso_providers")

    def __repr__(self):
        return f"<SSOProvider {self.name} ({self.type})>"


class UserSSOMapping(Base):
    """
    Maps local users to external SSO identities

    Tracks the relationship between internal user accounts and external SSO providers
    """
    __tablename__ = "user_sso_mappings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey('sso_providers.id'), nullable=False, index=True)

    # External user identifier from SSO provider
    external_id = Column(String(255), nullable=False, index=True)

    # External user attributes (cached from provider)
    external_email = Column(String(255))
    external_name = Column(String(255))
    external_attributes = Column(JSON)  # Additional attributes from provider

    # Sync tracking
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_sync = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="sso_mappings")
    provider = relationship("SSOProvider", back_populates="user_mappings")

    def __repr__(self):
        return f"<UserSSOMapping user_id={self.user_id} provider={self.provider_id} external_id={self.external_id}>"


class SSOLoginAttempt(Base):
    """
    SSO login attempt audit log

    Tracks all SSO authentication attempts for security monitoring
    """
    __tablename__ = "sso_login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey('sso_providers.id'), nullable=False, index=True)

    # User information
    external_id = Column(String(255), index=True)
    external_email = Column(String(255))
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)  # Null if login failed

    # Attempt details
    success = Column(Boolean, nullable=False, default=False, index=True)
    failure_reason = Column(Text)  # Error message if failed

    # Request metadata
    ip_address = Column(String(45))
    user_agent = Column(Text)

    # Timestamps
    attempted_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    provider = relationship("SSOProvider")
    user = relationship("User")

    def __repr__(self):
        status = "SUCCESS" if self.success else "FAILURE"
        return f"<SSOLoginAttempt {status} provider_id={self.provider_id} external_id={self.external_id}>"
