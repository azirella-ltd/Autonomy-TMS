import logging

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from ..models import (
    Group,
    User,
    SupplyChainConfig,
    Scenario as Game,
    ScenarioStatus as GameStatus,
    Participant as Player,
    ParticipantRole as PlayerRole,
    ParticipantType as PlayerType,
    ParticipantStrategy as PlayerStrategy,
)
from ..models.user import UserTypeEnum
from ..models.supply_chain_config import (
    # Item, ProductSiteConfig - REMOVED: migrated to Product table
    Node,
    TransportationLane,
    Market,
    MarketDemand,
    NodeType,
)
from ..models.sc_entities import Product, ProductBom
from ..schemas.group import GroupCreate, GroupUpdate
from ..core.security import get_password_hash
from app.core.time_buckets import TimeBucket
from .supply_chain_config_service import SupplyChainConfigService
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat

logger = logging.getLogger(__name__)

DEFAULT_SITE_TYPE_DEFINITIONS = [
    {
        "type": "factory",
        "label": "Factory",
        "order": 4,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "distributor",
        "label": "Distributor",
        "order": 3,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "wholesaler",
        "label": "Wholesaler",
        "order": 2,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "retailer",
        "label": "Retailer",
        "order": 1,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "market_supply",
        "label": "Market Supply",
        "order": 5,
        "is_required": True,
        "master_type": "market_supply",
    },
    {
        "type": "market_demand",
        "label": "Market Demand",
        "order": 0,
        "is_required": True,
        "master_type": "market_demand",
    },
]


