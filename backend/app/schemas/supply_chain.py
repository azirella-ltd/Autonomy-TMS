from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

# Shared properties
class DistributionParams(BaseModel):
    distribution: str = "lognormal"
    mean: float = Field(..., gt=0, description="Mean of the distribution")
    std: float = Field(..., gt=0, description="Standard deviation of the distribution")

# Node Type schemas
class NodeTypeBase(BaseModel):
    name: str
    description: Optional[str] = None

class NodeTypeCreate(NodeTypeBase):
    pass

class NodeType(NodeTypeBase):
    id: int
    
    class Config:
        orm_mode = True

# Node schemas
class NodeBase(BaseModel):
    name: str
    node_type_id: int
    capacity: DistributionParams
    lead_time: DistributionParams
    throughput: DistributionParams

class NodeCreate(NodeBase):
    pass

class Node(NodeBase):
    id: int
    
    class Config:
        orm_mode = True

# Edge schemas
class EdgeBase(BaseModel):
    source_id: int
    destination_id: int
    cost_per_unit: float = 0.0
    transport_lead_time: DistributionParams

class EdgeCreate(EdgeBase):
    pass

class Edge(EdgeBase):
    id: int
    
    class Config:
        orm_mode = True

# Inventory schemas
class InventoryBase(BaseModel):
    site_id: int
    product_id: int
    quantity: int = 0
    safety_stock: int = 0
    reorder_point: int = 0

class InventoryCreate(InventoryBase):
    pass

class Inventory(InventoryBase):
    id: int
    
    class Config:
        orm_mode = True

# Product schemas
class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    unit_cost: float = 0.0

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    id: int
    
    class Config:
        orm_mode = True

# Simulation Run schemas
class SimulationRunBase(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

class SimulationRunCreate(SimulationRunBase):
    pass

class SimulationRun(SimulationRunBase):
    id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    
    class Config:
        orm_mode = True

# Simulation Step schemas
class SimulationStepBase(BaseModel):
    simulation_run_id: int
    step_number: int
    state: Dict[str, Any]

class SimulationStepCreate(SimulationStepBase):
    pass

class SimulationStep(SimulationStepBase):
    id: int
    timestamp: datetime
    
    class Config:
        orm_mode = True

# Response models
class SupplyChainGraph(BaseModel):
    nodes: List[Node]
    edges: List[Edge]

class SimulationResult(BaseModel):
    simulation: SimulationRun
    steps: List[SimulationStep]

class BullwhipAnalysis(BaseModel):
    simulation_id: int
    order_variations: Dict[str, List[float]]
    inventory_variations: Dict[str, List[float]]
    bullwhip_effect: float
    
    class Config:
        schema_extra = {
            "example": {
                "simulation_id": 1,
                "order_variations": {
                    "retailer": [0.1, 0.2, 0.15, ...],
                    "distributor": [0.2, 0.3, 0.25, ...],
                    "manufacturer": [0.3, 0.4, 0.35, ...]
                },
                "inventory_variations": {
                    "retailer": [5, 4, 6, ...],
                    "distributor": [10, 12, 9, ...],
                    "manufacturer": [20, 18, 22, ...]
                },
                "bullwhip_effect": 1.8
            }
        }
