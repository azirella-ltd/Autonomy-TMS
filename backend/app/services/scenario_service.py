"""TMS ScenarioService — subclasses Core BaseScenarioService.

Implements the TMS-specific bindings:
  - _solve: delegates to MixedScenarioService.start_new_round (simulation engine)
  - _report: delegates to MixedScenarioService.get_report
  - _list_query / _state_query / _scenario_config_id: TMS scenarios table
  - create_scenario: MixedScenarioService.create_scenario + scenario branching
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from azirella_data_model.simulation.scenario_service import BaseScenarioService
except ImportError:
    # Fallback if Core not yet installed with this module
    from abc import ABC
    BaseScenarioService = ABC  # type: ignore

logger = logging.getLogger(__name__)


class ScenarioService(BaseScenarioService):
    """TMS-specific scenario service.

    Thin adapter over BaseScenarioService lifecycle, delegating
    heavy simulation logic to the legacy MixedScenarioService engine.
    """

    def __init__(self, db: Session):
        super().__init__(db)
        # Lazy-init to avoid circular imports
        self._engine: Optional[Any] = None

    @property
    def engine(self):
        """Lazy-loaded MixedScenarioService for simulation delegation."""
        if self._engine is None:
            from app.services.mixed_scenario_service import MixedScenarioService
            self._engine = MixedScenarioService(self.db)
        return self._engine

    # ------------------------------------------------------------------
    # Abstract implementations
    # ------------------------------------------------------------------

    def _list_query(self, tenant_id: int | None) -> List[Dict[str, Any]]:
        filters = ["1=1"]
        params: Dict[str, Any] = {}
        if tenant_id is not None:
            filters.append("s.tenant_id = :tid")
            params["tid"] = tenant_id

        rows = self.db.execute(
            text(f"""
                SELECT s.id, s.name, s.description, s.status::text AS status,
                       s.current_period, s.max_periods,
                       s.created_at, s.started_at, s.finished_at, s.tenant_id,
                       s.created_by, s.is_public, s.supply_chain_config_id,
                       scc.name AS config_name,
                       (SELECT COUNT(*) FROM scenario_users su
                        WHERE su.scenario_id = s.id) AS participant_count
                FROM scenarios s
                LEFT JOIN supply_chain_configs scc
                  ON scc.id = s.supply_chain_config_id
                WHERE {' AND '.join(filters)}
                ORDER BY s.created_at DESC
            """),
            params,
        ).mappings().all()

        return [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "status": r["status"],
                "current_period": r["current_period"] or 0,
                "max_periods": r["max_periods"] or 0,
                "created_at": (
                    r["created_at"].isoformat() if r["created_at"] else None
                ),
                "updated_at": (
                    (r["started_at"] or r["finished_at"] or r["created_at"]).isoformat()
                    if (r["started_at"] or r["finished_at"] or r["created_at"])
                    else None
                ),
                "tenant_id": r["tenant_id"],
                "created_by": r["created_by"],
                "config_name": r["config_name"],
                "supply_chain_config_id": r["supply_chain_config_id"],
                "is_public": r["is_public"],
                "participant_count": int(r["participant_count"] or 0),
            }
            for r in rows
        ]

    def _scenario_config_id(self, scenario_id: int) -> int | None:
        row = self.db.execute(
            text("SELECT supply_chain_config_id FROM scenarios WHERE id = :sid"),
            {"sid": scenario_id},
        ).scalar()
        return int(row) if row else None

    def _solve(self, scenario_id: int, config_id: int) -> Dict[str, Any]:
        """Run one simulation period via the TMS simulation engine."""
        rnd = self.engine.start_new_round(scenario_id)
        return {
            "round_number": getattr(rnd, "round_number", None) if rnd else None,
            "scenario_id": scenario_id,
        }

    def _report(self, scenario_id: int, config_id: int) -> Dict[str, Any]:
        """Delegate to the TMS simulation report builder."""
        return self.engine.get_report(scenario_id)

    def _state_query(self, scenario_id: int) -> Dict[str, Any]:
        """Return TMS scenario state as a dict."""
        state = self.engine.get_scenario_state(scenario_id)
        # ScenarioState is a Pydantic model — serialise to dict
        if hasattr(state, "dict"):
            return state.dict()
        if hasattr(state, "model_dump"):
            return state.model_dump()
        return dict(state)

    def create_scenario(
        self,
        *,
        name: str,
        description: str = "",
        tenant_id: int,
        config_id: int,
        max_periods: int = 52,
        created_by: int | None = None,
        scenario_type: str = "WORKING",
        **extra,
    ) -> Dict[str, Any]:
        """Create a TMS scenario via branching + the simulation engine.

        Falls back to a direct INSERT when ScenarioBranchingService is
        available, otherwise delegates entirely to MixedScenarioService.
        """
        try:
            from app.services.scenario_branching_service import ScenarioBranchingService

            brancher = ScenarioBranchingService(self.db)
            branch = brancher.create_branch(
                parent_config_id=config_id,
                name=name,
                description=description,
                scenario_type=scenario_type,
                created_by=created_by,
            )

            self.db.execute(
                text("""
                    INSERT INTO scenarios
                        (name, description, status, tenant_id,
                         supply_chain_config_id, current_period, max_periods,
                         created_by, created_at, is_public, config,
                         time_bucket, start_date,
                         use_sc_planning, role_assignments, use_dag_sequential)
                    VALUES
                        (:n, :d, 'CREATED', :tid,
                         :cfg, 0, :mp,
                         :cb, NOW(), FALSE, '{}',
                         'week', CURRENT_DATE,
                         TRUE, '{}', TRUE)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "n": name, "d": description, "tid": tenant_id,
                    "cfg": branch.id, "mp": max_periods, "cb": created_by,
                },
            )
            self.db.commit()

            return {
                "id": branch.id,
                "name": name,
                "description": description,
                "status": "CREATED",
                "current_period": 0,
                "max_periods": max_periods,
                "config_id": branch.id,
                "parent_config_id": config_id,
                "tenant_id": tenant_id,
                "created_at": datetime.utcnow().isoformat(),
            }
        except ImportError:
            logger.warning(
                "ScenarioBranchingService not available; "
                "falling back to MixedScenarioService.create_scenario"
            )
            from app.schemas.scenario import ScenarioCreate
            scenario_data = ScenarioCreate(
                name=name,
                max_periods=max_periods,
                supply_chain_config_id=config_id,
                description=description,
                **extra,
            )
            scenario = self.engine.create_scenario(scenario_data, created_by=created_by)
            return {
                "id": scenario.id,
                "name": scenario.name,
                "status": "CREATED",
                "current_period": 0,
                "max_periods": max_periods,
                "config_id": getattr(scenario, "supply_chain_config_id", config_id),
                "tenant_id": tenant_id,
                "created_at": datetime.utcnow().isoformat(),
            }

    # ------------------------------------------------------------------
    # Reset hook — TMS clears simulation rounds, not supply_plan
    # ------------------------------------------------------------------

    def _on_reset(self, scenario_id: int, config_id: int):
        """Clear TMS simulation rounds and engine state on reset."""
        self.db.execute(
            text("DELETE FROM periods WHERE scenario_id = :sid"),
            {"sid": scenario_id},
        )
        self.db.execute(
            text("""
                UPDATE scenarios
                SET config = jsonb_set(
                    COALESCE(config, '{}'::jsonb),
                    '{engine_state}', '{}'::jsonb
                )
                WHERE id = :sid
            """),
            {"sid": scenario_id},
        )
