"""
Planning Cascade API Endpoints

Full cascade from S&OP through Supply Commit and Allocation Commit.
Supports both FULL mode (all layers) and INPUT mode (agents only).

Endpoints:
- Policy Envelope (S&OP parameters)
- Supply Baseline Pack (MRS candidates)
- Supply Commit (Supply Agent decisions)
- Allocation Commit (Allocation Agent decisions)
- Feed-back Signals
- Cascade Orchestration
"""

from typing import Dict, List, Optional, Any
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.session import get_db, get_sync_db
from app.services.planning_cascade import (
    SOPService, SOPMode, SOPParameters, ServiceTierTarget, CategoryPolicy,
    MRSService, ProductInventoryState, SupplierInfo,
    SupplyAgent, AllocationAgent,
    CascadeOrchestrator, CascadeMode,
)

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class ServiceTierTargetInput(BaseModel):
    """Service tier target input"""
    segment: str
    otif_floor: float = Field(..., ge=0, le=1)
    fill_rate_target: float = Field(0.98, ge=0, le=1)


class CategoryPolicyInput(BaseModel):
    """Category policy input"""
    category: str
    safety_stock_wos: float = Field(..., ge=0)
    dos_ceiling: int = Field(..., ge=1)
    expedite_cap: float = Field(..., ge=0)


class PolicyEnvelopeCreate(BaseModel):
    """Create policy envelope request"""
    config_id: int
    group_id: int
    mode: str = Field("INPUT", description="FULL or INPUT")
    service_tiers: List[ServiceTierTargetInput]
    category_policies: List[CategoryPolicyInput]
    total_inventory_cap: Optional[float] = None
    gmroi_target: float = 3.0
    effective_date: Optional[date] = None


class CustomerPlanOrder(BaseModel):
    """Single order in customer plan"""
    sku: str
    supplier_id: Optional[str] = None
    destination_id: str = "DC-001"
    qty: float
    order_date: date
    receipt_date: Optional[date] = None


class SupplyBaselinePackCreate(BaseModel):
    """Create SupBP request"""
    config_id: int
    group_id: int
    policy_envelope_id: int
    mode: str = Field("FULL", description="FULL or INPUT")
    customer_plan: Optional[List[CustomerPlanOrder]] = None


class SupplyCommitReview(BaseModel):
    """Review supply commit request"""
    action: str = Field(..., description="accept, override, or reject")
    override_details: Optional[Dict[str, Any]] = None


class AllocationCommitReview(BaseModel):
    """Review allocation commit request"""
    action: str = Field(..., description="accept, override, or reject")
    override_details: Optional[Dict[str, Any]] = None


class CascadeRunRequest(BaseModel):
    """Run full cascade request"""
    config_id: int
    group_id: int
    mode: str = Field("INPUT", description="FULL or INPUT")
    agent_mode: str = Field("copilot", description="copilot or autonomous")
    use_food_dist_defaults: bool = False


class FeedBackSignalCreate(BaseModel):
    """Create feed-back signal request"""
    config_id: int
    group_id: int
    signal_type: str
    metric_name: str
    metric_value: float
    threshold: Optional[float] = None
    details: Optional[Dict[str, Any]] = None
    supply_commit_id: Optional[int] = None
    allocation_commit_id: Optional[int] = None


# =============================================================================
# Policy Envelope Endpoints
# =============================================================================

@router.post("/policy-envelope", tags=["S&OP"])
def create_policy_envelope(
    request: PolicyEnvelopeCreate,
    db: Session = Depends(get_sync_db),
):
    """
    Create a policy envelope.

    In FULL mode: Runs S&OP simulation to generate optimized parameters.
    In INPUT mode: Uses provided parameters directly.
    """
    mode = SOPMode.FULL if request.mode.upper() == "FULL" else SOPMode.INPUT
    service = SOPService(db, mode)

    params = SOPParameters(
        service_tiers=[
            ServiceTierTarget(
                segment=t.segment,
                otif_floor=t.otif_floor,
                fill_rate_target=t.fill_rate_target,
            )
            for t in request.service_tiers
        ],
        category_policies=[
            CategoryPolicy(
                category=p.category,
                safety_stock_wos=p.safety_stock_wos,
                dos_ceiling=p.dos_ceiling,
                expedite_cap=p.expedite_cap,
            )
            for p in request.category_policies
        ],
        total_inventory_cap=request.total_inventory_cap,
        gmroi_target=request.gmroi_target,
        effective_date=request.effective_date or date.today(),
    )

    try:
        envelope = service.create_policy_envelope(
            config_id=request.config_id,
            group_id=request.group_id,
            params=params,
        )
        return envelope
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/policy-envelope/active/{config_id}", tags=["S&OP"])
def get_active_policy_envelope(
    config_id: int,
    as_of_date: Optional[date] = None,
    db: Session = Depends(get_sync_db),
):
    """Get the active policy envelope for a config"""
    service = SOPService(db)
    envelope = service.get_active_envelope(config_id, as_of_date)
    if not envelope:
        raise HTTPException(status_code=404, detail="No active policy envelope")
    return envelope


@router.get("/policy-envelope/feedback/{config_id}", tags=["S&OP"])
def get_feed_back_signals(
    config_id: int,
    db: Session = Depends(get_sync_db),
):
    """Get feed-back signals for re-tuning S&OP parameters"""
    service = SOPService(db)
    signals = service.get_feed_back_signals(config_id)
    return {"signals": signals, "count": len(signals)}


# =============================================================================
# Supply Baseline Pack Endpoints
# =============================================================================

