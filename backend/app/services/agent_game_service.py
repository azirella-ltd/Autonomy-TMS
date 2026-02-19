"""Service layer for running fully automated Beer Game simulations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.demand_patterns import (
    DEFAULT_CLASSIC_PARAMS,
    DEFAULT_DEMAND_PATTERN,
    DemandGenerator,
    DemandPatternType,
    normalize_demand_pattern,
)
from app.models.scenario import Scenario, ScenarioStatus
from app.models.participant import Participant, ParticipantRole
from app.models.supply_chain import ScenarioRound, ParticipantInventory, ParticipantRound
from app.schemas.scenario import ScenarioCreate, DemandPattern

# Aliases for backwards compatibility
Game = Scenario
GameStatus = ScenarioStatus
Player = Participant
PlayerRole = ParticipantRole
GameRound = ScenarioRound
PlayerInventory = ParticipantInventory
PlayerRound = ParticipantRound
GameCreate = ScenarioCreate

from .engine import SupplyChainLine, DEFAULT_ORDER_LEAD_TIME, DEFAULT_SHIPMENT_LEAD_TIME
from .policy_factory import make_policy
from .supply_chain_config_service import SupplyChainConfigService


class AgentGameService:
    """Manage Beer Game simulations where every role is controlled by an agent."""

    # The role labels come directly from the SupplyChainLine's lane definition so that
    # "Manufacturer" remains the sole upstream node sending material to the
    # Distributor. Orders follow the reverse direction of these shipment lanes.

    ROLE_LABELS: Dict[PlayerRole, str] = {
        PlayerRole[label.upper()]: label for label in SupplyChainLine.role_sequence_names()
    }
    ROLE_SEQUENCE: List[PlayerRole] = list(ROLE_LABELS.keys())
    LABEL_TO_ROLE: Dict[str, PlayerRole] = {
        label: role for role, label in ROLE_LABELS.items()
    }

    def __init__(self, db_session: Session) -> None:
        self.db = db_session
        self._demand_visible = False
        self._supply_chain_service: SupplyChainConfigService | None = None

    # ------------------------------------------------------------------
    # Game lifecycle helpers
    # ------------------------------------------------------------------

    def create_game(self, game_data: GameCreate) -> Game:
        """Create a new Beer Game and register AI players for every role."""

        supply_chain_config_id = getattr(game_data, "supply_chain_config_id", None)
        if supply_chain_config_id is None:
            raise ValueError("supply_chain_config_id is required to create an agent-only game")

        pattern_config = self._resolve_demand_pattern(game_data, supply_chain_config_id)
        game = Game(
            name=game_data.name,
            status=GameStatus.CREATED,
            current_round=0,
            max_rounds=game_data.max_rounds,
            demand_pattern=pattern_config,
            config={"agent_policies": self._default_policy_config()},
            supply_chain_config_id=int(supply_chain_config_id),
        )
        self.db.add(game)
        self.db.commit()
        self.db.refresh(game)

        self._create_ai_players(game.id)
        return game

    def start_game(self, game_id: int) -> Game:
        game = self._get_game(game_id)
        if game.status not in {GameStatus.CREATED, GameStatus.ROUND_COMPLETED}:
            raise ValueError("Game is already in progress or finished")

        config = self._ensure_agent_config(game)
        sim_params = self._load_simulation_parameters(game, config)
        order_lead, ship_lead = self._extract_lead_times(sim_params)
        policies = self._build_policy_map(config)
        base_stocks = self._extract_base_stocks(config)
        steady_demand = self._steady_state_demand(game)
        line = SupplyChainLine(
            role_policies=policies,
            base_stocks=base_stocks,
            demand_lead_time=order_lead,
            shipment_lead_time=ship_lead,
            initial_demand=steady_demand,
        )

        config["agent_engine_state"] = line.to_dict()
        game.config = config
        game.status = GameStatus.STARTED
        game.current_round = 1
        game.started_at = datetime.utcnow()

        self._initialise_inventories(game, line)

        self.db.commit()
        self.db.refresh(game)
        return game

    def play_round(self, game_id: int) -> Dict[str, Any]:
        game = self._get_game(game_id)
        if game.status not in {
            GameStatus.STARTED,
            GameStatus.ROUND_COMPLETED,
            GameStatus.ROUND_IN_PROGRESS,
        }:
            raise ValueError("Game must be started before playing rounds")

        config = self._ensure_agent_config(game)
        state = config.get("agent_engine_state")
        if not state:
            raise ValueError("Game engine state is missing; ensure the game is started")

        demand_pattern = DemandPattern(**game.demand_pattern)
        current_demand = self._get_current_demand(game.current_round, demand_pattern)

        sim_params = self._load_simulation_parameters(game, config)
        order_lead, ship_lead = self._extract_lead_times(sim_params)
        policies = self._build_policy_map(config)
        base_stocks = self._extract_base_stocks(config)
        steady_demand = self._steady_state_demand(game)
        line = SupplyChainLine(
            role_policies=policies,
            base_stocks=base_stocks,
            state=state,
            demand_lead_time=order_lead,
            shipment_lead_time=ship_lead,
            initial_demand=steady_demand,
        )

        tick_stats = line.tick(current_demand)
        config["agent_engine_state"] = line.to_dict()
        game.config = config

        players = self._get_players_in_order(game_id)
        round_record = self._get_or_create_round(game, current_demand)

        node_map = {node.name: node for node in line.nodes}
        for player in players:
            label = self.ROLE_LABELS[player.role]
            node = node_map[label]
            node_stats = tick_stats[label]

            inventory_before = int(node_stats.get("inventory_before", node.inv))
            inventory_after = int(node_stats.get("inventory_after", node.inv))
            backlog_before = int(node_stats.get("backlog_before", node.backlog))
            backlog_after = int(node_stats.get("backlog_after", node.backlog))
            order_placed = int(node_stats.get("order_placed", 0))
            order_received = int(node_stats.get("incoming_shipment", 0))

            holding_cost = float(max(node.inv, 0))
            backlog_cost = float(node.backlog * 2)

            player_round = (
                self.db.query(PlayerRound)
                .filter(
                    PlayerRound.round_id == round_record.id,
                    PlayerRound.player_id == player.id,
                )
                .one_or_none()
            )
            if not player_round:
                player_round = PlayerRound(
                    round_id=round_record.id,
                    player_id=player.id,
                    order_placed=order_placed,
                    order_received=order_received,
                    inventory_before=inventory_before,
                    inventory_after=inventory_after,
                    backorders_before=backlog_before,
                    backorders_after=backlog_after,
                    holding_cost=holding_cost,
                    backorder_cost=backlog_cost,
                    total_cost=holding_cost + backlog_cost,
                )
                self.db.add(player_round)
            else:
                player_round.order_placed = order_placed
                player_round.order_received = order_received
                player_round.inventory_before = inventory_before
                player_round.inventory_after = inventory_after
                player_round.backorders_before = backlog_before
                player_round.backorders_after = backlog_after
                player_round.holding_cost = holding_cost
                player_round.backorder_cost = backlog_cost
                player_round.total_cost = holding_cost + backlog_cost

            inventory = player.inventory
            if not inventory:
                inventory = PlayerInventory(player_id=player.id)
                self.db.add(inventory)
            inventory.current_stock = node.inv
            inventory.backorders = node.backlog
            inventory.incoming_shipments = list(node.pipeline_shipments)
            inventory.cost = node.cost

        round_record.is_completed = True
        round_record.completed_at = datetime.utcnow()

        if game.current_round >= game.max_rounds:
            game.status = GameStatus.FINISHED
            game.finished_at = datetime.utcnow()
        else:
            game.current_round += 1
            game.status = GameStatus.ROUND_COMPLETED

        self.db.commit()
        return self.get_game_state(game_id)

    def get_game_state(self, game_id: int) -> Dict[str, Any]:
        game = self._get_game(game_id)

        players = self._get_players_in_order(game_id)
        player_states: List[Dict[str, Any]] = []
        for player in players:
            inventory = player.inventory
            player_states.append(
                {
                    "id": player.id,
                    "name": player.name,
                    "role": player.role,
                    "is_ai": player.is_ai,
                    "inventory": inventory.current_stock if inventory else 0,
                    "backlog": inventory.backorders if inventory else 0,
                    "incoming_shipments": inventory.incoming_shipments if inventory else [0, 0],
                    "cost": inventory.cost if inventory else 0.0,
                }
            )

        return {
            "game_id": game.id,
            "name": game.name,
            "status": game.status,
            "current_round": game.current_round,
            "max_rounds": game.max_rounds,
            "players": player_states,
            "demand_pattern": game.demand_pattern,
        }

    # ------------------------------------------------------------------
    # Strategy management
    # ------------------------------------------------------------------

    def set_agent_strategy(
        self,
        game_id: int,
        role: str,
        strategy: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        game = self._get_game(game_id)
        config = self._ensure_agent_config(game)

        label = self._normalise_role_label(role)

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

    def _default_policy_config(self) -> Dict[str, Dict[str, Any]]:
        return {
            label: {"policy": "naive", "params": {"base_stock": 20}}
            for label in self.ROLE_LABELS.values()
        }

    def _ensure_agent_config(self, game: Game) -> Dict[str, Any]:
        config = game.config or {}
        if not isinstance(config, dict):
            config = {}
        policies = config.get("agent_policies")
        if not isinstance(policies, dict) or not policies:
            policies = self._default_policy_config()
        else:
            for label in self.ROLE_LABELS.values():
                policies.setdefault(label, {"policy": "naive", "params": {"base_stock": 20}})
        config["agent_policies"] = policies
        game.config = config
        return config

    def _load_simulation_parameters(self, game: Game, config: Dict[str, Any]) -> Dict[str, Any]:
        sim_params = config.get("simulation_parameters")
        if isinstance(sim_params, dict) and sim_params:
            return sim_params

        params: Dict[str, Any] = {}
        service = self._get_supply_chain_service()
        if service and game.supply_chain_config_id:
            try:
                snapshot = service.create_game_from_config(
                    game.supply_chain_config_id,
                    {"name": game.name or "Agent Game", "description": game.description or ""},
                )
                params = snapshot.get("simulation_parameters", {}) or {}
            except Exception:
                params = {}

        if params:
            config["simulation_parameters"] = params
            game.config = config
        return params

    def _resolve_demand_pattern(
        self, game_data: GameCreate, supply_chain_config_id: int
    ) -> Dict[str, Any]:
        """Select the demand pattern for an agent-only game.

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
                    "max_rounds": game_data.max_rounds,
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

    def _extract_lead_times(self, sim_params: Dict[str, Any]) -> tuple[int, int]:
        order_lead = sim_params.get("demand_lead_time") or sim_params.get("order_leadtime")
        ship_lead = sim_params.get("shipping_lead_time") or sim_params.get("supply_leadtime")

        try:
            order_val = int(order_lead) if order_lead is not None else DEFAULT_ORDER_LEAD_TIME
        except (TypeError, ValueError):
            order_val = DEFAULT_ORDER_LEAD_TIME

        try:
            ship_val = int(ship_lead) if ship_lead is not None else DEFAULT_SHIPMENT_LEAD_TIME
        except (TypeError, ValueError):
            ship_val = DEFAULT_SHIPMENT_LEAD_TIME

        return max(0, order_val), max(0, ship_val)

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

    def _extract_base_stocks(self, config: Dict[str, Any]) -> Dict[str, int]:
        base_stocks: Dict[str, int] = {}
        for label, spec in config.get("agent_policies", {}).items():
            params = spec.get("params") or {}
            base_stocks[label] = int(params.get("base_stock", 20))
        return base_stocks

    def _steady_state_demand(self, game: Game) -> int:
        try:
            demand_pattern = DemandPattern(**game.demand_pattern)
        except Exception:
            return DEFAULT_CLASSIC_PARAMS["initial_demand"]

        initial = self._get_current_demand(1, demand_pattern)
        try:
            return max(0, int(initial))
        except (TypeError, ValueError):
            return DEFAULT_CLASSIC_PARAMS["initial_demand"]

    def _create_ai_players(self, game_id: int) -> None:
        for role in self.ROLE_SEQUENCE:
            player = Player(
                game_id=game_id,
                name=f"AI {self.ROLE_LABELS[role]}",
                role=role,
                is_ai=True,
            )
            self.db.add(player)
        self.db.commit()

    def _initialise_inventories(self, game: Game, line: SupplyChainLine) -> None:
        players = self._get_players_in_order(game.id)
        node_map = {node.name: node for node in line.nodes}
        for player in players:
            node = node_map[self.ROLE_LABELS[player.role]]
            inventory = player.inventory
            if not inventory:
                inventory = PlayerInventory(player_id=player.id)
                self.db.add(inventory)
            inventory.current_stock = node.inv
            inventory.backorders = node.backlog
            inventory.incoming_shipments = list(node.pipeline_shipments)
            inventory.cost = node.cost

    def _get_game(self, game_id: int) -> Game:
        game = self.db.query(Game).filter(Game.id == game_id).first()
        if not game:
            raise ValueError("Game not found")
        return game

    def _get_players_in_order(self, game_id: int) -> List[Player]:
        players = self.db.query(Player).filter(Player.game_id == game_id).all()
        players.sort(key=lambda p: self.ROLE_SEQUENCE.index(p.role))
        return players

    def _get_or_create_round(self, game: Game, demand: int) -> GameRound:
        round_record = (
            self.db.query(GameRound)
            .filter(
                GameRound.game_id == game.id,
                GameRound.round_number == game.current_round,
            )
            .one_or_none()
        )
        if not round_record:
            round_record = GameRound(
                game_id=game.id,
                round_number=game.current_round,
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

    def _normalise_role_label(self, role: str) -> str:
        if not role:
            raise ValueError("Role name is required")
        role_clean = role.strip()
        if role_clean.title() in self.LABEL_TO_ROLE:
            return role_clean.title()
        role_upper = role_clean.upper()
        for enum_role, label in self.ROLE_LABELS.items():
            if enum_role.name == role_upper:
                return label
        raise ValueError(f"Unknown role: {role}")
