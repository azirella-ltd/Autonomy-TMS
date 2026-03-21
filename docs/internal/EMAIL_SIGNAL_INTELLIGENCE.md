# Email Signal Intelligence — GDPR-Safe Email Ingestion

## Overview

Email Signal Intelligence monitors customer and supplier inboxes, extracts supply chain signals from incoming emails, and routes them to the appropriate TRM agents for action. Personal identifiers are stripped before any text is stored — only the sending company (resolved via domain→TradingPartner) is persisted.

This addresses a key pain point: **the time and effort to evaluate customer/supplier communications**. Instead of a planner manually reading emails, triaging urgency, and assessing impact, an AI agent reads emails as they arrive, classifies them into structured SC signals, prepares impact assessments, and surfaces actionable items to humans via the Decision Stream.

## GDPR Compliance

GDPR Article 5(1)(c) requires data minimization. Email Signal Intelligence achieves this by design:

| What | Stored? | How |
|------|---------|-----|
| Sender name | NO | Stripped by PII scrubber |
| Sender email address | NO | Domain extracted, then address removed |
| Phone numbers | NO | Regex-detected and replaced with `[PHONE]` |
| Physical addresses | NO | Regex-detected and replaced with `[ADDRESS]` |
| Signature blocks | NO | Detected and removed |
| Sender domain | YES | `acme-corp.com` — used for TradingPartner resolution |
| Company name | YES | Resolved from domain via TradingPartner table |
| Partner type | YES | `customer` or `vendor` from TradingPartner.tpartner_type |
| Email body (scrubbed) | YES | All PII removed, SC context preserved |
| Subject (scrubbed) | YES | PII removed |
| Signal classification | YES | Type, direction, magnitude, urgency, summary |

**The original email is NEVER stored.** Only PII-scrubbed text persists.

**No "right to erasure" complexity.** Since no personal data is stored, there are no data subject rights requests to handle for email content.

## Architecture

### Pipeline

```
IMAP/Gmail Inbox
    |
    v
Email Connector (IMAPConnector)
    |  Fetch new emails since last_poll_uid
    |
    v
PII Scrubber (email_pii_scrubber.py)
    |  Strip names, emails, phones, addresses, signatures
    |  Extract sender domain
    |
    v
TradingPartner Resolution
    |  domain → trading_partners table
    |  "acme-corp.com" → "ACME Corporation" (vendor)
    |
    v
LLM Classification (Haiku tier, ~$0.0018/call)
    |  → signal_type, direction, magnitude, urgency, summary
    |  → product_refs, site_refs, time_horizon
    |
    v
Scope Resolution
    |  Fuzzy-match product/site refs against tenant data
    |
    v
EmailSignal persisted (GDPR-safe)
    |
    ├──→ Auto-route to TRM(s) if confidence ≥ threshold
    |       → ForecastAdjustmentTRM.evaluate_signal()
    |       → Creates powell_forecast_adjustment_decisions
    |
    └──→ Decision Stream alert for human review
```

### Signal Types

| Signal Type | Description | Primary TRM | Secondary TRM |
|------------|-------------|-------------|---------------|
| `demand_increase` | Customer signals higher demand | forecast_adjustment | inventory_buffer |
| `demand_decrease` | Customer signals lower demand / cancellation | forecast_adjustment | inventory_buffer |
| `supply_disruption` | Supplier cannot fulfill (shortage, force majeure) | po_creation | to_execution |
| `lead_time_change` | Supplier lead times extended/shortened | po_creation | inventory_buffer |
| `price_change` | Supplier price increase/decrease | po_creation | — |
| `quality_issue` | Quality defect, recall, non-conformance | quality_disposition | mo_execution |
| `new_product` | New product launch / introduction | forecast_adjustment | inventory_buffer |
| `discontinuation` | Product end-of-life / phase-out | forecast_adjustment | inventory_buffer |
| `order_exception` | Order-level issue (wrong quantity, damage) | order_tracking | atp_executor |
| `capacity_change` | Supplier capacity reduction / expansion | mo_execution | maintenance_scheduling |
| `regulatory` | Regulatory change affecting SC (no auto-route, escalate) | — | — |
| `general_inquiry` | Non-actionable general communication | — | — |

