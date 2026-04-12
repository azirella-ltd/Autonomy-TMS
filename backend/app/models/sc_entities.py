"""SC entities — re-exports from canonical azirella-data-model.

All 34 classes from the original sc_entities.py are now in the canonical
azirella-data-model master subpackage. This file re-exports them so
existing imports (`from app.models.sc_entities import Product`) work
unchanged.

Stage 3 Phase 3c — TMS adopts azirella-data-model master subpackage.
"""
from azirella_data_model.master import (  # noqa: F401
    Backorder,
    Company,
    ConsensusDemand,
    CustomerCost,
    FinalAssemblySchedule,
    Forecast,
    FulfillmentOrder,
    Geography,
    InboundOrder,
    InboundOrderLine,
    InboundOrderLineSchedule,
    InvLevel,
    InvPolicy,
    InventoryProjection,
    OutboundOrder,
    OutboundOrderLine,
    OutboundShipment,
    ProcessHeader,
    ProcessOperation,
    ProcessProduct,
    Product,
    ProductBom,
    ProductHierarchy,
    ProductionProcess,
    Reservation,
    Segmentation,
    Shipment,
    ShipmentLot,
    ShipmentStop,
    SourcingRules,
    SupplementaryTimeSeries,
    SupplyPlan,
    SupplyPlanningParameters,
    TradingPartner,
)
