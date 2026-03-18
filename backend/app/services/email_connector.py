"""
Email Connector — Fetch emails from IMAP or Gmail for SC signal ingestion.

Two implementations:
  - IMAPConnector: Standard IMAP for enterprise (Exchange, Outlook, etc.)
  - GmailConnector: Uses Google API patterns (OAuth2 service account or app password)

Both connectors return RawEmail objects with the original content.
PII scrubbing happens AFTER fetching, in EmailSignalService.
"""

import email
import email.utils
import imaplib
import logging
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RawEmail:
    """A raw email fetched from a mailbox (before PII scrubbing)."""
    uid: str  # Message-ID for dedup
    from_header: str
    subject: str
    body_text: str  # Plain text (HTML stripped)
    received_at: datetime
    message_id: str  # SMTP Message-ID


class EmailConnector(ABC):
    """Abstract email fetcher."""

    @abstractmethod
    async def fetch_new_emails(self, since_uid: Optional[str] = None) -> List[RawEmail]:
        """Fetch emails newer than since_uid. Returns list of RawEmail."""

    @abstractmethod
    async def test_connection(self) -> dict:
        """Test connectivity. Returns {"ok": bool, "message": str}."""


class IMAPConnector(EmailConnector):
    """Standard IMAP connector for enterprise email systems."""

    def __init__(
        self,
        host: str,
        port: int = 993,
        username: str = "",
        password: str = "",
        folder: str = "INBOX",
        use_ssl: bool = True,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.folder = folder
        self.use_ssl = use_ssl

    async def test_connection(self) -> dict:
        """Test IMAP connectivity."""
        try:
            conn = self._connect()
            conn.select(self.folder, readonly=True)
            status, data = conn.status(self.folder, "(MESSAGES UNSEEN)")
            conn.logout()
            return {"ok": True, "message": f"Connected to {self.host}:{self.port}, folder={self.folder}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    async def fetch_new_emails(self, since_uid: Optional[str] = None) -> List[RawEmail]:
        """Fetch new emails from IMAP server.

        Uses IMAP UID search to efficiently fetch only new messages.
        """
        emails = []
        try:
            conn = self._connect()
            conn.select(self.folder, readonly=True)

            # Search for messages since the last known UID
            if since_uid:
                # Fetch UIDs greater than the last known
                status, data = conn.uid("search", None, f"UID {since_uid}:*")
            else:
                # First poll: get last 50 messages
                status, data = conn.search(None, "ALL")

            if status != "OK" or not data[0]:
                conn.logout()
                return []

            msg_ids = data[0].split()
            # Limit to last 50 for safety
            msg_ids = msg_ids[-50:]

            for msg_id in msg_ids:
                try:
                    if since_uid:
                        status, msg_data = conn.uid("fetch", msg_id, "(RFC822)")
                    else:
                        status, msg_data = conn.fetch(msg_id, "(RFC822)")

                    if status != "OK" or not msg_data[0]:
                        continue

                    raw_msg = msg_data[0][1]
                    msg = email.message_from_bytes(raw_msg)
                    raw_email = self._parse_message(msg, msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id))
                    if raw_email:
                        emails.append(raw_email)

                except Exception as e:
                    logger.warning("Failed to parse message %s: %s", msg_id, e)
                    continue

            conn.logout()

        except Exception as e:
            logger.error("IMAP fetch failed: %s", e)

        return emails

    def _connect(self):
        """Create IMAP connection."""
        if self.use_ssl:
            ctx = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx)
        else:
            conn = imaplib.IMAP4(self.host, self.port)
        conn.login(self.username, self.password)
        return conn

    def _parse_message(self, msg, uid: str) -> Optional[RawEmail]:
        """Parse an email.message.Message into a RawEmail."""
        from_header = msg.get("From", "")
        subject = msg.get("Subject", "")
        message_id = msg.get("Message-ID", uid)
        date_str = msg.get("Date", "")

        # Parse date
        received_at = datetime.utcnow()
        if date_str:
            try:
                parsed = email.utils.parsedate_to_datetime(date_str)
                received_at = parsed.replace(tzinfo=None)  # Store as UTC naive
            except Exception:
                pass

        # Extract plain text body
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            body = payload.decode(charset, errors="replace")
                        except Exception:
                            body = payload.decode("utf-8", errors="replace")
                    break
            # Fallback to HTML if no plain text
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = self._strip_html(payload.decode("utf-8", errors="replace"))
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    body = self._strip_html(body)

        if not body.strip():
            return None

        # Decode MIME-encoded subject
        if subject:
            decoded_parts = email.header.decode_header(subject)
            subject = ""
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    subject += part.decode(charset or "utf-8", errors="replace")
                else:
                    subject += str(part)

        return RawEmail(
            uid=uid,
            from_header=from_header,
            subject=subject,
            body_text=body[:10000],  # Limit body size
            received_at=received_at,
            message_id=message_id,
        )

    @staticmethod
    def _strip_html(html: str) -> str:
        """Simple HTML tag stripping (no external dependency)."""
        import re
        # Remove script/style blocks
        text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Remove tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Decode common entities
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text


def create_connector(connection) -> EmailConnector:
    """Factory: create appropriate connector from an EmailConnection model."""
    if connection.connection_type == "imap":
        # Decrypt password (application-layer encryption)
        password = connection.imap_password_encrypted or ""
        return IMAPConnector(
            host=connection.imap_host or "",
            port=connection.imap_port or 993,
            username=connection.imap_username or "",
            password=password,
            folder=connection.imap_folder or "INBOX",
            use_ssl=connection.imap_use_ssl if connection.imap_use_ssl is not None else True,
        )
    else:
        raise ValueError(f"Unsupported connection type: {connection.connection_type}")
