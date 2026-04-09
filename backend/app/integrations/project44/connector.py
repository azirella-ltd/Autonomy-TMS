"""
project44 API Connector

OAuth 2.0 Client Credentials connector for project44's REST API (v4).
Handles authentication, token refresh, rate limiting, and HTTP methods.

Usage:
    connector = P44Connector(P44ConnectionConfig(
        client_id="your-client-id",
        client_secret="your-client-secret",
    ))
    await connector.authenticate()
    shipment = await connector.get("/api/v4/shipments/{id}")
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import aiohttp
import json

logger = logging.getLogger(__name__)


@dataclass
class P44ConnectionConfig:
    """Configuration for a project44 API connection."""
    client_id: str = ""
    client_secret: str = ""
    # Environment
    base_url: str = "https://na12.api.project44.com"  # Production
    auth_url: str = "https://na12.api.project44.com/oauth/token"
    # Sandbox override
    use_sandbox: bool = False
    sandbox_base_url: str = "https://na12.api.sandbox.p-44.com"
    sandbox_auth_url: str = "https://na12.api.sandbox.p-44.com/oauth/token"
    # HTTP
    timeout: int = 30
    max_retries: int = 3
    retry_backoff_sec: float = 1.0
    # Rate limiting (p44 default: 100 req/sec)
    rate_limit_per_sec: int = 80  # Conservative headroom
    # Webhook
    webhook_secret: str = ""  # For webhook signature verification

    @property
    def effective_base_url(self) -> str:
        return self.sandbox_base_url if self.use_sandbox else self.base_url

    @property
    def effective_auth_url(self) -> str:
        return self.sandbox_auth_url if self.use_sandbox else self.auth_url


class P44Connector:
    """
    OAuth 2.0 connector for project44's REST API.

    Follows the same connection-test-extract pattern as D365/SAP connectors.
    Thread-safe token refresh with automatic retry on 401.
    """

    def __init__(self, config: P44ConnectionConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._token_lock = asyncio.Lock()
        self._request_semaphore: Optional[asyncio.Semaphore] = None

    # ── Connection Lifecycle ─────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        self._access_token = None
        self._token_expiry = None

    async def __aenter__(self):
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # ── Authentication ───────────────────────────────────────────────────

    async def authenticate(self) -> bool:
        """Obtain OAuth 2.0 bearer token via client credentials grant."""
        async with self._token_lock:
            # Skip if token is still valid (with 60s buffer)
            if self._access_token and self._token_expiry:
                if datetime.utcnow() < self._token_expiry - timedelta(seconds=60):
                    return True

            session = await self._get_session()
            auth_url = self.config.effective_auth_url

            payload = {
                "grant_type": "client_credentials",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            }

            try:
                async with session.post(
                    auth_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(f"P44 auth failed: {resp.status} — {body}")
                        return False

                    data = await resp.json()
                    self._access_token = data["access_token"]
                    expires_in = data.get("expires_in", 3600)
                    self._token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
                    logger.info(f"P44 authenticated, token expires in {expires_in}s")
                    return True

            except Exception as e:
                logger.error(f"P44 auth exception: {e}")
                return False

    async def _ensure_token(self):
        """Ensure we have a valid token, refresh if needed."""
        if not self._access_token or not self._token_expiry:
            await self.authenticate()
        elif datetime.utcnow() >= self._token_expiry - timedelta(seconds=60):
            await self.authenticate()

    def _auth_headers(self) -> Dict[str, str]:
        """Return authorization headers."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    # ── Rate Limiting ────────────────────────────────────────────────────

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazy-init rate limit semaphore."""
        if self._request_semaphore is None:
            self._request_semaphore = asyncio.Semaphore(self.config.rate_limit_per_sec)
        return self._request_semaphore

    # ── HTTP Methods ─────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute an HTTP request against the p44 API.

        Handles: token refresh, retries with backoff, rate limiting.
        Returns parsed JSON response or raises on failure.
        """
        await self._ensure_token()
        session = await self._get_session()
        url = f"{self.config.effective_base_url}{path}"

        sem = self._get_semaphore()
        async with sem:
            try:
                kwargs: Dict[str, Any] = {
                    "headers": self._auth_headers(),
                }
                if params:
                    kwargs["params"] = params
                if data is not None:
                    kwargs["json"] = data

                async with session.request(method, url, **kwargs) as resp:
                    # Token expired — refresh and retry once
                    if resp.status == 401 and retry_count == 0:
                        logger.info("P44 token expired, refreshing...")
                        self._access_token = None
                        return await self._request(method, path, data, params, retry_count=1)

                    # Rate limited — backoff and retry
                    if resp.status == 429 and retry_count < self.config.max_retries:
                        retry_after = int(resp.headers.get("Retry-After", "2"))
                        logger.warning(f"P44 rate limited, retrying in {retry_after}s")
                        await asyncio.sleep(retry_after)
                        return await self._request(method, path, data, params, retry_count + 1)

                    # Server error — retry with backoff
                    if resp.status >= 500 and retry_count < self.config.max_retries:
                        backoff = self.config.retry_backoff_sec * (2 ** retry_count)
                        logger.warning(f"P44 server error {resp.status}, retry in {backoff}s")
                        await asyncio.sleep(backoff)
                        return await self._request(method, path, data, params, retry_count + 1)

                    # Read response
                    body = await resp.text()
                    if resp.status >= 400:
                        logger.error(f"P44 {method} {path} → {resp.status}: {body[:500]}")
                        raise P44APIError(resp.status, body, path)

                    # 204 No Content
                    if resp.status == 204 or not body.strip():
                        return {"status": resp.status}

                    return json.loads(body)

            except aiohttp.ClientError as e:
                if retry_count < self.config.max_retries:
                    backoff = self.config.retry_backoff_sec * (2 ** retry_count)
                    logger.warning(f"P44 connection error: {e}, retry in {backoff}s")
                    await asyncio.sleep(backoff)
                    return await self._request(method, path, data, params, retry_count + 1)
                raise

    async def get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """GET request to p44 API."""
        return await self._request("GET", path, params=params)

    async def post(self, path: str, data: Dict) -> Dict[str, Any]:
        """POST request to p44 API."""
        return await self._request("POST", path, data=data)

    async def put(self, path: str, data: Dict) -> Dict[str, Any]:
        """PUT request to p44 API."""
        return await self._request("PUT", path, data=data)

    async def delete(self, path: str) -> Dict[str, Any]:
        """DELETE request to p44 API."""
        return await self._request("DELETE", path)

    # ── Connection Test ──────────────────────────────────────────────────

    async def test_connection(self) -> Dict[str, Any]:
        """Test connectivity to p44 API. Returns status and account info."""
        try:
            authenticated = await self.authenticate()
            if not authenticated:
                return {"connected": False, "error": "Authentication failed"}

            # Try a lightweight endpoint to verify access
            result = await self.get("/api/v4/capacityproviders/accounts")
            return {
                "connected": True,
                "base_url": self.config.effective_base_url,
                "sandbox": self.config.use_sandbox,
                "account_count": len(result.get("results", [])) if isinstance(result, dict) else 0,
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}


class P44APIError(Exception):
    """project44 API error with status code and response body."""

    def __init__(self, status_code: int, body: str, path: str = ""):
        self.status_code = status_code
        self.body = body
        self.path = path
        super().__init__(f"P44 API error {status_code} on {path}: {body[:200]}")
