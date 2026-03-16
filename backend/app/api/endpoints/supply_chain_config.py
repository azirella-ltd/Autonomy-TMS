import hashlib
import json
import subprocess
import sys
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status, Body, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app import crud, models, schemas
from app.api import deps
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.supply_chain_config_service import (
    SupplyChainConfigService,
    _normalize_site_type_definitions,
)
from app.models.supply_chain_config import (
    ConfigLineage,
    Lane,
    Market,
    MarketDemand,
    Site as Node,
    NodeType,
    SupplyChainConfig,
    SupplyChainTrainingArtifact,
)
from app.models.user import UserTypeEnum
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat
from app.schemas.scenario import ScenarioCreate
from app.rl.data_generator import load_sequences_from_db, DbLookupConfig
from app.rl.config import SimulationParams
from app.services.mixed_scenario_service import MixedScenarioService

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# RAG Indexing Hook — auto-indexes SC config docs into tenant knowledge base
# ---------------------------------------------------------------------------

def _enqueue_rag_indexing(
    background_tasks: Optional[BackgroundTasks],
    config_id: int,
    tenant_id: int,
) -> None:
    """Schedule background RAG indexing of a supply chain config."""
    if background_tasks is None:
        return
    background_tasks.add_task(_index_config_to_rag, config_id, tenant_id)


def _enqueue_rag_deletion(
    background_tasks: Optional[BackgroundTasks],
    config_id: int,
    tenant_id: int,
) -> None:
    """Schedule background deletion of RAG docs for a config."""
    if background_tasks is None:
        return
    background_tasks.add_task(_delete_config_from_rag, config_id, tenant_id)


async def _index_config_to_rag(config_id: int, tenant_id: int) -> None:
    """Background task: index SC config into tenant's knowledge base."""
    try:
        from app.db.kb_session import get_kb_session
        from app.services.sc_config_indexer import ScConfigIndexer

        async with get_kb_session() as kb_db:
            indexer = ScConfigIndexer(kb_db=kb_db, tenant_id=tenant_id)
            result = await indexer.index_config(config_id)
            logger.info(f"RAG indexed config {config_id}: {result.get('status', 'ok')}")
    except Exception as e:
        logger.warning(f"RAG indexing failed for config {config_id}: {e}")


async def _delete_config_from_rag(config_id: int, tenant_id: int) -> None:
    """Background task: delete KB docs for a deleted config."""
    try:
        from app.db.kb_session import get_kb_session
        from app.services.sc_config_indexer import ScConfigIndexer

        async with get_kb_session() as kb_db:
            indexer = ScConfigIndexer(kb_db=kb_db, tenant_id=tenant_id)
            deleted = await indexer.delete_config_docs(config_id)
            logger.info(f"RAG deleted {deleted} doc(s) for config {config_id}")
    except Exception as e:
        logger.warning(f"RAG deletion failed for config {config_id}: {e}")

BACKEND_ROOT = Path(__file__).resolve().parents[3]
TRAINING_ROOT = BACKEND_ROOT / "training_jobs"
MODEL_ROOT = BACKEND_ROOT / "checkpoints" / "supply_chain_configs"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "-", value.strip().lower()).strip("-")
    return slug or "config"


class ConfigTrainingRequest(BaseModel):
    num_runs: int = Field(128, ge=4, le=512, description="Number of simulation runs to generate")
    T: int = Field(64, ge=16, le=512, description="Number of periods in each simulation run")
    window: int = Field(52, ge=1, le=128, description="Input window length for training samples")
    horizon: int = Field(1, ge=1, le=8, description="Forecast horizon for the temporal model")
    epochs: int = Field(5, ge=1, le=500, description="Training epochs for the temporal GNN")
    device: Optional[str] = Field(None, description="Optional device hint passed to the trainer (e.g. 'cpu', 'cuda')")
    use_simpy: Optional[bool] = Field(None, description="Override simulator backend; defaults to environment setting")
    sim_alpha: Optional[float] = Field(0.3, ge=0.0, le=1.0, description="Smoothing factor for SimPy simulator")
    sim_wip_k: Optional[float] = Field(1.0, ge=0.0, le=10.0, description="WIP gain parameter for SimPy simulator")


class ConfigTrainingResponse(BaseModel):
    status: str
    message: str
    dataset_path: str
    model_path: str
    trained_at: Optional[datetime]
    log: str

# --- Helper functions ---

def get_config_or_404(db: Session, config_id: int):
    config = (
        db.query(SupplyChainConfig)
        .options(
            # Note: items and item_configs migrated to Product/ProductBom (SC compliant)
            # joinedload(SupplyChainConfig.items),  # DEPRECATED - use Product table
            # joinedload(SupplyChainConfig.nodes).joinedload(Node.item_configs),  # DEPRECATED - use InvPolicy
            joinedload(SupplyChainConfig.sites).joinedload(Node.upstream_lanes),
            joinedload(SupplyChainConfig.sites).joinedload(Node.downstream_lanes),
            joinedload(SupplyChainConfig.transportation_lanes).joinedload(Lane.upstream_site),
            joinedload(SupplyChainConfig.transportation_lanes).joinedload(Lane.downstream_site),
            joinedload(SupplyChainConfig.markets),
            joinedload(SupplyChainConfig.market_demands).joinedload(MarketDemand.market),
            # joinedload(SupplyChainConfig.market_demands).joinedload(MarketDemand.item),  # DEPRECATED - use .product
        )
        .filter(SupplyChainConfig.id == config_id)
        .first()
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found"
        )
    return config

def get_product_or_404(db: Session, product_id: str, config_id: int):
    """Get product by ID or raise 404. AWS SC DM compliant."""
    product = crud.product.get(db, id=product_id)
    if not product or product.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found in this configuration"
        )
    return product


def get_site_or_404(db: Session, site_id: int, config_id: int):
    """Get site by ID or raise 404. AWS SC DM: site = node in DB."""
    site = crud.site.get(db, id=site_id)
    if not site or site.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found in this configuration"
        )
    return site


def get_transportation_lane_or_404(db: Session, lane_id: int, config_id: int):
    """Get transportation lane by ID or raise 404 (AWS SC DM standard)."""
    lane = crud.transportation_lane.get(db, id=lane_id)
    if not lane or lane.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transportation lane not found in this configuration",
        )
    return lane


# DEPRECATED: Use get_transportation_lane_or_404
get_lane_or_404 = get_transportation_lane_or_404


def _master_type_to_node_type(master_type: str) -> models.NodeType:
    canonical = str(master_type or "").strip().lower()
    mapping: Dict[str, models.NodeType] = {
        # Current names
        "vendor": models.NodeType.VENDOR,
        "customer": models.NodeType.CUSTOMER,
        "manufacturer": models.NodeType.MANUFACTURER,
        "inventory": models.NodeType.INVENTORY,
        # Legacy names (backward compatibility)
        "market_supply": models.NodeType.VENDOR,
        "market_demand": models.NodeType.CUSTOMER,
    }
    return mapping.get(canonical, models.NodeType.MANUFACTURER)


def _build_site_type_map(config: SupplyChainConfig) -> Dict[str, Dict[str, Any]]:
    definitions, _ = _normalize_site_type_definitions(
        getattr(config, "site_type_definitions", None)
    )
    result: Dict[str, Dict[str, Any]] = {}
    for entry in definitions:
        node_type_value = entry.get("type")
        if not node_type_value:
            continue
        token = MixedScenarioService._canonical_role(node_type_value)
        if not token:
            continue
        master = entry.get("master_type") or ""
        result[token] = {
            "dag_type": token,
            "master_type": MixedScenarioService._canonical_role(master) or "manufacturer",
        }
    return result


def _get_site_type_entry(value: Any, config: SupplyChainConfig) -> Dict[str, Any]:
    token = MixedScenarioService._canonical_role(value)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid site type '{value}'",
        )
    type_map = _build_site_type_map(config)
    entry = type_map.get(token)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid site type '{value}'",
        )
    return entry


def get_product_site_config_or_404(db: Session, config_id: int, config_entry_id: int):
    entry = crud.product_site_config.get(db, id=config_entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item-node configuration not found",
        )

    site = crud.site.get(db, id=entry.site_id)
    product = crud.product.get(db, id=entry.product_id)
    if not site or site.config_id != config_id or not product or product.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product-site configuration not found in this configuration",
        )
    return entry


def get_market_demand_or_404(db: Session, config_id: int, demand_id: int):
    demand = crud.market_demand.get(db, id=demand_id)
    if not demand or demand.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market demand entry not found in this configuration",
        )
    return demand


def _transportation_lane_to_payload(lane: models.TransportationLane) -> Dict[str, Any]:
    """Convert TransportationLane model to API response payload (AWS SC DM standard)."""
    lead_time_days = lane.lead_time_days or {}
    min_lead = lead_time_days.get("min")
    max_lead = lead_time_days.get("max")

    if min_lead is not None and max_lead is not None and min_lead == max_lead:
        lead_time = min_lead
    elif min_lead is not None:
        lead_time = min_lead
    elif max_lead is not None:
        lead_time = max_lead
    else:
        lead_time = None
    demand_lead_time = getattr(lane, "demand_lead_time", None) or {"type": "deterministic", "value": 1}
    supply_lead_time = getattr(lane, "supply_lead_time", None) or {"type": "deterministic", "value": lead_time or 1}

    return {
        "id": lane.id,
        "from_site_id": lane.from_site_id,  # AWS SC DM standard
        "to_site_id": lane.to_site_id,      # AWS SC DM standard
        "capacity": lane.capacity,
        "lead_time_days": lead_time_days,
        "lead_time": lead_time,
        "demand_lead_time": demand_lead_time,
        "supply_lead_time": supply_lead_time,
        "cost_per_unit": None,
    }


# DEPRECATED: Use _transportation_lane_to_payload
_lane_to_payload = _transportation_lane_to_payload