@router.post("/supply-baseline-pack", tags=["MRS"])
def create_supply_baseline_pack(
    request: SupplyBaselinePackCreate,
    db: Session = Depends(get_sync_db),
):
    """
    Create a Supply Baseline Pack.

    In FULL mode: Generate multiple candidates via MRS with different parameterizations.
    In INPUT mode: Accept customer's single MRP output.
    """
    from app.models.planning_cascade import PolicyEnvelope

    # Get policy envelope
    envelope = db.query(PolicyEnvelope).filter_by(id=request.policy_envelope_id).first()
    if not envelope:
        raise HTTPException(status_code=404, detail="Policy envelope not found")

    service = MRSService(db, mode=request.mode.upper())

    # For demo, use default inventory state
    # In production, this would come from actual inventory data
    inventory_state = [
        ProductInventoryState(
            sku=f"SKU-{i:03d}",
            category="default",
            on_hand=500,
            in_transit=100,
            committed=50,
            avg_daily_demand=30,
            demand_std=10,
            unit_cost=10.0,
            min_order_qty=50,
        )
        for i in range(1, 11)
    ]

    supplier_info = {
        p.sku: [SupplierInfo(
            supplier_id="SUPPLIER-001",
            lead_time_days=5,
            lead_time_variability=0.2,
            reliability=0.95,
            min_order_value=1000,
            unit_cost=10.0,
        )]
        for p in inventory_state
    }

    demand_forecast = {
        p.sku: [p.avg_daily_demand for _ in range(28)]
        for p in inventory_state
    }

    customer_plan = None
    if request.customer_plan:
        customer_plan = [
            {
                "sku": o.sku,
                "supplier_id": o.supplier_id,
                "destination_id": o.destination_id,
                "qty": o.qty,
                "order_date": o.order_date,
                "receipt_date": o.receipt_date,
            }
            for o in request.customer_plan
        ]

    try:
        supbp = service.generate_supply_baseline_pack(
            config_id=request.config_id,
            group_id=request.group_id,
            policy_envelope_id=request.policy_envelope_id,
            policy_envelope_hash=envelope.hash,
            inventory_state=inventory_state,
            supplier_info=supplier_info,
            demand_forecast=demand_forecast,
            customer_plan=customer_plan,
        )
        return supbp
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/supply-baseline-pack/{supbp_id}", tags=["MRS"])
def get_supply_baseline_pack(
    supbp_id: int,
    db: Session = Depends(get_sync_db),
):
    """Get a Supply Baseline Pack by ID"""
    from app.models.planning_cascade import SupplyBaselinePack

    supbp = db.query(SupplyBaselinePack).filter_by(id=supbp_id).first()
    if not supbp:
        raise HTTPException(status_code=404, detail="SupBP not found")

    return {
        "id": supbp.id,
        "hash": supbp.hash,
        "policy_envelope_hash": supbp.policy_envelope_hash,
        "candidates": supbp.candidates,
        "tradeoff_frontier": supbp.tradeoff_frontier,
        "generated_by": supbp.generated_by.value,
        "generated_at": supbp.generated_at.isoformat() if supbp.generated_at else None,
    }


# =============================================================================
# Supply Commit Endpoints
# =============================================================================

@router.post("/supply-commit/{supbp_id}", tags=["Supply Agent"])
def generate_supply_commit(
    supbp_id: int,
    mode: str = Query("copilot", description="copilot or autonomous"),
    db: Session = Depends(get_sync_db),
):
    """Generate a Supply Commit from SupBP"""
    from app.models.planning_cascade import SupplyBaselinePack, PolicyEnvelope

    supbp = db.query(SupplyBaselinePack).filter_by(id=supbp_id).first()
    if not supbp:
        raise HTTPException(status_code=404, detail="SupBP not found")

    envelope = db.query(PolicyEnvelope).filter_by(id=supbp.policy_envelope_id).first()
    if not envelope:
        raise HTTPException(status_code=404, detail="Policy envelope not found")

    agent = SupplyAgent(db)

    # Build policy envelope dict
    policy_envelope = {
        "safety_stock_targets": envelope.safety_stock_targets,
        "otif_floors": envelope.otif_floors,
        "allocation_reserves": envelope.allocation_reserves,
        "expedite_caps": envelope.expedite_caps,
        "dos_ceilings": envelope.dos_ceilings,
        "supplier_concentration_limits": envelope.supplier_concentration_limits,
    }

    # Dummy inventory state for demo
    inventory_state = {
        f"SKU-{i:03d}": {
            "inventory_position": 550,
            "avg_daily_demand": 30,
            "demand_std": 10,
            "unit_cost": 10.0,
            "min_order_qty": 50,
            "category": "default",
        }
        for i in range(1, 11)
    }

    try:
        commit = agent.generate_supply_commit(
            config_id=supbp.config_id,
            group_id=supbp.group_id,
            supply_baseline_pack_id=supbp.id,
            supply_baseline_pack_hash=supbp.hash,
            policy_envelope=policy_envelope,
            inventory_state=inventory_state,
            mode=mode,
        )
        return commit
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/supply-commit/{commit_id}", tags=["Supply Agent"])
def get_supply_commit(
    commit_id: int,
    db: Session = Depends(get_sync_db),
):
    """Get a Supply Commit by ID"""
    from app.models.planning_cascade import SupplyCommit

    commit = db.query(SupplyCommit).filter_by(id=commit_id).first()
    if not commit:
        raise HTTPException(status_code=404, detail="Supply Commit not found")

    agent = SupplyAgent(db)
    return agent._commit_to_dict(commit)


@router.post("/supply-commit/{commit_id}/review", tags=["Supply Agent"])
def review_supply_commit(
    commit_id: int,
    request: SupplyCommitReview,
    user_id: int = Query(..., description="Reviewing user ID"),
    db: Session = Depends(get_sync_db),
):
    """Review a Supply Commit (accept, override, or reject)"""
    agent = SupplyAgent(db)

    try:
        commit = agent.review_supply_commit(
            commit_id=commit_id,
            user_id=user_id,
            action=request.action,
            override_details=request.override_details,
        )
        return commit
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/supply-commit/{commit_id}/submit", tags=["Supply Agent"])
def submit_supply_commit(
    commit_id: int,
    user_id: Optional[int] = None,
    db: Session = Depends(get_sync_db),
):
    """Submit a Supply Commit for execution"""
    agent = SupplyAgent(db)

    try:
        commit = agent.submit_supply_commit(commit_id, user_id)
        return commit
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Allocation Commit Endpoints
# =============================================================================

@router.post("/allocation-commit/{supply_commit_id}", tags=["Allocation Agent"])
def generate_allocation_commit(
    supply_commit_id: int,
    mode: str = Query("copilot", description="copilot or autonomous"),
    db: Session = Depends(get_sync_db),
):
    """Generate an Allocation Commit from Supply Commit"""
    from app.models.planning_cascade import SupplyCommit, PolicyEnvelope

    supply_commit = db.query(SupplyCommit).filter_by(id=supply_commit_id).first()
    if not supply_commit:
        raise HTTPException(status_code=404, detail="Supply Commit not found")

    # Get policy envelope through SupBP chain
    from app.models.planning_cascade import SupplyBaselinePack
    supbp = db.query(SupplyBaselinePack).filter_by(id=supply_commit.supply_baseline_pack_id).first()
    envelope = db.query(PolicyEnvelope).filter_by(id=supbp.policy_envelope_id).first()

    agent = AllocationAgent(db)

    policy_envelope = {
        "otif_floors": envelope.otif_floors,
        "allocation_reserves": envelope.allocation_reserves,
    }

    # Dummy demand by segment
    demand_by_segment = {
        "strategic": {f"SKU-{i:03d}": 50 for i in range(1, 11)},
        "standard": {f"SKU-{i:03d}": 100 for i in range(1, 11)},
        "transactional": {f"SKU-{i:03d}": 30 for i in range(1, 11)},
    }

    try:
        commit = agent.generate_allocation_commit(
            config_id=supply_commit.config_id,
            group_id=supply_commit.group_id,
            supply_commit_id=supply_commit.id,
            supply_commit_hash=supply_commit.hash,
            policy_envelope=policy_envelope,
            demand_by_segment=demand_by_segment,
            mode=mode,
        )
        return commit
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/allocation-commit/{commit_id}", tags=["Allocation Agent"])
def get_allocation_commit(
    commit_id: int,
    db: Session = Depends(get_sync_db),
):
    """Get an Allocation Commit by ID"""
    from app.models.planning_cascade import AllocationCommit

    commit = db.query(AllocationCommit).filter_by(id=commit_id).first()
    if not commit:
        raise HTTPException(status_code=404, detail="Allocation Commit not found")

    agent = AllocationAgent(db)
    return agent._commit_to_dict(commit)


