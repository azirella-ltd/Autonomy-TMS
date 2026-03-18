"""GDPR-compliant PII scrubber for email content.

Strips personal identifiers (names, email addresses, phone numbers,
physical addresses) while preserving supply chain context (company names,
product references, quantities, dates, terms).

The sender's domain is extracted BEFORE scrubbing to enable
TradingPartner resolution (company identification without personal identity).
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class ScrubResult:
    """Result of PII scrubbing."""
    scrubbed_text: str
    sender_domain: str
    sender_display_name: Optional[str] = None  # NOT stored — used only for logging
    pii_items_removed: int = 0


# ── Regex patterns ───────────────────────────────────────────────────────────

# Email addresses
_EMAIL_RE = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE,
)

# Phone numbers — international formats
_PHONE_RE = re.compile(
    r'(?:(?:\+\d{1,3}[\s\-.]?)?\(?\d{1,4}\)?[\s\-.]?\d{1,4}[\s\-.]?\d{1,9})',
)

# Physical street addresses (US/EU patterns)
_ADDRESS_RE = re.compile(
    r'\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:St(?:reet)?|Ave(?:nue)?|Rd|Road|Blvd|Boulevard|Dr(?:ive)?|Ln|Lane|Way|Pl(?:ace)?|Ct|Court)\.?',
    re.IGNORECASE,
)

# Greeting patterns: "Dear John", "Hi Sarah,"
_GREETING_RE = re.compile(
    r'(?:Dear|Hi|Hello|Hey)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[,:]?',
)

# Signature patterns: "Regards, John Smith", "Best, Jane"
_SIGNATURE_RE = re.compile(
    r'(?:(?:Best|Kind|Warm|Sincerely|Regards|Thanks|Thank\s+you|Cheers|Yours)\s*(?:regards|wishes)?\s*,?\s*\n\s*)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})',
    re.IGNORECASE | re.MULTILINE,
)

# Standalone name-like patterns after common prefixes
_NAME_PREFIX_RE = re.compile(
    r'(?:From|Sent\s+by|Contact|Attn|Attention)\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})',
)

# Job title + name patterns: "John Smith, VP of Supply Chain"
_TITLE_NAME_RE = re.compile(
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*,\s*(?:VP|Director|Manager|Head|Chief|SVP|EVP|CEO|CFO|COO|CTO)',
)

# Postal/ZIP codes
_POSTAL_RE = re.compile(
    r'\b\d{5}(?:-\d{4})?\b'  # US ZIP
    r'|\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',  # UK postcode
    re.IGNORECASE,
)


def extract_sender_domain(from_header: str) -> str:
    """Extract domain from email From header.

    Handles formats:
    - "John Smith <john@acme-corp.com>" → "acme-corp.com"
    - "john@acme-corp.com" → "acme-corp.com"
    - "<john@acme-corp.com>" → "acme-corp.com"
    """
    match = _EMAIL_RE.search(from_header)
    if match:
        email = match.group(0)
        return email.split("@")[1].lower()
    return "unknown"


def scrub_email(text: str, from_header: str = "") -> ScrubResult:
    """Remove PII from email text while preserving SC context.

    Args:
        text: Raw email body (plain text, HTML already stripped).
        from_header: The From: header for domain extraction.

    Returns:
        ScrubResult with scrubbed text, sender domain, and PII removal count.
    """
    domain = extract_sender_domain(from_header)
    count = 0
    scrubbed = text

    # 1. Replace email addresses
    found_emails = _EMAIL_RE.findall(scrubbed)
    count += len(found_emails)
    scrubbed = _EMAIL_RE.sub("[EMAIL]", scrubbed)

    # 2. Replace phone numbers (careful: avoid matching quantities like "1000 units")
    phone_matches = _PHONE_RE.findall(scrubbed)
    for pm in phone_matches:
        # Only replace if it looks phone-like (has separators or starts with +)
        if any(c in pm for c in ['+', '-', '(', ')']) or len(pm.strip()) >= 10:
            scrubbed = scrubbed.replace(pm, "[PHONE]", 1)
            count += 1

    # 3. Replace greeting names
    for m in _GREETING_RE.finditer(scrubbed):
        name = m.group(1)
        scrubbed = scrubbed.replace(m.group(0), m.group(0).replace(name, "[NAME]"), 1)
        count += 1

    # 4. Replace signature names
    for m in _SIGNATURE_RE.finditer(scrubbed):
        name = m.group(1)
        scrubbed = scrubbed.replace(name, "[NAME]", 1)
        count += 1

    # 5. Replace name prefix patterns (From: John Smith)
    for m in _NAME_PREFIX_RE.finditer(scrubbed):
        name = m.group(1)
        scrubbed = scrubbed.replace(name, "[NAME]", 1)
        count += 1

    # 6. Replace title-name patterns
    for m in _TITLE_NAME_RE.finditer(scrubbed):
        name = m.group(1)
        scrubbed = scrubbed.replace(name, "[NAME]", 1)
        count += 1

    # 7. Replace street addresses
    addr_matches = _ADDRESS_RE.findall(scrubbed)
    count += len(addr_matches)
    scrubbed = _ADDRESS_RE.sub("[ADDRESS]", scrubbed)

    # 8. Clean up signature blocks (lines with only [NAME], [EMAIL], [PHONE])
    lines = scrubbed.split('\n')
    cleaned_lines = []
    in_signature = False
    for line in lines:
        stripped = line.strip()
        # Detect signature start
        if stripped.lower() in ('--', '---', '- -', '____'):
            in_signature = True
            continue
        if in_signature:
            # In signature block, keep only lines with SC content
            if any(kw in stripped.lower() for kw in
                   ['order', 'shipment', 'delivery', 'quantity', 'sku', 'po#', 'ref']):
                cleaned_lines.append(line)
            continue
        cleaned_lines.append(line)

    scrubbed = '\n'.join(cleaned_lines)

    # Collapse multiple blank lines
    scrubbed = re.sub(r'\n{3,}', '\n\n', scrubbed).strip()

    return ScrubResult(
        scrubbed_text=scrubbed,
        sender_domain=domain,
        pii_items_removed=count,
    )


def scrub_subject(subject: str) -> str:
    """Scrub PII from email subject line."""
    result = _EMAIL_RE.sub("[EMAIL]", subject)
    # Remove Re:/Fwd: chains but keep substance
    result = re.sub(r'^(?:Re|Fwd|FW)\s*:\s*', '', result, flags=re.IGNORECASE).strip()
    return result
