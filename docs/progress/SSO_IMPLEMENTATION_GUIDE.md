# SSO Implementation Guide - Complete Documentation

**Last Updated**: 2026-01-16
**Status**: ✅ OAuth2 and LDAP Fully Implemented | ⚠️ SAML2 Infrastructure Ready (Not Implemented)

---

## Table of Contents

1. [Overview](#overview)
2. [Supported Authentication Methods](#supported-authentication-methods)
3. [Architecture](#architecture)
4. [Database Schema](#database-schema)
5. [API Endpoints](#api-endpoints)
6. [OAuth2 Implementation](#oauth2-implementation)
7. [LDAP Implementation](#ldap-implementation)
8. [SAML2 Status](#saml2-status)
9. [Configuration Examples](#configuration-examples)
10. [Security Features](#security-features)
11. [Integration Guide](#integration-guide)
12. [Troubleshooting](#troubleshooting)

---

## Overview

The Beer Game now supports enterprise-grade Single Sign-On (SSO) authentication, allowing organizations to use their existing identity providers for user authentication. This eliminates the need for separate passwords and enables centralized user management.

### Key Features

✅ **OAuth 2.0** - Fully Implemented
✅ **LDAP/Active Directory** - Fully Implemented
⚠️ **SAML 2.0** - Infrastructure Ready, Implementation Pending
✅ **Auto-Provisioning** - Automatic user creation on first login
✅ **Domain Restrictions** - Only allow specific email domains
✅ **Audit Logging** - Track all authentication attempts
✅ **Multi-Provider Support** - Multiple SSO providers per tenant
✅ **User Mapping** - Link local users to external identities

---

## Supported Authentication Methods

### 1. OAuth 2.0 ✅ FULLY IMPLEMENTED

**Supported Providers:**
- Google Workspace
- Microsoft Azure AD / Office 365
- Okta
- GitHub
- GitLab
- Any OAuth2-compliant provider

**Implementation Status**: Production-ready with full feature support

**Authentication Flow:**
1. User clicks "Sign in with [Provider]"
2. Redirected to provider's authorization page
3. User grants permissions
4. Provider redirects back with authorization code
5. Backend exchanges code for access token
6. Backend fetches user info from provider
7. User is created/updated and JWT token issued

### 2. LDAP / Active Directory ✅ FULLY IMPLEMENTED

**Supported Systems:**
- Microsoft Active Directory
- OpenLDAP
- FreeIPA
- Any LDAP v3-compliant directory

**Implementation Status**: Production-ready with full feature support

**Authentication Flow:**
1. User enters username and password
2. Backend attempts LDAP bind with credentials
3. On success, fetches user attributes from directory
4. User is created/updated and JWT token issued

### 3. SAML 2.0 ⚠️ INFRASTRUCTURE READY

**Status**: Dependencies installed, models defined, infrastructure in place, but actual SAML authentication logic **NOT YET IMPLEMENTED**

**What's Ready:**
- `python3-saml` library installed
- Database models support SAML provider type
- SSO service has placeholder for SAML

**What's Missing:**
- SAML assertion parsing
- SAML signature validation
- Service Provider metadata generation
- Identity Provider metadata consumption
- Actual SAML authentication endpoints

**Estimated Implementation Time**: 2-3 days

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React)                        │
│  • Login page with SSO provider list                         │
│  • OAuth2 redirect handling                                  │
│  • JWT token storage                                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Backend (main.py)                       │
│  Router: /api/v1/sso                                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│          SSO API Endpoints (sso.py)                          │
│  • GET  /sso/providers                                       │
│  • GET  /sso/oauth2/{slug}/authorize                         │
│  • GET  /sso/oauth2/{slug}/callback                          │
│  • POST /sso/ldap/login                                      │
│  • POST /sso/admin/providers (admin)                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│            SSO Service (sso_service.py)                      │
│  • OAuth2 authentication (authlib)                           │
│  • LDAP authentication (ldap3)                               │
│  • User auto-provisioning                                    │
│  • Domain validation                                         │
│  • Audit logging                                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│             Database Models (sso_provider.py)                │
│  • sso_providers - Provider configurations                   │
│  • user_sso_mappings - User identity mapping                 │
│  • sso_login_attempts - Audit trail                          │
└─────────────────────────────────────────────────────────────┘
```

### File Structure

```
backend/
├── app/
│   ├── models/
│   │   └── sso_provider.py         # SSO data models (208 lines)
│   ├── services/
│   │   └── sso_service.py          # SSO authentication logic (450 lines)
│   ├── api/endpoints/
│   │   └── sso.py                  # SSO API routes (308 lines)
│   └── main.py                     # Router registration
├── migrations/versions/
│   └── 20260115_add_sso_tables.py  # Database schema
└── requirements.txt                # Dependencies added
```

---

## Database Schema

### Table: `sso_providers`

Stores SSO provider configurations.

```sql
CREATE TABLE sso_providers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,                    -- Display name
    slug VARCHAR(50) NOT NULL UNIQUE,              -- URL-safe identifier
    type ENUM('oauth2', 'ldap', 'saml') NOT NULL,  -- Provider type
    config JSON NOT NULL,                          -- Provider-specific configuration
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    allowed_domains JSON,                          -- Whitelist of email domains
    auto_create_users BOOLEAN NOT NULL DEFAULT TRUE,
    default_user_type VARCHAR(50) DEFAULT 'PLAYER',
    default_group_id INT,                          -- Auto-assign to this group
    created_at DATETIME NOT NULL,
    updated_at DATETIME,
    created_by INT,
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (default_group_id) REFERENCES groups(id),
    INDEX idx_slug (slug),
    INDEX idx_enabled (enabled)
);
```

**Config JSON Structure by Type:**

**OAuth2:**
```json
{
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "authorization_url": "https://provider.com/oauth/authorize",
    "token_url": "https://provider.com/oauth/token",
    "userinfo_url": "https://provider.com/oauth/userinfo",
    "scope": "openid email profile"
}
```

**LDAP:**
```json
{
    "server": "ldap://ldap.company.com",
    "port": 389,
    "use_ssl": false,
    "base_dn": "dc=company,dc=com",
    "user_dn_template": "uid={},ou=users,dc=company,dc=com",
    "bind_dn": "cn=admin,dc=company,dc=com",       # Optional
    "bind_password": "admin_password",             # Optional
    "default_domain": "company.com"                # For email generation
}
```

**SAML (Not Implemented):**
```json
{
    "entity_id": "https://beergame.com/saml/metadata",
    "sso_url": "https://idp.company.com/saml/sso",
    "slo_url": "https://idp.company.com/saml/slo",
    "x509_cert": "-----BEGIN CERTIFICATE-----...",
    "metadata_url": "https://idp.company.com/saml/metadata"
}
```

### Table: `user_sso_mappings`

Links local users to external SSO identities.

```sql
CREATE TABLE user_sso_mappings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    provider_id INT NOT NULL,
    external_id VARCHAR(255) NOT NULL,        -- External user ID (sub, uid, etc.)
    external_email VARCHAR(255),
    external_name VARCHAR(255),
    external_attributes JSON,                 -- Cached attributes from provider
    created_at DATETIME NOT NULL,
    last_sync DATETIME,
    last_login DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (provider_id) REFERENCES sso_providers(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_provider_id (provider_id),
    INDEX idx_external_id (external_id)
);
```

### Table: `sso_login_attempts`

Audit log for all SSO authentication attempts.

```sql
CREATE TABLE sso_login_attempts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    provider_id INT NOT NULL,
    external_id VARCHAR(255),
    external_email VARCHAR(255),
    user_id INT,                              -- NULL if login failed
    success BOOLEAN NOT NULL DEFAULT FALSE,
    failure_reason TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    attempted_at DATETIME NOT NULL,
    FOREIGN KEY (provider_id) REFERENCES sso_providers(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_provider_id (provider_id),
    INDEX idx_success (success),
    INDEX idx_attempted_at (attempted_at)
);
```

---

## API Endpoints

### Public Endpoints (No Authentication Required)

#### 1. List SSO Providers

```http
GET /api/v1/sso/providers
```

Returns list of enabled SSO providers for login page.

**Response:**
```json
[
    {
        "id": 1,
        "name": "Google Workspace",
        "slug": "google",
        "type": "oauth2"
    },
    {
        "id": 2,
        "name": "Corporate LDAP",
        "slug": "ldap",
        "type": "ldap"
    }
]
```

#### 2. Initiate OAuth2 Flow

```http
GET /api/v1/sso/oauth2/{provider_slug}/authorize?redirect_uri={url}
```

**Parameters:**
- `provider_slug`: Provider identifier (e.g., "google", "okta")
- `redirect_uri`: Optional. Where to redirect after authentication (defaults to frontend callback)

**Response:** HTTP 302 Redirect to provider's authorization page

**Example:**
```bash
curl -X GET "http://localhost:8088/api/v1/sso/oauth2/google/authorize"
# Redirects to: https://accounts.google.com/o/oauth2/v2/auth?client_id=...
```

#### 3. OAuth2 Callback

```http
GET /api/v1/sso/oauth2/{provider_slug}/callback?code={auth_code}&redirect_uri={url}
```

**Parameters:**
- `provider_slug`: Provider identifier
- `code`: Authorization code from provider (query parameter)
- `redirect_uri`: Must match the one used in authorize request

**Response:**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "user": {
        "id": 123,
        "email": "user@company.com",
        "full_name": "John Doe",
        "user_type": "PLAYER"
    },
    "is_new_user": true
}
```

**Note:** Also sets `refresh_token` as HTTP-only cookie

#### 4. LDAP Login

```http
POST /api/v1/sso/ldap/login
Content-Type: application/json

{
    "provider_slug": "corporate-ldap",
    "username": "jdoe",
    "password": "secret"
}
```

**Response:**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "user": {
        "id": 123,
        "email": "jdoe@company.com",
        "full_name": "John Doe",
        "user_type": "PLAYER"
    },
    "is_new_user": false
}
```

### Admin Endpoints (Require SYSTEM_ADMIN Role)

#### 5. Create SSO Provider

```http
POST /api/v1/sso/admin/providers
Authorization: Bearer {admin_token}
Content-Type: application/json

{
    "name": "Google OAuth",
    "slug": "google",
    "type": "oauth2",
    "config": {
        "client_id": "123456789.apps.googleusercontent.com",
        "client_secret": "your-client-secret",
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scope": "openid email profile"
    },
    "enabled": true,
    "allowed_domains": ["company.com", "subsidiary.com"],
    "auto_create_users": true,
    "default_user_type": "PLAYER",
    "default_group_id": null
}
```

**Response:** HTTP 201 Created
```json
{
    "id": 1,
    "name": "Google OAuth",
    "slug": "google",
    "type": "oauth2"
}
```

#### 6. List All Providers (Admin)

```http
GET /api/v1/sso/admin/providers
Authorization: Bearer {admin_token}
```

Returns all providers including disabled ones with full configuration.

#### 7. Get Provider Details

```http
GET /api/v1/sso/admin/providers/{provider_id}
Authorization: Bearer {admin_token}
```

#### 8. Update Provider

```http
PUT /api/v1/sso/admin/providers/{provider_id}
Authorization: Bearer {admin_token}
Content-Type: application/json

{
    "enabled": false,
    "allowed_domains": ["company.com"]
}
```

#### 9. Delete Provider

```http
DELETE /api/v1/sso/admin/providers/{provider_id}
Authorization: Bearer {admin_token}
```

---

## OAuth2 Implementation

### Supported OAuth2 Providers

#### Google Workspace

**Configuration:**
```json
{
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "client_secret": "YOUR_CLIENT_SECRET",
    "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_url": "https://oauth2.googleapis.com/token",
    "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
    "scope": "openid email profile"
}
```

**Setup Steps:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URI: `http://your-domain.com/api/v1/sso/oauth2/google/callback`
6. Copy Client ID and Client Secret

#### Microsoft Azure AD

**Configuration:**
```json
{
    "client_id": "YOUR_APPLICATION_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "authorization_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
    "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
    "userinfo_url": "https://graph.microsoft.com/v1.0/me",
    "scope": "openid email profile User.Read"
}
```

**Setup Steps:**
1. Go to [Azure Portal](https://portal.azure.com/)
2. Navigate to Azure Active Directory
3. Go to App registrations → New registration
4. Add redirect URI: `http://your-domain.com/api/v1/sso/oauth2/azure/callback`
5. Create client secret in Certificates & secrets
6. Copy Application (client) ID and client secret

#### Okta

**Configuration:**
```json
{
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "authorization_url": "https://your-domain.okta.com/oauth2/v1/authorize",
    "token_url": "https://your-domain.okta.com/oauth2/v1/token",
    "userinfo_url": "https://your-domain.okta.com/oauth2/v1/userinfo",
    "scope": "openid email profile"
}
```

**Setup Steps:**
1. Log in to Okta Admin Console
2. Go to Applications → Create App Integration
3. Select OIDC - OpenID Connect
4. Select Web Application
5. Add Sign-in redirect URI: `http://your-domain.com/api/v1/sso/oauth2/okta/callback`
6. Copy Client ID and Client Secret

### Authentication Flow Diagram

```
┌──────────┐                                  ┌──────────────┐
│  User    │                                  │   Provider   │
│ Browser  │                                  │  (Google)    │
└────┬─────┘                                  └──────┬───────┘
     │                                               │
     │ 1. GET /sso/oauth2/google/authorize          │
     ├──────────────────────────────────────────────▶
     │                                               │
     │ 2. Redirect to Google                         │
     ├──────────────────────────────────────────────▶
     │                                               │
     │ 3. User grants permissions                    │
     │◀──────────────────────────────────────────────┤
     │                                               │
     │ 4. Redirect with auth code                    │
     ◀───────────────────────────────────────────────┤
     │                                               │
     │ 5. GET /sso/oauth2/google/callback?code=...  │
     ├──────────────────────────────────────────────▶
     │                                               │
     │        Backend exchanges code for token       │
     │        ────────────────────────────────────────▶
     │                                               │
     │        Returns access token                   │
     │        ◀────────────────────────────────────────
     │                                               │
     │        Backend fetches user info              │
     │        ────────────────────────────────────────▶
     │                                               │
     │        Returns user profile                   │
     │        ◀────────────────────────────────────────
     │                                               │
     │ 6. Returns JWT token + user info              │
     ◀───────────────────────────────────────────────┤
     │                                               │
```

### Code Example (Python)

```python
from app.services.sso_service import SSOService

# Create SSO service
sso_service = SSOService(db)

# Get provider
provider = await sso_service.get_provider_by_slug("google")

# Initiate OAuth2 flow
authorization_url = await sso_service.get_oauth_authorization_url(
    provider=provider,
    redirect_uri="http://localhost:3000/auth/callback"
)

# User is redirected to authorization_url...
# Provider redirects back with code...

# Exchange code for user
user, is_new = await sso_service.authenticate_oauth2(
    provider=provider,
    code=request_code,
    redirect_uri="http://localhost:3000/auth/callback",
    ip_address=request.client.host,
    user_agent=request.headers.get('user-agent')
)

# Generate JWT token
from app.services.auth_service import create_access_token
token = create_access_token(data={"sub": str(user.id)})
```

---

## LDAP Implementation

### Supported LDAP Servers

- **Microsoft Active Directory**
- **OpenLDAP**
- **FreeIPA**
- **389 Directory Server**
- Any LDAP v3-compliant directory

### Configuration

**Basic LDAP:**
```json
{
    "server": "ldap://ldap.company.com",
    "port": 389,
    "use_ssl": false,
    "base_dn": "dc=company,dc=com",
    "user_dn_template": "uid={},ou=users,dc=company,dc=com"
}
```

**Active Directory:**
```json
{
    "server": "ldap://ad.company.com",
    "port": 389,
    "use_ssl": false,
    "base_dn": "dc=company,dc=com",
    "user_dn_template": "cn={},ou=Users,dc=company,dc=com",
    "bind_dn": "cn=service_account,ou=ServiceAccounts,dc=company,dc=com",
    "bind_password": "service_password",
    "default_domain": "company.com"
}
```

**LDAPS (Secure):**
```json
{
    "server": "ldaps://ldap.company.com",
    "port": 636,
    "use_ssl": true,
    "base_dn": "dc=company,dc=com",
    "user_dn_template": "uid={},ou=users,dc=company,dc=com"
}
```

### Authentication Flow

```
┌──────────┐                    ┌──────────────┐
│  User    │                    │ LDAP Server  │
│ Browser  │                    │   (AD)       │
└────┬─────┘                    └──────┬───────┘
     │                                 │
     │ 1. POST /sso/ldap/login         │
     │    {username, password}         │
     ├─────────────────────────────────▶
     │                                 │
     │      Backend: LDAP Bind         │
     │      ──────────────────────────▶
     │                                 │
     │      Bind Success/Failure       │
     │      ◀──────────────────────────
     │                                 │
     │      Backend: Fetch Attributes  │
     │      ──────────────────────────▶
     │                                 │
     │      User Attributes            │
     │      ◀──────────────────────────
     │                                 │
     │ 2. Returns JWT token            │
     ◀─────────────────────────────────┤
     │                                 │
```

### Code Example

```python
from app.services.sso_service import SSOService

# Create SSO service
sso_service = SSOService(db)

# Get LDAP provider
provider = await sso_service.get_provider_by_slug("corporate-ldap")

# Authenticate with LDAP
user, is_new = await sso_service.authenticate_ldap(
    provider=provider,
    username="jdoe",
    password="secret",
    ip_address=request.client.host,
    user_agent=request.headers.get('user-agent')
)

# Generate JWT token
token = create_access_token(data={"sub": str(user.id)})
```

### Testing LDAP Connection

Use `ldapsearch` command to test connectivity:

```bash
# Test anonymous bind
ldapsearch -x -H ldap://ldap.company.com -b "dc=company,dc=com"

# Test user bind
ldapsearch -x -H ldap://ldap.company.com \
    -D "uid=jdoe,ou=users,dc=company,dc=com" \
    -w "password" \
    -b "dc=company,dc=com" "(uid=jdoe)"
```

---

## SAML2 Status

### Current State

⚠️ **SAML 2.0 is NOT yet implemented**. The infrastructure is ready but the actual SAML authentication logic needs to be built.

### What's Already Done

1. ✅ `python3-saml` library installed
2. ✅ Database models support `type='saml'`
3. ✅ SSO provider table has SAML enum value
4. ✅ Config JSON structure defined

### What Needs to Be Built

1. **Service Provider Metadata Generation**
   - Generate SP metadata XML
   - Entity ID configuration
   - Assertion Consumer Service URL
   - Single Logout Service URL

2. **Identity Provider Metadata Consumption**
   - Parse IDP metadata XML
   - Extract SSO URL, SLO URL, certificates

3. **SAML Authentication Flow**
   - Generate SAML AuthnRequest
   - Parse SAML Response
   - Validate signature
   - Extract assertions
   - Map attributes to user fields

4. **API Endpoints**
   - `GET /api/v1/sso/saml/{slug}/metadata` - SP metadata
   - `POST /api/v1/sso/saml/{slug}/login` - Initiate SAML request
   - `POST /api/v1/sso/saml/{slug}/acs` - Assertion Consumer Service
   - `GET /api/v1/sso/saml/{slug}/slo` - Single Logout

### Estimated Implementation Time

**2-3 days** for a skilled developer familiar with SAML 2.0 protocol.

### Implementation Guide (For Future Reference)

```python
# backend/app/services/saml_service.py (TO BE CREATED)

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from onelogin.saml2.utils import OneLogin_Saml2_Utils

class SAMLService:
    async def generate_metadata(self, provider: SSOProvider):
        """Generate SP metadata XML"""
        settings = self._build_settings(provider)
        saml_settings = OneLogin_Saml2_Settings(settings)
        metadata = saml_settings.get_sp_metadata()
        return metadata

    async def initiate_login(self, provider: SSOProvider):
        """Initiate SAML login"""
        auth = self._get_auth_object(provider)
        return auth.login(return_to=callback_url)

    async def process_assertion(self, provider: SSOProvider, saml_response: str):
        """Process SAML response and extract user info"""
        auth = self._get_auth_object(provider)
        auth.process_response()

        if not auth.is_authenticated():
            raise HTTPException(401, "SAML authentication failed")

        attributes = auth.get_attributes()
        external_id = auth.get_nameid()

        # Map SAML attributes to user fields
        # ...
```

---

## Configuration Examples

### Example 1: Google Workspace SSO

```bash
curl -X POST http://localhost:8088/api/v1/sso/admin/providers \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Google Workspace",
    "slug": "google",
    "type": "oauth2",
    "config": {
      "client_id": "123456789.apps.googleusercontent.com",
      "client_secret": "GOCSPX-xxxxxxxxxxxx",
      "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
      "token_url": "https://oauth2.googleapis.com/token",
      "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
      "scope": "openid email profile"
    },
    "enabled": true,
    "allowed_domains": ["mycompany.com"],
    "auto_create_users": true,
    "default_user_type": "PLAYER"
  }'
```

### Example 2: Active Directory LDAP

```bash
curl -X POST http://localhost:8088/api/v1/sso/admin/providers \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Corporate Active Directory",
    "slug": "corporate-ad",
    "type": "ldap",
    "config": {
      "server": "ldap://ad.mycompany.com",
      "port": 389,
      "use_ssl": false,
      "base_dn": "dc=mycompany,dc=com",
      "user_dn_template": "cn={},ou=Users,dc=mycompany,dc=com",
      "bind_dn": "cn=svc_beergame,ou=ServiceAccounts,dc=mycompany,dc=com",
      "bind_password": "service_password",
      "default_domain": "mycompany.com"
    },
    "enabled": true,
    "allowed_domains": ["mycompany.com"],
    "auto_create_users": true,
    "default_user_type": "PLAYER",
    "default_group_id": 1
  }'
```

### Example 3: Okta OAuth2

```bash
curl -X POST http://localhost:8088/api/v1/sso/admin/providers \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Okta SSO",
    "slug": "okta",
    "type": "oauth2",
    "config": {
      "client_id": "0oa1a2b3c4d5e6f7g8h9",
      "client_secret": "abcdefghijklmnopqrstuvwxyz123456",
      "authorization_url": "https://mycompany.okta.com/oauth2/v1/authorize",
      "token_url": "https://mycompany.okta.com/oauth2/v1/token",
      "userinfo_url": "https://mycompany.okta.com/oauth2/v1/userinfo",
      "scope": "openid email profile"
    },
    "enabled": true,
    "allowed_domains": ["mycompany.com"],
    "auto_create_users": true,
    "default_user_type": "PLAYER"
  }'
```

---

## Security Features

### 1. Domain Whitelisting

Restrict SSO access to specific email domains:

```json
{
    "allowed_domains": ["company.com", "subsidiary.com"]
}
```

- Users with other email domains will be rejected
- Prevents unauthorized external users from accessing via SSO
- Useful for Google Workspace with personal Gmail accounts

### 2. Auto-Provisioning Control

Control whether new users are created automatically:

```json
{
    "auto_create_users": true,   // Allow new users
    "default_user_type": "PLAYER", // Default role for new users
    "default_group_id": 1        // Auto-assign to group
}
```

Set to `false` to require manual user creation first.

### 3. Audit Logging

Every SSO login attempt is logged:

```sql
SELECT * FROM sso_login_attempts
WHERE provider_id = 1
ORDER BY attempted_at DESC;
```

Tracks:
- Successful and failed attempts
- IP addresses
- User agents
- Failure reasons
- Timestamps

### 4. JWT Token Security

After successful SSO:
- Short-lived access tokens (8 days default)
- Long-lived refresh tokens (30 days default)
- HTTP-only cookies
- CSRF protection

### 5. Provider Disabling

Quickly disable a compromised provider:

```bash
curl -X PUT http://localhost:8088/api/v1/sso/admin/providers/1 \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

## Integration Guide

### Frontend Integration (React)

#### 1. Display SSO Providers on Login Page

```javascript
// Fetch available providers
const providers = await fetch('/api/v1/sso/providers').then(r => r.json());

// Render login buttons
providers.map(provider => (
  <button onClick={() => handleSSOLogin(provider.slug)}>
    Sign in with {provider.name}
  </button>
));
```

#### 2. Handle OAuth2 Login

```javascript
const handleSSOLogin = (providerSlug) => {
  // Redirect to authorization endpoint
  window.location.href = `/api/v1/sso/oauth2/${providerSlug}/authorize?redirect_uri=${window.location.origin}/auth/callback`;
};
```

#### 3. Handle OAuth2 Callback

```javascript
// In /auth/callback route
const urlParams = new URLSearchParams(window.location.search);
const code = urlParams.get('code');
const providerSlug = getProviderFromPath(); // Extract from URL

// Exchange code for token
const response = await fetch(`/api/v1/sso/oauth2/${providerSlug}/callback?code=${code}`, {
  credentials: 'include' // Include cookies
});

const { access_token, user } = await response.json();

// Store token
localStorage.setItem('access_token', access_token);

// Redirect to app
window.location.href = '/dashboard';
```

#### 4. Handle LDAP Login

```javascript
const handleLDAPLogin = async (providerSlug, username, password) => {
  const response = await fetch('/api/v1/sso/ldap/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ provider_slug: providerSlug, username, password })
  });

  const { access_token, user } = await response.json();
  localStorage.setItem('access_token', access_token);
  window.location.href = '/dashboard';
};
```

---

## Troubleshooting

### Common Issues

#### 1. OAuth2: "redirect_uri_mismatch" Error

**Problem:** Provider rejects redirect URI

**Solution:** Ensure redirect URI in provider config matches exactly:
- Check protocol (http vs https)
- Check domain
- Check port
- Check path

**Example:** `http://localhost:8088/api/v1/sso/oauth2/google/callback`

#### 2. LDAP: "Invalid credentials" but password is correct

**Problem:** Wrong user DN format

**Solution:** Check `user_dn_template` format for your LDAP server:
- OpenLDAP: `uid={},ou=users,dc=company,dc=com`
- Active Directory: `cn={},ou=Users,dc=company,dc=com`
- Some systems: `{username}@domain.com`

Test with `ldapsearch`:
```bash
ldapsearch -x -H ldap://server -D "uid=jdoe,ou=users,dc=company,dc=com" -w password
```

#### 3. OAuth2: "Provider did not return required user information"

**Problem:** Provider didn't return `sub` or `email`

**Solution:** Check OAuth scopes include `email` and `profile`:
```json
{
    "scope": "openid email profile"
}
```

#### 4. Auto-provisioning creates users with wrong group

**Problem:** New users not assigned to correct group

**Solution:** Set `default_group_id` in provider config:
```json
{
    "default_group_id": 1
}
```

#### 5. LDAP: Connection timeout

**Problem:** Cannot reach LDAP server

**Solution:**
- Check firewall rules
- Verify server address and port
- Test with `telnet ldap.company.com 389`
- Try LDAPS on port 636 if 389 is blocked

#### 6. Domain restriction rejecting valid users

**Problem:** User email domain not in whitelist

**Solution:** Add domain to `allowed_domains`:
```bash
curl -X PUT /api/v1/sso/admin/providers/1 \
  -d '{"allowed_domains": ["company.com", "contractor-company.com"]}'
```

---

## Appendix

### Dependencies Installed

```
authlib==1.3.0
ldap3==2.9.1
python3-saml==1.15.0
```

### Files Created

```
backend/app/models/sso_provider.py          # 208 lines
backend/app/services/sso_service.py         # 450 lines
backend/app/api/endpoints/sso.py            # 308 lines
backend/migrations/versions/20260115_add_sso_tables.py
```

### Database Tables

```
sso_providers (11 columns, 3 indexes)
user_sso_mappings (10 columns, 3 indexes)
sso_login_attempts (9 columns, 4 indexes)
```

### API Endpoints Summary

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/sso/providers` | Public | List enabled providers |
| GET | `/sso/oauth2/{slug}/authorize` | Public | Start OAuth2 flow |
| GET | `/sso/oauth2/{slug}/callback` | Public | OAuth2 callback |
| POST | `/sso/ldap/login` | Public | LDAP login |
| POST | `/sso/admin/providers` | Admin | Create provider |
| GET | `/sso/admin/providers` | Admin | List all providers |
| GET | `/sso/admin/providers/{id}` | Admin | Get provider details |
| PUT | `/sso/admin/providers/{id}` | Admin | Update provider |
| DELETE | `/sso/admin/providers/{id}` | Admin | Delete provider |

---

## Support

For issues or questions:
- Check logs: `docker compose logs backend | grep SSO`
- Review audit logs: `SELECT * FROM sso_login_attempts ORDER BY attempted_at DESC LIMIT 50;`
- Test provider config with curl
- Verify network connectivity to provider

---

**Last Updated**: 2026-01-16
**Version**: 1.0
**Status**: ✅ Production Ready (OAuth2 & LDAP) | ⚠️ SAML2 Pending Implementation
