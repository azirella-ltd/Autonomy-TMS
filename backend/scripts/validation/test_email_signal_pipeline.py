#!/usr/bin/env python3
"""G1: Email Signal Pipeline Validation"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Set minimum env vars for app imports (DB not actually used)
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://x:x@localhost:5432/x")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from datetime import date, datetime, timedelta

passed = 0
failed = 0
errors = []


def test(name, condition, detail=""):
    global passed, failed, errors
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} -- {detail}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"G1: Email Signal Pipeline Validation")
    print(f"{'='*60}")

    from app.services.email_pii_scrubber import (
        scrub_email,
        scrub_subject,
        extract_sender_domain,
        ScrubResult,
    )
    from app.models.email_signal import SIGNAL_TRM_ROUTING

    # ── Test 1: PII scrubber removes email addresses ──────────────────
    print("\n[Test 1] PII scrubber removes email addresses")
    body_with_email = (
        "Hello,\n\n"
        "Please contact john.smith@acme-corp.com for shipping inquiries.\n"
        "We need 500 units of SKU-1234 by March 15.\n\n"
        "Regards,\nSupply Team"
    )
    result = scrub_email(body_with_email, "John Smith <john.smith@acme-corp.com>")
    test(
        "Email address removed from body",
        "john.smith@acme-corp.com" not in result.scrubbed_text,
        f"Email still present in: {result.scrubbed_text[:100]}",
    )
    test(
        "Email replaced with [EMAIL] placeholder",
        "[EMAIL]" in result.scrubbed_text,
        "No [EMAIL] placeholder found",
    )
    test(
        "Sender domain extracted correctly",
        result.sender_domain == "acme-corp.com",
        f"Got domain: {result.sender_domain}",
    )

    # ── Test 2: PII scrubber removes phone numbers ────────────────────
    print("\n[Test 2] PII scrubber removes phone numbers")
    body_with_phone = (
        "Call us at +1-555-123-4567 for urgent matters.\n"
        "We can ship 200 pallets of product X next week.\n"
    )
    result_phone = scrub_email(body_with_phone, "ops@supplier.com")
    test(
        "Phone number removed from body",
        "+1-555-123-4567" not in result_phone.scrubbed_text,
        f"Phone still present in: {result_phone.scrubbed_text[:100]}",
    )
    test(
        "Phone replaced with [PHONE] placeholder",
        "[PHONE]" in result_phone.scrubbed_text,
        "No [PHONE] placeholder found",
    )

    # ── Test 3: PII scrubber removes personal names ───────────────────
    print("\n[Test 3] PII scrubber removes personal names (greeting/signature)")
    body_with_names = (
        "Dear Michael,\n\n"
        "We are experiencing a 15% increase in demand for Product Alpha.\n"
        "The forecast for Q2 needs to be adjusted upward.\n\n"
        "Best regards,\n"
        "Sarah Johnson"
    )
    result_names = scrub_email(body_with_names, "sarah@partner.com")
    test(
        "Greeting name replaced",
        "Michael" not in result_names.scrubbed_text
        or "[NAME]" in result_names.scrubbed_text,
        f"Name still present in: {result_names.scrubbed_text[:100]}",
    )
    test(
        "[NAME] placeholder used for scrubbed names",
        "[NAME]" in result_names.scrubbed_text,
        "No [NAME] placeholder found",
    )
    test(
        "PII items removed count > 0",
        result_names.pii_items_removed > 0,
        f"Count: {result_names.pii_items_removed}",
    )

    # ── Test 4: SC content preserved ──────────────────────────────────
    print("\n[Test 4] Supply chain content preserved after scrubbing")
    body_sc = (
        "Dear Buyer,\n\n"
        "We need to inform you that due to a raw material shortage,\n"
        "our lead time for Part XYZ-100 will increase by 2 weeks.\n"
        "Current inventory: 5,000 units. New delivery: April 30, 2026.\n"
        "Contact supply@vendor.com for updates.\n\n"
        "Thanks,\nProcurement Team"
    )
    result_sc = scrub_email(body_sc, "supply@vendor.com")
    test(
        "Product reference preserved (Part XYZ-100)",
        "XYZ-100" in result_sc.scrubbed_text,
        "Product reference removed",
    )
    test(
        "Quantity preserved (5,000 units)",
        "5,000" in result_sc.scrubbed_text,
        "Quantity removed",
    )
    test(
        "Date preserved (April 30)",
        "April 30" in result_sc.scrubbed_text,
        "Date removed",
    )
    test(
        "Lead time keyword preserved",
        "lead time" in result_sc.scrubbed_text.lower(),
        "Lead time keyword removed",
    )

    # ── Test 5: Signal type routing - demand_increase ─────────────────
    print("\n[Test 5] Signal type routing - demand_increase -> forecast_adjustment")
    trm_targets = SIGNAL_TRM_ROUTING.get("demand_increase", [])
    test(
        "demand_increase routes to forecast_adjustment",
        "forecast_adjustment" in trm_targets,
        f"Targets: {trm_targets}",
    )
    test(
        "demand_increase also routes to inventory_buffer",
        "inventory_buffer" in trm_targets,
        f"Targets: {trm_targets}",
    )

    # ── Test 6: Signal type routing - supply_disruption ────────────────
    print("\n[Test 6] Signal type routing - supply_disruption -> po_creation")
    trm_targets_sd = SIGNAL_TRM_ROUTING.get("supply_disruption", [])
    test(
        "supply_disruption routes to po_creation",
        "po_creation" in trm_targets_sd,
        f"Targets: {trm_targets_sd}",
    )
    test(
        "supply_disruption also routes to to_execution",
        "to_execution" in trm_targets_sd,
        f"Targets: {trm_targets_sd}",
    )

    # ── Test 7: Additional routing checks ─────────────────────────────
    print("\n[Test 7] Additional routing and completeness checks")
    test(
        "quality_issue routes to quality_disposition",
        "quality_disposition" in SIGNAL_TRM_ROUTING.get("quality_issue", []),
        f"Targets: {SIGNAL_TRM_ROUTING.get('quality_issue', [])}",
    )
    test(
        "lead_time_change routes to po_creation",
        "po_creation" in SIGNAL_TRM_ROUTING.get("lead_time_change", []),
        f"Targets: {SIGNAL_TRM_ROUTING.get('lead_time_change', [])}",
    )
    test(
        "general_inquiry has empty routing (informational only)",
        SIGNAL_TRM_ROUTING.get("general_inquiry") == [],
        f"Targets: {SIGNAL_TRM_ROUTING.get('general_inquiry')}",
    )

    # ── Test 8: extract_sender_domain handles formats ─────────────────
    print("\n[Test 8] Sender domain extraction formats")
    test(
        "Extracts domain from display name format",
        extract_sender_domain("John Smith <john@acme.com>") == "acme.com",
        f"Got {extract_sender_domain('John Smith <john@acme.com>')}",
    )
    test(
        "Extracts domain from bare email",
        extract_sender_domain("john@acme.com") == "acme.com",
        f"Got {extract_sender_domain('john@acme.com')}",
    )
    test(
        "Returns 'unknown' for unparseable header",
        extract_sender_domain("no-email-here") == "unknown",
        f"Got {extract_sender_domain('no-email-here')}",
    )

    # ── Test 9: scrub_subject ─────────────────────────────────────────
    print("\n[Test 9] Subject line scrubbing")
    test(
        "Re: prefix stripped",
        scrub_subject("Re: PO Update for March") == "PO Update for March",
        f"Got: {scrub_subject('Re: PO Update for March')}",
    )
    test(
        "Email in subject replaced",
        "[EMAIL]" in scrub_subject("Contact bob@partner.com about shipment"),
        f"Got: {scrub_subject('Contact bob@partner.com about shipment')}",
    )

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)