def _coerce_transportation_lane_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce incoming transportation lane payload to AWS SC DM standard fields.

    Accepts both old field names (from_node_id, to_node_id) and new AWS SC DM
    standard names (from_site_id, to_site_id) for backward compatibility.
    """
    # Accept both old (from_node_id) and AWS SC DM standard (from_site_id)
    upstream = payload.get("from_site_id", payload.get("from_node_id"))
    downstream = payload.get("to_site_id", payload.get("to_node_id"))

    lead_time_days = payload.get("lead_time_days")
    if not lead_time_days and payload.get("lead_time") is not None:
        try:
            value = int(payload["lead_time"])
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead time must be a whole number",
            )
        lead_time_days = {"min": value, "max": value}

    demand_lead_time = payload.get("demand_lead_time")
    supply_lead_time = payload.get("supply_lead_time")

    if supply_lead_time is None and lead_time_days:
        min_lead = lead_time_days.get("min")
        max_lead = lead_time_days.get("max")
        if min_lead is not None and max_lead is not None and min_lead == max_lead:
            supply_lead_time = {"type": "deterministic", "value": min_lead}
        elif min_lead is not None and max_lead is not None:
            supply_lead_time = {
                "type": "uniform",
                "minimum": min_lead,
                "maximum": max_lead,
            }
        elif min_lead is not None:
            supply_lead_time = {"type": "deterministic", "value": min_lead}
        elif max_lead is not None:
            supply_lead_time = {"type": "deterministic", "value": max_lead}

    if supply_lead_time is None and payload.get("lead_time") is not None:
        try:
            value = int(payload["lead_time"])
            supply_lead_time = {"type": "deterministic", "value": max(value, 0)}
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead time must be a whole number",
            )

    if demand_lead_time is None:
        demand_lead_time = {"type": "deterministic", "value": 1}

    if supply_lead_time is None:
        supply_lead_time = {"type": "deterministic", "value": 1}

    data = {
        "from_site_id": upstream,
        "to_site_id": downstream,
        "capacity": payload.get("capacity"),
        "lead_time_days": lead_time_days,
        "demand_lead_time": demand_lead_time,
        "supply_lead_time": supply_lead_time,
    }

    return data


# DEPRECATED: Use _coerce_transportation_lane_payload
_coerce_lane_payload = _coerce_transportation_lane_payload


def _get_user_admin_tenant_id(db: Session, user: models.User) -> Optional[int]:
    """Return the group ID managed by the provided user, if any.

    Note: Uses user_type (not is_superuser) to determine admin status.
    SYSTEM_ADMIN users return None (they see all configs).
    TENANT_ADMIN users return their administered tenant's ID.
    """
    user_type = getattr(user, "user_type", None)
    if isinstance(user_type, str):
        try:
            user_type = UserTypeEnum(user_type)
        except ValueError:
            user_type = None

    # SYSTEM_ADMIN sees all configs (return None to indicate no group filter)
    if user_type == UserTypeEnum.SYSTEM_ADMIN:
        return None

    # First, check if the user is explicitly registered as the group's primary admin
    direct_group = (
        db.query(models.Customer)
        .filter(models.Customer.admin_id == user.id)
        .first()
    )
    if direct_group:
        return direct_group.id

    # TENANT_ADMIN sees their tenant's configs
    if user_type == UserTypeEnum.TENANT_ADMIN and user.tenant_id:
        group = (
            db.query(models.Customer)
            .filter(models.Customer.id == user.tenant_id)
            .first()
        )
        if group:
            return group.id

    return None


def _ensure_user_can_manage_config(
    db: Session,
    user: models.User,
    config: SupplyChainConfig,
):
    """Ensure the current user can manage (mutate) the provided configuration."""
    user_type = getattr(user, "user_type", None)
    if user_type == UserTypeEnum.SYSTEM_ADMIN:
        return

    admin_tenant_id = _get_user_admin_tenant_id(db, user)
    if config.tenant_id is None:
        return
    if admin_tenant_id and config.tenant_id == admin_tenant_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this configuration",
    )


def _ensure_user_can_view_config(
    db: Session,
    user: models.User,
    config: SupplyChainConfig,
):
    """Ensure the current user can view (read) the provided configuration."""
    user_type = getattr(user, "user_type", None)
    if user_type == UserTypeEnum.SYSTEM_ADMIN:
        return

    config_tenant_id = getattr(config, "tenant_id", None)
    if config_tenant_id is None:
        return

    admin_tenant_id = _get_user_admin_tenant_id(db, user)
    if admin_tenant_id and config_tenant_id == admin_tenant_id:
        return

    user_tenant_id = getattr(user, "tenant_id", None)
    if user_tenant_id and user_tenant_id == config_tenant_id:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this configuration",
    )


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _compute_config_hash(db: Session, config_id: int) -> Optional[str]:
    config = crud.supply_chain_config.get(db, id=config_id)
    if not config:
        return None

    products = crud.product.get_by_config(db, config_id=config_id)
    sites = crud.site.get_multi_by_config(db, config_id=config_id, limit=1000)
    lanes = crud.lane.get_by_config(db, config_id=config_id)
    product_site_configs = crud.product_site_config.get_by_config(db, config_id=config_id)  # Legacy table
    market_demands = crud.market_demand.get_by_config(db, config_id=config_id)

    payload = {
        "config": {
            "name": config.name,
            "description": config.description,
            "is_active": bool(config.is_active),
            "tenant_id": config.tenant_id,
        },
        "items": [
            {
                "name": item.name,
                "unit_cost_range": item.unit_cost_range,
            }
            for item in sorted(items, key=lambda obj: obj.id)
        ],
        "sites": [
            {
                "name": node.name,
                "type": str(getattr(node, "dag_type", None) or getattr(node, "type", "")).lower(),
                "attributes": getattr(node, "attributes", {}) or {},
            }
            for node in sorted(nodes, key=lambda obj: obj.id)
        ],
        "lanes": [
            {
                "upstream": lane.from_site_id,
                "downstream": lane.to_site_id,
                "capacity": lane.capacity,
                "lead_time_days": lane.lead_time_days,
                "demand_lead_time": getattr(lane, "demand_lead_time", None),
                "supply_lead_time": getattr(lane, "supply_lead_time", None),
            }
            for lane in sorted(lanes, key=lambda obj: obj.id)
        ],
        "product_site_configs": [
            {
                "product_id": psc.product_id,
                "site_id": psc.site_id,
                "inventory_target_range": psc.inventory_target_range,
                "initial_inventory_range": psc.initial_inventory_range,
                "holding_cost_range": psc.holding_cost_range,
                "backlog_cost_range": psc.backlog_cost_range,
                "selling_price_range": psc.selling_price_range,
            }
            for psc in sorted(product_site_configs, key=lambda obj: obj.id)
        ],
        "market_demands": [
            {
                "product_id": md.product_id,
                "trading_partner_id": md.trading_partner_id,
                "market_id": md.market_id,  # deprecated — use trading_partner_id
                "demand_pattern": md.demand_pattern,
            }
            for md in sorted(market_demands, key=lambda obj: obj.id)
        ],
        "markets": [
            {
                "id": market.id,
                "name": market.name,
                "description": market.description,
                "company": getattr(market, "company", None),
            }
            for market in sorted(markets, key=lambda obj: obj.id)
        ],
    }

    encoded = json.dumps(payload, sort_keys=True, default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _mark_config_requires_training(
    db: Session,
    config: SupplyChainConfig,
    status_label: str = "pending",
) -> SupplyChainConfig:
    config.needs_training = True
    config.training_status = status_label
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _create_training_artifact(
    db: Session,
    config_id: int,
    dataset_path: Path,
    model_path: Path,
) -> SupplyChainTrainingArtifact:
    artifact = SupplyChainTrainingArtifact(
        config_id=config_id,
        dataset_name=dataset_path.name,
        model_name=model_path.name,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def _set_training_outcome(
    db: Session,
    config: SupplyChainConfig,
    *,
    status_label: str,
    needs_training: bool,
    trained_at: Optional[datetime] = None,
    model_path: Optional[str] = None,
    config_hash: Optional[str] = None,
) -> SupplyChainConfig:
    config.training_status = status_label
    config.needs_training = needs_training
    config.trained_at = trained_at
    config.trained_model_path = model_path
    config.last_trained_config_hash = config_hash
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _generate_training_dataset(
    config: SupplyChainConfig,
    params: ConfigTrainingRequest,
) -> Dict[str, Any]:
    TRAINING_ROOT.mkdir(parents=True, exist_ok=True)
    slug = _slugify(config.name)
    dataset_filename = f"{slug}_dataset.npz"
    dataset_path = TRAINING_ROOT / dataset_filename

    db_url = settings.SQLALCHEMY_DATABASE_URI or None
    if not db_url:
        raise ValueError("Database URL not configured")
    cfg = DbLookupConfig(database_url=db_url)
    X, A, P, Y = load_sequences_from_db(
        cfg,
        SimulationParams(),
        window=int(params.window),
        horizon=int(params.horizon),
        config_id=config.id,
    )
    np.savez(dataset_path, X=X, A=A, P=P, Y=Y)

    return {
        "path": str(dataset_path),
        "filename": dataset_filename,
        "samples": int(X.shape[0]),
        "window": int(params.window),
        "horizon": int(params.horizon),
    }


def _run_training_process(
    config: SupplyChainConfig,
    dataset_path: Path,
    params: ConfigTrainingRequest,
) -> Dict[str, Any]:
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    slug = _slugify(config.name)

    model_filename = f"{slug}_temporal_gnn.pt"
    model_path = MODEL_ROOT / model_filename
    log_path = MODEL_ROOT / f"{slug}_train.log"
    script_path = BACKEND_ROOT / "scripts" / "training" / "train_gnn.py"

    cmd = [
        sys.executable,
        str(script_path),
        "--source",
        "sim",
        "--window",
        str(params.window),
        "--horizon",
        str(params.horizon),
        "--epochs",
        str(params.epochs),
        "--save-path",
        str(model_path),
        "--dataset",
        str(dataset_path),
    ]
    if params.device:
        cmd.extend(["--device", params.device])

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        log_output = stdout + ("\n" + stderr if stderr else "")
    except subprocess.CalledProcessError as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        log_output = stdout + ("\n" + stderr if stderr else "")
        log_path.write_text(log_output)
        raise RuntimeError(log_output.strip() or str(exc)) from exc

    log_path.write_text(log_output)

    return {
        "model_path": str(model_path),
        "log": log_output,
        "log_path": str(log_path),
        "command": cmd,
    }


def _enqueue_training(
    background_tasks: Optional[BackgroundTasks],
    config_id: int,
    params: Optional[ConfigTrainingRequest] = None,
) -> None:
    payload = (params or ConfigTrainingRequest()).dict()
    if background_tasks is None:
        _train_config_task(config_id, payload)
    else:
        background_tasks.add_task(_train_config_task, config_id, payload)


def _train_config_task(config_id: int, params_data: Dict[str, Any]) -> None:
    """Run dataset generation and training for a configuration in the background."""
    db = SessionLocal()
    try:
        params = ConfigTrainingRequest(**params_data)
        config = crud.supply_chain_config.get(db, id=config_id)
        if not config:
            logger.warning("Config %s no longer exists; skipping training", config_id)
            return

        try:
            dataset_info = _generate_training_dataset(config, params)
        except Exception:
            logger.exception("Dataset generation failed for config %s", config_id)
            fresh = crud.supply_chain_config.get(db, id=config_id)
            if fresh:
                _set_training_outcome(
                    db,
                    fresh,
                    status_label="failed",
                    needs_training=True,
                    trained_at=fresh.trained_at,
                    model_path=fresh.trained_model_path,
                    config_hash=fresh.last_trained_config_hash,
                )
            return

        config = _set_training_outcome(
            db,
            config,
            status_label="in_progress",
            needs_training=False,
            trained_at=None,
            model_path=config.trained_model_path,
            config_hash=config.last_trained_config_hash,
        )

        try:
            dataset_path = Path(dataset_info["path"])
            training_info = _run_training_process(config, dataset_path, params)
            config_hash = _compute_config_hash(db, config_id)
            config = _set_training_outcome(
                db,
                config,
                status_label="trained",
                needs_training=False,
                trained_at=datetime.utcnow(),
                model_path=training_info["model_path"],
                config_hash=config_hash,
            )
            _create_training_artifact(db, config_id, dataset_path, Path(training_info["model_path"]))
        except Exception:
            logger.exception("Training process failed for config %s", config_id)
            fresh = crud.supply_chain_config.get(db, id=config_id)
            if fresh:
                _set_training_outcome(
                    db,
                    fresh,
                    status_label="failed",
                    needs_training=True,
                    trained_at=fresh.trained_at,
                    model_path=fresh.trained_model_path,
                    config_hash=fresh.last_trained_config_hash,
                )
    finally:
        db.close()

# --- Configuration Endpoints ---
# --- Configuration Endpoints ---

@router.get("/", response_model=List[schemas.SupplyChainConfig])
async def read_configs(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Retrieve all supply chain configurations."""
    # Only SYSTEM_ADMIN users see all configs; TENANT_ADMIN sees their tenant's configs
    if current_user.user_type == UserTypeEnum.SYSTEM_ADMIN:
        return crud.supply_chain_config.get_multi(db, skip=skip, limit=limit)

    # TENANT_ADMIN sees configs for their administered tenant
    admin_tenant_id = _get_user_admin_tenant_id(db, current_user)
    if admin_tenant_id:
        return crud.supply_chain_config.get_multi(
            db,
            skip=skip,
            limit=limit,
            tenant_id=admin_tenant_id,
        )

    # Regular users see configs for their assigned tenant
    user_tenant_id = getattr(current_user, "tenant_id", None)
    if user_tenant_id:
        return crud.supply_chain_config.get_multi(
            db,
            skip=skip,
            limit=limit,
            tenant_id=user_tenant_id,
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to view these configurations",
    )

