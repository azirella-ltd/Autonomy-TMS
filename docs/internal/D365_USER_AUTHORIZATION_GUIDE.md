# D365 F&O User Authorization Guide

## Quick Reference: Minimum Permissions for Autonomy Integration

### Azure AD App Registration

| Setting | Value |
|---------|-------|
| **App Type** | Single-tenant (organizational directory only) |
| **Redirect URI** | None (client credentials flow) |
| **API Permission** | `Dynamics ERP > Odata.FullAccess` (Application) |
| **Admin Consent** | Required (Global Admin grants) |
| **Client Secret Expiry** | 12 months (set calendar reminder to rotate) |

### D365 F&O Registration

| Setting | Value |
|---------|-------|
| **Location** | System administration > Setup > Microsoft Entra applications |
| **Client ID** | Application (client) ID from Azure AD |
| **User ID** | `AUTONOMY_SVC` (dedicated service account) |

### Service Account Security Roles

| Role | Duty | Purpose | Can Be Removed If... |
|------|------|---------|---------------------|
| **Entity store reader** | Read all data entities | Core: OData access | Never — always required |
| **Product information management clerk** | Product read | Products, BOMs | Products not extracted |
| **Procurement agent** | PO read | Purchase orders, vendors | POs not extracted |
| **Sales order clerk** | SO read | Sales orders, customers | SOs not extracted |
| **Warehouse manager** | Inventory read | Inventory, warehouses | Inventory not extracted |
| **Production floor manager** | MO read | Production orders | No manufacturing |
| **Master planning clerk** | Planning read | Forecasts, coverage | No planning data |

### Connection Details

| Parameter | Trial Environment | Production |
|-----------|------------------|------------|
| **Token Endpoint** | `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token` | Same |
| **OData Base** | `https://{env}.operations.dynamics.com/data/` | Same |
| **Data Area** | `usmf` (Contoso) | Customer-specific |
| **Token Lifetime** | 3,600 seconds (1 hour) | Same |
| **Rate Limit** | Throttled (shared infra) | Higher (dedicated) |
| **Max Page Size** | 10,000 records | Same |

---

## Step-by-Step Setup Checklist

### For the Azure AD Administrator

- [ ] Register application in Azure AD (portal.azure.com)
- [ ] Note Application ID and Tenant ID
- [ ] Create client secret and share securely (not email)
- [ ] Add `Dynamics ERP > Odata.FullAccess` permission
- [ ] Grant admin consent
- [ ] Document secret expiry date for rotation

### For the D365 System Administrator

- [ ] Create service account user (`AUTONOMY_SVC`)
- [ ] Assign minimum security roles (see table above)
- [ ] Register Azure AD app in Microsoft Entra Applications
- [ ] Map app Client ID to service account User ID
- [ ] Test: verify OData endpoint returns data for the user
- [ ] Document the legal entity code (dataAreaId) for extraction

### For the Autonomy Platform Administrator

- [ ] Create ERP connection in Autonomy (Admin > ERP Data Management)
- [ ] Enter: base URL, Azure tenant ID, client ID, client secret
- [ ] Set data area (legal entity code)
- [ ] Test connection
- [ ] Run initial master data extraction
- [ ] Verify entity counts match expected Contoso data
- [ ] Schedule CDC (change data capture) sync

---

## Security Hardening (Production)

### Principle of Least Privilege

1. **Never use System Administrator** in production — use the specific roles listed above
2. Create a **custom security role** that combines only the required duties:
   - Copy "Entity store reader" as base
   - Add read-only duties for Product, Procurement, Sales, Warehouse, Production, Planning
   - Name it: `Autonomy Read-Only Integration`
3. Assign only this custom role to the service account

### Network Security

1. **IP whitelisting**: Configure Azure AD Conditional Access to allow token issuance only from Autonomy's server IP(s)
2. **Private endpoints**: For Azure-hosted D365, use Azure Private Link to avoid public internet
3. **Audit logging**: Enable D365 audit logging for the service account to track all data access

### Secret Rotation

| Item | Rotation Period | How |
|------|-----------------|-----|
| Client secret | Every 12 months | Azure AD > App registration > Certificates & secrets |
| Service account password | Per company policy | D365 > System admin > Users |
| API token | Auto-refreshed (1 hour) | No manual action needed |

### Data Minimization

- Use `$select` to request only needed fields (not `*`)
- Use `$filter` with `dataAreaId` to scope to one legal entity
- Avoid `cross-company=true` unless explicitly needed
- Extract only the entities required for your planning scope

---

## Contoso USMF Legal Entity Reference

The trial environment uses Contoso Entertainment System USA (USMF) as the primary demo company.

### Sites

| Site ID | Name | Type |
|---------|------|------|
| 1 | Main site | Manufacturing |
| 2 | Secondary site | Distribution |
| 5 | Warehouse site | Distribution |

### Key Warehouses

| Warehouse | Site | Type | Notes |
|-----------|------|------|-------|
| 11 | 1 | Standard | Main finished goods |
| 12 | 1 | Standard | Raw materials |
| 13 | 1 | Standard | Quality inspection |
| 21 | 2 | Standard | Distribution |
| 51 | 5 | Advanced (WMS) | Advanced warehouse management |

### Product Examples

| Item Number | Name | Type | Standard Cost |
|-------------|------|------|--------------|
| D0001 | Cabinet | Finished | $120 |
| D0002 | Lamp | Finished | $45 |
| D0003 | TV Remote | Finished | $15 |
| M0001 | HDMI Cable (6ft) | Raw material | $3 |
| M0004 | Cabinet Housing | Component | $25 |

### BOM Example (D0001 Cabinet)

```
D0001 Cabinet (qty: 1)
├── M0004 Cabinet Housing (qty: 1)
├── M0005 Cabinet Door (qty: 2)
├── M0010 Hinge (qty: 4)
└── M0012 Screws (qty: 8)
```

---

## Troubleshooting Permission Errors

### `403 Forbidden` on OData

1. Check: Is the Azure AD app registered in D365 Microsoft Entra Applications?
2. Check: Is the mapped User ID active and not locked?
3. Check: Does the user have "Entity store reader" role?
4. Check: Did admin consent get granted for the API permissions?

### `401 Unauthorized`

1. Check: Is the client secret expired?
2. Check: Is the scope correct? Must be `https://{env}.operations.dynamics.com/.default`
3. Check: Is the tenant ID correct?

### Empty Results (0 records)

1. Check: Is `dataAreaId` filter correct? (case-sensitive: `usmf` not `USMF`)
2. Check: Does the user have access to the target legal entity?
3. Check: Try adding `cross-company=true` to see if records exist in other legal entities

### `404 Not Found` on Entity

1. Check: Is the entity name spelled correctly? (PascalCase, exact name)
2. Check: Is the entity `IsPublic = Yes`?
3. Verify available entities: `GET /data/$metadata`
