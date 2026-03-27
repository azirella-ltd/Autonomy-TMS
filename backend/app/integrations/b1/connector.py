"""
SAP Business One Service Layer Connector

Provides connectivity to SAP Business One via the Service Layer REST API (OData v4).

Authentication: Session-based (POST /Login with CompanyDB, UserName, Password).
The Service Layer returns a session cookie (B1SESSION) valid for 30 minutes.

Service Layer API Reference:
    https://help.sap.com/doc/056f69366b5345a386bb8149f1700c19/10.0/en-US/Service%20Layer%20API%20Reference.html

Usage:
    connector = B1Connector(B1ConnectionConfig(
        base_url="https://my-b1-server:50000/b1s/v2",
        company_db="SBODemoUS",
        username="manager",
        password="manager",
    ))
    await connector.login()
    items = await connector.query("Items", top=100)
    bps = await connector.query("BusinessPartners", filters="CardType eq 'cSupplier'")
"""

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class B1ConnectionConfig:
    """Configuration for a SAP Business One Service Layer connection."""
    base_url: str = ""          # e.g. https://server:50000/b1s/v2
    company_db: str = ""        # e.g. SBODemoUS, SBODemoGB
    username: str = "manager"
    password: str = "manager"
    timeout: int = 120
    verify_ssl: bool = False    # B1 often uses self-signed certs
    # CSV-based extraction (offline)
    csv_directory: Optional[str] = None


