"""
Infor ION API Gateway Connector

Provides connectivity to Infor M3/LN/CloudSuite via the ION API Gateway (REST + OAuth 2.0).

Authentication: OAuth 2.0 Bearer tokens via .ionapi credential files.
The .ionapi file contains ClientID, ClientSecret, TokenURL, and IFS base URL.

ION API Gateway reference:
    https://docs.infor.com/inforos/2025.x/en-us/useradminlib_cloud/apigatewayag_cloud/

M3 API pattern:
    GET /M3/m3api-rest/v2/execute/{MI_Program}/{Transaction}
    Example: GET .../execute/MMS200MI/Get?ITNO=ABC123

SDK reference:
    https://github.com/infor-cloud/ion-api-sdk

Usage:
    connector = InforConnector(InforConnectionConfig(
        ionapi_file="/path/to/credentials.ionapi",
    ))
    await connector.authenticate()
    items = await connector.m3_api("MMS200MI", "LstByNumber", params={"NFTR": 1})
    pos = await connector.m3_api("PPS200MI", "LstByNumber")
"""

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class InforConnectionConfig:
    """Configuration for an Infor ION API Gateway connection.

    Primary auth: .ionapi credential file (JSON with OAuth2 params).
    Alternative: explicit client_id/client_secret/token_url for environments
    where the .ionapi file is not available.
    """
    # .ionapi file path (preferred — contains all OAuth2 params)
    ionapi_file: Optional[str] = None

    # Explicit OAuth2 params (used if ionapi_file not provided)
    base_url: str = ""              # ION API Gateway base (e.g., https://mingle-ionapi.inforcloudsuite.com/TENANT)
    token_url: str = ""             # OAuth2 token endpoint
    client_id: str = ""
    client_secret: str = ""
    username: str = ""              # Resource Owner grant (optional)
    password: str = ""              # Resource Owner grant (optional)

    # M3-specific
    m3_company: str = ""            # M3 company number (CONO), e.g., "100"
    m3_division: str = ""           # M3 division (DIVI), e.g., "AAA"

    timeout: int = 120
    verify_ssl: bool = True

    # CSV-based extraction (offline)
    csv_directory: Optional[str] = None

    def __post_init__(self):
        """Load .ionapi file if provided."""
        if self.ionapi_file and Path(self.ionapi_file).exists():
            self._load_ionapi()

    def _load_ionapi(self):
        """Parse .ionapi credential file.

        Format (JSON):
        {
            "ti": "TENANT_ID",
            "cn": "CLIENT_NAME",
            "dt": "v2",
            "ci": "CLIENT_ID_HERE",
            "cs": "CLIENT_SECRET_HERE",
            "iu": "https://mingle-ionapi.inforcloudsuite.com",
            "pu": "https://mingle-sso.inforcloudsuite.com:443/TENANT/as/",
            "oa": "authorization.oauth2",
            "ot": "token.oauth2",
            "or": "revoke_token.oauth2",
            "ev": "M3_ENDPOINT_VALUE",
            "v": "1.0",
            "saession_id": "..."
        }
        """
        with open(self.ionapi_file, encoding="utf-8") as f:
            creds = json.load(f)

        self.client_id = creds.get("ci", self.client_id)
        self.client_secret = creds.get("cs", self.client_secret)

        # Build token URL from pu (base SSO) + ot (token path)
        pu = creds.get("pu", "").rstrip("/")
        ot = creds.get("ot", "token.oauth2")
        if pu:
            self.token_url = f"{pu}/{ot}"

        # Build base URL from iu (ION API base) + ti (tenant)
        iu = creds.get("iu", "").rstrip("/")
        ti = creds.get("ti", "")
        if iu and ti:
            self.base_url = f"{iu}/{ti}"
        elif iu:
            self.base_url = iu


