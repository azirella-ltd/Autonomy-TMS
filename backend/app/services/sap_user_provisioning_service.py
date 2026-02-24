"""
SAP User Provisioning Service

Imports supply-chain-relevant users from SAP S/4HANA into the Autonomy
platform. Filters by authorization objects and transaction codes to ensure
only SC planning users are imported.
"""

import fnmatch
import logging
import re
from collections import defaultdict
from datetime import datetime, date
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.sap_user_import import SAPRoleMapping, SAPUserImportLog
from app.models.user import User, UserTypeEnum, PowellRoleEnum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SC Relevance Filter Constants
# ---------------------------------------------------------------------------

# Authorization objects whose presence in AGR_1251 marks a role as SC-relevant.
SC_AUTH_OBJECTS: set[str] = {
    # Purchasing
    "M_BEST_BSA", "M_BEST_EKG", "M_BEST_EKO", "M_BEST_WRK",
    # Purchase requisitions
    "M_BANF_BSA", "M_BANF_EKG", "M_BANF_WRK",
    # Production orders
    "C_AFKO_AWK", "C_AFKO_STA",
    # Internal orders
    "C_AUFK_AWK",
    # Sales orders
    "V_VBAK_AAT", "V_VBAK_VKO",
    # Material master
    "M_MATE_WRK", "M_MATE_STA",
    # FI posting (S&OP finance)
    "B_BSEG_BSA",
    # APO planning
    "/SAPAPO/RRP", "/SAPAPO/SDL",
}

# Transaction codes whose presence in AGR_TCODES marks a role as SC-relevant.
SC_TRANSACTION_CODES: set[str] = {
    # MRP
    "MD01", "MD02", "MD03", "MD04", "MD05", "MD06", "MD07",
    # MPS
    "MD40", "MD41", "MD42", "MD43",
    # Purchase requisitions
    "ME51N", "ME52N", "ME53N", "ME54N", "ME55",
    # Purchase orders
    "ME21N", "ME22N", "ME23N", "ME2N", "ME2M",
    # Sales orders
    "VA01", "VA02", "VA03", "VA05",
    # Production orders
    "CO01", "CO02", "CO03", "CO04", "COHV",
    # Deliveries
    "VL01N", "VL02N", "VL03N", "VL06O",
    # Material master
    "MM01", "MM02", "MM03", "MM60",
    # Stock overview
    "MMBE", "MB52", "MB51",
    # Inventory management
    "MIGO", "MB1A", "MB1B", "MB1C",
    # APO
    "/SAPAPO/RRP3", "/SAPAPO/SDP94", "/SAPAPO/POV",
    # S&OP / Demand
    "MC62", "MC63", "MC87", "MC88", "MC89",
    # Warehouse
    "LT01", "LT0A", "LT21",
}

# Role name patterns used as fallback when AGR_1251/AGR_TCODES not available.
_SC_ROLE_NAME_PATTERNS = [
    "MM_", "PP_", "SD_", "APO_", "SCM_", "IBP_",
    "PROCUREMENT", "PLANNING", "SUPPLY_CHAIN", "INVENTORY",
    "MRP", "MPS", "DEMAND", "WAREHOUSE", "LOGISTICS",
]


def is_sc_relevant_role(
    role_name: str,
    auth_objects: set[str],
    tcodes: set[str],
) -> bool:
    """Check if a SAP role grants SC planning access."""
    if auth_objects & SC_AUTH_OBJECTS:
        return True
    if tcodes & SC_TRANSACTION_CODES:
        return True
    name_upper = role_name.upper()
    return any(pat in name_upper for pat in _SC_ROLE_NAME_PATTERNS)