class B1Connector:
    """OData v4 connector for SAP Business One Service Layer.

    Session-based auth: POST /Login → B1SESSION cookie → all subsequent
    requests carry the cookie. Session expires after 30 min idle.

    Pagination: B1 returns odata.nextLink for result sets > 20 (default page size).
    Use $top and $skip for explicit pagination.
    """

    def __init__(self, config: B1ConnectionConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_id: Optional[str] = None
        self._logged_in: bool = False

    # ── Connection Lifecycle ─────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            conn = aiohttp.TCPConnector(ssl=self.config.verify_ssl)
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(
                connector=conn,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            # Logout to release server session
            if self._logged_in:
                try:
                    await self._session.post(f"{self.config.base_url}/Logout")
                except Exception:
                    pass
            await self._session.close()
            self._logged_in = False

    # ── Authentication ───────────────────────────────────────────────────

    async def login(self) -> bool:
        """Authenticate via Service Layer /Login endpoint.

        Returns True on success. The session cookie (B1SESSION) is
        automatically managed by aiohttp's cookie jar.
        """
        session = await self._get_session()
        payload = {
            "CompanyDB": self.config.company_db,
            "UserName": self.config.username,
            "Password": self.config.password,
        }
        url = f"{self.config.base_url}/Login"
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._session_id = data.get("SessionId")
                    self._logged_in = True
                    logger.info("B1 Service Layer login OK (company=%s)", self.config.company_db)
                    return True
                else:
                    text = await resp.text()
                    logger.error("B1 login failed (%d): %s", resp.status, text[:200])
                    return False
        except Exception as e:
            logger.error("B1 login error: %s", e)
            return False

    async def test_connection(self) -> Dict[str, Any]:
        """Test connectivity and return company info."""
        if not self._logged_in:
            ok = await self.login()
            if not ok:
                return {"connected": False, "error": "Login failed"}

        try:
            info = await self.query("CompanyService_GetCompanyInfo", raw_path=True)
            return {
                "connected": True,
                "company_db": self.config.company_db,
                "company_name": info.get("CompanyName", ""),
                "version": info.get("Version", ""),
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    # ── Query / CRUD ─────────────────────────────────────────────────────

    async def query(
        self,
        entity: str,
        *,
        filters: Optional[str] = None,
        select: Optional[str] = None,
        top: int = 0,
        skip: int = 0,
        order_by: Optional[str] = None,
        expand: Optional[str] = None,
        raw_path: bool = False,
    ) -> List[Dict[str, Any]]:
        """Query a Service Layer entity with OData v4 parameters.

        Args:
            entity: Service Layer entity name (e.g., "Items", "BusinessPartners")
            filters: OData $filter expression
            select: Comma-separated field list ($select)
            top: Maximum records to return ($top). 0 = all (with pagination).
            skip: Records to skip ($skip)
            order_by: Sort expression ($orderby)
            expand: Related entities to expand ($expand)
            raw_path: If True, use entity as a raw URL path (for service calls)

        Returns:
            List of entity records as dicts.
        """
        if not self._logged_in:
            await self.login()

        session = await self._get_session()

        if raw_path:
            url = f"{self.config.base_url}/{entity}"
            async with session.post(url, json={}) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {}

        # Build query params
        params = {}
        if filters:
            params["$filter"] = filters
        if select:
            params["$select"] = select
        if top > 0:
            params["$top"] = str(top)
        if skip > 0:
            params["$skip"] = str(skip)
        if order_by:
            params["$orderby"] = order_by
        if expand:
            params["$expand"] = expand

        url = f"{self.config.base_url}/{entity}"

        # Paginate through all results
        all_records: List[Dict] = []
        while url:
            async with session.get(url, params=params if not all_records else None) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error("B1 query %s failed (%d): %s", entity, resp.status, text[:200])
                    break

                data = await resp.json()
                records = data.get("value", [])
                all_records.extend(records)

                # Follow odata.nextLink for pagination
                next_link = data.get("odata.nextLink") or data.get("@odata.nextLink")
                if next_link and (top == 0 or len(all_records) < top):
                    # nextLink is relative in B1
                    if next_link.startswith("http"):
                        url = next_link
                    else:
                        url = f"{self.config.base_url}/{next_link}"
                    params = None  # params already in nextLink
                else:
                    break

            if top > 0 and len(all_records) >= top:
                break

        return all_records[:top] if top > 0 else all_records

    async def get_count(self, entity: str, filters: Optional[str] = None) -> int:
        """Get the count of records for an entity."""
        if not self._logged_in:
            await self.login()

        session = await self._get_session()
        url = f"{self.config.base_url}/{entity}/$count"
        params = {"$filter": filters} if filters else {}
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                text = await resp.text()
                return int(text.strip())
            return 0

    # ── Bulk Extraction ──────────────────────────────────────────────────

    async def extract_entity(
        self,
        entity: str,
        select: Optional[str] = None,
        filters: Optional[str] = None,
    ) -> List[Dict]:
        """Extract all records for an entity (handles pagination)."""
        logger.info("Extracting %s...", entity)
        records = await self.query(entity, select=select, filters=filters)
        logger.info("  %s: %d records", entity, len(records))
        return records

    async def extract_all(
        self,
        entities: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict]]:
        """Extract multiple entities. Returns {entity_name: [records]}."""
        from app.models.b1_staging import B1_ENTITY_REGISTRY

        if entities is None:
            entities = list(B1_ENTITY_REGISTRY.keys())

        result = {}
        for entity in entities:
            try:
                records = await self.extract_entity(entity)
                result[entity] = records
            except Exception as e:
                logger.warning("Failed to extract %s: %s", entity, e)
                result[entity] = []

        return result

    # ── CSV Extraction ───────────────────────────────────────────────────

    def extract_from_csv(self, entity: str) -> List[Dict]:
        """Load entity data from a CSV file (offline extraction).

        Expects CSV files named after the Service Layer entity:
            {csv_directory}/{entity}.csv
        """
        if not self.config.csv_directory:
            return []

        csv_path = Path(self.config.csv_directory) / f"{entity}.csv"
        if not csv_path.exists():
            # Try DB table name
            from app.models.b1_staging import B1_ENTITY_TO_TABLE
            db_table = B1_ENTITY_TO_TABLE.get(entity, "")
            csv_path = Path(self.config.csv_directory) / f"{db_table}.csv"

        if not csv_path.exists():
            return []

        with open(csv_path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

        logger.info("  CSV %s: %d records", csv_path.name, len(rows))
        return rows