### Signal Lifecycle

```
INGESTED → CLASSIFIED → ROUTED → ACTED → DISMISSED
```

- **INGESTED**: Email received and PII-scrubbed
- **CLASSIFIED**: LLM extracted signal type, direction, urgency
- **ROUTED**: Sent to TRM(s) for evaluation; powell_*_decisions created
- **ACTED**: TRM recommendation accepted by human
- **DISMISSED**: Human determined signal is not actionable (with reason)

## PII Scrubber

The scrubber (`email_pii_scrubber.py`) uses regex patterns — no external NLP dependency required:

| Pattern | Action | Example |
|---------|--------|---------|
| Email addresses | → `[EMAIL]` | `john@acme.com` → `[EMAIL]` |
| Phone numbers | → `[PHONE]` | `+1 (555) 123-4567` → `[PHONE]` |
| Greeting names | → `[NAME]` | `Dear John,` → `Dear [NAME],` |
| Signature names | → `[NAME]` | `Best regards, Sarah Smith` → `Best regards, [NAME]` |
| Title-name patterns | → `[NAME]` | `John Smith, VP of Sales` → `[NAME], VP of Sales` |
| Name prefixes | → `[NAME]` | `From: John Smith` → `From: [NAME]` |
| Street addresses | → `[ADDRESS]` | `123 Main St` → `[ADDRESS]` |
| Signature blocks | Removed | Everything after `--` or `___` |

The scrubber preserves supply chain content: product names, quantities, dates, order numbers, SKU references.

### Domain → TradingPartner Resolution

```python
# Extract domain from From: header
"Sarah Johnson <sarah@acme-supplies.com>" → "acme-supplies.com"

# Resolve against TradingPartner table
SELECT id, tpartner_type, description FROM trading_partners
WHERE LOWER(description) LIKE '%acme%'
→ ("TP_ACME_001", "vendor", "ACME Supplies Inc.")

# Result stored on EmailSignal (company only, no person)
partner_name = "ACME Supplies Inc."
partner_type = "vendor"
```

## Email Connectors

### IMAP Connector

Standard IMAP4 connector for enterprise email (Exchange, Outlook, etc.):
- SSL/TLS support
- UID-based dedup (tracks `last_poll_uid` high-water mark)
- MIME parsing (handles multipart, HTML-to-text conversion)
- Configurable folder (default: INBOX)

### Gmail

For Gmail integration, use Google Workspace API with OAuth2 service account, or IMAP with app-specific password.

### Polling

Connections are polled at configurable intervals (default: 5 minutes). Manual polling is also available via the API.

## LLM Classification

Uses the Claude Skills client at the Haiku tier (~$0.0018/call). At 100 emails/day, cost is ~$5.40/month.

The classification prompt provides:
- Partner name and type (customer/vendor)
- Tenant's product families and site names for scope resolution
- The 12 valid signal types

The prompt returns structured JSON: signal_type, direction, magnitude_pct, confidence, urgency, summary, product_refs, site_refs, time_horizon_weeks, target_trm_types.

### Heuristic Fallback

When LLM is unavailable (air-gapped deployment, vLLM down):
- Keyword-based signal type detection ("shortage" → supply_disruption, "price increase" → price_change)
- Percentage extraction via regex
- Lower confidence scores (0.2-0.4)
- Maintains service availability without LLM

## Integration Points

### ForecastAdjustmentTRM

Demand signals create `ForecastAdjustmentState` objects with `source="email"`:

```python
state = ForecastAdjustmentState(
    signal_id=f"email_{signal.id}",
    product_id=product_id,
    site_id=site_id,
    source="email",
    signal_type=signal.signal_type,
    signal_text=signal.signal_summary,
    signal_confidence=signal.signal_confidence,
    direction=signal.signal_direction,
    magnitude_hint=signal.signal_magnitude_pct,
)
rec = ForecastAdjustmentTRM(site_id).evaluate_signal(state)
```

This feeds the existing `signal_source="email"` path that was already designed in the ForecastAdjustmentTRM.

### Decision Stream

Email signals appear in the Decision Stream as alerts for roles with `"email_signal"` in their `ROLE_RELEVANCE` set (SC_VP, EXECUTIVE, SOP_DIRECTOR, MPS_MANAGER). Deep-link goes to `/admin/email-signals`.