@router.get("/active", response_model=schemas.SupplyChainConfig)
def read_active_config(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Get the active supply chain configuration for the current user.

    Resolution order:
    1. User's default_config_id (if set) — returns that specific config.
    2. Tenant's is_active=True BASELINE config (existing behaviour).
    """
    # Priority 1: user has a personal default config selected
    user_default_config_id = getattr(current_user, "default_config_id", None)
    if user_default_config_id:
        config = db.query(SupplyChainConfig).filter(
            SupplyChainConfig.id == user_default_config_id
        ).first()
        if config:
            # Validate the config still belongs to the user's tenant
            user_tenant_id = getattr(current_user, "tenant_id", None)
            user_type = getattr(current_user, "user_type", None)
            if user_type == UserTypeEnum.SYSTEM_ADMIN or config.tenant_id == user_tenant_id:
                return config
            # Config no longer belongs to this tenant — fall through to default

    # Priority 2: tenant's active baseline (existing behaviour)
    user_type = getattr(current_user, "user_type", None)
    if user_type == UserTypeEnum.SYSTEM_ADMIN:
        # System admin: try their tenant first, fall back to any active baseline
        tenant_id = getattr(current_user, "tenant_id", None)
        if tenant_id:
            config = deps.get_active_baseline_config(db, tenant_id)
        else:
            config = (
                db.query(SupplyChainConfig)
                .filter(
                    SupplyChainConfig.is_active == True,
                    SupplyChainConfig.scenario_type == "BASELINE",
                )
                .first()
            )
    else:
        admin_tenant_id = _get_user_admin_tenant_id(db, current_user)
        tenant_id = admin_tenant_id or getattr(current_user, "tenant_id", None)
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this configuration",
            )
        config = deps.get_active_baseline_config(db, tenant_id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active baseline configuration found",
        )
    return config

@router.post("/", response_model=schemas.SupplyChainConfig, status_code=status.HTTP_201_CREATED)
def create_config(
    *,
    db: Session = Depends(deps.get_db),
    config_in: schemas.SupplyChainConfigCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    """Create a new supply chain configuration."""
    admin_tenant_id = _get_user_admin_tenant_id(db, current_user)
    user_type = getattr(current_user, "user_type", None)

    if user_type == UserTypeEnum.SYSTEM_ADMIN:
        target_tenant_id = config_in.tenant_id
        if target_tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant is required to create a configuration",
            )

        if not db.query(models.Customer).filter(models.Customer.id == target_tenant_id).first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Specified tenant not found",
            )

        payload = config_in
    else:
        if not admin_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to create configurations",
            )

        payload = config_in.copy(update={"tenant_id": admin_tenant_id})

    cfg = crud.supply_chain_config.create(db, obj_in=payload)
    # Attach creator if column exists
    try:
        cfg.created_by = current_user.id
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    except Exception:
        pass
    cfg = _mark_config_requires_training(db, cfg)
    _enqueue_training(background_tasks, cfg.id)
    _enqueue_rag_indexing(background_tasks, cfg.id, cfg.tenant_id)
    return cfg

@router.get("/{config_id}", response_model=schemas.SupplyChainConfig)
def read_config(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Get a specific configuration by ID."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_view_config(db, current_user, config)
    return config

@router.put("/{config_id}", response_model=schemas.SupplyChainConfig)
def update_config(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    config_in: schemas.SupplyChainConfigUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    """Update a configuration."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)

    update_data = config_in.dict(exclude_unset=True)
    user_type = getattr(current_user, "user_type", None)

    if user_type == UserTypeEnum.SYSTEM_ADMIN:
        if "tenant_id" in update_data:
            new_tenant_id = update_data["tenant_id"]
            if new_tenant_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Tenant cannot be null",
                )
            if not db.query(models.Customer).filter(models.Customer.id == new_tenant_id).first():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Specified tenant not found",
                )
    else:
        if "tenant_id" in update_data and update_data["tenant_id"] != config.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot reassign this configuration to another tenant",
            )
        update_data.pop("tenant_id", None)

    updated = crud.supply_chain_config.update(db, db_obj=config, obj_in=update_data)
    changed_keys = set(update_data.keys())
    if not changed_keys or changed_keys <= {"is_active"}:
        return updated
    updated = _mark_config_requires_training(db, updated)
    _enqueue_training(background_tasks, updated.id)
    _enqueue_rag_indexing(background_tasks, updated.id, updated.tenant_id)
    return updated


@router.post("/{config_id}/train", response_model=ConfigTrainingResponse)
def train_supply_chain_config(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    params: ConfigTrainingRequest = Body(default_factory=ConfigTrainingRequest),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Generate synthetic training data and train the temporal GNN for a configuration."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)

    if config.training_status == "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Training is already running for this configuration.",
        )

    dataset_info = _generate_training_dataset(config, params)

    # Mark as in progress before launching the trainer
    _set_training_outcome(
        db,
        config,
        status_label="in_progress",
        needs_training=False,
        trained_at=None,
        model_path=config.trained_model_path,
        config_hash=config.last_trained_config_hash,
    )

    try:
        dataset_path = Path(dataset_info["path"])
        training_info = _run_training_process(
            config,
            dataset_path,
            params,
        )
        config_hash = _compute_config_hash(db, config_id)
        updated = _set_training_outcome(
            db,
            config,
            status_label="trained",
            needs_training=False,
            trained_at=datetime.utcnow(),
            model_path=training_info["model_path"],
            config_hash=config_hash,
        )
        _create_training_artifact(db, config.id, dataset_path, Path(training_info["model_path"]))
    except Exception as exc:  # noqa: BLE001 - surface training failure to client
        _set_training_outcome(
            db,
            config,
            status_label="failed",
            needs_training=True,
            trained_at=config.trained_at,
            model_path=config.trained_model_path,
            config_hash=config.last_trained_config_hash,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Training failed: {exc}",
        ) from exc

    return ConfigTrainingResponse(
        status=updated.training_status,
        message="Training completed successfully.",
        dataset_path=dataset_info["path"],
        model_path=updated.trained_model_path or training_info["model_path"],
        trained_at=updated.trained_at,
        log=training_info["log"],
    )

@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    """Delete a configuration."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    tenant_id = config.tenant_id
    crud.supply_chain_config.remove(db, id=config_id)
    _enqueue_rag_deletion(background_tasks, config_id, tenant_id)
    return None

# --- Item Endpoints ---

# ============================================================================
# Product Endpoints (SC Compliant)
# ============================================================================

@router.get("/{config_id}/products", response_model=List[schemas.ProductResponse])
def list_products(
    config_id: int,
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Get all products for a supply chain configuration with computed hierarchy_path."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_view_config(db, current_user, config)
    # Use hierarchy-aware method to include hierarchy_path from product_hierarchy table
    products = crud.product.get_by_config_with_hierarchy(db, config_id=config_id)
    return products[skip:skip+limit]


@router.post("/{config_id}/products", response_model=schemas.Product, status_code=status.HTTP_201_CREATED)
def create_product(
    *,
    config_id: int,
    product_in: schemas.ProductCreate,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    """Create a new product in a configuration."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)

    # Check for duplicate product ID
    existing = crud.product.get(db, id=product_in.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product with ID '{product_in.id}' already exists"
        )

    # Set config_id if not provided
    if not product_in.config_id:
        product_in.config_id = config_id

    created = crud.product.create(db, obj_in=product_in)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return created


