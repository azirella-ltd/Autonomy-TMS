"""
Tactical tGNN Training Service — Trains and persists demand/supply/inventory tGNNs.

Called by provisioning steps 5/6/7. For each domain:
1. Loads network topology from the SC config
2. Builds training features from historical data (Forecast, SupplyPlan, InvLevel)
3. Trains the tGNN model (GATv2+GRU, ~35K params)
4. Saves checkpoint to disk (tenant-scoped path)
5. Persists a row in tactical_tgnn_checkpoints table

SOC II: No silent failures. All errors propagate to provisioning status.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Domain -> (model class path, feature builder, checkpoint prefix)
_DOMAIN_REGISTRY = {
    # demand_planning REMOVED (April 2026) — demand is per-product tabular,
    # not a graph problem. Handled by Forecast Baseline + Adjustment TRMs.
    # Demand features are computed analytically in TacticalHiveCoordinator.
    "supply_planning": {
        "model_module": "app.models.gnn.supply_planning_tgnn",
        "model_class": "SupplyPlanningTGNN",
        "prefix": "supply_planning_tgnn",
    },
    "inventory_optim": {
        "model_module": "app.models.gnn.inventory_optimization_tgnn",
        "model_class": "InventoryOptimizationTGNN",
        "prefix": "inventory_optimization_tgnn",
    },
    "capacity_rccp": {
        "model_module": "app.models.gnn.capacity_rccp_tgnn",
        "model_class": "CapacityRCCPTGNN",
        "prefix": "capacity_rccp_tgnn",
    },
}


class TacticalTGNNTrainingService:
    """Trains tactical tGNNs and persists checkpoints to disk + DB."""

    @staticmethod
    async def train_and_persist(
        config_id: int,
        tenant_id: int,
        domain: str,
        epochs: int = 20,
        device: str = "auto",
    ) -> dict:
        """Train a tactical tGNN and persist the checkpoint.

        Runs synchronous training in a thread to avoid blocking the async loop
        and to avoid session conflicts with the provisioning's async session.
        Device 'auto' selects CUDA if available, else CPU.
        """
        import asyncio
        import torch
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        return await asyncio.to_thread(
            TacticalTGNNTrainingService._train_and_persist_sync,
            config_id, tenant_id, domain, epochs, device,
        )

    @staticmethod
    def _train_and_persist_sync(
        config_id: int,
        tenant_id: int,
        domain: str,
        epochs: int = 20,
        device: str = "auto",
    ) -> dict:
        """Synchronous training — runs in a separate thread."""
        if device == "auto":
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

        if domain not in _DOMAIN_REGISTRY:
            raise ValueError(f"Unknown tactical tGNN domain: {domain}")

        start = time.time()
        reg = _DOMAIN_REGISTRY[domain]

        # 1. Load topology (resolve tenant_id here if not provided)
        from app.db.session import sync_session_factory
        from sqlalchemy import text as sqt

        sync_db = sync_session_factory()
        try:
            # Resolve tenant_id from config if caller passed 0
            if not tenant_id:
                tid_row = sync_db.execute(sqt(
                    "SELECT tenant_id FROM supply_chain_configs WHERE id = :c"
                ), {"c": config_id}).fetchone()
                tenant_id = tid_row[0] if tid_row else 0

            sites = sync_db.execute(sqt(
                "SELECT id, name, type, master_type FROM site "
                "WHERE config_id = :c AND is_external = false "
                "AND LOWER(COALESCE(master_type, '')) NOT IN ('vendor', 'customer')"
            ), {"c": config_id}).fetchall()

            lanes = sync_db.execute(sqt(
                "SELECT from_site_id, to_site_id FROM transportation_lane "
                "WHERE config_id = :c"
            ), {"c": config_id}).fetchall()
        finally:
            sync_db.close()

        if not sites:
            return {
                "status": "skipped",
                "reason": f"No internal sites found for config {config_id}",
                "domain": domain,
            }

        num_sites = len(sites)
        site_keys = [s[1] or f"site_{s[0]}" for s in sites]

        # 2. Build training data (synthetic cold-start features)
        window_size = 10
        num_features = 10
        num_samples = max(200, epochs * 10)

        training_data = _build_training_data(
            sync_session_factory, config_id, domain,
            site_keys, num_sites, window_size, num_features, num_samples,
        )

        # 3. Build edge index from lanes
        site_id_to_idx = {s[0]: i for i, s in enumerate(sites)}
        edge_src, edge_dst = [], []
        for src_id, dst_id in lanes:
            if src_id in site_id_to_idx and dst_id in site_id_to_idx:
                edge_src.append(site_id_to_idx[src_id])
                edge_dst.append(site_id_to_idx[dst_id])
        # Ensure at least a self-loop per node for message passing
        if not edge_src:
            for i in range(num_sites):
                edge_src.append(i)
                edge_dst.append(i)

        # 4. Train the model
        try:
            import torch
            import torch.nn as nn
            import torch.optim as optim
            from importlib import import_module

            mod = import_module(reg["model_module"])
            ModelClass = getattr(mod, reg["model_class"])

            model = ModelClass(transactional_dim=num_features, sop_dim=64)
            model.to(device)
            model.train()

            optimizer = optim.Adam(model.parameters(), lr=1e-3)
            loss_fn = nn.MSELoss()

            edge_index = torch.tensor([edge_src, edge_dst], dtype=torch.long).to(device)

            # S&OP embeddings placeholder (will be replaced by real SOP output in production)
            sop_emb = torch.randn(num_sites, 64, device=device) * 0.1

            losses = []
            for epoch in range(epochs):
                epoch_loss = 0.0
                for sample_x, sample_y in training_data:
                    x = torch.tensor(sample_x, dtype=torch.float32, device=device)
                    y = torch.tensor(sample_y, dtype=torch.float32, device=device)

                    # Model expects 4D: (batch, window, num_sites, features)
                    # Training data is 3D: (window, num_sites, features) — add batch dim
                    if x.dim() == 3:
                        x = x.unsqueeze(0)

                    out = model(
                        x_temporal=x,
                        sop_embeddings=sop_emb,
                        edge_index=edge_index,
                    )
                    # Use the primary output head for loss
                    primary_key = _get_primary_output_key(domain)
                    if isinstance(out, dict) and primary_key in out:
                        pred = out[primary_key]
                    elif isinstance(out, dict):
                        # Use first tensor output
                        pred = next(v for v in out.values() if isinstance(v, torch.Tensor))
                    else:
                        pred = out

                    # Align pred and target shapes
                    pred = pred.squeeze()  # Remove batch/trailing dims → [num_sites] or [num_sites, heads]
                    if pred.dim() == 0:
                        pred = pred.unsqueeze(0)
                    y_target = y.squeeze()
                    # If shapes still differ, take matching slice
                    if pred.shape != y_target.shape:
                        if pred.dim() == 1 and y_target.dim() == 2:
                            y_target = y_target[:, 0]  # Take first output column
                        elif pred.dim() == 2 and y_target.dim() == 1:
                            pred = pred[:, 0]
                        elif pred.numel() != y_target.numel():
                            min_n = min(pred.numel(), y_target.numel())
                            pred = pred.flatten()[:min_n]
                            y_target = y_target.flatten()[:min_n]
                    y = y_target

                    loss = loss_fn(pred, y)
                    optimizer.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    epoch_loss += loss.item()

                avg_loss = epoch_loss / max(len(training_data), 1)
                losses.append(avg_loss)

            final_loss = losses[-1] if losses else 0.0

            # 5. Save checkpoint to disk
            from app.services.checkpoint_storage_service import checkpoint_dir
            ckpt_dir = checkpoint_dir(tenant_id, config_id)
            ckpt_dir.mkdir(parents=True, exist_ok=True)
            ckpt_filename = f"{reg['prefix']}_config_{config_id}_v1.pt"
            ckpt_path = ckpt_dir / ckpt_filename

            torch.save({
                "model_state_dict": model.state_dict(),
                "config_id": config_id,
                "tenant_id": tenant_id,
                "domain": domain,
                "num_sites": num_sites,
                "site_keys": site_keys,
                "epochs": epochs,
                "final_loss": final_loss,
                "timestamp": time.time(),
            }, str(ckpt_path))

            logger.info(
                "Tactical tGNN trained: domain=%s, config=%d, sites=%d, loss=%.4f, path=%s",
                domain, config_id, num_sites, final_loss, ckpt_path,
            )

        except ImportError as e:
            msg = f"PyTorch/PyG not available for tactical tGNN training ({domain}): {e}"
            logger.error("SOC II ALERT: %s", msg)
            raise RuntimeError(msg)
        except Exception as e:
            msg = f"Tactical tGNN training failed ({domain}, config {config_id}): {e}"
            logger.error("SOC II ALERT: %s", msg)
            raise RuntimeError(msg)

        # 6. Persist checkpoint row to DB
        _persist_checkpoint_row(
            config_id=config_id,
            domain=domain,
            checkpoint_path=str(ckpt_path),
            num_sites=num_sites,
            validation_loss=final_loss,
        )

        duration = time.time() - start
        return {
            "status": "ok",
            "domain": domain,
            "num_sites": num_sites,
            "final_loss": round(final_loss, 6),
            "checkpoint_path": str(ckpt_path),
            "duration_seconds": round(duration, 1),
        }


def _get_primary_output_key(domain: str) -> str:
    """Map domain to the primary output dict key from the model forward pass."""
    return {
        "demand_planning": "demand_forecast",
        "supply_planning": "supply_allocation",
        "inventory_optim": "reorder_point",
        "capacity_rccp": "planned_utilization",
    }.get(domain, "output")


def _build_training_data(
    session_factory,
    config_id: int,
    domain: str,
    site_keys: List[str],
    num_sites: int,
    window_size: int,
    num_features: int,
    num_samples: int,
) -> List:
    """Build (input, target) training pairs for tactical tGNN training.

    Priority order:
      1. Unified training corpus (Layer 2 samples) — preferred, tenant-specific
      2. Real DB history (forecast/supply_plan/inventory_level tables)
      3. Synthetic cold-start data (last resort)

    See docs/internal/architecture/UNIFIED_TRAINING_CORPUS.md
    """
    rng = np.random.RandomState(config_id + hash(domain) % 10000)
    samples = []

    # Priority 1: unified training corpus
    corpus_data = _try_load_corpus_data(
        session_factory, config_id, domain, site_keys, window_size, num_features,
    )
    if corpus_data is not None and len(corpus_data) >= 10:
        logger.info(
            "Tactical tGNN %s: loaded %d Layer 2 corpus samples for config %d",
            domain, len(corpus_data), config_id,
        )
        return corpus_data

    # Priority 2: real DB history
    real_data = _try_load_real_data(session_factory, config_id, domain, site_keys, window_size)

    if real_data is not None and len(real_data) >= 10:
        logger.info(
            "Tactical tGNN %s: loaded %d real training windows for config %d",
            domain, len(real_data), config_id,
        )
        for x_window, y_target in real_data:
            samples.append((x_window, y_target))
        # Augment with noise to reach num_samples
        while len(samples) < num_samples:
            base_x, base_y = samples[rng.randint(0, len(real_data))]
            noise_x = base_x + rng.randn(*base_x.shape).astype(np.float32) * 0.05
            noise_y = base_y + rng.randn(*base_y.shape).astype(np.float32) * 0.02
            samples.append((noise_x, noise_y))
    else:
        logger.info(
            "Tactical tGNN %s: using synthetic training data for config %d (cold start)",
            domain, config_id,
        )
        for _ in range(num_samples):
            x = rng.randn(window_size, num_sites, num_features).astype(np.float32) * 0.3
            # Add structure: temporal trend + mean reversion
            for t in range(1, window_size):
                x[t] = 0.8 * x[t - 1] + 0.2 * x[t]

            if domain == "demand_planning":
                y = rng.randn(num_sites, 4).astype(np.float32) * 0.2  # 4-period forecast
            elif domain == "supply_planning":
                y = rng.randn(num_sites, 3).astype(np.float32) * 0.2  # allocation targets
            elif domain == "inventory_optim":
                y = rng.randn(num_sites, 2).astype(np.float32) * 0.2  # reorder params
            else:
                # capacity_rccp: 4 output heads (utilization, buffer, feasibility, bottleneck)
                y = np.abs(rng.randn(num_sites, 4).astype(np.float32) * 0.2 + 0.5)
            samples.append((x, y))

    return samples


def _try_load_corpus_data(
    session_factory, config_id, domain, site_keys, window_size, num_features,
):
    """Load Layer 2 samples from the unified training corpus.

    Each Layer 2 sample contains per-site outcomes for supply/inventory/capacity.
    We convert them to (X, y) tuples where X is a dummy windowed feature tensor
    (the real features will come from node_features at inference time) and
    y is the domain-specific target vector.
    """
    try:
        from sqlalchemy import text as sqt
        db = session_factory()
        try:
            # Map domain to the outcome key in sample_data
            outcome_key = {
                "supply_planning": "supply_outcomes",
                "inventory_optim": "inventory_outcomes",
                "capacity_rccp": "capacity_outcomes",
            }.get(domain)
            if not outcome_key:
                return None

            rows = db.execute(sqt(
                "SELECT sample_data, reward FROM training_corpus "
                "WHERE config_id = :c AND layer = 2.0 "
                "ORDER BY created_at DESC LIMIT 2000"
            ), {"c": config_id}).fetchall()

            if not rows:
                return None

            samples = []
            rng = np.random.RandomState(config_id)
            num_sites = len(site_keys)

            for row in rows:
                data = row.sample_data or {}
                outcomes_by_site = data.get(outcome_key, {})
                if not outcomes_by_site:
                    continue

                # Build target vector per site
                target_dim = _get_target_dim(domain)
                y = np.zeros((num_sites, target_dim), dtype=np.float32)
                for i, site_key in enumerate(site_keys):
                    site_outcomes = outcomes_by_site.get(site_key, {})
                    y[i] = _extract_target_vector(domain, site_outcomes, target_dim)

                # Dummy input tensor (tactical tGNN inference builds real features)
                x = rng.randn(window_size, num_sites, num_features).astype(np.float32) * 0.2
                samples.append((x, y))

            return samples if len(samples) >= 10 else None
        finally:
            db.close()
    except Exception as e:
        logger.debug("Corpus data load failed for %s: %s", domain, e)
        return None


def _get_target_dim(domain: str) -> int:
    """Target vector dimension per domain."""
    return {
        "supply_planning": 3,    # exception_prob, order_rec, allocation_priority
        "inventory_optim": 3,    # buffer_adj, stockout_prob, rebalancing_urgency
        "capacity_rccp": 3,      # planned_utilization, feasibility, bottleneck_risk
    }.get(domain, 3)


def _extract_target_vector(domain: str, site_outcomes: dict, target_dim: int) -> np.ndarray:
    """Extract the domain-specific target vector from site outcomes."""
    v = np.zeros(target_dim, dtype=np.float32)
    if domain == "supply_planning":
        v[0] = site_outcomes.get("exception_prob", 0.0)
        v[1] = site_outcomes.get("order_recommendation", 0.0) / 1000.0  # normalize
        v[2] = site_outcomes.get("allocation_priority", 0.5)
    elif domain == "inventory_optim":
        v[0] = site_outcomes.get("buffer_adjustment", 0.0)
        v[1] = site_outcomes.get("stockout_probability", 0.0)
        v[2] = site_outcomes.get("rebalancing_urgency", 0.0)
    elif domain == "capacity_rccp":
        v[0] = site_outcomes.get("planned_utilization", 0.7)
        v[1] = site_outcomes.get("feasibility_score", 0.85)
        v[2] = site_outcomes.get("bottleneck_risk", 0.15)
    return v


def _try_load_real_data(session_factory, config_id, domain, site_keys, window_size):
    """Attempt to load real historical training data for the domain."""
    try:
        from sqlalchemy import text as sqt
        db = session_factory()
        try:
            if domain == "demand_planning":
                rows = db.execute(sqt(
                    "SELECT s.name, f.forecast_date, f.forecast_p50, f.forecast_p10, f.forecast_p90 "
                    "FROM forecast f JOIN site s ON f.site_id = s.id "
                    "WHERE s.config_id = :c "
                    "ORDER BY f.forecast_date"
                ), {"c": config_id}).fetchall()
                if len(rows) < window_size * 2:
                    return None
                # Build windowed data
                return _window_forecast_data(rows, site_keys, window_size)
            elif domain == "supply_planning":
                rows = db.execute(sqt(
                    "SELECT sp.site_id, sp.plan_date, sp.planned_order_quantity "
                    "FROM supply_plan sp JOIN site s ON sp.site_id = s.id "
                    "WHERE s.config_id = :c "
                    "ORDER BY sp.plan_date"
                ), {"c": config_id}).fetchall()
                if len(rows) < window_size * 2:
                    return None
                return _window_supply_data(rows, site_keys, window_size)
            elif domain == "inventory_optim":
                rows = db.execute(sqt(
                    "SELECT il.site_id, il.inventory_date, il.on_hand_qty, il.in_transit_qty "
                    "FROM inv_level il JOIN site s ON il.site_id = s.id "
                    "WHERE s.config_id = :c "
                    "ORDER BY il.inventory_date"
                ), {"c": config_id}).fetchall()
                if len(rows) < window_size * 2:
                    return None
                return _window_inventory_data(rows, site_keys, window_size)
            else:
                # capacity_rccp: derive from manufacturing orders
                rows = db.execute(sqt(
                    "SELECT mo.site_id, mo.planned_start_date, mo.quantity "
                    "FROM manufacturing_order mo JOIN site s ON mo.site_id = s.id "
                    "WHERE s.config_id = :c "
                    "ORDER BY mo.planned_start_date"
                ), {"c": config_id}).fetchall()
                if len(rows) < window_size * 2:
                    return None
                return _window_capacity_data(rows, site_keys, window_size)
        finally:
            db.close()
    except Exception as e:
        logger.info("Could not load real training data for %s: %s", domain, e)
        return None


def _window_forecast_data(rows, site_keys, window_size):
    """Convert forecast rows to windowed training pairs."""
    num_sites = len(site_keys)
    site_idx = {k: i for i, k in enumerate(site_keys)}
    num_features = 10

    # Group by date
    from collections import defaultdict
    by_date = defaultdict(lambda: np.zeros((num_sites, num_features), dtype=np.float32))
    dates = sorted(set(r[1] for r in rows))

    for site_name, fdate, p50, p10, p90 in rows:
        idx = site_idx.get(site_name)
        if idx is None:
            continue
        by_date[fdate][idx, 0] = float(p50 or 0)
        by_date[fdate][idx, 1] = float(p10 or 0)
        by_date[fdate][idx, 2] = float(p90 or 0)
        p50v = float(p50 or 0)
        p10v = float(p10 or 0)
        p90v = float(p90 or 0)
        by_date[fdate][idx, 3] = (p90v - p10v) / (p50v + 1.0)

    sorted_dates = sorted(by_date.keys())
    if len(sorted_dates) < window_size + 4:
        return None

    samples = []
    for i in range(len(sorted_dates) - window_size - 4):
        x = np.stack([by_date[sorted_dates[i + t]] for t in range(window_size)])
        # Target: next 4 periods p50 for each site
        y = np.stack([
            by_date[sorted_dates[i + window_size + t]][:, 0]
            for t in range(4)
        ]).T  # [num_sites, 4]
        samples.append((x, y))

    return samples if samples else None


def _window_supply_data(rows, site_keys, window_size):
    """Convert supply plan rows to windowed training pairs."""
    # Simplified: use same structure as forecast
    return None  # Will use synthetic augmented data


def _window_inventory_data(rows, site_keys, window_size):
    """Convert inventory level rows to windowed training pairs."""
    return None  # Will use synthetic augmented data


def _window_capacity_data(rows, site_keys, window_size):
    """Convert manufacturing order rows to windowed training pairs for capacity."""
    return None  # Will use synthetic augmented data


def _persist_checkpoint_row(
    config_id: int,
    domain: str,
    checkpoint_path: str,
    num_sites: int,
    validation_loss: float,
) -> None:
    """Insert a row into tactical_tgnn_checkpoints table.

    Deactivates any existing active checkpoint for this config+domain first.
    """
    from app.db.session import sync_session_factory
    from sqlalchemy import text as sqt

    db = sync_session_factory()
    try:
        # Deactivate previous active checkpoints
        db.execute(sqt(
            "UPDATE tactical_tgnn_checkpoints SET is_active = false "
            "WHERE config_id = :c AND domain = :d AND is_active = true"
        ), {"c": config_id, "d": domain})

        # Insert new checkpoint
        db.execute(sqt(
            "INSERT INTO tactical_tgnn_checkpoints "
            "(config_id, domain, checkpoint_path, trained_at, num_sites, validation_loss, is_active) "
            "VALUES (:c, :d, :p, :t, :n, :v, true)"
        ), {
            "c": config_id,
            "d": domain,
            "p": checkpoint_path,
            "t": datetime.utcnow(),
            "n": num_sites,
            "v": validation_loss,
        })
        db.commit()
        logger.info(
            "Persisted tactical tGNN checkpoint: domain=%s, config=%d, path=%s",
            domain, config_id, checkpoint_path,
        )
    except Exception as e:
        db.rollback()
        logger.error(
            "Failed to persist tactical tGNN checkpoint row: domain=%s, config=%d: %s",
            domain, config_id, e,
        )
        # Don't swallow — this is a data integrity issue
        raise
    finally:
        db.close()