### Azirella

Email signals complement the Azirella directive capture. Azirella handles human intent ("I want to increase revenue in the SW region"). Email signals handle external intelligence ("our supplier just announced a 3-week lead time extension"). Both feed the same Powell cascade.

## Implementation

### Backend

| File | Purpose |
|------|---------|
| `backend/app/services/email_pii_scrubber.py` | PII removal (regex, no external deps) |
| `backend/app/services/email_signal_service.py` | Classification, routing, queries |
| `backend/app/services/email_connector.py` | IMAP connector |
| `backend/app/api/endpoints/email_signals.py` | REST API endpoints |
| `backend/app/models/email_signal.py` | EmailSignal + EmailConnection models |
| `backend/migrations/versions/20260311_email_signals.py` | Database migration |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/pages/admin/EmailSignalsDashboard.jsx` | 4-tab admin page |

Dashboard tabs:
1. **Signals** — Table of ingested signals with expand-for-detail, dismiss action
2. **Connections** — Configure IMAP connections, test, poll, domain filters
3. **Analytics** — Signal type breakdown, partner breakdown, status distribution
4. **Test Ingestion** — Paste an email to test the classification pipeline

### API Endpoints

```bash
# Connections
POST /api/v1/email-signals/connections                # Create connection
GET  /api/v1/email-signals/connections                # List connections
PUT  /api/v1/email-signals/connections/{id}           # Update connection
DELETE /api/v1/email-signals/connections/{id}          # Delete connection
POST /api/v1/email-signals/connections/{id}/test      # Test connection
POST /api/v1/email-signals/connections/{id}/poll      # Manual poll

# Signals
GET  /api/v1/email-signals/signals                    # List (filterable)
GET  /api/v1/email-signals/signals/{id}               # Detail
POST /api/v1/email-signals/signals/{id}/dismiss       # Dismiss
POST /api/v1/email-signals/signals/{id}/reclassify    # Re-classify

# Dashboard & testing
GET  /api/v1/email-signals/dashboard                  # Summary stats
POST /api/v1/email-signals/ingest-manual              # Manual email paste
```

### Database

**Table: `email_connections`** — IMAP/Gmail inbox configurations per tenant
**Table: `email_signals`** — GDPR-safe classified signals with full audit trail

Key columns on `email_signals`:
- `sender_domain` — GDPR-safe company identification
- `resolved_partner_id` → `trading_partners.id`
- `body_scrubbed` — PII-removed email text
- `signal_type`, `signal_direction`, `signal_magnitude_pct`, `signal_confidence`, `signal_urgency`
- `resolved_product_ids`, `resolved_site_ids` — Scope matched against tenant data
- `target_trm_types` — Which TRMs the signal was routed to
- `status` — INGESTED → CLASSIFIED → ROUTED → ACTED → DISMISSED

## Cost Model

| Volume | LLM Cost | Notes |
|--------|----------|-------|
| 10 emails/day | ~$0.54/mo | Small deployment |
| 100 emails/day | ~$5.40/mo | Typical mid-market |
| 1000 emails/day | ~$54/mo | Large enterprise |

Heuristic fallback (air-gapped): $0/mo, lower accuracy (~0.4 confidence vs ~0.8 with LLM).

## Design Principles

1. **GDPR by design** — PII is scrubbed before persistence, not after. The system never sees or stores personal identity.

2. **Emails are signal sources, not decision types** — We don't create a 12th TRM for emails. Instead, emails feed the existing `ForecastAdjustmentTRM` (demand signals), `POCreationTRM` (supply signals), etc.

3. **Company, not person** — The valuable SC intelligence is "ACME Supplies is extending lead times", not "Sarah Johnson sent an email". Domain→TradingPartner resolution captures the company context without personal identity.

4. **Confidence-gated auto-routing** — Only high-confidence signals (≥0.6 default) are auto-routed to TRMs. Low-confidence signals are surfaced for human review.

5. **Testable without infrastructure** — The manual ingestion endpoint (`/ingest-manual`) allows testing the full classification pipeline by pasting email text, without configuring an actual IMAP connection.