@router.get("/{config_id}/products/{product_id}", response_model=schemas.ProductResponse)
def get_product(
    *,
    config_id: int,
    product_id: str,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Get a product by ID with computed hierarchy_path."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_view_config(db, current_user, config)

    # Use hierarchy-aware method to include hierarchy_path from product_hierarchy table
    product = crud.product.get_with_hierarchy(db, id=product_id)
    if not product or product.get("config_id") != config_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{product_id}' not found in this configuration"
        )
    return product


@router.put("/{config_id}/products/{product_id}", response_model=schemas.Product)
def update_product(
    *,
    config_id: int,
    product_id: str,
    product_in: schemas.ProductUpdate,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    """Update a product."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)

    product = crud.product.get(db, id=product_id)
    if not product or product.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{product_id}' not found in this configuration"
        )

    updated = crud.product.update(db, db_obj=product, obj_in=product_in)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return updated


@router.delete("/{config_id}/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    *,
    config_id: int,
    product_id: str,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    """Delete a product."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)

    product = crud.product.get(db, id=product_id)
    if not product or product.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{product_id}' not found in this configuration"
        )

    crud.product.remove(db, id=product_id)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return None


# ============================================================================
# Legacy Item Endpoints (Commented Out - Use Products Instead)
# ============================================================================

# TODO: Migrate to Product endpoints - Phase 4
# @router.get("/{config_id}/items", response_model=List[schemas.Item])
# def read_items(
#     config_id: int,
#     db: Session = Depends(deps.get_db),
#     skip: int = 0,
#     limit: int = 100,
#     current_user: models.User = Depends(deps.get_current_active_user),
# ):
#     """Get all items for a configuration."""
#     config = get_config_or_404(db, config_id)
#     _ensure_user_can_manage_config(db, current_user, config)
#     return crud.item.get_multi_by_config(db, config_id=config_id, skip=skip, limit=limit)
#
# @router.post("/{config_id}/items", response_model=schemas.Item, status_code=status.HTTP_201_CREATED)
# def create_item(
#     *,
#     db: Session = Depends(deps.get_db),
#     config_id: int,
#     item_in: schemas.ItemCreate,
#     current_user: models.User = Depends(deps.get_current_active_user),
# ):
#     """Create a new item in a configuration."""
#     config = get_config_or_404(db, config_id)
#     _ensure_user_can_manage_config(db, current_user, config)
#
#     # Check for duplicate name
#     if crud.item.get_by_name(db, name=item_in.name, config_id=config_id):
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="An item with this name already exists in this configuration"
#         )
#
#     created = crud.item.create_with_config(db, obj_in=item_in, config_id=config_id)
#     _mark_config_requires_training(db, config)
#     return created
#
# @router.get("/{config_id}/items/{product_id}", response_model=schemas.Item)
# def read_item(
#     *,
#     db: Session = Depends(deps.get_db),
#     config_id: int,
#     product_id: int,
#     current_user: models.User = Depends(deps.get_current_active_user),
# ):
#     config = get_config_or_404(db, config_id)
#     _ensure_user_can_manage_config(db, current_user, config)
#     return get_item_or_404(db, product_id, config_id)
#
#
# @router.put("/{config_id}/items/{product_id}", response_model=schemas.Item)
# def update_item(
#     *,
#     db: Session = Depends(deps.get_db),
#     config_id: int,
#     product_id: int,
#     item_in: schemas.ItemUpdate,
#     current_user: models.User = Depends(deps.get_current_active_user),
# ):
#     config = get_config_or_404(db, config_id)
#     _ensure_user_can_manage_config(db, current_user, config)
#     db_item = get_item_or_404(db, product_id, config_id)
#
#     new_name = item_in.name.strip() if isinstance(item_in.name, str) else db_item.name
#     if new_name and new_name != db_item.name:
#         existing = crud.item.get_by_name(db, name=new_name, config_id=config_id)
#         if existing and existing.id != db_item.id:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="An item with this name already exists in this configuration",
#             )
#
#     updated = crud.item.update(db, db_obj=db_item, obj_in=item_in)
#     _mark_config_requires_training(db, config)
#     return updated
#
#
# @router.delete("/{config_id}/items/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
# def delete_item(
#     *,
#     db: Session = Depends(deps.get_db),
#     config_id: int,
#     product_id: int,
#     current_user: models.User = Depends(deps.get_current_active_user),
# ):
#     config = get_config_or_404(db, config_id)
#     _ensure_user_can_manage_config(db, current_user, config)
#     db_item = get_item_or_404(db, product_id, config_id)
#
#     crud.item.remove(db, id=db_item.id)
#     _mark_config_requires_training(db, config)
#     return None

# ... (Additional endpoints for items, nodes, lanes, product_site_configs, and market_demands)
# The full implementation would include similar CRUD endpoints for all models
# including proper error handling and permissions

# --- Site Endpoints (AWS SC DM) ---

def _build_geo_region_map(db: Session, sites) -> Dict[str, str]:
    """Build a geo_id → region_name lookup by walking the geography parent chain.

    Geography hierarchy: Country → Region → State → City
    Sites link to city-level geography. We walk up 2 levels (city → state → region)
    to find the region description.
    """
    from app.models.sc_entities import Geography

    geo_ids = {s.geo_id for s in sites if s.geo_id}
    if not geo_ids:
        return {}

    # Load all geography records that could be in the ancestor chain
    all_geos = db.query(Geography).filter(
        Geography.id.in_(list(geo_ids))
    ).all()
    geo_map = {g.id: g for g in all_geos}

    # Load parents (state level)
    parent_ids = {g.parent_geo_id for g in all_geos if g.parent_geo_id}
    if parent_ids:
        parents = db.query(Geography).filter(Geography.id.in_(list(parent_ids))).all()
        for p in parents:
            geo_map[p.id] = p

    # Load grandparents (region level)
    grandparent_ids = {
        geo_map[pid].parent_geo_id
        for pid in parent_ids
        if pid in geo_map and geo_map[pid].parent_geo_id
    }
    if grandparent_ids:
        grandparents = db.query(Geography).filter(Geography.id.in_(list(grandparent_ids))).all()
        for gp in grandparents:
            geo_map[gp.id] = gp

    # Build geo_id → region name for each site-level geo
    region_map = {}
    for geo_id in geo_ids:
        geo = geo_map.get(geo_id)
        if not geo:
            logger.warning(f"Geography not found for geo_id={geo_id}")
            continue
        # Walk up: city → state → region
        state_geo = geo_map.get(geo.parent_geo_id) if geo.parent_geo_id else None
        region_geo = geo_map.get(state_geo.parent_geo_id) if state_geo and state_geo.parent_geo_id else None
        if region_geo and region_geo.description:
            # Strip " Region" suffix if present for cleaner display
            name = region_geo.description
            if name.endswith(" Region"):
                name = name[:-7]
            region_map[geo_id] = name
        elif state_geo and state_geo.description:
            # Fallback: use state description as region
            region_map[geo_id] = state_geo.description
    logger.info(f"Resolved {len(region_map)}/{len(geo_ids)} site geo regions")
    return region_map


def _enrich_sites_with_region(sites, region_map: Dict[str, str]) -> List[dict]:
    """Convert site ORM objects to dicts with region added to geography."""
    result = []
    for site in sites:
        site_dict = {
            "id": site.id,
            "config_id": site.config_id,
            "name": site.name,
            "type": site.type,
            "dag_type": site.dag_type,
            "master_type": _master_type_to_node_type(site.master_type).value,
            "priority": site.priority,
            "order_aging": site.order_aging,
            "lost_sale_cost": site.lost_sale_cost,
            "attributes": site.attributes,
            "geo_id": site.geo_id,
            "segment_id": site.segment_id,
            "company_id": site.company_id,
        }
        # Geographic coordinates: prefer Geography record, fall back to site columns,
        # then to city/country in attributes for display.
        attrs = site.attributes or {}
        if site.geography:
            site_dict["geography"] = {
                "id": site.geography.id,
                "city": site.geography.city,
                "state_prov": site.geography.state_prov,
                "region": region_map.get(site.geo_id),
                "country": site.geography.country,
                "latitude": site.geography.latitude or site.latitude,
                "longitude": site.geography.longitude or site.longitude,
            }
        elif site.latitude is not None and site.longitude is not None:
            site_dict["geography"] = {
                "id": None,
                "city": attrs.get("city"),
                "state_prov": attrs.get("state"),
                "region": None,
                "country": attrs.get("country"),
                "latitude": site.latitude,
                "longitude": site.longitude,
            }
        else:
            site_dict["geography"] = None
        result.append(site_dict)
    return result


@router.get("/{config_id}/sites")
def read_sites(
    config_id: int,
    site_type: Optional[str] = None,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Get all sites for a configuration, optionally filtered by type."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_view_config(db, current_user, config)

    if site_type:
        dag_token = MixedScenarioService._canonical_role(site_type)
        if not dag_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid site type '{site_type}'",
            )
        sites = crud.site.get_by_type(db, node_type=dag_token, config_id=config_id)
    else:
        sites = crud.site.get_multi_by_config(db, config_id=config_id, limit=1000)

    region_map = _build_geo_region_map(db, sites)
    return _enrich_sites_with_region(sites, region_map)

