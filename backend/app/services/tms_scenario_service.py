"""TMS Scenario Service — transportation-domain subclass of BaseScenarioService.

Implements the 6 abstract methods that bind to TMS's transportation_plan,
MovementGapAnalyzer, and scenario tables. Lifecycle (start/stop/reset/advance)
comes from the base class in azirella_data_model.simulation.scenario_service.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from azirella_data_model.simulation.scenario_service import BaseScenarioService

logger = logging.getLogger(__name__)


class TmsScenarioService(BaseScenarioService):
    """Transportation scenario lifecycle — subclass per product pattern."""

    def create_scenario(self, **kwargs) -> Dict[str, Any]:
        name = kwargs.get("name", f"TMS Scenario {datetime.utcnow():%Y-%m-%d %H:%M}")
        tenant_id = kwargs.get("tenant_id")
        config_id = kwargs.get("config_id")
        max_periods = kwargs.get("max_periods", 13)
        description = kwargs.get("description", "")

        self.db.execute(
            text("""
                INSERT INTO scenarios (name, status, current_period, max_periods,
                    description, tenant_id, supply_chain_config_id, created_at)
                VALUES (:name, 'CREATED', 0, :max_p, :desc, :tid, :cid, :now)
            """),
            {
                "name": name,
                "max_p": max_periods,
                "desc": description,
                "tid": tenant_id,
                "cid": config_id,
                "now": datetime.utcnow(),
            },
        )
        self.db.commit()

        row = self.db.execute(
            text("SELECT id FROM scenarios WHERE name = :name AND tenant_id = :tid ORDER BY id DESC LIMIT 1"),
            {"name": name, "tid": tenant_id},
        ).mappings().one_or_none()

        return {
            "scenario_id": row["id"] if row else None,
            "name": name,
            "status": "CREATED",
            "config_id": config_id,
        }

    def _list_query(self, tenant_id: int | None) -> List[Dict[str, Any]]:
        q = "SELECT id, name, status, current_period, max_periods, supply_chain_config_id AS config_id, created_at FROM scenarios"
        params: Dict[str, Any] = {}
        if tenant_id is not None:
            q += " WHERE tenant_id = :tid"
            params["tid"] = tenant_id
        q += " ORDER BY created_at DESC"
        rows = self.db.execute(text(q), params).mappings().all()
        return [dict(r) for r in rows]

    def _scenario_config_id(self, scenario_id: int) -> int | None:
        row = self.db.execute(
            text("SELECT supply_chain_config_id FROM scenarios WHERE id = :sid"),
            {"sid": scenario_id},
        ).mappings().one_or_none()
        return row["supply_chain_config_id"] if row else None

    def _solve(self, scenario_id: int, config_id: int) -> Dict[str, Any]:
        """Run the bootstrap heuristic or GNN planner (when available) on this scenario's config.

        For now, returns a stub — the actual planner (Phase F bootstrap heuristic
        or Phase D GNN) will be wired in when available per TMS_TIER3_FIRST_PLAN.md.
        """
        return {
            "solver": "stub_pending_tier3",
            "config_id": config_id,
            "note": "Planner not yet wired — see docs/TMS_TIER3_FIRST_PLAN.md Phase D/F",
        }

    def _report(self, scenario_id: int, config_id: int) -> Dict[str, Any]:
        """Produce a movement gap report for this scenario's config."""
        from app.services.tms_planning.movement_gap_analyzer import MovementGapAnalyzer
        analyzer = MovementGapAnalyzer(self.db)
        return analyzer.analyze(config_id)

    def _state_query(self, scenario_id: int) -> Dict[str, Any]:
        row = self.db.execute(
            text("""
                SELECT s.id, s.name, s.status, s.current_period, s.max_periods,
                       s.supply_chain_config_id AS config_id,
                       (SELECT count(*) FROM transportation_plan tp
                        WHERE tp.config_id = s.supply_chain_config_id) AS plan_count,
                       (SELECT count(*) FROM transportation_plan_item tpi
                        JOIN transportation_plan tp2 ON tp2.id = tpi.plan_id
                        WHERE tp2.config_id = s.supply_chain_config_id) AS plan_item_count
                FROM scenarios s
                WHERE s.id = :sid
            """),
            {"sid": scenario_id},
        ).mappings().one_or_none()
        if row is None:
            return {"error": f"Scenario {scenario_id} not found"}
        return dict(row)

    def _on_reset(self, scenario_id: int, config_id: int):
        """TMS-specific cleanup: delete constrained_live transportation_plan rows."""
        self.db.execute(
            text("DELETE FROM transportation_plan WHERE config_id = :cfg AND plan_version = 'constrained_live'"),
            {"cfg": config_id},
        )