class SAPUserProvisioningService:
    """Import SC-relevant SAP users into the Autonomy platform."""

    def __init__(self, db: AsyncSession, group_id: int):
        self.db = db
        self.group_id = group_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def preview_import(
        self,
        raw_data: dict[str, list[dict]],
        filter_config: Optional[dict] = None,
    ) -> dict:
        """Dry-run: return proposed user mappings without writing DB records."""
        user_map = self._build_user_role_map(raw_data)
        effective_auth = self._effective_auth_objects(filter_config)
        effective_tcodes = self._effective_tcodes(filter_config)
        include_ustyp = (filter_config or {}).get("include_ustyp", ["A"])
        exclude_expired = (filter_config or {}).get("exclude_expired", True)

        mappings = await self._load_role_mappings()
        preview_rows = []
        role_dist: dict[str, int] = defaultdict(int)
        unmapped_roles: set[str] = set()

        for bname, info in user_map.items():
            # Filter: user type
            if info["ustyp"] not in include_ustyp:
                continue
            # Filter: expired
            if exclude_expired and info.get("gltgb"):
                try:
                    valid_to = self._parse_date(info["gltgb"])
                    if valid_to and valid_to < date.today():
                        continue
                except (ValueError, TypeError):
                    pass

            # Filter: SC relevance
            sc_roles = []
            for agr_name in info["agr_names"]:
                role_auths = info["role_auth_objects"].get(agr_name, set())
                role_tcodes = info["role_tcodes"].get(agr_name, set())
                if is_sc_relevant_role(
                    agr_name,
                    role_auths & effective_auth,
                    role_tcodes & effective_tcodes,
                ):
                    sc_roles.append(agr_name)

            if not sc_roles:
                continue

            # Resolve mapping
            powell_role, user_type = self._resolve_powell_role(
                sc_roles, mappings
            )
            site_scope = self._extract_werks_scope(
                sc_roles, info.get("auth_values", {})
            )

            # Check existing user
            email = info.get("email") or f"{bname.lower()}@sap.local"
            existing = await self.db.execute(
                select(User).where(User.email == email)
            )
            existing_user = existing.scalar_one_or_none()
            action = "update" if existing_user else "create"

            # Track unmapped
            for r in sc_roles:
                if not self._find_mapping(r, mappings):
                    unmapped_roles.add(r)

            full_name = " ".join(
                filter(None, [info.get("first_name"), info.get("last_name")])
            ) or bname

            preview_rows.append({
                "sap_username": bname,
                "email": email,
                "full_name": full_name,
                "sc_roles": sc_roles,
                "all_roles": info["agr_names"],
                "proposed_powell_role": powell_role,
                "proposed_user_type": user_type,
                "proposed_site_scope": site_scope,
                "action": action,
            })
            role_dist[powell_role] += 1

        return {
            "total_users": len(user_map),
            "sc_eligible_users": len(preview_rows),
            "preview_rows": preview_rows,
            "role_distribution": dict(role_dist),
            "unmapped_roles": sorted(unmapped_roles),
            "filter_summary": {
                "auth_objects_count": len(effective_auth),
                "tcodes_count": len(effective_tcodes),
                "include_ustyp": include_ustyp,
                "exclude_expired": exclude_expired,
            },
        }

    async def execute_import(
        self,
        raw_data: dict[str, list[dict]],
        filter_config: Optional[dict] = None,
        initiated_by_user_id: Optional[int] = None,
    ) -> SAPUserImportLog:
        """Commit import: create/update Autonomy User records."""
        start_time = datetime.utcnow()

        # Create audit log
        log = SAPUserImportLog(
            group_id=self.group_id,
            filter_config=filter_config or {},
            role_mapping_config={},
            is_preview=False,
            initiated_by=initiated_by_user_id,
            started_at=start_time,
        )
        self.db.add(log)
        await self.db.flush()

        user_map = self._build_user_role_map(raw_data)
        effective_auth = self._effective_auth_objects(filter_config)
        effective_tcodes = self._effective_tcodes(filter_config)
        include_ustyp = (filter_config or {}).get("include_ustyp", ["A"])
        exclude_expired = (filter_config or {}).get("exclude_expired", True)
        mappings = await self._load_role_mappings()

        log.users_discovered = len(user_map)
        errors = []
        created = updated = skipped = failed = 0
        sc_eligible = 0

        for bname, info in user_map.items():
            try:
                # Same filtering as preview
                if info["ustyp"] not in include_ustyp:
                    skipped += 1
                    continue
                if exclude_expired and info.get("gltgb"):
                    try:
                        valid_to = self._parse_date(info["gltgb"])
                        if valid_to and valid_to < date.today():
                            skipped += 1
                            continue
                    except (ValueError, TypeError):
                        pass

                sc_roles = []
                for agr_name in info["agr_names"]:
                    role_auths = info["role_auth_objects"].get(agr_name, set())
                    role_tcodes = info["role_tcodes"].get(agr_name, set())
                    if is_sc_relevant_role(
                        agr_name,
                        role_auths & effective_auth,
                        role_tcodes & effective_tcodes,
                    ):
                        sc_roles.append(agr_name)

                if not sc_roles:
                    skipped += 1
                    continue

                sc_eligible += 1
                powell_role, user_type_str = self._resolve_powell_role(
                    sc_roles, mappings
                )
                site_scope = self._extract_werks_scope(
                    sc_roles, info.get("auth_values", {})
                )
                email = info.get("email") or f"{bname.lower()}@sap.local"
                full_name = " ".join(
                    filter(None, [info.get("first_name"), info.get("last_name")])
                ) or bname

                # Check existing
                result = await self.db.execute(
                    select(User).where(User.email == email)
                )
                existing_user = result.scalar_one_or_none()

                if existing_user:
                    changed = False
                    try:
                        target_role = PowellRoleEnum[powell_role]
                    except KeyError:
                        target_role = PowellRoleEnum.MPS_MANAGER
                    if existing_user.powell_role != target_role:
                        existing_user.powell_role = target_role
                        changed = True
                    if existing_user.site_scope != site_scope:
                        existing_user.site_scope = site_scope
                        changed = True
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                else:
                    try:
                        target_role = PowellRoleEnum[powell_role]
                    except KeyError:
                        target_role = PowellRoleEnum.MPS_MANAGER
                    try:
                        target_user_type = UserTypeEnum[user_type_str]
                    except KeyError:
                        target_user_type = UserTypeEnum.USER

                    new_user = User(
                        email=email,
                        username=bname.lower(),
                        full_name=full_name,
                        hashed_password=get_password_hash("Autonomy@2025"),
                        is_active=True,
                        is_superuser=False,
                        user_type=target_user_type,
                        powell_role=target_role,
                        site_scope=site_scope,
                        group_id=self.group_id,
                    )
                    self.db.add(new_user)
                    await self.db.flush()
                    created += 1

            except Exception as e:
                logger.error(f"Failed to import SAP user {bname}: {e}")
                errors.append({"sap_username": bname, "error": str(e)})
                failed += 1

        end_time = datetime.utcnow()
        log.users_sc_eligible = sc_eligible
        log.users_created = created
        log.users_updated = updated
        log.users_skipped = skipped
        log.users_failed = failed
        log.errors = errors if errors else None
        log.completed_at = end_time
        log.duration_seconds = int((end_time - start_time).total_seconds())

        # Store role mapping config snapshot
        log.role_mapping_config = [m.to_dict() for m in mappings]

        await self.db.commit()
        await self.db.refresh(log)
        return log

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_user_role_map(
        self, raw_data: dict[str, list[dict]]
    ) -> dict[str, dict[str, Any]]:
        """Join 7 SAP tables into a per-user dict."""
        users: dict[str, dict] = {}

        # USR02 — base user records
        for row in raw_data.get("usr02", []):
            bname = (row.get("BNAME") or "").strip().upper()
            if not bname:
                continue
            users[bname] = {
                "bname": bname,
                "ustyp": (row.get("USTYP") or "A").strip().upper(),
                "gltgv": row.get("GLTGV"),
                "gltgb": row.get("GLTGB"),
                "account_class": row.get("CLASS"),
                "email": None,
                "first_name": None,
                "last_name": None,
                "agr_names": [],
                "role_auth_objects": {},
                "role_tcodes": {},
                "auth_values": {},
            }

        # USR21 + ADRP — resolve names and email
        person_map: dict[str, str] = {}  # PERSNUMBER → BNAME
        for row in raw_data.get("usr21", []):
            bname = (row.get("BNAME") or "").strip().upper()
            persnr = (row.get("PERSNUMBER") or "").strip()
            if bname and persnr:
                person_map[persnr] = bname

        for row in raw_data.get("adrp", []):
            persnr = (row.get("PERSNUMBER") or "").strip()
            bname = person_map.get(persnr)
            if bname and bname in users:
                users[bname]["email"] = (
                    row.get("SMTP_ADDR") or ""
                ).strip() or None
                users[bname]["first_name"] = (
                    row.get("NAME_FIRST") or ""
                ).strip() or None
                users[bname]["last_name"] = (
                    row.get("NAME_LAST") or ""
                ).strip() or None

        # AGR_USERS — role assignments
        for row in raw_data.get("agr_users", []):
            uname = (row.get("UNAME") or "").strip().upper()
            agr_name = (row.get("AGR_NAME") or "").strip()
            if uname in users and agr_name:
                users[uname]["agr_names"].append(agr_name)

        # AGR_1251 — auth objects per role
        role_auth: dict[str, set[str]] = defaultdict(set)
        role_auth_values: dict[str, list[dict]] = defaultdict(list)
        for row in raw_data.get("agr_1251", []):
            agr_name = (row.get("AGR_NAME") or "").strip()
            obj = (row.get("OBJECT") or "").strip()
            if agr_name and obj:
                role_auth[agr_name].add(obj)
                role_auth_values[agr_name].append({
                    "OBJECT": obj,
                    "FIELD": (row.get("FIELD") or "").strip(),
                    "LOW": (row.get("LOW") or "").strip(),
                    "HIGH": (row.get("HIGH") or "").strip(),
                })

        # AGR_TCODES — tcodes per role
        role_tcode: dict[str, set[str]] = defaultdict(set)
        for row in raw_data.get("agr_tcodes", []):
            agr_name = (row.get("AGR_NAME") or "").strip()
            tcode = (row.get("TCODE") or "").strip()
            if agr_name and tcode:
                role_tcode[agr_name].add(tcode)

        # Attach role-level data to each user
        for bname, info in users.items():
            for agr_name in info["agr_names"]:
                info["role_auth_objects"][agr_name] = role_auth.get(
                    agr_name, set()
                )
                info["role_tcodes"][agr_name] = role_tcode.get(
                    agr_name, set()
                )
                info["auth_values"][agr_name] = role_auth_values.get(
                    agr_name, []
                )

        return users

    def _effective_auth_objects(
        self, filter_config: Optional[dict]
    ) -> set[str]:
        """Build effective auth object filter set."""
        base = set(SC_AUTH_OBJECTS)
        if filter_config:
            base |= set(filter_config.get("extra_auth_objects", []))
            base -= set(filter_config.get("excluded_auth_objects", []))
        return base

    def _effective_tcodes(self, filter_config: Optional[dict]) -> set[str]:
        """Build effective tcode filter set."""
        base = set(SC_TRANSACTION_CODES)
        if filter_config:
            base |= set(filter_config.get("extra_tcodes", []))
            base -= set(filter_config.get("excluded_tcodes", []))
        return base

    async def _load_role_mappings(self) -> list[SAPRoleMapping]:
        """Load active role mappings for this group, ordered by priority."""
        result = await self.db.execute(
            select(SAPRoleMapping)
            .where(
                SAPRoleMapping.group_id == self.group_id,
                SAPRoleMapping.is_active == True,  # noqa: E712
            )
            .order_by(SAPRoleMapping.priority)
        )
        return list(result.scalars().all())

    def _resolve_powell_role(
        self,
        agr_names: list[str],
        mappings: list[SAPRoleMapping],
    ) -> tuple[str, str]:
        """Map SAP roles to Autonomy powell_role via 3-layer cascade."""
        # Layer 1: configured mappings
        for agr_name in agr_names:
            mapping = self._find_mapping(agr_name, mappings)
            if mapping:
                return mapping.powell_role, mapping.user_type

        # Layer 2: heuristic fallback
        return self._heuristic_powell_role(agr_names)

    def _find_mapping(
        self, agr_name: str, mappings: list[SAPRoleMapping]
    ) -> Optional[SAPRoleMapping]:
        """Find first matching mapping rule for a role name."""
        for mapping in mappings:
            if self._pattern_matches(
                agr_name, mapping.agr_name_pattern, mapping.pattern_type
            ):
                return mapping
        return None

    @staticmethod
    def _pattern_matches(
        agr_name: str, pattern: str, pattern_type: str
    ) -> bool:
        """Test if agr_name matches a glob or regex pattern."""
        if pattern_type == "regex":
            return bool(re.search(pattern, agr_name, re.IGNORECASE))
        return fnmatch.fnmatch(agr_name.upper(), pattern.upper())

    @staticmethod
    def _heuristic_powell_role(agr_names: list[str]) -> tuple[str, str]:
        """Fallback role mapping from well-known SAP naming conventions."""
        combined = " ".join(agr_names).upper()

        if any(x in combined for x in [
            "SC_VP", "SUPPLY_VP", "IBP_EXECUTIVE", "SC_DIRECTOR"
        ]):
            return "SC_VP", "USER"
        if any(x in combined for x in [
            "SOP", "IBP_PLANNER", "DEMAND_DIRECTOR", "SC_PLANNER_SR"
        ]):
            return "SOP_DIRECTOR", "USER"
        if any(x in combined for x in [
            "MRP_CTRL", "PP_PLANNER", "APO_PLANNER", "MPS_MANAGER"
        ]):
            return "MPS_MANAGER", "USER"
        if any(x in combined for x in [
            "MM_BUYER", "PROCUREMENT", "PO_ANALYST", "PURCHASING"
        ]):
            return "PO_ANALYST", "USER"
        if any(x in combined for x in [
            "ALLOCATION", "ALLOC_MGR"
        ]):
            return "ALLOCATION_MANAGER", "USER"

        return "MPS_MANAGER", "USER"

    @staticmethod
    def _extract_werks_scope(
        agr_names: list[str],
        auth_values: dict[str, list[dict]],
    ) -> Optional[list[str]]:
        """Extract plant (WERKS) values from auth objects for site_scope."""
        werks_objects = {"M_BEST_WRK", "M_BANF_WRK", "C_AFKO_AWK", "M_MATE_WRK"}
        site_keys: list[str] = []

        for agr_name in agr_names:
            for auth in auth_values.get(agr_name, []):
                if (
                    auth.get("OBJECT") in werks_objects
                    and auth.get("FIELD") == "WERKS"
                ):
                    low = auth.get("LOW", "")
                    high = auth.get("HIGH", "")
                    if low == "*" or low == "":
                        return None  # wildcard = full access
                    if high and high != low:
                        site_keys.append(f"SAP_WERKS_{low}..{high}")
                    elif low:
                        site_keys.append(f"SITE_{low}")

        return site_keys if site_keys else None

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        """Parse a date from various SAP formats."""
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            value = value.strip()
            if not value or value == "00000000":
                return None
            for fmt in ("%Y%m%d", "%Y-%m-%d", "%d.%m.%Y"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
        return None