@router.post("/allocation-commit/{commit_id}/review", tags=["Allocation Agent"])
def review_allocation_commit(
    commit_id: int,
    request: AllocationCommitReview,
    user_id: int = Query(..., description="Reviewing user ID"),
    db: Session = Depends(get_sync_db),
):
    """Review an Allocation Commit"""
    agent = AllocationAgent(db)

    try:
        commit = agent.review_allocation_commit(
            commit_id=commit_id,
            user_id=user_id,
            action=request.action,
            override_details=request.override_details,
        )
        return commit
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/allocation-commit/{commit_id}/submit", tags=["Allocation Agent"])
def submit_allocation_commit(
    commit_id: int,
    user_id: Optional[int] = None,
    db: Session = Depends(get_sync_db),
):
    """Submit an Allocation Commit for execution"""
    agent = AllocationAgent(db)

    try:
        commit = agent.submit_allocation_commit(commit_id, user_id)
        return commit
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Cascade Orchestration Endpoints
# =============================================================================

@router.post("/cascade/run", tags=["Cascade"])
def run_cascade(
    request: CascadeRunRequest,
    user_id: Optional[int] = None,
    db: Session = Depends(get_sync_db),
):
    """
    Run the full planning cascade.

    In FULL mode: S&OP simulation + MRS candidates + Agents.
    In INPUT mode: Customer parameters + single plan + Agents.
    """
    mode = CascadeMode.FULL if request.mode.upper() == "FULL" else CascadeMode.INPUT

    orchestrator = CascadeOrchestrator(
        db=db,
        mode=mode,
        agent_mode=request.agent_mode,
    )

    try:
        if request.use_food_dist_defaults:
            result = orchestrator.run_cascade_for_food_dist(
                config_id=request.config_id,
                group_id=request.group_id,
                user_id=user_id,
            )
        else:
            result = orchestrator.run_cascade(
                config_id=request.config_id,
                group_id=request.group_id,
                user_id=user_id,
            )

        return {
            "policy_envelope_hash": result.policy_envelope["hash"],
            "supply_baseline_pack_hash": result.supply_baseline_pack["hash"],
            "supply_commit": result.supply_commit,
            "allocation_commit": result.allocation_commit,
            "summary": {
                "total_orders": result.total_orders,
                "total_allocations": result.total_allocations,
                "integrity_violations": result.integrity_violations,
                "risk_flags": result.risk_flags,
                "requires_review": result.requires_review,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cascade/status/{config_id}", tags=["Cascade"])
def get_cascade_status(
    config_id: int,
    db: Session = Depends(get_sync_db),
):
    """Get status of recent cascade runs"""
    orchestrator = CascadeOrchestrator(db)
    return orchestrator.get_cascade_status(config_id)


# =============================================================================
# Feed-Back Signal Endpoints
# =============================================================================

@router.post("/feedback-signal", tags=["Feed-Back"])
def create_feed_back_signal(
    request: FeedBackSignalCreate,
    db: Session = Depends(get_sync_db),
):
    """Record a feed-back signal from execution"""
    orchestrator = CascadeOrchestrator(db)

    try:
        signal = orchestrator.record_feed_back_signal(
            config_id=request.config_id,
            group_id=request.group_id,
            signal_type=request.signal_type,
            metric_name=request.metric_name,
            metric_value=request.metric_value,
            threshold=request.threshold,
            details=request.details,
            supply_commit_id=request.supply_commit_id,
            allocation_commit_id=request.allocation_commit_id,
        )
        return signal
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Worklist Endpoints
# =============================================================================

@router.get("/worklist/supply/{config_id}", tags=["Worklist"])
def get_supply_worklist(
    config_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_sync_db),
):
    """
    Get Supply Commit worklist.

    Returns commits requiring review, grouped by exception type.
    """
    from app.models.planning_cascade import SupplyCommit, CommitStatus

    query = db.query(SupplyCommit).filter(
        SupplyCommit.config_id == config_id,
        SupplyCommit.requires_review == True,
    )

    if status:
        query = query.filter(SupplyCommit.status == CommitStatus(status))

    commits = query.order_by(SupplyCommit.created_at.desc()).all()

    # Group by exception type
    by_violation_type = {}
    by_risk_type = {}

    for commit in commits:
        for v in (commit.integrity_violations or []):
            vtype = v.get("type", "unknown")
            if vtype not in by_violation_type:
                by_violation_type[vtype] = []
            by_violation_type[vtype].append({
                "commit_id": commit.id,
                "hash": commit.hash[:8],
                "detail": v.get("detail"),
            })

        for r in (commit.risk_flags or []):
            rtype = r.get("type", "unknown")
            if rtype not in by_risk_type:
                by_risk_type[rtype] = []
            by_risk_type[rtype].append({
                "commit_id": commit.id,
                "hash": commit.hash[:8],
                "detail": r.get("detail"),
            })

    return {
        "total_pending": len(commits),
        "integrity_violations": by_violation_type,
        "risk_flags": by_risk_type,
        "commits": [
            {
                "id": c.id,
                "hash": c.hash[:8],
                "status": c.status.value,
                "integrity_violations_count": len(c.integrity_violations or []),
                "risk_flags_count": len(c.risk_flags or []),
                "created_at": c.created_at.isoformat(),
            }
            for c in commits
        ],
    }


# =============================================================================
# Layer License Endpoints
# =============================================================================

class LayerLicenseUpdate(BaseModel):
    """Update layer license"""
    layer: str
    mode: str = Field(..., description="active, input, or disabled")
    package_tier: Optional[str] = None


@router.get("/layer-license/{group_id}", tags=["License"])
async def get_layer_licenses(
    group_id: int,
    db: Session = Depends(get_db),
):
    """Get all layer licenses for a group"""
    from app.models.planning_cascade import LayerLicense, LayerName, LayerMode

    result = await db.execute(select(LayerLicense).where(LayerLicense.group_id == group_id))
    licenses = result.scalars().all()

    # Build full map with defaults for missing layers
    layer_map = {}
    for layer in LayerName:
        layer_map[layer.value] = {
            "layer": layer.value,
            "mode": LayerMode.DISABLED.value if layer != LayerName.EXECUTION else LayerMode.ACTIVE.value,
            "package_tier": None,
            "activated_at": None,
            "expires_at": None,
        }

    for lic in licenses:
        layer_map[lic.layer.value] = {
            "layer": lic.layer.value,
            "mode": lic.mode.value,
            "package_tier": lic.package_tier,
            "activated_at": lic.activated_at.isoformat() if lic.activated_at else None,
            "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
        }

    return {"group_id": group_id, "layers": layer_map}


@router.put("/layer-license/{group_id}", tags=["License"])
def update_layer_license(
    group_id: int,
    request: LayerLicenseUpdate,
    user_id: Optional[int] = None,
    db: Session = Depends(get_sync_db),
):
    """Set layer mode for a group (admin only)"""
    from app.models.planning_cascade import LayerLicense, LayerName, LayerMode
    from datetime import datetime

    try:
        layer_name = LayerName(request.layer)
        layer_mode = LayerMode(request.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing = db.query(LayerLicense).filter_by(
        group_id=group_id, layer=layer_name
    ).first()

    if existing:
        existing.mode = layer_mode
        existing.package_tier = request.package_tier
        existing.updated_by = user_id
        if layer_mode == LayerMode.ACTIVE and not existing.activated_at:
            existing.activated_at = datetime.utcnow()
    else:
        new_license = LayerLicense(
            group_id=group_id,
            layer=layer_name,
            mode=layer_mode,
            package_tier=request.package_tier,
            activated_at=datetime.utcnow() if layer_mode == LayerMode.ACTIVE else None,
            updated_by=user_id,
        )
        db.add(new_license)

    db.commit()
    return {"status": "ok", "group_id": group_id, "layer": request.layer, "mode": request.mode}


@router.put("/layer-license/{group_id}/package/{tier}", tags=["License"])
def set_package_tier(
    group_id: int,
    tier: str,
    user_id: Optional[int] = None,
    db: Session = Depends(get_sync_db),
):
    """
    Set a package tier for a group, automatically configuring all layer modes.

    Tiers:
    - foundation: execution=active, all others=input
    - ai_execution: execution+supply_agent+allocation_agent=active, mrs+sop=input
    - planning: execution+supply_agent+allocation_agent+mrs=active, sop=input
    - enterprise: all layers=active
    """
    from app.models.planning_cascade import LayerLicense, LayerName, LayerMode
    from datetime import datetime

    tier_configs = {
        "foundation": {
            LayerName.EXECUTION: LayerMode.ACTIVE,
            LayerName.ALLOCATION_AGENT: LayerMode.INPUT,
            LayerName.SUPPLY_AGENT: LayerMode.INPUT,
            LayerName.MRS: LayerMode.INPUT,
            LayerName.SOP: LayerMode.INPUT,
        },
        "ai_execution": {
            LayerName.EXECUTION: LayerMode.ACTIVE,
            LayerName.ALLOCATION_AGENT: LayerMode.ACTIVE,
            LayerName.SUPPLY_AGENT: LayerMode.ACTIVE,
            LayerName.MRS: LayerMode.INPUT,
            LayerName.SOP: LayerMode.INPUT,
        },
        "planning": {
            LayerName.EXECUTION: LayerMode.ACTIVE,
            LayerName.ALLOCATION_AGENT: LayerMode.ACTIVE,
            LayerName.SUPPLY_AGENT: LayerMode.ACTIVE,
            LayerName.MRS: LayerMode.ACTIVE,
            LayerName.SOP: LayerMode.INPUT,
        },
        "enterprise": {
            LayerName.EXECUTION: LayerMode.ACTIVE,
            LayerName.ALLOCATION_AGENT: LayerMode.ACTIVE,
            LayerName.SUPPLY_AGENT: LayerMode.ACTIVE,
            LayerName.MRS: LayerMode.ACTIVE,
            LayerName.SOP: LayerMode.ACTIVE,
        },
    }

    if tier not in tier_configs:
        raise HTTPException(status_code=400, detail=f"Unknown tier: {tier}. Valid: {list(tier_configs.keys())}")

    config = tier_configs[tier]
    now = datetime.utcnow()

    for layer_name, mode in config.items():
        existing = db.query(LayerLicense).filter_by(
            group_id=group_id, layer=layer_name
        ).first()

        if existing:
            existing.mode = mode
            existing.package_tier = tier
            existing.updated_by = user_id
            if mode == LayerMode.ACTIVE and not existing.activated_at:
                existing.activated_at = now
        else:
            db.add(LayerLicense(
                group_id=group_id,
                layer=layer_name,
                mode=mode,
                package_tier=tier,
                activated_at=now if mode == LayerMode.ACTIVE else None,
                updated_by=user_id,
            ))

    db.commit()
    return {"status": "ok", "group_id": group_id, "tier": tier, "layers": {k.value: v.value for k, v in config.items()}}


# =============================================================================
# Ask Why Endpoints
# =============================================================================

@router.get("/supply-commit/{commit_id}/ask-why", tags=["Supply Agent"])
def ask_why_supply_commit(
    commit_id: int,
    db: Session = Depends(get_sync_db),
):
    """
    Get detailed agent reasoning for a Supply Commit.

    Returns the full decision trace: which SupBP candidate was selected,
    what policy parameters drove the decision, tradeoffs considered.
    """
    from app.models.planning_cascade import SupplyCommit, SupplyBaselinePack, PolicyEnvelope

    commit = db.query(SupplyCommit).filter_by(id=commit_id).first()
    if not commit:
        raise HTTPException(status_code=404, detail="Supply Commit not found")

    supbp = db.query(SupplyBaselinePack).filter_by(id=commit.supply_baseline_pack_id).first()
    envelope = db.query(PolicyEnvelope).filter_by(id=supbp.policy_envelope_id).first() if supbp else None

    return {
        "commit_id": commit_id,
        "agent_confidence": commit.agent_confidence,
        "agent_reasoning": commit.agent_reasoning,
        "selected_method": commit.selected_method,
        "policy_envelope": {
            "hash": envelope.hash[:12] if envelope else None,
            "safety_stock_targets": envelope.safety_stock_targets if envelope else None,
            "otif_floors": envelope.otif_floors if envelope else None,
            "source": envelope.generated_by.value if envelope else None,
        },
        "supply_baseline_pack": {
            "hash": supbp.hash[:12] if supbp else None,
            "candidates_count": len(supbp.candidates) if supbp and supbp.candidates else 0,
            "candidate_methods": [c.get("method") for c in (supbp.candidates or [])] if supbp else [],
            "tradeoff_frontier": supbp.tradeoff_frontier if supbp else None,
        },
        "integrity_violations": commit.integrity_violations,
        "risk_flags": commit.risk_flags,
        "projected_outcomes": {
            "otif": commit.projected_otif,
            "inventory_cost": commit.projected_inventory_cost,
            "dos": commit.projected_dos,
        },
        "supply_pegging": commit.supply_pegging,
    }


@router.get("/allocation-commit/{commit_id}/ask-why", tags=["Allocation Agent"])
def ask_why_allocation_commit(
    commit_id: int,
    db: Session = Depends(get_sync_db),
):
    """Get detailed agent reasoning for an Allocation Commit"""
    from app.models.planning_cascade import (
        AllocationCommit, SolverBaselinePack, SupplyCommit,
        SupplyBaselinePack, PolicyEnvelope
    )

    commit = db.query(AllocationCommit).filter_by(id=commit_id).first()
    if not commit:
        raise HTTPException(status_code=404, detail="Allocation Commit not found")

    sbp = db.query(SolverBaselinePack).filter_by(id=commit.solver_baseline_pack_id).first()
    sc = db.query(SupplyCommit).filter_by(id=commit.supply_commit_id).first()

    return {
        "commit_id": commit_id,
        "agent_confidence": commit.agent_confidence,
        "agent_reasoning": commit.agent_reasoning,
        "selected_method": commit.selected_method,
        "solver_baseline_pack": {
            "hash": sbp.hash[:12] if sbp else None,
            "candidates_count": len(sbp.candidates) if sbp and sbp.candidates else 0,
            "candidate_methods": [c.get("method") for c in (sbp.candidates or [])] if sbp else [],
            "binding_constraints": sbp.binding_constraints if sbp else None,
            "marginal_values": sbp.marginal_values if sbp else None,
        },
        "supply_commit": {
            "hash": sc.hash[:12] if sc else None,
            "status": sc.status.value if sc else None,
            "recommendations_count": len(sc.recommendations) if sc and sc.recommendations else 0,
        },
        "integrity_violations": commit.integrity_violations,
        "risk_flags": commit.risk_flags,
        "unallocated": commit.unallocated,
        "pegging_summary": commit.pegging_summary,
    }


# =============================================================================
# Lineage Endpoint
# =============================================================================

@router.get("/lineage/{artifact_type}/{artifact_id}", tags=["Lineage"])
def get_artifact_lineage(
    artifact_type: str,
    artifact_id: int,
    db: Session = Depends(get_sync_db),
):
    """
    Get full hash-chain lineage for any cascade artifact.

    Traces upstream (where did this come from?) and downstream (what depends on this?).
    """
    from app.models.planning_cascade import (
        PolicyEnvelope, SupplyBaselinePack, SupplyCommit,
        SolverBaselinePack, AllocationCommit
    )

    lineage = {"upstream": [], "artifact": None, "downstream": []}

    if artifact_type == "policy_envelope":
        pe = db.query(PolicyEnvelope).filter_by(id=artifact_id).first()
        if not pe:
            raise HTTPException(status_code=404, detail="Policy Envelope not found")
        lineage["artifact"] = {"type": "policy_envelope", "id": pe.id, "hash": pe.hash[:12], "source": pe.generated_by.value}
        supbps = db.query(SupplyBaselinePack).filter_by(policy_envelope_id=pe.id).all()
        for s in supbps:
            lineage["downstream"].append({"type": "supply_baseline_pack", "id": s.id, "hash": s.hash[:12]})

    elif artifact_type == "supply_baseline_pack":
        supbp = db.query(SupplyBaselinePack).filter_by(id=artifact_id).first()
        if not supbp:
            raise HTTPException(status_code=404, detail="SupBP not found")
        pe = db.query(PolicyEnvelope).filter_by(id=supbp.policy_envelope_id).first()
        lineage["upstream"].append({"type": "policy_envelope", "id": pe.id, "hash": pe.hash[:12]})
        lineage["artifact"] = {"type": "supply_baseline_pack", "id": supbp.id, "hash": supbp.hash[:12]}
        scs = db.query(SupplyCommit).filter_by(supply_baseline_pack_id=supbp.id).all()
        for sc in scs:
            lineage["downstream"].append({"type": "supply_commit", "id": sc.id, "hash": sc.hash[:12], "status": sc.status.value})

    elif artifact_type == "supply_commit":
        sc = db.query(SupplyCommit).filter_by(id=artifact_id).first()
        if not sc:
            raise HTTPException(status_code=404, detail="Supply Commit not found")
        supbp = db.query(SupplyBaselinePack).filter_by(id=sc.supply_baseline_pack_id).first()
        pe = db.query(PolicyEnvelope).filter_by(id=supbp.policy_envelope_id).first() if supbp else None
        if pe:
            lineage["upstream"].append({"type": "policy_envelope", "id": pe.id, "hash": pe.hash[:12]})
        if supbp:
            lineage["upstream"].append({"type": "supply_baseline_pack", "id": supbp.id, "hash": supbp.hash[:12]})
        lineage["artifact"] = {"type": "supply_commit", "id": sc.id, "hash": sc.hash[:12], "status": sc.status.value}
        acs = db.query(AllocationCommit).filter_by(supply_commit_id=sc.id).all()
        for ac in acs:
            lineage["downstream"].append({"type": "allocation_commit", "id": ac.id, "hash": ac.hash[:12], "status": ac.status.value})

    elif artifact_type == "allocation_commit":
        ac = db.query(AllocationCommit).filter_by(id=artifact_id).first()
        if not ac:
            raise HTTPException(status_code=404, detail="Allocation Commit not found")
        sc = db.query(SupplyCommit).filter_by(id=ac.supply_commit_id).first()
        sbp = db.query(SolverBaselinePack).filter_by(id=ac.solver_baseline_pack_id).first()
        supbp = db.query(SupplyBaselinePack).filter_by(id=sc.supply_baseline_pack_id).first() if sc else None
        pe = db.query(PolicyEnvelope).filter_by(id=supbp.policy_envelope_id).first() if supbp else None
        if pe:
            lineage["upstream"].append({"type": "policy_envelope", "id": pe.id, "hash": pe.hash[:12]})
        if supbp:
            lineage["upstream"].append({"type": "supply_baseline_pack", "id": supbp.id, "hash": supbp.hash[:12]})
        if sc:
            lineage["upstream"].append({"type": "supply_commit", "id": sc.id, "hash": sc.hash[:12], "status": sc.status.value})
        if sbp:
            lineage["upstream"].append({"type": "solver_baseline_pack", "id": sbp.id, "hash": sbp.hash[:12]})
        lineage["artifact"] = {"type": "allocation_commit", "id": ac.id, "hash": ac.hash[:12], "status": ac.status.value}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown artifact type: {artifact_type}")

    return lineage


# =============================================================================
# Metrics Endpoint
# =============================================================================

@router.get("/metrics/{config_id}/{agent_type}", tags=["Metrics"])
def get_agent_metrics(
    config_id: int,
    agent_type: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_sync_db),
):
    """Get AgentDecisionMetrics for dashboards (performance scores, touchless rate, override rate)"""
    from app.models.planning_cascade import AgentDecisionMetrics

    metrics = db.query(AgentDecisionMetrics).filter(
        AgentDecisionMetrics.config_id == config_id,
        AgentDecisionMetrics.agent_type == agent_type,
    ).order_by(AgentDecisionMetrics.period_start.desc()).limit(limit).all()

    return {
        "config_id": config_id,
        "agent_type": agent_type,
        "metrics": [
            {
                "period_start": m.period_start.isoformat() if m.period_start else None,
                "period_end": m.period_end.isoformat() if m.period_end else None,
                "touchless_rate": m.touchless_rate,
                "agent_score": m.agent_score,
                "user_score": m.user_score,
                "human_override_rate": m.human_override_rate,
                "override_dependency_ratio": m.override_dependency_ratio,
                "downstream_coherence": m.downstream_coherence,
                "total_decisions": m.total_decisions,
                "auto_submitted": m.auto_submitted,
                "reviewed": m.reviewed,
                "overridden": m.overridden,
                "rejected": m.rejected,
                "integrity_violations_count": m.integrity_violations_count,
                "risk_flags_count": m.risk_flags_count,
            }
            for m in metrics
        ],
    }


# =============================================================================
# Feed-back Signal Endpoints (extended)
# =============================================================================

@router.get("/feedback-signals/{config_id}", tags=["Feed-Back"])
def get_feedback_signals(
    config_id: int,
    fed_back_to: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_sync_db),
):
    """Get feed-back signals with filtering"""
    from app.models.planning_cascade import FeedBackSignal

    query = db.query(FeedBackSignal).filter(FeedBackSignal.config_id == config_id)

    if fed_back_to:
        query = query.filter(FeedBackSignal.fed_back_to == fed_back_to)
    if acknowledged is not None:
        query = query.filter(FeedBackSignal.acknowledged == acknowledged)

    signals = query.order_by(FeedBackSignal.measured_at.desc()).limit(limit).all()

    return {
        "config_id": config_id,
        "count": len(signals),
        "signals": [
            {
                "id": s.id,
                "signal_type": s.signal_type,
                "measured_at_layer": s.measured_at_layer,
                "fed_back_to": s.fed_back_to,
                "metric_name": s.metric_name,
                "metric_value": s.metric_value,
                "threshold": s.threshold,
                "deviation": s.deviation,
                "details": s.details,
                "suggested_retune": s.suggested_retune,
                "acknowledged": s.acknowledged,
                "actioned": s.actioned,
                "measured_at": s.measured_at.isoformat() if s.measured_at else None,
            }
            for s in signals
        ],
    }