@router.post("/{config_id}/sites", response_model=schemas.Site, status_code=status.HTTP_201_CREATED)
def create_site(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    site_in: schemas.SiteCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    """Create a new site in a configuration."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)

    type_entry = _get_site_type_entry(site_in.type, config)
    dag_type = type_entry["dag_type"]

    # Check for duplicate name and type
    if crud.site.get_by_name_and_type(
        db, name=site_in.name, node_type=dag_type, config_id=config_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A site with this name and type already exists in this configuration"
        )

    payload = site_in.dict(exclude_unset=True)
    payload["type"] = dag_type
    payload["dag_type"] = dag_type
    payload["master_type"] = type_entry["master_type"]

    created = crud.site.create_with_config(db, obj_in=payload, config_id=config_id)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return created


@router.get("/{config_id}/sites/{site_id}", response_model=schemas.Site)
def read_site(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    site_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Get a single site by ID."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_view_config(db, current_user, config)
    return get_site_or_404(db, site_id, config_id)


@router.put("/{config_id}/sites/{site_id}", response_model=schemas.Site)
def update_site(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    site_id: int,
    site_in: schemas.SiteUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    """Update an existing site."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    db_site = get_site_or_404(db, site_id, config_id)

    new_name = site_in.name.strip() if isinstance(site_in.name, str) else db_site.name
    type_entry: Optional[Dict[str, Any]] = None
    current_dag_type = str(db_site.dag_type or db_site.type or "")
    new_dag_type = MixedScenarioService._canonical_role(site_in.dag_type or site_in.type) or current_dag_type
    if site_in.type is not None:
        type_entry = _get_site_type_entry(site_in.type, config)
        new_dag_type = type_entry["dag_type"]
    elif site_in.dag_type is not None:
        canonical = MixedScenarioService._canonical_role(site_in.dag_type)
        if canonical:
            new_dag_type = canonical

    if (new_name != db_site.name) or (new_dag_type != current_dag_type):
        existing = crud.site.get_by_name_and_type(
            db,
            name=new_name,
            node_type=new_dag_type,
            config_id=config_id,
        )
        if existing and existing.id != db_site.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A site with this name and type already exists in this configuration",
            )

    # Apply updates directly with coerced enum values
    db_site.name = new_name
    if type_entry:
        db_site.type = type_entry["dag_type"]
        db_site.dag_type = type_entry["dag_type"]
        db_site.master_type = type_entry["master_type"]
    else:
        if new_dag_type:
            db_site.dag_type = new_dag_type
            db_site.type = new_dag_type
        if site_in.dag_type is not None:
            dag_token = MixedScenarioService._canonical_role(site_in.dag_type)
            if dag_token:
                db_site.dag_type = dag_token
                db_site.type = dag_token
        if site_in.master_type is not None:
            master_token = MixedScenarioService._canonical_role(site_in.master_type)
            if master_token:
                db_site.master_type = master_token
    if site_in.priority is not None:
        db_site.priority = site_in.priority
    if site_in.order_aging is not None:
        db_site.order_aging = site_in.order_aging
    if site_in.lost_sale_cost is not None:
        db_site.lost_sale_cost = site_in.lost_sale_cost
    if site_in.attributes is not None:
        db_site.attributes = site_in.attributes
    updated = crud.site.update(db, db_obj=db_site, obj_in={})
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return updated


@router.delete("/{config_id}/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    site_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    """Delete a site from the configuration."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    db_site = get_site_or_404(db, site_id, config_id)

    if db_site.upstream_lanes or db_site.downstream_lanes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Remove associated lanes before deleting this site",
        )

    crud.site.remove(db, id=db_site.id)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return None


# --- Transportation Lane Endpoints (AWS SC DM) ---
# Routes: /transportation-lanes (AWS SC DM standard), /lanes (deprecated alias)


@router.get("/{config_id}/transportation-lanes")
@router.get("/{config_id}/lanes")  # DEPRECATED: Use /transportation-lanes
def read_transportation_lanes(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> List[Dict[str, Any]]:
    """List all transportation lanes for a supply chain configuration."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_view_config(db, current_user, config)
    lanes = crud.transportation_lane.get_by_config(db, config_id=config_id)
    return [_transportation_lane_to_payload(lane) for lane in lanes]


@router.get("/{config_id}/transportation-lanes/{lane_id}")
@router.get("/{config_id}/lanes/{lane_id}")  # DEPRECATED: Use /transportation-lanes
def read_transportation_lane(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    lane_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Dict[str, Any]:
    """Get a specific transportation lane by ID."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_view_config(db, current_user, config)
    lane = get_transportation_lane_or_404(db, lane_id, config_id)
    return _transportation_lane_to_payload(lane)


@router.post("/{config_id}/transportation-lanes", status_code=status.HTTP_201_CREATED)
@router.post("/{config_id}/lanes", status_code=status.HTTP_201_CREATED)  # DEPRECATED
def create_transportation_lane(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    lane_in: Dict[str, Any] = Body(...),
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Create a new transportation lane connecting two sites."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)

    lane_data = _coerce_transportation_lane_payload(lane_in)
    upstream_id = lane_data.get("from_site_id")
    downstream_id = lane_data.get("to_site_id")
    capacity = lane_data.get("capacity")
    lead_time_days = lane_data.get("lead_time_days")
    supply_lead_time = lane_data.get("supply_lead_time")

    if not upstream_id or not downstream_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both source and destination sites are required",
        )

    upstream_site = get_site_or_404(db, upstream_id, config_id)
    downstream_site = get_site_or_404(db, downstream_id, config_id)

    if upstream_site.id == downstream_site.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination sites must be different",
        )

    if supply_lead_time is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supply lead time information is required",
        )

    if capacity is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Capacity is required",
        )

    existing = crud.transportation_lane.get_by_nodes(
        db,
        from_site_id=upstream_site.id,
        to_site_id=downstream_site.id,
        config_id=config_id,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A transportation lane between these sites already exists",
        )

    lane_payload = schemas.TransportationLaneCreate(**lane_data)
    created = crud.transportation_lane.create_with_config(db, obj_in=lane_payload, config_id=config_id)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return _transportation_lane_to_payload(created)


@router.put("/{config_id}/transportation-lanes/{lane_id}")
@router.put("/{config_id}/lanes/{lane_id}")  # DEPRECATED: Use /transportation-lanes
def update_transportation_lane(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    lane_id: int,
    lane_in: Dict[str, Any] = Body(...),
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Update an existing transportation lane."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    lane = get_transportation_lane_or_404(db, lane_id, config_id)

    update_payload: Dict[str, Any] = {}
    if "capacity" in lane_in and lane_in["capacity"] is not None:
        try:
            update_payload["capacity"] = int(lane_in["capacity"])
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Capacity must be a whole number",
            )

    lead_time_days = lane_in.get("lead_time_days")
    if not lead_time_days and lane_in.get("lead_time") is not None:
        try:
            value = int(lane_in["lead_time"])
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead time must be a whole number",
            )
        lead_time_days = {"min": value, "max": value}
    if lead_time_days is not None:
        update_payload["lead_time_days"] = lead_time_days

    if "demand_lead_time" in lane_in and lane_in["demand_lead_time"] is not None:
        update_payload["demand_lead_time"] = lane_in["demand_lead_time"]

    if "supply_lead_time" in lane_in and lane_in["supply_lead_time"] is not None:
        update_payload["supply_lead_time"] = lane_in["supply_lead_time"]

    if not update_payload:
        return _transportation_lane_to_payload(lane)

    lane_update = schemas.TransportationLaneUpdate(**update_payload)
    updated = crud.transportation_lane.update(db, db_obj=lane, obj_in=lane_update)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return _transportation_lane_to_payload(updated)


