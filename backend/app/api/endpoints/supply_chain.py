from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import json

from app.db.session import get_sync_db as get_db
from app.models.supply_chain import Node, NodeType, Edge, Inventory, Product, SimulationRun, SimulationStep
from app.schemas.supply_chain import (
    NodeCreate, NodeTypeCreate, EdgeCreate, InventoryCreate, ProductCreate,
    SimulationRunCreate, SimulationStepCreate, Node as NodeSchema, NodeType as NodeTypeSchema,
    Edge as EdgeSchema, Inventory as InventorySchema, Product as ProductSchema,
    SimulationRun as SimulationRunSchema, SimulationStep as SimulationStepSchema
)
from app.services.gnn_model import SupplyChainSimulator

router = APIRouter()

# Initialize the simulator
simulator = SupplyChainSimulator()

# Node Type Endpoints
@router.post("/node-types/", response_model=NodeTypeSchema)
def create_node_type(node_type: NodeTypeCreate, db: Session = Depends(get_db)):
    db_node_type = NodeType(**node_type.dict())
    db.add(db_node_type)
    db.commit()
    db.refresh(db_node_type)
    return db_node_type

@router.get("/node-types/", response_model=List[NodeTypeSchema])
def read_node_types(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(NodeType).offset(skip).limit(limit).all()

# Node Endpoints
@router.post("/nodes/", response_model=NodeSchema)
def create_node(node: NodeCreate, db: Session = Depends(get_db)):
    db_node = Node(**node.dict())
    db.add(db_node)
    db.commit()
    db.refresh(db_node)
    return db_node

@router.get("/nodes/", response_model=List[NodeSchema])
def read_nodes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Node).offset(skip).limit(limit).all()

# Edge Endpoints
@router.post("/edges/", response_model=EdgeSchema)
def create_edge(edge: EdgeCreate, db: Session = Depends(get_db)):
    db_edge = Edge(**edge.dict())
    db.add(db_edge)
    db.commit()
    db.refresh(db_edge)
    return db_edge

@router.get("/edges/", response_model=List[EdgeSchema])
def read_edges(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Edge).offset(skip).limit(limit).all()

# Simulation Endpoints
@router.post("/simulations/", response_model=SimulationRunSchema)
def create_simulation(simulation: SimulationRunCreate, db: Session = Depends(get_db)):
    db_simulation = SimulationRun(**simulation.dict())
    db.add(db_simulation)
    db.commit()
    db.refresh(db_simulation)
    return db_simulation

@router.post("/simulations/{simulation_id}/run")
def run_simulation(simulation_id: int, num_steps: int = 10, db: Session = Depends(get_db)):
    # Get the simulation
    db_simulation = db.query(SimulationRun).filter(SimulationRun.id == simulation_id).first()
    if not db_simulation:
        raise HTTPException(status_code=404, detail="Simulation not found")
    
    # Get the current state of the supply chain
    nodes = db.query(Node).all()
    edges = db.query(Edge).all()
    
    # Convert to a format suitable for the simulator
    initial_state = {
        'nodes': [{
            'id': node.id,
            'type': node.node_type,
            'capacity': node.capacity,
            'lead_time': node.lead_time,
            'throughput': node.throughput,
            'inventory': [inv.quantity for inv in node.inventory]
        } for node in nodes],
        'edges': [{
            'source': edge.source_id,
            'target': edge.destination_id,
            'cost_per_unit': edge.cost_per_unit,
            'transport_lead_time': edge.transport_lead_time
        } for edge in edges]
    }
    
    # Run the simulation
    states = simulator.run_simulation(initial_state, num_steps)
    
    # Save the simulation results
    for step, state in enumerate(states):
        db_step = SimulationStep(
            simulation_run_id=simulation_id,
            step_number=step,
            state=json.dumps(state)
        )
        db.add(db_step)
    
    db.commit()
    
    return {"status": "completed", "steps": len(states)}

@router.get("/simulations/{simulation_id}/steps/{step_number}")
def get_simulation_step(simulation_id: int, step_number: int, db: Session = Depends(get_db)):
    step = db.query(SimulationStep).filter(
        SimulationStep.simulation_run_id == simulation_id,
        SimulationStep.step_number == step_number
    ).first()
    
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    
    return json.loads(step.state)

# Analysis Endpoints
@router.get("/analysis/bullwhip-effect/{simulation_id}")
def analyze_bullwhip_effect(simulation_id: int, db: Session = Depends(get_db)):
    # Get all steps for this simulation
    steps = db.query(SimulationStep).filter(
        SimulationStep.simulation_run_id == simulation_id
    ).order_by(SimulationStep.step_number).all()
    
    # Calculate bullwhip effect metrics
    # This is a simplified example - implement your actual analysis here
    order_variations = []
    inventory_variations = []
    
    for i in range(1, len(steps)):
        prev_state = json.loads(steps[i-1].state)
        curr_state = json.loads(steps[i].state)
        
        # Calculate order variations
        for site_id, node in enumerate(curr_state['nodes']):
            # Compare with previous state to calculate variations
            pass
    
    return {
        "order_variations": order_variations,
        "inventory_variations": inventory_variations
    }