@router.post("/feedback-signals/{signal_id}/apply", tags=["Feed-Back"])
def apply_feedback_signal(
    signal_id: int,
    user_id: Optional[int] = None,
    db: Session = Depends(get_sync_db),
):
    """
    Apply a suggested re-tune from a feed-back signal to the upstream layer.

    Marks the signal as actioned and returns the suggested parameter change.
    """
    from app.models.planning_cascade import FeedBackSignal
    from datetime import datetime

    signal = db.query(FeedBackSignal).filter_by(id=signal_id).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Feed-back signal not found")

    if not signal.suggested_retune:
        raise HTTPException(status_code=400, detail="Signal has no suggested re-tune")

    signal.acknowledged = True
    signal.actioned = True
    signal.actioned_at = datetime.utcnow()
    signal.actioned_by = user_id
    db.commit()

    return {
        "status": "applied",
        "signal_id": signal_id,
        "fed_back_to": signal.fed_back_to,
        "suggested_retune": signal.suggested_retune,
    }


# =============================================================================
# Worklist Endpoints (existing, unchanged below)
# =============================================================================

# =============================================================================
# TRM Decision Override Endpoints
# =============================================================================

class TRMDecisionAction(BaseModel):
    """Action on a TRM decision"""
    action: str = Field(..., description="accept, override, or reject")
    reason_code: Optional[str] = Field(None, description="Reason code for override/reject")
    reason_text: Optional[str] = Field(None, description="Free-text reason")
    override_values: Optional[Dict[str, Any]] = Field(None, description="TRM-specific override values")


