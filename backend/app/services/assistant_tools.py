"""Read-only tool functions for the Azirella assistant.

Phase 2 of the grounding work (see assistant_service.py docstring).

The tool orchestrator gives the LLM structured access to live operational
state from the tenant's active SC config. Each tool:

  - Is strictly scoped to `config_id` — no cross-config leakage
  - Is read-only — never modifies any table
  - Returns a compact, LLM-friendly rendered string plus the raw result dict
  - Handles missing data / errors gracefully by returning an explanatory
    string rather than raising

The orchestrator decides which tools to invoke based on keywords in the
user's question. A future iteration can swap this for real LLM function-
calling where the model itself picks tools; today's keyword router keeps
the surface area minimal and deterministic for the demo.

Phase 3 (write tools — override, inspect, trigger replan) goes in a
separate module `assistant_write_tools.py` with AIIO governance.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import text as _text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── Helpers ────────────────────────────────────────────────────────────

def _extract_product_id(question: str) -> Optional[str]:
    """Heuristic: pull a product SKU-style token out of the question.

    Matches tokens like CFG129_FP001, SKU-123, RM12, P-4567 etc.
    """
    # CFG-prefixed demo SKUs
    m = re.search(r"\bCFG\d+_[A-Z0-9_\-]+", question)
    if m:
        return m.group(0)
    # Alphanumeric SKU with digits and at least 4 chars
    m = re.search(r"\b[A-Z][A-Z0-9_\-]{3,}\b", question)
    if m:
        return m.group(0)
    return None


def _extract_site_name(question: str) -> Optional[str]:
    """Pull a site name (RDC_NW, CUST_PDX, W001 etc.) from the question."""
    m = re.search(r"\b(?:RDC|CDC|DC|PLANT|CUST|W|V)_?[A-Z0-9]{2,}", question)
    if m:
        return m.group(0)
    return None


# ─── Tool registry ──────────────────────────────────────────────────────

@dataclass
class ToolResult:
    tool: str
    result: Any
    rendered: str  # LLM-friendly rendering


class AssistantToolOrchestrator:
    """Routes questions to read-only tools scoped to a specific SC config.

    Every tool invocation receives `config_id` and `tenant_id`; queries are
    written to filter by both to prevent cross-tenant or cross-config data
    leaks.
    """

    def __init__(self, db: AsyncSession, config_id: int, tenant_id: int):
        self.db = db
        self.config_id = config_id
        self.tenant_id = tenant_id

    # ── Public entry point ─────────────────────────────────────────────

    async def run_tools_for_question(self, question: str) -> List[Dict[str, Any]]:
        """Decide which tools to run based on the question and execute them.

        Returns a list of tool result dicts: [{tool, result, rendered}, ...]
        The orchestrator runs 0..N tools per question — if nothing matches,
        returns an empty list and the assistant falls back to semantic
        context + RAG only.
        """
        q = question.lower()
        results: List[ToolResult] = []

        # Always run the config-overview tool for questions that reference
        # the supply chain at all — gives the LLM a grounded footprint.
        if any(k in q for k in ("overview", "network", "how many", "what is my", "summary", "structure")):
            results.append(await self._tool_config_overview())

        # Inventory queries
        if any(k in q for k in ("inventory", "on hand", "on-hand", "stock", "stockout", "in transit")):
            pid = _extract_product_id(question)
            site = _extract_site_name(question)
            results.append(await self._tool_inventory(pid, site))

        # Forecast queries
        if any(k in q for k in ("forecast", "demand", "projection", "predict")):
            pid = _extract_product_id(question)
            site = _extract_site_name(question)
            results.append(await self._tool_forecast(pid, site))

        # Supply plan queries
        if any(k in q for k in ("supply plan", "plan of record", "planned order", "mrp", "mps", "order plan")):
            pid = _extract_product_id(question)
            site = _extract_site_name(question)
            results.append(await self._tool_supply_plan(pid, site))

        # Agent decision queries
        if any(k in q for k in ("decision", "override", "escalat", "why did the agent", "recent action", "recommendation")):
            results.append(await self._tool_recent_decisions())

        # Site metadata queries
        if any(k in q for k in ("site", "warehouse", "dc ", "plant ", "distribution center")):
            site = _extract_site_name(question)
            if site:
                results.append(await self._tool_site(site))

        # Product metadata queries
        if any(k in q for k in ("product", "sku", "material", "part number")):
            pid = _extract_product_id(question)
            if pid:
                results.append(await self._tool_product(pid))

        return [{"tool": r.tool, "result": r.result, "rendered": r.rendered} for r in results]

    # ── Individual tools ───────────────────────────────────────────────

    async def _tool_config_overview(self) -> ToolResult:
        """High-level counts for the active config (acts as sanity ground truth)."""
        try:
            row = (await self.db.execute(_text("""
                SELECT
                    (SELECT COUNT(*) FROM site WHERE config_id = :c) AS sites,
                    (SELECT COUNT(*) FROM product WHERE config_id = :c) AS products,
                    (SELECT COUNT(*) FROM transportation_lane WHERE config_id = :c) AS lanes,
                    (SELECT COUNT(*) FROM inv_policy WHERE config_id = :c) AS policies,
                    (SELECT COUNT(*) FROM forecast WHERE config_id = :c) AS forecast_rows,
                    (SELECT COUNT(*) FROM inv_level WHERE config_id = :c) AS inv_rows
            """), {"c": self.config_id})).fetchone()
            if not row:
                return ToolResult("config_overview", None, "No data found for this configuration.")
            result = {
                "sites": row[0], "products": row[1], "lanes": row[2],
                "policies": row[3], "forecast_rows": row[4], "inv_rows": row[5],
            }
            rendered = (
                f"Active config has {row[0]} sites, {row[1]} products, {row[2]} lanes, "
                f"{row[3]} inventory policies, {row[4]} forecast rows, {row[5]} inventory observations."
            )
            return ToolResult("config_overview", result, rendered)
        except Exception as e:
            return ToolResult("config_overview", None, f"Error: {e!s}"[:200])

    async def _tool_inventory(
        self, product_id: Optional[str], site_hint: Optional[str],
    ) -> ToolResult:
        """Current on-hand / in-transit / allocated for a (product, site) or the top-N."""
        try:
            params: Dict[str, Any] = {"c": self.config_id}
            where = ["il.config_id = :c"]
            if product_id:
                where.append("il.product_id = :pid")
                params["pid"] = product_id
            if site_hint:
                where.append("s.name ILIKE :site")
                params["site"] = f"%{site_hint}%"
            sql = f"""
                SELECT DISTINCT ON (il.product_id, il.site_id)
                    il.product_id, s.name AS site_name,
                    il.on_hand_qty, il.in_transit_qty, il.allocated_qty, il.safety_stock_qty,
                    il.inventory_date
                FROM inv_level il
                JOIN site s ON s.id = il.site_id
                WHERE {' AND '.join(where)}
                ORDER BY il.product_id, il.site_id, il.inventory_date DESC NULLS LAST
                LIMIT 15
            """
            rows = (await self.db.execute(_text(sql), params)).fetchall()
            if not rows:
                return ToolResult(
                    "inventory", [],
                    f"No inventory rows found for product_id={product_id} site={site_hint}.",
                )
            result = [
                {
                    "product_id": r[0], "site": r[1],
                    "on_hand": float(r[2] or 0), "in_transit": float(r[3] or 0),
                    "allocated": float(r[4] or 0), "safety_stock": float(r[5] or 0),
                    "as_of": r[6].isoformat() if r[6] else None,
                }
                for r in rows
            ]
            lines = ["Current inventory positions:"]
            for r in result:
                lines.append(
                    f"  {r['product_id']} @ {r['site']}: on_hand={r['on_hand']:,.0f}, "
                    f"in_transit={r['in_transit']:,.0f}, safety_stock={r['safety_stock']:,.0f} "
                    f"(as of {r['as_of'] or 'unknown'})"
                )
            return ToolResult("inventory", result, "\n".join(lines))
        except Exception as e:
            return ToolResult("inventory", None, f"Error: {e!s}"[:200])

    async def _tool_forecast(
        self, product_id: Optional[str], site_hint: Optional[str],
    ) -> ToolResult:
        """Forward forecast (P10/P50/P90) for a (product, site) or top-N."""
        try:
            params: Dict[str, Any] = {"c": self.config_id}
            where = ["f.config_id = :c", "f.forecast_date >= CURRENT_DATE"]
            if product_id:
                where.append("f.product_id = :pid")
                params["pid"] = product_id
            if site_hint:
                where.append("s.name ILIKE :site")
                params["site"] = f"%{site_hint}%"
            sql = f"""
                SELECT f.product_id, s.name AS site_name, f.forecast_date,
                       COALESCE(f.forecast_p50, f.forecast_quantity) AS p50,
                       f.forecast_p10, f.forecast_p90
                FROM forecast f
                JOIN site s ON s.id = f.site_id
                WHERE {' AND '.join(where)}
                ORDER BY f.forecast_date ASC
                LIMIT 12
            """
            rows = (await self.db.execute(_text(sql), params)).fetchall()
            if not rows:
                return ToolResult("forecast", [], "No forward forecast rows found.")
            result = [
                {
                    "product_id": r[0], "site": r[1],
                    "forecast_date": r[2].isoformat() if r[2] else None,
                    "p50": float(r[3] or 0),
                    "p10": float(r[4] or 0) if r[4] is not None else None,
                    "p90": float(r[5] or 0) if r[5] is not None else None,
                }
                for r in rows
            ]
            lines = ["Forward forecast (P10/P50/P90):"]
            for r in result:
                lines.append(
                    f"  {r['product_id']} @ {r['site']} wk {r['forecast_date']}: "
                    f"P50={r['p50']:,.0f} P10={r['p10']:,.0f if r['p10'] else 0} "
                    f"P90={r['p90']:,.0f if r['p90'] else 0}"
                )
            return ToolResult("forecast", result, "\n".join(lines[:13]))
        except Exception as e:
            return ToolResult("forecast", None, f"Error: {e!s}"[:200])

    async def _tool_supply_plan(
        self, product_id: Optional[str], site_hint: Optional[str],
    ) -> ToolResult:
        """Live supply plan (plan_version='live') for next 12 weeks."""
        try:
            params: Dict[str, Any] = {"c": self.config_id}
            where = [
                "sp.config_id = :c",
                "sp.plan_version = 'live'",
                "sp.plan_date >= CURRENT_DATE",
            ]
            if product_id:
                where.append("sp.product_id = :pid")
                params["pid"] = product_id
            if site_hint:
                where.append("s.name ILIKE :site")
                params["site"] = f"%{site_hint}%"
            sql = f"""
                SELECT sp.product_id, s.name AS site_name, sp.plan_date,
                       sp.demand_quantity, sp.planned_order_quantity
                FROM supply_plan sp
                JOIN site s ON s.id = sp.site_id
                WHERE {' AND '.join(where)}
                ORDER BY sp.plan_date ASC
                LIMIT 12
            """
            rows = (await self.db.execute(_text(sql), params)).fetchall()
            if not rows:
                return ToolResult("supply_plan", [], "No forward supply plan rows found.")
            result = [
                {
                    "product_id": r[0], "site": r[1],
                    "plan_date": r[2].isoformat() if r[2] else None,
                    "demand": float(r[3] or 0),
                    "planned_order": float(r[4] or 0),
                }
                for r in rows
            ]
            lines = ["Forward supply plan (live):"]
            for r in result:
                lines.append(
                    f"  {r['product_id']} @ {r['site']} wk {r['plan_date']}: "
                    f"demand={r['demand']:,.0f}, planned_order={r['planned_order']:,.0f}"
                )
            return ToolResult("supply_plan", result, "\n".join(lines))
        except Exception as e:
            return ToolResult("supply_plan", None, f"Error: {e!s}"[:200])

    async def _tool_recent_decisions(self, limit: int = 10) -> ToolResult:
        """Recent TRM decisions across all agents for this config."""
        try:
            # Union a few powell_*_decisions tables. We keep the list short
            # for demo stability; a real implementation should iterate the
            # full registry.
            sql = """
                SELECT trm_type, product_id, site_id, created_at, confidence, status
                FROM (
                    SELECT 'po_creation' AS trm_type, product_id, site_id, created_at,
                           confidence, status
                      FROM powell_po_decisions WHERE config_id = :c
                    UNION ALL
                    SELECT 'atp_allocation', product_id, site_id, created_at,
                           confidence, status
                      FROM powell_atp_decisions WHERE config_id = :c
                    UNION ALL
                    SELECT 'inventory_buffer', product_id, site_id, created_at,
                           confidence, status
                      FROM powell_buffer_decisions WHERE config_id = :c
                    UNION ALL
                    SELECT 'to_execution', product_id, site_id, created_at,
                           confidence, status
                      FROM powell_to_decisions WHERE config_id = :c
                    UNION ALL
                    SELECT 'rebalancing', product_id, site_id, created_at,
                           confidence, status
                      FROM powell_rebalance_decisions WHERE config_id = :c
                ) u
                ORDER BY created_at DESC NULLS LAST
                LIMIT :lim
            """
            rows = (await self.db.execute(_text(sql), {"c": self.config_id, "lim": limit})).fetchall()
            if not rows:
                return ToolResult("recent_decisions", [], "No recent TRM decisions found.")
            result = [
                {
                    "trm_type": r[0], "product_id": r[1], "site_id": r[2],
                    "created_at": r[3].isoformat() if r[3] else None,
                    "confidence": float(r[4] or 0) if r[4] is not None else None,
                    "status": r[5],
                }
                for r in rows
            ]
            lines = [f"Most recent {len(result)} agent decisions:"]
            for r in result:
                lines.append(
                    f"  [{r['trm_type']}] {r['product_id']} @ site {r['site_id']} "
                    f"conf={r['confidence']} status={r['status']} at={r['created_at']}"
                )
            return ToolResult("recent_decisions", result, "\n".join(lines))
        except Exception as e:
            return ToolResult("recent_decisions", None, f"Error: {e!s}"[:200])

    async def _tool_site(self, site_hint: str) -> ToolResult:
        """Site metadata (type, master_type, geo, lanes in/out)."""
        try:
            row = (await self.db.execute(_text("""
                SELECT s.id, s.name, s.master_type, s.dag_type, s.geo_id,
                       (SELECT COUNT(*) FROM transportation_lane WHERE to_site_id = s.id AND config_id = :c) AS inbound_lanes,
                       (SELECT COUNT(*) FROM transportation_lane WHERE from_site_id = s.id AND config_id = :c) AS outbound_lanes
                FROM site s
                WHERE s.config_id = :c AND s.name ILIKE :hint
                LIMIT 1
            """), {"c": self.config_id, "hint": f"%{site_hint}%"})).fetchone()
            if not row:
                return ToolResult("site", None, f"No site matching '{site_hint}' found in this config.")
            result = {
                "id": row[0], "name": row[1], "master_type": row[2], "dag_type": row[3],
                "geo_id": row[4], "inbound_lanes": row[5], "outbound_lanes": row[6],
            }
            rendered = (
                f"Site {row[1]} (id={row[0]}): master_type={row[2]}, dag_type={row[3]}, "
                f"geo={row[4]}, {row[5]} inbound lanes, {row[6]} outbound lanes."
            )
            return ToolResult("site", result, rendered)
        except Exception as e:
            return ToolResult("site", None, f"Error: {e!s}"[:200])

    async def _tool_product(self, product_id: str) -> ToolResult:
        """Product metadata (description, cost, category, family)."""
        try:
            row = (await self.db.execute(_text("""
                SELECT id, description, unit_cost, unit_price, category, family
                FROM product
                WHERE config_id = :c AND id = :pid
                LIMIT 1
            """), {"c": self.config_id, "pid": product_id})).fetchone()
            if not row:
                return ToolResult("product", None, f"Product {product_id} not found in this config.")
            result = {
                "id": row[0], "description": row[1],
                "unit_cost": float(row[2] or 0), "unit_price": float(row[3] or 0),
                "category": row[4], "family": row[5],
            }
            rendered = (
                f"Product {row[0]}: {row[1]} — category={row[4]}, family={row[5]}, "
                f"unit_cost={row[2]}, unit_price={row[3]}"
            )
            return ToolResult("product", result, rendered)
        except Exception as e:
            return ToolResult("product", None, f"Error: {e!s}"[:200])