class GroupService:
    def __init__(self, db: Session):
        self.db = db

    def get_groups(self):
        return self.db.query(Group).all()

    def get_group(self, group_id: int) -> Group:
        group = self.db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )
        return group

    def create_group(self, group_in: GroupCreate) -> Group:
        admin_data = group_in.admin
        hashed_password = get_password_hash(admin_data.password)
        try:
            admin_user = User(
                username=admin_data.username,
                email=admin_data.email,
                full_name=admin_data.full_name,
                hashed_password=hashed_password,
                user_type=UserTypeEnum.GROUP_ADMIN,
                is_active=True,
                is_superuser=False,
            )
            self.db.add(admin_user)
            self.db.flush()

            group = Group(
                name=group_in.name,
                description=group_in.description,
                logo=group_in.logo,
                admin_id=admin_user.id,
            )
            self.db.add(group)
            self.db.flush()

            admin_user.group_id = group.id
            self.db.add(admin_user)

            sc_config = SupplyChainConfig(
                name="Default Supply Chain",
                description="Default supply chain configuration",
                created_by=admin_user.id,
                group_id=group.id,
                is_active=True,
                time_bucket=TimeBucket.WEEK,
                site_type_definitions=DEFAULT_SITE_TYPE_DEFINITIONS,
            )
            self.db.add(sc_config)
            self.db.flush()

            item = Item(
                config_id=sc_config.id,
                name="Standard Product",
                description="Default product for the simulation"
            )
            self.db.add(item)
            self.db.flush()

            node_specs = [
                ("Market Demand", NodeType.MARKET_DEMAND, "market_demand", "market_demand"),
                ("Retailer", NodeType.RETAILER, "retailer", "inventory"),
                ("Wholesaler", NodeType.WHOLESALER, "wholesaler", "inventory"),
                ("Distributor", NodeType.DISTRIBUTOR, "distributor", "inventory"),
                ("Factory", NodeType.MANUFACTURER, "factory", "inventory"),
                ("Market Supply", NodeType.MARKET_SUPPLY, "market_supply", "market_supply"),
            ]
            nodes = {}
            for name, node_type, dag_type, master_type in node_specs:
                node = Node(
                    config_id=sc_config.id,
                    name=name,
                    type=dag_type,
                    dag_type=dag_type,
                    master_type=master_type,
                )
                self.db.add(node)
                self.db.flush()
                nodes[node_type] = node

            lane_specs = [
                (NodeType.MARKET_SUPPLY, NodeType.MANUFACTURER),
                (NodeType.MANUFACTURER, NodeType.DISTRIBUTOR),
                (NodeType.DISTRIBUTOR, NodeType.WHOLESALER),
                (NodeType.WHOLESALER, NodeType.RETAILER),
                (NodeType.RETAILER, NodeType.MARKET_DEMAND),
            ]
            for upstream_type, downstream_type in lane_specs:
                lane = TransportationLane(
                    config_id=sc_config.id,
                    from_site_id=nodes[upstream_type].id,
                    to_site_id=nodes[downstream_type].id,
                    capacity=9999,
                    lead_time_days={
                        "min": 0
                        if upstream_type == NodeType.MARKET_SUPPLY or downstream_type == NodeType.MARKET_DEMAND
                        else 2,
                        "max": 0
                        if upstream_type == NodeType.MARKET_SUPPLY or downstream_type == NodeType.MARKET_DEMAND
                        else 10,
                    },
                    demand_lead_time={"type": "deterministic", "value": 1},
                    supply_lead_time={"type": "deterministic", "value": 2},
                )
                self.db.add(lane)

            self.db.flush()

            for node in nodes.values():
                if str(node.master_type or "").lower() in {"market_supply", "market_demand"}:
                    continue
                product_site_config = ProductSiteConfig(
                    product_id=item.id,
                    site_id=node.id,
                    inventory_target_range={"min": 10, "max": 20},
                    initial_inventory_range={"min": 5, "max": 30},
                    holding_cost_range={"min": 1.0, "max": 5.0},
                    backlog_cost_range={"min": 5.0, "max": 10.0},
                    selling_price_range={"min": 25.0, "max": 50.0},
                )
                self.db.add(product_site_config)

                market = Market(
                    config_id=sc_config.id,
                    name="Default Market",
                    description="Primary demand market",
                )
                self.db.add(market)
                self.db.flush()

                market_demand = MarketDemand(
                    config_id=sc_config.id,
                    product_id=item.id,
                    market_id=market.id,
                    demand_pattern={
                        "demand_type": "constant",
                        "variability": {"type": "flat", "value": 4},
                        "seasonality": {"type": "none", "amplitude": 0, "period": 12, "phase": 0},
                        "trend": {"type": "none", "slope": 0, "intercept": 0},
                        "parameters": {"value": 4},
                        "params": {"value": 4},
                    },
                )
                self.db.add(market_demand)
                self.db.flush()

                config_service = SupplyChainConfigService(self.db)
                game_config = config_service.create_game_from_config(
                    sc_config.id,
                    {"name": "Default Scenario", "max_rounds": 50},
                )

                game = Game(
                    name=game_config.get("name", "Default Scenario"),
                    created_by=admin_user.id,
                    group_id=group.id,
                    status=GameStatus.CREATED,
                    max_rounds=game_config.get("max_rounds", 52),
                    config=game_config,
                    demand_pattern=game_config.get("demand_pattern", {}),
                    supply_chain_config_id=sc_config.id,
                )
                self.db.add(game)
                self.db.flush()

                group_suffix = f"g{group.id}"
                player_password_hash = get_password_hash("Autonomy@2025")
                default_users = [
                    {
                        "username": f"retailer_{group_suffix}",
                        "email": f"retailer+{group_suffix}@autonomy.ai",
                        "full_name": "Retailer",
                        "role": PlayerRole.RETAILER,
                    },
                    {
                        "username": f"distributor_{group_suffix}",
                        "email": f"distributor+{group_suffix}@autonomy.ai",
                        "full_name": "Distributor",
                        "role": PlayerRole.DISTRIBUTOR,
                    },
                    {
                        "username": f"manufacturer_{group_suffix}",
                        "email": f"manufacturer+{group_suffix}@autonomy.ai",
                        "full_name": "Factory",
                        "role": PlayerRole.MANUFACTURER,
                    },
                    {
                        "username": f"wholesaler_{group_suffix}",
                        "email": f"wholesaler+{group_suffix}@autonomy.ai",
                        "full_name": "Wholesaler",
                        "role": PlayerRole.WHOLESALER,
                    },
                ]

                player_users = []
                for spec in default_users:
                    user = User(
                        username=spec["username"],
                        email=spec["email"],
                        full_name=spec["full_name"],
                        hashed_password=player_password_hash,
                        user_type=UserTypeEnum.USER,
                        group_id=group.id,
                        is_active=True,
                        is_superuser=False,
                    )
                    self.db.add(user)
                    self.db.flush()
                    player_users.append((user, spec["role"], spec["full_name"]))

                players = []
                for user_obj, role_enum, display_name in player_users:
                    player = Player(
                        scenario_id=game.id,
                        user_id=user_obj.id,
                        name=display_name,
                        role=role_enum,
                        type=PlayerType.AI,
                        strategy=PlayerStrategy.MANUAL,
                        is_ai=True,
                        ai_strategy="naive",
                    )
                    players.append(player)

                self.db.add_all(players)

                game.role_assignments = {
                    role_enum.value: {
                        "is_ai": True,
                        "agent_config_id": None,
                        "user_id": user_obj.id,
                        "strategy": "naive",
                    }
                    for user_obj, role_enum, _ in player_users
                }
                self.db.add(game)

                self.db.commit()
                self.db.refresh(group)
                return group
        except Exception:
            self.db.rollback()
            logger.exception("Failed to create group %s", group_in.name)
            raise HTTPException(status_code=500, detail="Error creating group")

    def update_group(self, group_id: int, group_update: GroupUpdate) -> Group:
        group = self.db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        for field, value in group_update.dict(exclude_unset=True).items():
            setattr(group, field, value)
        self.db.commit()
        self.db.refresh(group)
        return group

    def delete_group(self, group_id: int):
        group = self.db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        self.db.delete(group)
        self.db.commit()
        return {"message": "Group deleted"}