@router.get("/trm-decisions/{config_id}/{trm_type}", tags=["TRM Worklist"])
async def get_trm_decisions(
    config_id: int,
    trm_type: str,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Get TRM decisions for a specific agent type.

    trm_type: atp, rebalancing, po_creation, order_tracking
    Maps to AgentDecision.decision_type:
      atp → atp_allocation
      rebalancing → inventory_rebalance
      po_creation → purchase_order
      order_tracking → exception_resolution
    """
    from app.models.decision_tracking import AgentDecision, DecisionType, DecisionStatus as DTStatus

    trm_to_decision_type = {
        "atp": DecisionType.ATP_ALLOCATION,
        "rebalancing": DecisionType.INVENTORY_REBALANCE,
        "po_creation": DecisionType.PURCHASE_ORDER,
        "order_tracking": DecisionType.EXCEPTION_RESOLUTION,
    }

    if trm_type not in trm_to_decision_type:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trm_type. Valid: {list(trm_to_decision_type.keys())}"
        )

    decision_type = trm_to_decision_type[trm_type]

    stmt = select(AgentDecision).where(
        AgentDecision.group_id == config_id,  # config_id used as group context
        AgentDecision.decision_type == decision_type,
    )

    # Map frontend status names to model statuses
    if status:
        status_map = {
            "PROPOSED": DTStatus.PENDING,
            "PENDING": DTStatus.PENDING,
            "ACCEPTED": DTStatus.ACCEPTED,
            "OVERRIDDEN": DTStatus.REJECTED,  # "rejected" in model = overridden by user
            "REJECTED": DTStatus.REJECTED,
            "EXECUTED": DTStatus.AUTO_EXECUTED,
        }
        mapped = status_map.get(status.upper())
        if mapped:
            stmt = stmt.where(AgentDecision.status == mapped)

    stmt = stmt.order_by(AgentDecision.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    decisions = result.scalars().all()

    return {
        "config_id": config_id,
        "trm_type": trm_type,
        "count": len(decisions),
        "decisions": [
            {
                "id": d.id,
                "agent_type": d.agent_type,
                "decision_type": d.decision_type.value,
                "status": _map_status_to_frontend(d.status, d.user_action),
                "confidence": d.agent_confidence,
                "context": d.context_data,
                "recommendation": d.agent_recommendation,
                "agent_reasoning": d.agent_reasoning,
                "override_values": {"value": d.user_value} if d.user_value is not None else None,
                "reason_code": None,
                "reason_text": d.override_reason,
                "outcome": {"value": d.outcome_value, "quality_score": d.outcome_quality_score} if d.outcome_measured else None,
                "item_code": d.item_code,
                "item_name": d.item_name,
                "category": d.category,
                "recommended_value": d.recommended_value,
                "previous_value": d.previous_value,
                "reviewed_by": d.user_id,
                "reviewed_at": d.action_timestamp.isoformat() if d.action_timestamp else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in decisions
        ],
    }


@router.post("/trm-decisions/{decision_id}/action", tags=["TRM Worklist"])
async def submit_trm_decision_action(
    decision_id: int,
    request: TRMDecisionAction,
    user_id: int = Query(..., description="Reviewing user ID"),
    db: Session = Depends(get_db),
):
    """
    Submit an action on a TRM decision (accept, override, or reject).

    Override values + reason are stored for RL training feedback:
    - Stored in agent_decisions table (status, user_value, override_reason)
    - Written to trm_replay_buffer with is_expert=True for RL fine-tuning
    """
    from app.models.decision_tracking import AgentDecision, DecisionStatus as DTStatus
    from datetime import datetime

    result = await db.execute(select(AgentDecision).where(AgentDecision.id == decision_id))
    decision = result.scalars().first()
    if not decision:
        raise HTTPException(status_code=404, detail="TRM decision not found")

    valid_actions = {"accept", "override", "reject"}
    action = request.action.lower()
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Valid: {valid_actions}")

    if action == "override" and not request.override_values:
        raise HTTPException(status_code=400, detail="Override values required for override action")

    if action in ("override", "reject") and not request.reason_code:
        raise HTTPException(status_code=400, detail="Reason code required for override/reject")

    # Update decision record
    now = datetime.utcnow()
    if action == "accept":
        decision.status = DTStatus.ACCEPTED
        decision.user_action = "accept"
    elif action == "override":
        decision.status = DTStatus.REJECTED  # model uses REJECTED for human overrides
        decision.user_action = "override"
    elif action == "reject":
        decision.status = DTStatus.REJECTED
        decision.user_action = "reject"

    decision.user_id = user_id
    decision.action_timestamp = now

    # Build override reason from code + text
    reason_parts = []
    if request.reason_code:
        reason_parts.append(f"[{request.reason_code}]")
    if request.reason_text:
        reason_parts.append(request.reason_text)
    if reason_parts:
        decision.override_reason = " ".join(reason_parts)

    # Store override value if provided
    if request.override_values:
        # Extract numeric value if present for user_value field
        override_val = request.override_values.get("value") or request.override_values.get("qty")
        if override_val is not None:
            try:
                decision.user_value = float(override_val)
            except (ValueError, TypeError):
                pass
        # Store full override context in context_data
        existing_context = decision.context_data or {}
        existing_context["override_values"] = request.override_values
        existing_context["reason_code"] = request.reason_code
        decision.context_data = existing_context

    await db.flush()

    # Write to TRM replay buffer for RL training (is_expert=True)
    try:
        await _write_to_replay_buffer(
            db=db,
            decision=decision,
            action=action,
            user_id=user_id,
            override_values=request.override_values,
        )
    except Exception:
        # Non-critical: log but don't fail the override
        pass

    await db.commit()

    return {
        "id": decision.id,
        "status": _map_status_to_frontend(decision.status, decision.user_action),
        "action": action,
        "reviewed_by": user_id,
        "reviewed_at": now.isoformat(),
        "override_values": request.override_values,
        "reason_code": request.reason_code,
    }


@router.get("/trm-decisions/{decision_id}/detail", tags=["TRM Worklist"])
async def get_trm_decision_detail(
    decision_id: int,
    db: Session = Depends(get_db),
):
    """
    Get full detail for a single TRM decision including context and reasoning.
    """
    from app.models.decision_tracking import AgentDecision

    result = await db.execute(select(AgentDecision).where(AgentDecision.id == decision_id))
    decision = result.scalars().first()
    if not decision:
        raise HTTPException(status_code=404, detail="TRM decision not found")

    return {
        "id": decision.id,
        "agent_type": decision.agent_type,
        "decision_type": decision.decision_type.value,
        "status": _map_status_to_frontend(decision.status, decision.user_action),
        "confidence": decision.agent_confidence,
        "context": decision.context_data,
        "recommendation": decision.agent_recommendation,
        "agent_reasoning": decision.agent_reasoning,
        "issue_summary": decision.issue_summary,
        "impact_value": decision.impact_value,
        "impact_description": decision.impact_description,
        "item_code": decision.item_code,
        "item_name": decision.item_name,
        "category": decision.category,
        "recommended_value": decision.recommended_value,
        "previous_value": decision.previous_value,
        "override_values": (decision.context_data or {}).get("override_values"),
        "reason_code": (decision.context_data or {}).get("reason_code"),
        "reason_text": decision.override_reason,
        "outcome": {"value": decision.outcome_value, "quality_score": decision.outcome_quality_score} if decision.outcome_measured else None,
        "reviewed_by": decision.user_id,
        "reviewed_at": decision.action_timestamp.isoformat() if decision.action_timestamp else None,
        "created_at": decision.created_at.isoformat() if decision.created_at else None,
        "group_id": decision.group_id,
    }


@router.get("/trm-summary/{config_id}/{trm_type}", tags=["TRM Worklist"])
async def get_trm_summary(
    config_id: int,
    trm_type: str,
    db: Session = Depends(get_db),
):
    """
    Get summary statistics for a TRM type (for dashboard cards).

    Returns counts by status, avg confidence, override rate, etc.
    """
    from app.models.decision_tracking import AgentDecision, DecisionType, DecisionStatus as DTStatus

    trm_to_decision_type = {
        "atp": DecisionType.ATP_ALLOCATION,
        "rebalancing": DecisionType.INVENTORY_REBALANCE,
        "po_creation": DecisionType.PURCHASE_ORDER,
        "order_tracking": DecisionType.EXCEPTION_RESOLUTION,
    }

    if trm_type not in trm_to_decision_type:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trm_type. Valid: {list(trm_to_decision_type.keys())}"
        )

    decision_type = trm_to_decision_type[trm_type]

    base_filters = [
        AgentDecision.group_id == config_id,
        AgentDecision.decision_type == decision_type,
    ]

    total_result = await db.execute(select(func.count(AgentDecision.id)).where(*base_filters))
    total = total_result.scalar() or 0

    proposed_result = await db.execute(select(func.count(AgentDecision.id)).where(
        *base_filters, AgentDecision.status == DTStatus.PENDING
    ))
    proposed = proposed_result.scalar() or 0

    accepted_result = await db.execute(select(func.count(AgentDecision.id)).where(
        *base_filters, AgentDecision.status == DTStatus.ACCEPTED
    ))
    accepted = accepted_result.scalar() or 0

    overridden_result = await db.execute(select(func.count(AgentDecision.id)).where(
        *base_filters, AgentDecision.status == DTStatus.REJECTED, AgentDecision.user_action == "override"
    ))
    overridden = overridden_result.scalar() or 0

    rejected_result = await db.execute(select(func.count(AgentDecision.id)).where(
        *base_filters, AgentDecision.status == DTStatus.REJECTED, AgentDecision.user_action == "reject"
    ))
    rejected = rejected_result.scalar() or 0

    executed_result = await db.execute(select(func.count(AgentDecision.id)).where(
        *base_filters, AgentDecision.status == DTStatus.AUTO_EXECUTED
    ))
    executed = executed_result.scalar() or 0

    avg_conf_result = await db.execute(select(func.avg(AgentDecision.agent_confidence)).where(*base_filters))
    avg_confidence = avg_conf_result.scalar() or 0.0

    reviewed = accepted + overridden + rejected
    override_rate = (overridden / reviewed * 100) if reviewed > 0 else 0.0
    touchless_rate = (executed / total * 100) if total > 0 else 0.0

    return {
        "config_id": config_id,
        "trm_type": trm_type,
        "total": total,
        "by_status": {
            "proposed": proposed,
            "accepted": accepted,
            "overridden": overridden,
            "rejected": rejected,
            "executed": executed,
        },
        "avg_confidence": round(avg_confidence, 3),
        "override_rate": round(override_rate, 1),
        "touchless_rate": round(touchless_rate, 1),
    }


def _map_status_to_frontend(status, user_action: Optional[str] = None) -> str:
    """Map AgentDecision status + user_action to frontend-friendly status string."""
    from app.models.decision_tracking import DecisionStatus as DTStatus

    if status == DTStatus.PENDING:
        return "PROPOSED"
    elif status == DTStatus.ACCEPTED:
        return "ACCEPTED"
    elif status == DTStatus.REJECTED:
        if user_action == "override":
            return "OVERRIDDEN"
        return "REJECTED"
    elif status == DTStatus.AUTO_EXECUTED:
        return "EXECUTED"
    elif status == DTStatus.EXPIRED:
        return "EXPIRED"
    return str(status.value).upper() if hasattr(status, 'value') else str(status).upper()


def _trm_type_from_decision_type(decision_type) -> str:
    """Map DecisionType enum to TRM type string."""
    from app.models.decision_tracking import DecisionType
    mapping = {
        DecisionType.ATP_ALLOCATION: "atp",
        DecisionType.INVENTORY_REBALANCE: "rebalancing",
        DecisionType.PURCHASE_ORDER: "po_creation",
        DecisionType.EXCEPTION_RESOLUTION: "order_tracking",
    }
    return mapping.get(decision_type, "unknown")


async def _write_to_replay_buffer(
    db: Session,
    decision,
    action: str,
    user_id: int,
    override_values: Optional[Dict[str, Any]] = None,
):
    """
    Write human override to TRM replay buffer for RL training.

    Expert overrides (is_expert=True) are used to fine-tune the TRM agent
    via behavioral cloning or reward shaping in the RL training loop.
    """
    from app.models.trm_training_data import TRMReplayBuffer
    from datetime import datetime, date as date_type

    # Build a simple state vector from decision context
    # Real implementation would vectorize properly; here we store a placeholder
    context = decision.context_data or {}
    state_vector = [
        float(decision.recommended_value or 0),
        float(decision.previous_value or 0),
        float(decision.agent_confidence or 0),
    ]

    # The action: 0=accept, 1=override, 2=reject
    action_map = {"accept": 0, "override": 1, "reject": 2}
    action_discrete = action_map.get(action, 0)

    # Reward signal: accepted = agent was right, overridden/rejected = agent was wrong
    reward = 1.0 if action == "accept" else -0.5

    entry = TRMReplayBuffer(
        group_id=decision.group_id,
        config_id=decision.group_id,  # Use group_id as config context
        trm_type=_trm_type_from_decision_type(decision.decision_type),
        decision_log_id=decision.id,
        decision_log_table="agent_decisions",
        state_vector=state_vector,
        state_dim=len(state_vector),
        action_discrete=action_discrete,
        action_dim=1,
        reward=reward,
        reward_components={"expert_signal": reward, "reason_code": (override_values or {}).get("reason_code")},
        is_expert=True,
        priority=2.0,  # Expert samples get higher priority
        transition_date=date_type.today(),
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()


@router.get("/worklist/allocation/{config_id}", tags=["Worklist"])
async def get_allocation_worklist(
    config_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get Allocation Commit worklist"""
    from app.models.planning_cascade import AllocationCommit, CommitStatus

    filters = [AllocationCommit.config_id == config_id]

    if status:
        filters.append(AllocationCommit.status == CommitStatus(status))

    stmt = select(AllocationCommit).where(*filters)

    stmt = stmt.order_by(AllocationCommit.created_at.desc())
    result = await db.execute(stmt)
    commits = result.scalars().all()

    commit_list = [
        {
            "id": c.id,
            "hash": c.hash[:8],
            "status": c.status.value,
            "agent_confidence": c.agent_confidence,
            "agent_reasoning": c.agent_reasoning,
            "integrity_violations": c.integrity_violations or [],
            "risk_flags": c.risk_flags or [],
            "integrity_violations_count": len(c.integrity_violations or []),
            "risk_flags_count": len(c.risk_flags or []),
            "created_at": c.created_at.isoformat(),
            "reviewed_by": c.reviewed_by,
            "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
        }
        for c in commits
    ]

    return {
        "total_pending": len(commits),
        "items": commit_list,
        "commits": commit_list,
    }