@router.delete("/{config_id}/transportation-lanes/{lane_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{config_id}/lanes/{lane_id}", status_code=status.HTTP_204_NO_CONTENT)  # DEPRECATED
def delete_transportation_lane(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    lane_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    """Delete a transportation lane."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    lane = get_transportation_lane_or_404(db, lane_id, config_id)

    crud.transportation_lane.remove(db, id=lane.id)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return None


# --- Product-Site Configuration Endpoints (AWS SC DM) ---


def _read_product_site_configs_impl(db: Session, config_id: int, current_user):
    """Shared implementation for product-site config read."""
    from sqlalchemy import text

    config = get_config_or_404(db, config_id)
    _ensure_user_can_view_config(db, current_user, config)

    query = text("""
        SELECT
            inc.id,
            inc.product_id,
            inc.site_id,
            inc.inventory_target_range,
            inc.initial_inventory_range,
            inc.holding_cost_range,
            inc.backlog_cost_range,
            inc.selling_price_range
        FROM item_node_configs inc
        INNER JOIN site s ON inc.site_id = s.id
        WHERE s.config_id = :config_id
        ORDER BY inc.product_id, inc.site_id
    """)

    result = db.execute(query, {"config_id": config_id})
    rows = result.fetchall()

    configs = []
    for row in rows:
        configs.append({
            "id": row[0],
            "product_id": row[1],
            "site_id": row[2],
            "inventory_target_range": row[3] or {"min": 10, "max": 50},
            "initial_inventory_range": row[4] or {"min": 10, "max": 30},
            "holding_cost_range": row[5] or {"min": 0.1, "max": 0.5},
            "backlog_cost_range": row[6] or {"min": 1.0, "max": 3.0},
            "selling_price_range": row[7] or {"min": 50, "max": 150},
        })

    return configs


@router.get("/{config_id}/product-site-configs")
def read_product_site_configs(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Returns product-site configurations for the supply chain config (AWS SC DM)."""
    return _read_product_site_configs_impl(db, config_id, current_user)


@router.get("/{config_id}/item-node-configs")
def read_product_site_configs_compat(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """DEPRECATED: Use /product-site-configs instead."""
    return _read_product_site_configs_impl(db, config_id, current_user)


@router.post(
    "/{config_id}/product-site-configs",
    response_model=schemas.ProductSiteConfig,
    status_code=status.HTTP_201_CREATED,
)
def create_product_site_config(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    config_in: schemas.ProductSiteConfigCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Create a product-site configuration entry."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)

    product = crud.product.get(db, id=config_in.product_id)
    site = crud.site.get(db, id=config_in.site_id)
    if not product or product.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product must belong to this configuration",
        )
    if not site or site.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site must belong to this configuration",
        )

    existing = crud.product_site_config.get_by_product_and_site(
        db,
        product_id=config_in.product_id,
        site_id=config_in.site_id,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This product already has configuration for the specified site",
        )

    created = crud.product_site_config.create(db, obj_in=config_in)
    _mark_config_requires_training(db, config)
    return created


@router.put(
    "/{config_id}/product-site-configs/{config_entry_id}",
    response_model=schemas.ProductSiteConfig,
)
def update_product_site_config(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    config_entry_id: int,
    config_in: schemas.ProductSiteConfigUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Update a product-site configuration entry."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    entry = get_product_site_config_or_404(db, config_id, config_entry_id)

    updated = crud.product_site_config.update(db, db_obj=entry, obj_in=config_in)
    _mark_config_requires_training(db, config)
    return updated


@router.delete(
    "/{config_id}/product-site-configs/{config_entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product_site_config(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    config_entry_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Delete a product-site configuration entry."""
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    entry = get_product_site_config_or_404(db, config_id, config_entry_id)

    crud.product_site_config.remove(db, id=entry.id)
    _mark_config_requires_training(db, config)
    return None


# --- Market Demand Endpoints ---

@router.get(
    "/{config_id}/markets",
    response_model=List[schemas.Market],
)
def read_markets(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    return crud.market.get_by_config(db, config_id=config_id)


@router.post(
    "/{config_id}/markets",
    response_model=schemas.Market,
    status_code=status.HTTP_201_CREATED,
)
def create_market(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    market_in: schemas.MarketCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)

    existing = crud.market.get_by_name(db, config_id=config_id, name=market_in.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A market with this name already exists in the configuration",
        )

    created = crud.market.create_with_config(db, obj_in=market_in, config_id=config_id)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return created


@router.put(
    "/{config_id}/markets/{market_id}",
    response_model=schemas.Market,
)
def update_market(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    market_id: int,
    market_in: schemas.MarketUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    market = db.query(Market).filter(Market.id == market_id, Market.config_id == config_id).first()
    if not market:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found")

    if market_in.name and market_in.name != market.name:
        existing = crud.market.get_by_name(db, config_id=config_id, name=market_in.name)
        if existing and existing.id != market_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A market with this name already exists",
            )

    updated = crud.market.update(db, db_obj=market, obj_in=market_in)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return updated


@router.delete(
    "/{config_id}/markets/{market_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_market(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    market_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    market = db.query(Market).filter(Market.id == market_id, Market.config_id == config_id).first()
    if not market:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found")
    if market.demands:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a market that has demand assignments",
        )
    crud.market.remove(db, id=market.id)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return None


@router.get(
    "/{config_id}/market-demands",
    response_model=List[schemas.MarketDemand],
)
def read_market_demands(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    return crud.market_demand.get_by_config(db, config_id=config_id)


@router.post(
    "/{config_id}/market-demands",
    response_model=schemas.MarketDemand,
    status_code=status.HTTP_201_CREATED,
)
def create_market_demand(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    demand_in: schemas.MarketDemandCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)

    product = crud.product.get(db, id=demand_in.product_id)
    market = crud.market.get(db, id=demand_in.market_id)

    if not product or product.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product must belong to this configuration",
        )

    if not market or market.config_id != config_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Market must belong to this configuration",
        )

    existing = crud.market_demand.get_by_item_and_market(
        db,
        product_id=demand_in.product_id,
        market_id=demand_in.market_id,
        config_id=config_id,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A market demand entry already exists for this product and market",
        )

    created = crud.market_demand.create(db, obj_in=demand_in)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return created


@router.put(
    "/{config_id}/market-demands/{demand_id}",
    response_model=schemas.MarketDemand,
)
def update_market_demand(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    demand_id: int,
    demand_in: schemas.MarketDemandUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    demand = get_market_demand_or_404(db, config_id, demand_id)

    updated = crud.market_demand.update(db, db_obj=demand, obj_in=demand_in)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return updated


@router.delete(
    "/{config_id}/market-demands/{demand_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_market_demand(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    demand_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks,
):
    config = get_config_or_404(db, config_id)
    _ensure_user_can_manage_config(db, current_user, config)
    demand = get_market_demand_or_404(db, config_id, demand_id)

    crud.market_demand.remove(db, id=demand.id)
    _mark_config_requires_training(db, config)
    _enqueue_rag_indexing(background_tasks, config_id, config.tenant_id)
    return None
# --- Scenario Integration Endpoints ---

@router.post("/{config_id}/create-scenario", response_model=Dict[str, Any])
def create_scenario_from_config(
    *,
    db: Session = Depends(deps.get_db),
    config_id: int,
    scenario_data: Dict[str, Any] = Body(
        default={
            "name": "New Scenario",
            "description": "Scenario created from supply chain configuration",
            "max_rounds": 52,
            "is_public": True
        },
        example={
            "name": "New Scenario",
            "description": "Scenario created from supply chain configuration",
            "max_rounds": 52,
            "is_public": True
        }
    ),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Create a scenario configuration from a supply chain configuration.

    This endpoint generates a scenario configuration based on the supply chain configuration
    with the specified ID. The configuration includes node policies, demand patterns,
    and other settings derived from the supply chain model.

    Returns a scenario configuration that can be used to create a new scenario.
    """
    # Verify the configuration exists
    config = db.query(SupplyChainConfig).filter(SupplyChainConfig.id == config_id).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supply chain configuration with ID {config_id} not found"
        )

    _ensure_user_can_manage_config(db, current_user, config)

    # Use the service to create the scenario configuration
    service = SupplyChainConfigService(db)
    try:
        scenario_config = service.create_scenario_from_config(config_id, scenario_data)
        return scenario_config
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scenario configuration: {str(e)}"
        )


@router.post("/{config_id}/validate", response_model=Dict[str, Any])
def validate_supply_chain_config(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Validate a supply chain configuration for priority conflicts.

    Checks that each item-node combination has unique supplier priorities.
    """
    from app.services.supply_chain_config_service import SupplyChainConfigService

    service = SupplyChainConfigService(db)

    # Check if config exists and user has access
    config = db.query(SupplyChainConfig).filter(SupplyChainConfig.id == config_id).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supply chain configuration not found"
        )

    # Validate access (must be in same group or be system admin)
    if current_user.type != UserTypeEnum.SYSTEM_ADMIN:
        if config.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to validate this configuration"
            )

    try:
        is_valid, errors = service.validate_config(config_id)
        return {
            "is_valid": is_valid,
            "validation_status": "valid" if is_valid else "invalid",
            "errors": errors,
            "validated_at": config.validated_at.isoformat() if config.validated_at else None,
        }
    except Exception as e:
        logger.error(f"Error validating config {config_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate configuration: {str(e)}"
        )


# ... (Additional CRUD endpoints for nodes, lanes, product_site_configs, and market_demands)


# =============================================================================
# Scenario Branching Endpoints (Git-like Configuration Inheritance)
# =============================================================================

class ScenarioBranchRequest(BaseModel):
    """Request to create a new scenario branch"""
    name: str = Field(..., min_length=1, max_length=100, description="Name for the new scenario")
    description: Optional[str] = Field(None, max_length=500, description="Description of branch purpose")
    scenario_type: str = Field("WORKING", description="BASELINE, WORKING, or SIMULATION")


class ScenarioUpdateRequest(BaseModel):
    """Request to record a delta in a scenario"""
    entity_type: str = Field(..., description="Type of entity (node, lane, market_demand, etc.)")
    operation: str = Field(..., description="Operation: create, update, or delete")
    entity_id: Optional[int] = Field(None, description="ID of entity (NULL for create)")
    delta_data: Dict[str, Any] = Field(..., description="Entity data for the change")
    description: Optional[str] = Field(None, max_length=500, description="Human-readable description")


@router.post("/{config_id}/branch", status_code=status.HTTP_201_CREATED)
def create_scenario_branch(
    config_id: int,
    request: ScenarioBranchRequest,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    """
    Create a new scenario branch from a parent configuration.

    Implements git-like branching with copy-on-write semantics:
    - Child inherits all entities from parent
    - Changes stored as deltas
    - Efficient storage (only differences stored)

    Example:
        TBG Root → Case TBG → Six-Pack TBG → Bottle TBG → Three FG

    Args:
        config_id: Parent configuration ID
        request: Branch creation request

    Returns:
        New child configuration

    Raises:
        404: Parent configuration not found
        403: Not authorized to branch from parent
    """
    from app.services.scenario_branching_service import ScenarioBranchingService

    # Get parent config
    parent = get_config_or_404(db, config_id)

    # Validate access
    if current_user.type != UserTypeEnum.SYSTEM_ADMIN:
        if parent.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to branch from this configuration"
            )

    # Create branch
    service = ScenarioBranchingService(db)
    try:
        child = service.create_branch(
            parent_config_id=config_id,
            name=request.name,
            description=request.description or "",
            scenario_type=request.scenario_type,
            created_by=current_user.id,
        )
        return {
            "id": child.id,
            "name": child.name,
            "description": child.description,
            "parent_config_id": child.parent_config_id,
            "base_config_id": child.base_config_id,
            "scenario_type": child.scenario_type,
            "branched_at": child.branched_at.isoformat() if child.branched_at else None,
            "message": f"Successfully created branch '{child.name}' from '{parent.name}'"
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating branch from config {config_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create branch: {str(e)}"
        )


@router.get("/{config_id}/effective")
def get_effective_configuration(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    """
    Get the effective configuration by merging parent + all ancestor deltas.

    Returns the materialized view of the configuration, with all inherited
    entities from ancestors plus all deltas applied.

    Algorithm:
    1. Get lineage (self → parent → grandparent → root)
    2. Start with root config's entities
    3. Apply deltas in order (root → parent → self)
    4. Return merged configuration

    Args:
        config_id: Configuration to compute

    Returns:
        Effective configuration dictionary with:
        - config: Metadata
        - nodes: List of nodes
        - lanes: List of lanes
        - markets: List of markets
        - market_demands: List of market demands
        - products: List of products
        - boms: List of BOMs

    Raises:
        404: Configuration not found
        403: Not authorized
    """
    from app.services.scenario_branching_service import ScenarioBranchingService

    # Get config
    config = get_config_or_404(db, config_id)

    # Validate access
    if current_user.type != UserTypeEnum.SYSTEM_ADMIN:
        if config.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this configuration"
            )

    # Get effective configuration
    service = ScenarioBranchingService(db)
    try:
        effective = service.get_effective_config(config_id)
        return effective
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting effective config {config_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get effective configuration: {str(e)}"
        )


@router.post("/{config_id}/update", status_code=status.HTTP_201_CREATED)
def update_scenario(
    config_id: int,
    request: ScenarioUpdateRequest,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    """
    Record a change to a scenario as a delta.

    Stores the change without immediately materializing it to the database.
    Changes are applied when computing effective configuration or when committing.

    Example usage:
        # Add a new node
        POST /api/supply-chain-configs/2/update
        {
          "entity_type": "node",
          "operation": "create",
          "delta_data": {"name": "Case Manufacturer", "type": "MANUFACTURER", ...},
          "description": "Add Case Manufacturer node"
        }

        # Update existing node
        POST /api/supply-chain-configs/2/update
        {
          "entity_type": "node",
          "operation": "update",
          "entity_id": 5,
          "delta_data": {"name": "Updated Name"},
          "description": "Rename node"
        }

        # Delete node
        POST /api/supply-chain-configs/2/update
        {
          "entity_type": "node",
          "operation": "delete",
          "entity_id": 5,
          "delta_data": {},
          "description": "Remove obsolete node"
        }

    Args:
        config_id: Configuration to update
        request: Update request with delta information

    Returns:
        Created ConfigDelta record

    Raises:
        404: Configuration not found
        403: Not authorized
        400: Invalid operation or data
    """
    from app.services.scenario_branching_service import ScenarioBranchingService

    # Get config
    config = get_config_or_404(db, config_id)

    # Validate access
    if current_user.type != UserTypeEnum.SYSTEM_ADMIN:
        if config.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this configuration"
            )

    # Record delta
    service = ScenarioBranchingService(db)
    try:
        delta = service.update_scenario(
            config_id=config_id,
            entity_type=request.entity_type,
            operation=request.operation,
            delta_data=request.delta_data,
            entity_id=request.entity_id,
            created_by=current_user.id,
            description=request.description,
        )
        return {
            "id": delta.id,
            "config_id": delta.config_id,
            "entity_type": delta.entity_type,
            "entity_id": delta.entity_id,
            "operation": delta.operation,
            "created_at": delta.created_at.isoformat() if delta.created_at else None,
            "message": "Delta recorded successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating scenario {config_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update scenario: {str(e)}"
        )


@router.post("/{config_id}/commit")
def commit_scenario(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    """
    Commit a working scenario to its baseline.

    Materializes all deltas into the parent configuration and marks the
    scenario as committed. For WORKING scenarios that branch from BASELINE,
    this promotes changes to the baseline.

    Example:
        Case TBG (working) → TBG Root (baseline)
        - All deltas from Case TBG applied to TBG Root
        - Case TBG marked as committed and deactivated

    Args:
        config_id: Working scenario to commit

    Returns:
        Updated parent configuration

    Raises:
        404: Configuration not found
        403: Not authorized
        400: Invalid scenario type (only WORKING can be committed)
    """
    from app.services.scenario_branching_service import ScenarioBranchingService

    # Get config
    config = get_config_or_404(db, config_id)

    # Validate access
    if current_user.type != UserTypeEnum.SYSTEM_ADMIN:
        if config.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to commit this configuration"
            )

    # Commit scenario
    service = ScenarioBranchingService(db)
    try:
        parent = service.commit_scenario(config_id, committed_by=current_user.id)
        return {
            "parent_id": parent.id,
            "parent_name": parent.name,
            "committed_scenario_id": config_id,
            "committed_scenario_name": config.name,
            "committed_at": config.committed_at.isoformat() if config.committed_at else None,
            "message": f"Successfully committed '{config.name}' to '{parent.name}'"
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error committing scenario {config_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to commit scenario: {str(e)}"
        )


@router.post("/{config_id}/rollback")
def rollback_scenario(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    """
    Rollback all changes to a scenario (delete all deltas).

    Discards all uncommitted changes and returns the scenario to its
    parent's state. This operation is irreversible.

    Args:
        config_id: Scenario to rollback

    Returns:
        Success message

    Raises:
        404: Configuration not found
        403: Not authorized
        400: Cannot rollback BASELINE scenarios
    """
    from app.services.scenario_branching_service import ScenarioBranchingService

    # Get config
    config = get_config_or_404(db, config_id)

    # Validate access
    if current_user.type != UserTypeEnum.SYSTEM_ADMIN:
        if config.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to rollback this configuration"
            )

    # Rollback scenario
    service = ScenarioBranchingService(db)
    try:
        service.rollback_scenario(config_id)
        return {
            "config_id": config_id,
            "config_name": config.name,
            "message": f"Successfully rolled back all changes to '{config.name}'"
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error rolling back scenario {config_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback scenario: {str(e)}"
        )


@router.get("/{config_id}/diff/{other_config_id}")
def diff_scenarios(
    config_id: int,
    other_config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    """
    Compare two configurations and return differences.

    Returns entities that were added, removed, or modified between
    the two configurations.

    Args:
        config_id: First configuration (baseline)
        other_config_id: Second configuration (comparison)

    Returns:
        Dictionary with:
        - added: Entities in other but not in config
        - removed: Entities in config but not in other
        - modified: Entities in both but with different values

    Raises:
        404: One or both configurations not found
        403: Not authorized
    """
    from app.services.scenario_branching_service import ScenarioBranchingService

    # Get configs
    config = get_config_or_404(db, config_id)
    other_config = get_config_or_404(db, other_config_id)

    # Validate access
    if current_user.type != UserTypeEnum.SYSTEM_ADMIN:
        if config.tenant_id != current_user.tenant_id or other_config.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to compare these configurations"
            )

    # Diff scenarios
    service = ScenarioBranchingService(db)
    try:
        diff = service.diff_scenarios(config_id, other_config_id)
        return {
            "config_a": {"id": config_id, "name": config.name},
            "config_b": {"id": other_config_id, "name": other_config.name},
            "diff": diff
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error diffing scenarios {config_id} and {other_config_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to diff scenarios: {str(e)}"
        )


@router.get("/{config_id}/tree")
def get_scenario_tree(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user),
):
    """
    Get the scenario tree (lineage) for a configuration.

    Returns the configuration's ancestors and descendants, forming
    a tree structure suitable for visualization.

    Args:
        config_id: Root configuration for tree

    Returns:
        Tree structure with:
        - config: Root configuration
        - ancestors: List of ancestors (parent, grandparent, ...)
        - children: List of direct children
        - descendants: All descendants (recursive)

    Raises:
        404: Configuration not found
        403: Not authorized
    """
    from app.models.supply_chain_config import ConfigLineage

    # Get config
    config = get_config_or_404(db, config_id)

    # Validate access
    if current_user.type != UserTypeEnum.SYSTEM_ADMIN:
        if config.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this configuration tree"
            )

    # Get ancestors
    ancestors = (
        db.query(ConfigLineage)
        .filter(ConfigLineage.config_id == config_id)
        .filter(ConfigLineage.depth > 0)
        .order_by(ConfigLineage.depth)
        .all()
    )
    ancestor_ids = [a.ancestor_id for a in ancestors]
    ancestor_configs = db.query(SupplyChainConfig).filter(SupplyChainConfig.id.in_(ancestor_ids)).all() if ancestor_ids else []

    # Get direct children
    children = db.query(SupplyChainConfig).filter(SupplyChainConfig.parent_config_id == config_id).all()

    return {
        "config": {
            "id": config.id,
            "name": config.name,
            "description": config.description,
            "scenario_type": config.scenario_type,
            "parent_config_id": config.parent_config_id,
            "base_config_id": config.base_config_id,
            "branched_at": config.branched_at.isoformat() if config.branched_at else None,
            "committed_at": config.committed_at.isoformat() if config.committed_at else None,
        },
        "ancestors": [
            {
                "id": a.id,
                "name": a.name,
                "scenario_type": a.scenario_type,
            }
            for a in ancestor_configs
        ],
        "children": [
            {
                "id": c.id,
                "name": c.name,
                "scenario_type": c.scenario_type,
                "branched_at": c.branched_at.isoformat() if c.branched_at else None,
            }
            for c in children
        ],
    }


# =============================================================================
# Decision Proposal Endpoints
# =============================================================================


class DecisionProposalRequest(BaseModel):
    """Request body for creating a decision proposal"""
    title: str
    description: Optional[str] = None
    action_type: str  # 'expedite', 'increase_safety_stock', 'add_supplier', etc.
    action_params: Dict[str, Any]  # Action-specific parameters
    proposed_by: str  # User ID or Agent ID
    proposed_by_type: str = "human"  # 'human' or 'agent'
    authority_level_required: Optional[str] = None
    requires_approval_from: Optional[str] = None


class ComputeImpactRequest(BaseModel):
    """Request body for computing business impact"""
    planning_horizon: int = 52
    simulation_runs: int = 1000


class ApprovalRequest(BaseModel):
    """Request body for approving a proposal"""
    approved_by: str
    commit_to_parent: bool = True


class RejectionRequest(BaseModel):
    """Request body for rejecting a proposal"""
    rejected_by: str
    reason: str
    delete_scenario: bool = True


@router.post("/{config_id}/proposals", status_code=201)
def create_decision_proposal(
    config_id: int,
    request: DecisionProposalRequest,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Create a decision proposal from a scenario.

    Creates a proposal linked to a child scenario for simulating business impact
    of proposed changes. The proposal enters 'pending' status awaiting approval.

    Use Cases:
    - Strategic: Network redesign, acquisition scenarios
    - Tactical: Safety stock adjustments, sourcing changes
    - Operational: Expedite requests, emergency purchases

    Returns:
        Created decision proposal with ID and status
    """
    from app.models.supply_chain_config import DecisionProposal
    from app.services.scenario_branching_service import ScenarioBranchingService

    # Verify config exists
    config = get_config_or_404(db, config_id)

    # Create proposal
    proposal = DecisionProposal(
        scenario_id=config_id,
        parent_scenario_id=config.parent_config_id,
        title=request.title,
        description=request.description,
        action_type=request.action_type,
        action_params=request.action_params,
        proposed_by=request.proposed_by,
        proposed_by_type=request.proposed_by_type,
        authority_level_required=request.authority_level_required,
        requires_approval_from=request.requires_approval_from,
        status="pending",
    )

    db.add(proposal)
    db.commit()
    db.refresh(proposal)

    return {
        "id": proposal.id,
        "scenario_id": proposal.scenario_id,
        "status": proposal.status,
        "message": f"Decision proposal '{proposal.title}' created successfully",
    }


@router.get("/{config_id}/proposals")
def list_decision_proposals(
    config_id: int,
    status: Optional[str] = None,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    List decision proposals for a scenario.

    Args:
        config_id: Scenario ID
        status: Optional status filter ('pending', 'approved', 'rejected', 'executed')

    Returns:
        List of decision proposals with metadata
    """
    from app.models.supply_chain_config import DecisionProposal

    # Verify config exists
    config = get_config_or_404(db, config_id)

    # Query proposals
    query = db.query(DecisionProposal).filter(
        or_(
            DecisionProposal.scenario_id == config_id,
            DecisionProposal.parent_scenario_id == config_id,
        )
    )

    if status:
        query = query.filter(DecisionProposal.status == status)

    proposals = query.order_by(DecisionProposal.created_at.desc()).all()

    return {
        "proposals": [
            {
                "id": p.id,
                "title": p.title,
                "action_type": p.action_type,
                "status": p.status,
                "proposed_by": p.proposed_by,
                "proposed_by_type": p.proposed_by_type,
                "created_at": p.created_at.isoformat(),
                "approved_at": p.approved_at.isoformat() if p.approved_at else None,
            }
            for p in proposals
        ]
    }


@router.get("/proposals/{proposal_id}")
def get_decision_proposal(
    proposal_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Get decision proposal details including business case.

    Returns:
        Full proposal details with computed business impact metrics
    """
    from app.models.supply_chain_config import DecisionProposal

    proposal = db.query(DecisionProposal).filter_by(id=proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")

    return {
        "id": proposal.id,
        "scenario_id": proposal.scenario_id,
        "parent_scenario_id": proposal.parent_scenario_id,
        "title": proposal.title,
        "description": proposal.description,
        "action_type": proposal.action_type,
        "action_params": proposal.action_params,
        "proposed_by": proposal.proposed_by,
        "proposed_by_type": proposal.proposed_by_type,
        "status": proposal.status,
        "business_case": proposal.business_case,
        "financial_impact": proposal.financial_impact,
        "operational_impact": proposal.operational_impact,
        "strategic_impact": proposal.strategic_impact,
        "risk_metrics": proposal.risk_metrics,
        "created_at": proposal.created_at.isoformat(),
        "approved_at": proposal.approved_at.isoformat() if proposal.approved_at else None,
        "approved_by": proposal.approved_by,
        "rejection_reason": proposal.rejection_reason,
    }


@router.post("/proposals/{proposal_id}/compute-impact")
def compute_proposal_impact(
    proposal_id: int,
    request: ComputeImpactRequest,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Compute business impact for a decision proposal.

    Runs probabilistic simulation comparing parent scenario (baseline)
    vs child scenario (with proposed changes) and computes balanced scorecard metrics.

    Args:
        proposal_id: Decision proposal ID
        request: Simulation parameters (horizon, runs)

    Returns:
        Computed business impact with P10/P50/P90 distributions
    """
    from app.services.business_impact_service import BusinessImpactService

    service = BusinessImpactService(db)

    try:
        result = service.compute_business_impact(
            proposal_id=proposal_id,
            planning_horizon=request.planning_horizon,
            simulation_runs=request.simulation_runs,
        )

        return {
            "proposal_id": proposal_id,
            "status": "completed",
            "business_case": result["business_case"],
            "parent_metrics": result["parent_metrics"],
            "child_metrics": result["child_metrics"],
            "delta_metrics": result["delta_metrics"],
            "improvement_probability": result["improvement_probability"],
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute business impact: {str(e)}",
        )


@router.post("/proposals/{proposal_id}/approve")
def approve_decision_proposal(
    proposal_id: int,
    request: ApprovalRequest,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Approve a decision proposal.

    Approves the proposal and optionally commits the child scenario to parent.
    This executes the proposed changes and updates the baseline configuration.

    Args:
        proposal_id: Decision proposal ID
        request: Approval details (approver, commit flag)

    Returns:
        Approval confirmation with updated parent config ID
    """
    from app.services.business_impact_service import BusinessImpactService

    service = BusinessImpactService(db)

    try:
        parent_config = service.approve_proposal(
            proposal_id=proposal_id,
            approved_by=request.approved_by,
            commit_to_parent=request.commit_to_parent,
        )

        return {
            "proposal_id": proposal_id,
            "status": "approved",
            "parent_config_id": parent_config.id if parent_config else None,
            "message": "Proposal approved successfully",
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to approve proposal: {str(e)}",
        )


@router.post("/proposals/{proposal_id}/reject")
def reject_decision_proposal(
    proposal_id: int,
    request: RejectionRequest,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Reject a decision proposal.

    Rejects the proposal and optionally deletes the child scenario.
    Preserves audit trail of rejected proposals.

    Args:
        proposal_id: Decision proposal ID
        request: Rejection details (rejecter, reason, delete flag)

    Returns:
        Rejection confirmation
    """
    from app.services.business_impact_service import BusinessImpactService

    service = BusinessImpactService(db)

    try:
        service.reject_proposal(
            proposal_id=proposal_id,
            rejected_by=request.rejected_by,
            reason=request.reason,
            delete_scenario=request.delete_scenario,
        )

        return {
            "proposal_id": proposal_id,
            "status": "rejected",
            "message": "Proposal rejected successfully",
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reject proposal: {str(e)}",
        )


# --- Config Lineage Endpoints ---


class ConfigLineageResponse(BaseModel):
    """Response model for config lineage."""
    config_id: int
    config_name: str
    ancestor_id: int
    ancestor_name: str
    depth: int


class ConfigTreeNode(BaseModel):
    """Tree node representation of a config in the lineage."""
    id: int
    name: str
    description: Optional[str] = None
    parent_config_id: Optional[int] = None
    base_config_id: Optional[int] = None
    scenario_type: Optional[str] = None
    depth: int = 0
    children: List["ConfigTreeNode"] = []


ConfigTreeNode.model_rebuild()  # For recursive reference


@router.get("/{config_id}/lineage", response_model=List[ConfigLineageResponse])
def get_config_lineage(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> List[ConfigLineageResponse]:
    """Get the complete lineage (ancestry tree) for a configuration.

    Returns all ancestors of the config ordered by depth (0=self, 1=parent, 2=grandparent, etc.)
    """
    config = crud.supply_chain_config.get(db, id=config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    _ensure_user_can_view_config(db, current_user, config)

    lineage_entries = (
        db.query(ConfigLineage)
        .filter(ConfigLineage.config_id == config_id)
        .order_by(ConfigLineage.depth)
        .all()
    )

    result = []
    for entry in lineage_entries:
        ancestor = crud.supply_chain_config.get(db, id=entry.ancestor_id)
        result.append(ConfigLineageResponse(
            config_id=entry.config_id,
            config_name=config.name,
            ancestor_id=entry.ancestor_id,
            ancestor_name=ancestor.name if ancestor else "Unknown",
            depth=entry.depth,
        ))

    return result


@router.get("/{config_id}/children", response_model=List[schemas.SupplyChainConfig])
def get_config_children(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> List[SupplyChainConfig]:
    """Get all direct children of a configuration.

    Returns configs that have this config as their parent_config_id.
    """
    config = crud.supply_chain_config.get(db, id=config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    _ensure_user_can_view_config(db, current_user, config)

    children = (
        db.query(SupplyChainConfig)
        .filter(SupplyChainConfig.parent_config_id == config_id)
        .all()
    )

    return children


@router.get("/{config_id}/tree", response_model=ConfigTreeNode)
def get_config_tree(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> ConfigTreeNode:
    """Get the full tree structure starting from a configuration.

    Returns the config and all its descendants as a nested tree structure.
    """
    config = crud.supply_chain_config.get(db, id=config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    _ensure_user_can_view_config(db, current_user, config)

    def build_tree(cfg: SupplyChainConfig, depth: int = 0) -> ConfigTreeNode:
        children = (
            db.query(SupplyChainConfig)
            .filter(SupplyChainConfig.parent_config_id == cfg.id)
            .all()
        )
        return ConfigTreeNode(
            id=cfg.id,
            name=cfg.name,
            description=cfg.description,
            parent_config_id=cfg.parent_config_id,
            base_config_id=cfg.base_config_id,
            scenario_type=cfg.scenario_type,
            depth=depth,
            children=[build_tree(child, depth + 1) for child in children],
        )

    return build_tree(config)


@router.get("/tenant/{tenant_id}/root", response_model=Optional[schemas.SupplyChainConfig])
def get_tenant_root_config(
    tenant_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Optional[SupplyChainConfig]:
    """Get the root configuration for a tenant.

    Returns the config that has no parent_config_id (the root of the lineage tree).
    """
    user_type = getattr(current_user, "user_type", None)
    if user_type != UserTypeEnum.SYSTEM_ADMIN:
        admin_tenant_id = _get_user_admin_tenant_id(db, current_user)
        user_tenant_id = getattr(current_user, "tenant_id", None)
        if admin_tenant_id != tenant_id and user_tenant_id != tenant_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this tenant's configurations"
            )

    root_config = (
        db.query(SupplyChainConfig)
        .filter(
            SupplyChainConfig.tenant_id == tenant_id,
            SupplyChainConfig.parent_config_id.is_(None),
        )
        .first()
    )

    return root_config


@router.get("/tenant/{tenant_id}/tree", response_model=List[ConfigTreeNode])
def get_tenant_config_tree(
    tenant_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> List[ConfigTreeNode]:
    """Get the full config tree for a tenant.

    Returns all root configs (configs with no parent) and their descendants.
    """
    user_type = getattr(current_user, "user_type", None)
    if user_type != UserTypeEnum.SYSTEM_ADMIN:
        admin_tenant_id = _get_user_admin_tenant_id(db, current_user)
        user_tenant_id = getattr(current_user, "tenant_id", None)
        if admin_tenant_id != tenant_id and user_tenant_id != tenant_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this tenant's configurations"
            )

    # Get all root configs (no parent)
    root_configs = (
        db.query(SupplyChainConfig)
        .filter(
            SupplyChainConfig.tenant_id == tenant_id,
            SupplyChainConfig.parent_config_id.is_(None),
        )
        .all()
    )

    def build_tree(cfg: SupplyChainConfig, depth: int = 0) -> ConfigTreeNode:
        children = (
            db.query(SupplyChainConfig)
            .filter(SupplyChainConfig.parent_config_id == cfg.id)
            .all()
        )
        return ConfigTreeNode(
            id=cfg.id,
            name=cfg.name,
            description=cfg.description,
            parent_config_id=cfg.parent_config_id,
            base_config_id=cfg.base_config_id,
            scenario_type=cfg.scenario_type,
            depth=depth,
            children=[build_tree(child, depth + 1) for child in children],
        )

    return [build_tree(root) for root in root_configs]
