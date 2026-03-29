"""Service layer for running fully automated supply chain simulations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.demand_patterns import (
    DEFAULT_CLASSIC_PARAMS,
    DEFAULT_DEMAND_PATTERN,
    DemandGenerator,
    DemandPatternType,
    normalize_demand_pattern,
)
from app.models.scenario import Scenario, ScenarioStatus
from app.models.scenario_user import ScenarioUser, ScenarioUserRole
from app.models.supply_chain import ScenarioRound, ScenarioUserInventory, ScenarioUserPeriod
from app.models.supply_chain_config import TransportationLane, Site
from app.schemas.scenario import ScenarioCreate, DemandPattern

# Short aliases used throughout this module
Game = Scenario
GameStatus = ScenarioStatus
ScenarioUser = ScenarioUser
ScenarioUserRole = ScenarioUserRole
ScenarioRound = ScenarioRound
ScenarioUserInventory = ScenarioUserInventory
ScenarioUserPeriod = ScenarioUserPeriod
GameCreate = ScenarioCreate

from .policy_factory import make_policy
from .supply_chain_config_service import SupplyChainConfigService


class AgentGameService:
    """Manage supply chain simulations where every site is controlled by an agent.

    The topology (material lanes and site names) is loaded dynamically from
    the scenario's ``SupplyChainConfig``.  No hardcoded topology assumptions.
    """

    def __init__(self, db_session: Session) -> None:
        self.db = db_session
        self._demand_visible = False
        self._supply_chain_service: SupplyChainConfigService | None = None

    # ------------------------------------------------------------------
    # Topology helpers — derive lanes and roles from the SC config
    # ------------------------------------------------------------------

    def _load_topology(self, game: Game) -> Dict[str, Any]:
        """Load the supply chain topology from the game's SC config.

        Returns a dict with:
          - material_lanes: list of (upstream_name, downstream_name) tuples
          - site_names: list of site names in downstream-to-upstream order
          - site_roles: dict mapping site name -> ScenarioUserRole value string
        """
        config = game.config or {}
        cached = config.get("topology")
        if isinstance(cached, dict) and cached.get("material_lanes"):
            return cached

        config_id = game.supply_chain_config_id
        if not config_id:
            raise ValueError("Game has no supply_chain_config_id")

        lanes = (
            self.db.query(TransportationLane)
            .filter(TransportationLane.config_id == config_id)
            .all()
        )

        material_lanes: List[Tuple[str, str]] = []
        for lane in lanes:
            up = lane.upstream_site
            down = lane.downstream_site
            if up and down:
                material_lanes.append((up.name, down.name))

        if not material_lanes:
            raise ValueError(f"No transportation lanes found for config {config_id}")

        sites = (
            self.db.query(Site)
            .filter(Site.config_id == config_id)
            .all()
        )

        site_roles: Dict[str, str] = {}
        for site in sites:
            site_type = (site.type or "RETAILER").upper()
            try:
                role = ScenarioUserRole(site_type)
            except (ValueError, AttributeError):
                role = ScenarioUserRole.RETAILER
            site_roles[site.name] = role.value

        site_names = self._topological_sort(material_lanes)

        topology: Dict[str, Any] = {
            "material_lanes": material_lanes,
            "site_names": site_names,
            "site_roles": site_roles,
        }

        # Cache in game config for subsequent calls
        config["topology"] = topology
        game.config = config

        return topology

    @staticmethod
    def _scenario_user_site_name(scenario_user: ScenarioUser) -> str:
        """Extract the site name from a scenario_user created by ``_create_ai_scenario_users``."""
        name = scenario_user.name or ""
        return name[3:] if name.startswith("AI ") else name

    @staticmethod
    def _topological_sort(material_lanes: List[Tuple[str, str]]) -> List[str]:
        """Sort sites downstream-first using Kahn's algorithm.

        material_lanes: list of (upstream_name, downstream_name) tuples.
        Returns site names ordered with pure-demand sites first (e.g. retailer before factory).
        """
        from collections import deque
        all_sites: set = set()
        downstream_of: Dict[str, set] = {}
        upstream_of: Dict[str, set] = {}
        for up, down in material_lanes:
            all_sites.add(up)
            all_sites.add(down)
            downstream_of.setdefault(up, set()).add(down)
            upstream_of.setdefault(down, set()).add(up)

        in_degree = {site: len(upstream_of.get(site, set())) for site in all_sites}
        queue: deque = deque(sorted(s for s in all_sites if in_degree[s] == 0))
        result: List[str] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for downstream in sorted(downstream_of.get(node, set())):
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    queue.append(downstream)
        # Append any remaining nodes (cycle-safe)
        for site in sorted(all_sites):
            if site not in result:
                result.append(site)
        return result

    # ------------------------------------------------------------------
    # Game lifecycle helpers
    # ------------------------------------------------------------------

    def create_game(self, game_data: GameCreate) -> Game:
        """Create a new scenario and register AI scenario_users for every site."""

        supply_chain_config_id = getattr(game_data, "supply_chain_config_id", None)
        if supply_chain_config_id is None:
            raise ValueError("supply_chain_config_id is required to create an agent-only game")

        pattern_config = self._resolve_demand_pattern(game_data, supply_chain_config_id)
        game = Game(
            name=game_data.name,
            status=GameStatus.CREATED,
            current_period=0,
            max_periods=game_data.max_periods,
            demand_pattern=pattern_config,
            config={},
            supply_chain_config_id=int(supply_chain_config_id),
        )
        self.db.add(game)
        self.db.commit()
        self.db.refresh(game)

        topology = self._load_topology(game)

        # Set default policy config now that topology is known
        config = game.config or {}
        config["agent_policies"] = self._default_policy_config(topology["site_names"])
        game.config = config

        self._create_ai_scenario_users(game, topology)
        self.db.commit()
        self.db.refresh(game)
        return game

    def start_game(self, scenario_id: int) -> Game:
        game = self._get_game(scenario_id)
        if game.status not in {GameStatus.CREATED, GameStatus.PERIOD_COMPLETED}:
            raise ValueError("Game is already in progress or finished")

        topology = self._load_topology(game)
        config = self._ensure_agent_config(game, topology)
        config["executor_mode"] = "sc_execution"
        game.config = config
        game.status = GameStatus.STARTED
        game.current_period = 1
        game.started_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(game)
        return game

    def play_round(self, scenario_id: int) -> Dict[str, Any]:
        game = self._get_game(scenario_id)
        if game.status not in {
            GameStatus.STARTED,
            GameStatus.PERIOD_COMPLETED,
            GameStatus.PERIOD_IN_PROGRESS,
        }:
            raise ValueError("Game must be started before playing rounds")

        topology = self._load_topology(game)
        config = self._ensure_agent_config(game, topology)
        return self._play_round_sc(game, config, topology)

    def get_game_state(self, scenario_id: int) -> Dict[str, Any]:
        game = self._get_game(scenario_id)

        scenario_users = self._get_scenario_users_in_order(scenario_id)
        scenario_user_states: List[Dict[str, Any]] = []
        for scenario_user in scenario_users:
            inventory = scenario_user.inventory
            scenario_user_states.append(
                {
                    "id": scenario_user.id,
                    "name": scenario_user.name,
                    "role": scenario_user.role,
                    "is_ai": scenario_user.is_ai,
                    "inventory": inventory.current_stock if inventory else 0,
                    "backlog": inventory.backorders if inventory else 0,
                    "incoming_shipments": inventory.incoming_shipments if inventory else [0, 0],
                    "cost": inventory.cost if inventory else 0.0,
                }
            )

        return {
            "scenario_id": game.id,
            "name": game.name,
            "status": game.status,
            "current_period": game.current_period,
            "max_periods": game.max_periods,
            "scenario_users": scenario_user_states,
            "demand_pattern": game.demand_pattern,
        }

    # ------------------------------------------------------------------
    # Strategy management
    # ------------------------------------------------------------------

    def set_agent_strategy(
        self,
        scenario_id: int,
        role: str,
        strategy: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        game = self._get_game(scenario_id)
        topology = self._load_topology(game)
        config = self._ensure_agent_config(game, topology)

        label = self._normalise_role_label(role, topology)

        existing = config["agent_policies"].get(label, {"policy": "naive", "params": {}})
        merged_params = existing.get("params", {}).copy()
        if params:
            merged_params.update(params)

        # Validate strategy configuration by instantiating the policy
        make_policy(strategy, merged_params)

        config["agent_policies"][label] = {
            "policy": strategy,
            "params": merged_params,
        }

        engine_state = config.get("agent_engine_state")
        if engine_state and label in engine_state:
            engine_state[label]["base_stock"] = int(merged_params.get("base_stock", engine_state[label].get("base_stock", 20)))
            engine_state[label]["policy_state"] = {}
            config["agent_engine_state"] = engine_state

        game.config = config
        self.db.commit()

    def set_demand_visibility(self, visible: bool) -> None:
        self._demand_visible = bool(visible)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_policy_config(site_names: List[str]) -> Dict[str, Dict[str, Any]]:
        return {
            label: {"policy": "naive", "params": {"base_stock": 20}}
            for label in site_names
        }

    def _ensure_agent_config(self, game: Game, topology: Dict[str, Any] | None = None) -> Dict[str, Any]:
        config = game.config or {}
        if not isinstance(config, dict):
            config = {}

        if topology is None:
            topology = self._load_topology(game)

        site_names = topology["site_names"]
        policies = config.get("agent_policies")
        if not isinstance(policies, dict) or not policies:
            policies = self._default_policy_config(site_names)
        else:
            for label in site_names:
                policies.setdefault(label, {"policy": "naive", "params": {"base_stock": 20}})
        config["agent_policies"] = policies
        game.config = config
        return config

    def _resolve_demand_pattern(
        self, game_data: GameCreate, supply_chain_config_id: int
    ) -> Dict[str, Any]:
        """Select the demand pattern for an agent-only scenario.

        If the caller provided a demand pattern, we normalise and use it. When a
        supply chain configuration is linked, we prefer its saved demand pattern
        so the simulated demand aligns with the market definition shown in the
        UI reports.
        """

        fallback = (
            normalize_demand_pattern(game_data.demand_pattern.dict())
            if game_data.demand_pattern
            else normalize_demand_pattern(DEFAULT_DEMAND_PATTERN)
        )

        service = self._get_supply_chain_service()
        if not service:
            return fallback

        try:
            snapshot = service.create_game_from_config(
                supply_chain_config_id,
                {
                    "name": game_data.name or "Agent Game",
                    "description": game_data.description or "",
                    "max_periods": game_data.max_periods,
                },
            )
        except Exception:
            return fallback

        pattern_override = snapshot.get("demand_pattern") if isinstance(snapshot, dict) else None
        if not isinstance(pattern_override, dict) or not pattern_override:
            return fallback

        try:
            return normalize_demand_pattern(pattern_override)
        except Exception:
            return fallback

    def _get_supply_chain_service(self) -> SupplyChainConfigService | None:
        if self._supply_chain_service is None:
            try:
                self._supply_chain_service = SupplyChainConfigService(self.db)
            except Exception:
                self._supply_chain_service = None
        return self._supply_chain_service

    def _build_policy_map(self, config: Dict[str, Any]) -> Dict[str, Any]:
        policy_map: Dict[str, Any] = {}
        for label, spec in config.get("agent_policies", {}).items():
            policy_map[label] = make_policy(spec.get("policy", "naive"), spec.get("params"))
        return policy_map

    def _create_ai_scenario_users(self, game: Game, topology: Dict[str, Any]) -> None:
        """Create one AI scenario_user per site in the supply chain topology."""
        site_roles = topology["site_roles"]
        for site_name in topology["site_names"]:
            role_value = site_roles.get(site_name, ScenarioUserRole.RETAILER.value)
            try:
                role = ScenarioUserRole(role_value)
            except (ValueError, AttributeError):
                role = ScenarioUserRole.RETAILER
            scenario_user = ScenarioUser(
                scenario_id=game.id,
                name=f"AI {site_name}",
                role=role,
                is_ai=True,
            )
            self.db.add(scenario_user)

    def _get_game(self, scenario_id: int) -> Game:
        game = self.db.query(Game).filter(Game.id == scenario_id).first()
        if not game:
            raise ValueError("Game not found")
        return game

    def _get_scenario_users_in_order(
        self, scenario_id: int, topology: Dict[str, Any] | None = None
    ) -> List[ScenarioUser]:
        scenario_users = self.db.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario_id).all()
        if topology:
            site_order = {name: i for i, name in enumerate(topology["site_names"])}
            scenario_users.sort(key=lambda p: site_order.get(self._scenario_user_site_name(p), 999))
        return scenario_users

    def _get_or_create_round(self, game: Game, demand: int) -> ScenarioRound:
        round_record = (
            self.db.query(ScenarioRound)
            .filter(
                ScenarioRound.scenario_id == game.id,
                ScenarioRound.round_number == game.current_period,
            )
            .one_or_none()
        )
        if not round_record:
            round_record = ScenarioRound(
                scenario_id=game.id,
                round_number=game.current_period,
                customer_demand=demand,
                started_at=datetime.utcnow(),
            )
            self.db.add(round_record)
            self.db.flush()
        else:
            round_record.customer_demand = demand
        return round_record

    def _get_current_demand(self, round_number: int, demand_pattern: DemandPattern) -> int:
        if not getattr(demand_pattern, "pattern", None):
            self._generate_demand_pattern(demand_pattern)

        pattern = getattr(demand_pattern, "pattern", [])
        if 0 <= round_number - 1 < len(pattern):
            return pattern[round_number - 1]
        return 4

    def _generate_demand_pattern(self, demand_pattern: DemandPattern) -> None:
        normalized = normalize_demand_pattern(demand_pattern.dict())
        params = normalized.get("params", {})
        pattern_type_raw = normalized.get("type", DemandPatternType.CLASSIC.value)

        try:
            pattern_type = DemandPatternType(pattern_type_raw)
        except ValueError:
            pattern_type = DemandPatternType.CLASSIC

        total_rounds = max(int(params.get("horizon", 52) or 52), 20)
        try:
            generated = DemandGenerator.generate(pattern_type, total_rounds, **params)
        except Exception:
            generated = DemandGenerator.generate(DemandPatternType.CLASSIC, total_rounds)

        demand_pattern.pattern = generated

    def _play_round_sc(
        self, game: Game, config: Dict[str, Any], topology: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute one round via SimulationExecutor (SC entities path).

        Called when ``config["executor_mode"] == "sc_execution"``.  Loads current
        InvLevel state for each site, applies the configured agent policy to produce
        order quantities, then delegates execution to SimulationExecutor which
        handles PO creation, ATP, and state persistence against SC entities.
        """
        from app.services.sc_execution.simulation_executor import SimulationExecutor
        from app.models.sc_entities import InvLevel, Product as ProductModel

        demand_pattern = DemandPattern(**game.demand_pattern)
        current_demand = self._get_current_demand(game.current_period, demand_pattern)

        # Load current inventory state from InvLevel for policy obs
        config_id = game.supply_chain_config_id
        product = (
            self.db.query(ProductModel)
            .filter(ProductModel.config_id == config_id)
            .first()
        )
        product_id = product.id if product else None

        sites = (
            self.db.query(Site)
            .filter(Site.config_id == config_id)
            .all()
        )
        site_obs: Dict[str, Dict[str, Any]] = {}
        if product_id:
            for site in sites:
                inv = (
                    self.db.query(InvLevel)
                    .filter(
                        InvLevel.site_id == site.id,
                        InvLevel.product_id == product_id,
                    )
                    .first()
                )
                site_obs[site.name] = {
                    "inventory": float(inv.on_hand_qty or 0) if inv else 0.0,
                    "backlog": float(inv.backorder_qty or 0) if inv else 0.0,
                    "pipeline_on_order": float(inv.in_transit_qty or 0) if inv else 0.0,
                    "demand": float(current_demand),
                }

        # Apply agent policies to generate per-site order quantities
        policies = self._build_policy_map(config)
        agent_decisions: Dict[str, float] = {}
        for site_name in topology["site_names"]:
            policy = policies.get(site_name)
            obs = site_obs.get(site_name, {
                "inventory": 0.0, "backlog": 0.0,
                "pipeline_on_order": 0.0, "demand": float(current_demand),
            })
            try:
                qty = policy.order(obs) if policy else current_demand
            except Exception:
                qty = current_demand
            agent_decisions[site_name] = float(max(0, qty))

        # Delegate to SimulationExecutor (handles PO creation + SC entity updates)
        executor = SimulationExecutor(db=self.db, scenario=game)
        executor._load_config()
        executor.execute_round(
            round_number=game.current_period,
            agent_decisions=agent_decisions,
            market_demand=float(current_demand),
        )

        round_record = self._get_or_create_round(game, current_demand)
        round_record.is_completed = True
        round_record.completed_at = datetime.utcnow()

        if game.current_period >= game.max_periods:
            game.status = GameStatus.FINISHED
            game.finished_at = datetime.utcnow()
        else:
            game.current_period += 1
            game.status = GameStatus.PERIOD_COMPLETED

        self.db.commit()
        return self.get_game_state(game.id)

    def _normalise_role_label(self, role: str, topology: Dict[str, Any] | None = None) -> str:
        """Normalise a role string to the canonical site name used in policies."""
        if not role:
            raise ValueError("Role name is required")
        role_clean = role.strip()

        if topology:
            site_names = topology["site_names"]
            # Direct match
            if role_clean in site_names:
                return role_clean
            # Case-insensitive match
            name_map = {n.lower(): n for n in site_names}
            if role_clean.lower() in name_map:
                return name_map[role_clean.lower()]
            # Match by role type (e.g. "RETAILER" matches a site with that type)
            site_roles = topology["site_roles"]
            role_upper = role_clean.upper()
            for site_name, role_value in site_roles.items():
                if role_value == role_upper:
                    return site_name

        raise ValueError(f"Unknown role: {role}")
