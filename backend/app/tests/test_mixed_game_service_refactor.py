import pytest
from unittest.mock import MagicMock, patch
from app.services.mixed_game_service import MixedScenarioService
from app.schemas.simulation import RoundContext, NodeState, TopologyConfig, OrderRequest, LaneConfig
from app.models.scenario import Scenario
from app.models.participant import Participant, ParticipantRole
from app.models.supply_chain import ScenarioRound
from app.services.agents import AgentManager, AgentType, AgentStrategy

@pytest.fixture
def mock_service():
    service = MixedScenarioService.__new__(MixedScenarioService)
    service.db = MagicMock()
    service.agent_manager = MagicMock()
    return service

@pytest.fixture
def mock_context():
    topology = TopologyConfig(
        lanes=[],
        shipments_map={},
        orders_map={"retailer": ["wholesaler"]},
        market_nodes=["customer"],
        all_nodes=["retailer", "wholesaler"],
        node_sequence=["wholesaler", "retailer"],
        lanes_by_upstream={},
        node_types={"retailer": "retailer", "wholesaler": "wholesaler"},
        lane_lookup={("wholesaler", "retailer"): LaneConfig(**{"from": "wholesaler", "to": "retailer", "demand_lead_time": 1})}
    )
    
    node_states = {
        "retailer": NodeState(
            inventory_by_item={"default": 10},
            current_round_demand={"default": 5}
        ),
        "wholesaler": NodeState(
            inventory_by_item={"default": 20},
            inbound_demand=[]
        )
    }
    
    return RoundContext(
        round_number=1,
        scenario_id=1,
        topology=topology,
        node_states=node_states,
        node_policies={"wholesaler": {"order_leadtime": 1}}
    )

def test_process_ai_players_places_order(mock_service, mock_context):
    # Setup
    game = Scenario(id=1, config={})
    game_round = ScenarioRound(round_number=1)
    player = Participant(id=1, scenario_id=1, role=ParticipantRole.RETAILER, is_ai=True)
    
    mock_service.db.query.return_value.filter.return_value.all.return_value = [player]
    
    # Mock resolve_player_mappings to return our player for retailer
    mock_service._resolve_player_mappings = MagicMock(return_value={"retailer": [player]})
    
    # Mock agent decision
    mock_agent = MagicMock()
    mock_agent.make_decision.return_value.quantity = 10
    mock_service.agent_manager.get_agent.return_value = mock_agent
    
    # Execute
    mock_service.process_ai_players(game, game_round, mock_context)
    
    # Verify
    # Check if order was added to wholesaler's queue
    wholesaler_queue = mock_context.node_states["wholesaler"].inbound_demand
    assert len(wholesaler_queue) == 1
    order = wholesaler_queue[0]
    assert order.quantity == 10
    assert order.source == "retailer"
    assert order.downstream == "retailer"
    assert order.due_round == 2 # current_period (1) + leadtime (1)

def test_process_ai_players_skips_if_no_players(mock_service, mock_context):
    game = Scenario(id=1)
    game_round = ScenarioRound(round_number=1)
    mock_service.db.query.return_value.filter.return_value.all.return_value = []
    
    mock_service._resolve_player_mappings = MagicMock()
    mock_service.process_ai_players(game, game_round, mock_context)
    
    assert not mock_service._resolve_player_mappings.called