class InforConnector:
    """REST connector for Infor via the ION API Gateway.

    Supports two API patterns:
    1. M3 MI Programs — structured record-level access (primary for extraction)
       GET /M3/m3api-rest/v2/execute/{MI}/{Transaction}?{params}
    2. ION BOD API — OAGIS document exchange (async pub/sub)

    OAuth2 flow: Client Credentials or Resource Owner Password grant.
    Access tokens are cached and auto-refreshed.

    Pagination: M3 APIs use NFTR (next filter) / maxrecs pattern.
    ION APIs use standard offset/limit.
    """

    def __init__(self, config: InforConnectionConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._authenticated: bool = False

    # ── Connection Lifecycle ─────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            conn = aiohttp.TCPConnector(ssl=self.config.verify_ssl)
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(
                connector=conn,
                timeout=timeout,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._authenticated = False

    # ── Authentication ───────────────────────────────────────────────────

    async def authenticate(self) -> bool:
        """Obtain an OAuth2 access token from the Infor SSO.

        Tries Client Credentials grant first; falls back to Resource Owner
        Password grant if username/password are provided.
        """
        session = await self._get_session()

        # Build token request
        data = {
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }

        # If username/password provided, use Resource Owner grant
        if self.config.username and self.config.password:
            data["grant_type"] = "password"
            data["username"] = self.config.username
            data["password"] = self.config.password

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            async with session.post(
                self.config.token_url,
                data=data,
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    token_data = await resp.json()
                    self._access_token = token_data["access_token"]
                    expires_in = token_data.get("expires_in", 7200)
                    self._token_expires = datetime.utcnow() + timedelta(
                        seconds=expires_in - 60  # refresh 60s before expiry
                    )
                    self._authenticated = True
                    logger.info(
                        "Infor ION OAuth2 token obtained (expires in %ds)",
                        expires_in,
                    )
                    return True
                else:
                    text = await resp.text()
                    logger.error(
                        "Infor OAuth2 token request failed (%d): %s",
                        resp.status,
                        text[:300],
                    )
                    return False
        except Exception as e:
            logger.error("Infor OAuth2 error: %s", e)
            return False

    async def _ensure_token(self):
        """Re-authenticate if token is expired or missing."""
        if (
            not self._authenticated
            or not self._access_token
            or (self._token_expires and datetime.utcnow() >= self._token_expires)
        ):
            await self.authenticate()

    def _auth_headers(self) -> Dict[str, str]:
        """Return Authorization header with current bearer token."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> Dict[str, Any]:
        """Test connectivity by requesting a token and querying M3 company info."""
        ok = await self.authenticate()
        if not ok:
            return {"connected": False, "error": "OAuth2 authentication failed"}

        try:
            # Try M3 company info (CRS610MI/GetBasicData or CMS100MI)
            records = await self.m3_api("CRS610MI", "GetBasicData", params={
                "CUNO": self.config.m3_company or "100",
            })
            return {
                "connected": True,
                "base_url": self.config.base_url,
                "m3_company": self.config.m3_company,
                "token_valid": True,
            }
        except Exception as e:
            # Token works even if M3 query fails
            return {
                "connected": True,
                "base_url": self.config.base_url,
                "token_valid": True,
                "m3_test": str(e),
            }

    # ── M3 MI Program API ────────────────────────────────────────────────

    async def m3_api(
        self,
        program: str,
        transaction: str,
        *,
        params: Optional[Dict[str, str]] = None,
        max_records: int = 0,
    ) -> List[Dict[str, Any]]:
        """Call an M3 MI program transaction via the ION API Gateway.

        Args:
            program: MI program name (e.g., "MMS200MI" for Item Master)
            transaction: Transaction name (e.g., "LstByNumber", "Get", "Add")
            params: Query parameters (M3 field codes, e.g., {"ITNO": "ABC123"})
            max_records: Max records to return. 0 = all (with pagination).

        Returns:
            List of record dicts with M3 field names as keys.

        M3 API pattern:
            GET {base_url}/M3/m3api-rest/v2/execute/{program}/{transaction}
            Response: {"results": [{"records": [{"ITNO": "...", "ITDS": "..."}]}]}
        """
        await self._ensure_token()
        session = await self._get_session()

        url = f"{self.config.base_url}/M3/m3api-rest/v2/execute/{program}/{transaction}"
        query_params = dict(params or {})

        # Add company/division if configured
        if self.config.m3_company and "CONO" not in query_params:
            query_params["CONO"] = self.config.m3_company
        if self.config.m3_division and "DIVI" not in query_params:
            query_params["DIVI"] = self.config.m3_division

        # M3 APIs support maxrecs for pagination
        if max_records > 0:
            query_params["maxrecs"] = str(max_records)

        all_records: List[Dict] = []

        try:
            async with session.get(
                url,
                params=query_params,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(
                        "M3 API %s/%s failed (%d): %s",
                        program, transaction, resp.status, text[:300],
                    )
                    return []

                data = await resp.json()

                # M3 API response structure
                results = data.get("results", [])
                for result in results:
                    records = result.get("records", [])
                    all_records.extend(records)

                # Check for nrOfRecords metadata
                metadata = data.get("metadata", {})
                nr_of_records = metadata.get("nrOfRecords", len(all_records))
                logger.debug(
                    "M3 %s/%s: %d records (total: %s)",
                    program, transaction, len(all_records), nr_of_records,
                )

        except Exception as e:
            logger.error("M3 API %s/%s error: %s", program, transaction, e)

        return all_records[:max_records] if max_records > 0 else all_records

    # ── ION API (generic REST) ───────────────────────────────────────────

    async def ion_get(
        self,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Generic GET request to the ION API Gateway.

        Args:
            path: API path relative to base_url (e.g., "/IONSERVICES/api/...")
            params: Query parameters
        """
        await self._ensure_token()
        session = await self._get_session()

        url = f"{self.config.base_url}{path}"
        try:
            async with session.get(
                url,
                params=params,
                headers=self._auth_headers(),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    logger.error("ION GET %s failed (%d): %s", path, resp.status, text[:300])
                    return {}
        except Exception as e:
            logger.error("ION GET %s error: %s", path, e)
            return {}

    # ── Bulk Extraction ──────────────────────────────────────────────────

    async def extract_entity(
        self,
        entity: str,
        mi_program: str,
        transaction: str = "LstByNumber",
        params: Optional[Dict[str, str]] = None,
    ) -> List[Dict]:
        """Extract all records for an entity via its M3 MI program.

        Args:
            entity: Logical entity name (for logging/registry lookup)
            mi_program: M3 MI program (e.g., "MMS200MI")
            transaction: List transaction (e.g., "LstByNumber", "Lst")
            params: Additional query params
        """
        logger.info("Extracting %s via %s/%s...", entity, mi_program, transaction)
        records = await self.m3_api(mi_program, transaction, params=params)
        logger.info("  %s: %d records", entity, len(records))
        return records

    async def extract_all(
        self,
        entities: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict]]:
        """Extract multiple entities using the Infor entity registry.

        Returns {entity_name: [records]}.
        """
        from app.models.infor_staging import INFOR_ENTITY_REGISTRY

        if entities is None:
            entities = list(INFOR_ENTITY_REGISTRY.keys())

        result = {}
        for entity in entities:
            meta = INFOR_ENTITY_REGISTRY.get(entity, {})
            mi_program = meta.get("mi_program", "")
            transaction = meta.get("list_transaction", "LstByNumber")

            if not mi_program:
                logger.warning("No MI program for %s, skipping", entity)
                result[entity] = []
                continue

            try:
                records = await self.extract_entity(
                    entity, mi_program, transaction,
                )
                result[entity] = records
            except Exception as e:
                logger.warning("Failed to extract %s: %s", entity, e)
                result[entity] = []

        return result

    # ── CSV/JSON Extraction ──────────────────────────────────────────────

    def extract_from_csv(self, entity: str) -> List[Dict]:
        """Load entity data from a CSV or JSON file (offline extraction).

        Expects files named after the entity:
            {csv_directory}/{entity}.csv   — CSV with header row
            {csv_directory}/{entity}.json  — JSON array of objects
        Also tries the OAGIS noun name as fallback.
        """
        if not self.config.csv_directory:
            return []

        from app.models.infor_staging import INFOR_ENTITY_TO_NOUN
        noun = INFOR_ENTITY_TO_NOUN.get(entity, "")
        base_dir = Path(self.config.csv_directory)

        # Try JSON first, then CSV
        for name in [entity, noun]:
            if not name:
                continue
            json_path = base_dir / f"{name}.json"
            if json_path.exists():
                with open(json_path, encoding="utf-8-sig") as f:
                    data = json.load(f)
                rows = data if isinstance(data, list) else data.get("value", data.get("records", [data]))
                logger.info("  JSON %s: %d records", json_path.name, len(rows))
                return rows

        for name in [entity, noun]:
            if not name:
                continue
            csv_path = base_dir / f"{name}.csv"
            if csv_path.exists():
                with open(csv_path, encoding="utf-8-sig") as f:
                    rows = list(csv.DictReader(f))
                logger.info("  CSV %s: %d records", csv_path.name, len(rows))
                return rows

        return []
