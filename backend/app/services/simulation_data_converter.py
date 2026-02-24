"""
Simulation Data Converter

Converts DAG simulator output (SimulationResult) to training-ready formats:

1. GNN (S&OP GraphSAGE + Execution tGNN):
   - Adjacency A[2,N,N] from topology
   - Node features X[B, window, N, F]
   - Targets Y[B, N, H] from ordering decisions
   - Saves as NPZ

2. TRM (11 Engine-TRM pairs):
   - Per-decision training records (state, action, reward, next_state)
   - Grouped by TRM type:
     atp, order (PO), rebalance, exception, transfer_order, mo_execution,
     quality, maintenance, subcontracting, forecast_adjustment, safety_stock
   - Inserts into powell_site_agent_decisions for CDC feedback loop

Generalised to N-node topologies (not hardcoded to 4-node simulation).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import logging
import json

import numpy as np

logger = logging.getLogger(__name__)


# ── TRM type mapping ──

TRM_TYPE_MAP = {
    "atp": "atp_executor",
    "order": "po_creation",
    "rebalance": "inventory_rebalancing",
    "exception": "order_tracking",
    "transfer_order": "to_execution",
    "mo_execution": "mo_execution",
    "quality": "quality_disposition",
    "maintenance": "maintenance_scheduling",
    "subcontracting": "subcontracting",
    "forecast_adjustment": "forecast_adjustment",
    "safety_stock": "safety_stock",
}

# Feature dimensions for GNN node features
GNN_FEATURES = [
    "on_hand",
    "backlog",
    "demand",
    "fulfilled",
    "in_transit",
    "safety_stock",
    "target_inventory",
    "order_placed",
    # Node type one-hot (4 master types)
    "is_supply",
    "is_demand",
    "is_inventory",
    "is_manufacturer",
    # Positional
    "topo_position",       # 0..1 normalised position in topo order
    "num_downstream",
]
NUM_GNN_FEATURES = len(GNN_FEATURES)

# State vector dimensions for TRM training
TRM_STATE_FEATURES = [
    "on_hand",
    "backlog",
    "in_transit",
    "safety_stock",
    "target_inventory",
    "demand_recent_avg",
    "demand_recent_std",
    "order_recent_avg",
    "fill_rate_recent",
    "dos",
    "inventory_position",
    # Decision-specific context (padded if absent)
    "ctx_0", "ctx_1", "ctx_2", "ctx_3", "ctx_4",
]
NUM_TRM_STATE = len(TRM_STATE_FEATURES)


# ── Data structures ──

@dataclass
class TrainingRecord:
    """Single training experience for TRM."""
    trm_type: str
    site_key: str
    product_id: str
    period: int
    state_features: np.ndarray   # [NUM_TRM_STATE]
    action: float                # Quantity or action index
    reward: float = 0.0
    next_state_features: Optional[np.ndarray] = None
    done: bool = False
    expert_action: Optional[float] = None
    confidence: float = 1.0
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversionResult:
    """Output of a full simulation → training data conversion."""
    # GNN arrays
    X: np.ndarray              # [B, T, N, F]
    A: np.ndarray              # [2, N, N]
    Y: np.ndarray              # [B, N, H]
    P: np.ndarray              # [B, 0] placeholder
    site_names: List[str]      # Ordered site names (index → name)
    product_ids: List[str]     # Ordered product IDs

    # TRM records grouped by type
    trm_records: Dict[str, List[TrainingRecord]]

    # Metadata
    num_samples: int
    num_sites: int
    num_products: int
    num_periods: int
    config_id: int
    config_name: str


class SimulationDataConverter:
    """Converts SimulationResult(s) to GNN and TRM training formats.

    Usage:
        converter = SimulationDataConverter(window=52, horizon=1)
        result = converter.convert(sim_result)
        converter.save_npz(result, Path("training_data.npz"))
    """

    def __init__(
        self,
        window: int = 52,
        horizon: int = 1,
        reward_config: Optional[Dict[str, float]] = None,
    ):
        self.window = window
        self.horizon = horizon
        self.reward_config = reward_config or {
            "fill_rate_weight": 1.0,
            "backlog_penalty": -0.5,
            "holding_penalty": -0.1,
            "service_bonus": 0.5,
        }

    # ========================================================================
    # Main conversion
    # ========================================================================

    def convert(self, sim_result) -> ConversionResult:
        """Convert a SimulationResult to training-ready format.

        Args:
            sim_result: SimulationResult from dag_simulator or dag_simpy_simulator

        Returns:
            ConversionResult with GNN arrays and TRM records.
        """
        # Build ordered indices
        site_names = self._extract_site_names(sim_result)
        product_ids = self._extract_product_ids(sim_result)
        N = len(site_names)
        P = len(product_ids)
        T = sim_result.num_periods

        site_idx = {name: i for i, name in enumerate(site_names)}
        prod_idx = {pid: i for i, pid in enumerate(product_ids)}

        # Build adjacency matrix from shipments
        A = self._build_adjacency(sim_result, site_idx, N)

        # Build node feature tensor: [T, N, F] (one product or aggregated)
        # For multi-product: aggregate across products per site
        node_features = self._build_node_features(
            sim_result, site_names, product_ids, site_idx, T, N
        )

        # Build target tensor: ordering decisions
        targets = self._build_targets(
            sim_result, site_names, product_ids, site_idx, T, N
        )

        # Window into training samples
        X, Y = self._create_windows(node_features, targets, T, N)

        # Context placeholder
        B = X.shape[0] if len(X.shape) == 4 else 0
        P_arr = np.zeros((max(B, 1), 0), dtype=np.float32)

        # Build TRM training records
        trm_records = self._build_trm_records(
            sim_result, site_names, product_ids, site_idx, T, N
        )

        return ConversionResult(
            X=X,
            A=A,
            Y=Y,
            P=P_arr,
            site_names=site_names,
            product_ids=product_ids,
            trm_records=trm_records,
            num_samples=B,
            num_sites=N,
            num_products=len(product_ids),
            num_periods=T,
            config_id=sim_result.config_id,
            config_name=sim_result.config_name,
        )

    def convert_multiple(self, sim_results: list) -> ConversionResult:
        """Convert multiple SimulationResults (e.g., Monte Carlo runs) into one dataset.

        Concatenates training samples from all runs.
        """
        if not sim_results:
            raise ValueError("No simulation results provided")

        # Convert each individually
        individual = [self.convert(r) for r in sim_results]

        # Stack GNN arrays (concatenate along batch dimension)
        X = np.concatenate([c.X for c in individual], axis=0)
        Y = np.concatenate([c.Y for c in individual], axis=0)
        P = np.zeros((X.shape[0], 0), dtype=np.float32)

        # Use adjacency from first (topology is the same)
        A = individual[0].A

        # Merge TRM records
        merged_trm: Dict[str, List[TrainingRecord]] = {}
        for conv in individual:
            for trm_type, records in conv.trm_records.items():
                merged_trm.setdefault(trm_type, []).extend(records)

        return ConversionResult(
            X=X,
            A=A,
            Y=Y,
            P=P,
            site_names=individual[0].site_names,
            product_ids=individual[0].product_ids,
            trm_records=merged_trm,
            num_samples=X.shape[0],
            num_sites=individual[0].num_sites,
            num_products=individual[0].num_products,
            num_periods=individual[0].num_periods,
            config_id=individual[0].config_id,
            config_name=individual[0].config_name,
        )

    # ========================================================================
    # GNN conversion helpers
    # ========================================================================

    def _extract_site_names(self, sim_result) -> List[str]:
        """Extract ordered site names from period states."""
        names = set()
        for ps in sim_result.period_states:
            names.add(ps.site_name)
        # Sort alphabetically for consistent indexing
        return sorted(names)

    def _extract_product_ids(self, sim_result) -> List[str]:
        """Extract ordered product IDs from period states."""
        pids = set()
        for ps in sim_result.period_states:
            pids.add(ps.product_id)
        return sorted(pids)

    def _build_adjacency(
        self, sim_result, site_idx: Dict[str, int], N: int
    ) -> np.ndarray:
        """Build adjacency matrices [2, N, N] from shipments.

        A[0] = shipment edges (material flow direction)
        A[1] = order edges (reverse flow)
        """
        A = np.zeros((2, N, N), dtype=np.float32)

        # Build from actual shipments
        for shipment in sim_result.shipments:
            # Find source and target from lane or shipment data
            # Shipments have lane_id; we need to find source→target
            # For now, use period_states to infer
            pass

        # Build from decisions (orders go upstream, shipments go downstream)
        for decision in sim_result.decisions:
            src_name = decision.site_name
            if src_name not in site_idx:
                continue
            src_i = site_idx[src_name]

            if decision.decision_type == "transfer_order":
                dest_name = decision.context.get("dest_site", "")
                if dest_name in site_idx:
                    dest_i = site_idx[dest_name]
                    A[0, src_i, dest_i] = 1.0  # Shipment edge

            elif decision.decision_type == "order":
                # Orders go upstream (reverse)
                ctx = decision.context
                upstream = ctx.get("supplier", "")
                if upstream in site_idx:
                    A[1, src_i, site_idx[upstream]] = 1.0  # Order edge

        # Ensure at least identity connections if sparse
        for i in range(N):
            if A[0, i, :].sum() == 0 and A[1, i, :].sum() == 0:
                A[0, i, i] = 1.0
                A[1, i, i] = 1.0

        return A

    def _build_node_features(
        self, sim_result, site_names: List[str], product_ids: List[str],
        site_idx: Dict[str, int], T: int, N: int,
    ) -> np.ndarray:
        """Build [T, N, F] node feature tensor, aggregated across products."""
        features = np.zeros((T, N, NUM_GNN_FEATURES), dtype=np.float32)

        # Index period states by (period, site)
        ps_map: Dict[Tuple[int, str], list] = {}
        for ps in sim_result.period_states:
            key = (ps.period, ps.site_name)
            ps_map.setdefault(key, []).append(ps)

        # Index decisions by (period, site)
        dec_map: Dict[Tuple[int, str], list] = {}
        for d in sim_result.decisions:
            key = (d.period, d.site_name)
            dec_map.setdefault(key, []).append(d)

        for t in range(T):
            for name in site_names:
                i = site_idx[name]
                states = ps_map.get((t, name), [])

                # Aggregate across products
                total_oh = sum(ps.on_hand for ps in states)
                total_bl = sum(ps.backlog for ps in states)
                total_demand = sum(ps.demand for ps in states)
                total_fulfilled = sum(ps.fulfilled for ps in states)
                total_it = sum(ps.in_transit for ps in states)
                total_ss = sum(ps.safety_stock for ps in states)
                total_target = sum(ps.target_inventory for ps in states)

                # Aggregate orders placed
                period_decisions = dec_map.get((t, name), [])
                total_ordered = sum(
                    d.quantity for d in period_decisions
                    if d.decision_type in ("order", "mo_execution")
                )

                # Node type from period state or name inference
                is_supply = 1.0 if any(
                    getattr(ps, 'master_type', '') == 'market_supply' for ps in states
                ) else 0.0
                is_demand = 1.0 if any(
                    getattr(ps, 'master_type', '') == 'market_demand' for ps in states
                ) else 0.0
                is_mfg = 1.0 if any(
                    getattr(ps, 'master_type', '') == 'manufacturer' for ps in states
                ) else 0.0
                is_inv = 1.0 if (not is_supply and not is_demand and not is_mfg) else 0.0

                # Count downstream connections from decisions
                num_ds = len(set(
                    d.context.get("dest_site", "")
                    for d in period_decisions
                    if d.decision_type == "transfer_order"
                ))

                features[t, i, :] = [
                    total_oh,
                    total_bl,
                    total_demand,
                    total_fulfilled,
                    total_it,
                    total_ss,
                    total_target,
                    total_ordered,
                    is_supply,
                    is_demand,
                    is_inv,
                    is_mfg,
                    i / max(N - 1, 1),  # Normalised topo position
                    float(num_ds),
                ]

        return features

    def _build_targets(
        self, sim_result, site_names: List[str], product_ids: List[str],
        site_idx: Dict[str, int], T: int, N: int,
    ) -> np.ndarray:
        """Build [T, N] target array from ordering decisions.

        Target = total order quantity per site per period.
        """
        targets = np.zeros((T, N), dtype=np.float32)

        for d in sim_result.decisions:
            if d.decision_type in ("order", "mo_execution"):
                if d.site_name in site_idx and 0 <= d.period < T:
                    targets[d.period, site_idx[d.site_name]] += d.quantity

        return targets

    def _create_windows(
        self, features: np.ndarray, targets: np.ndarray, T: int, N: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Create sliding windows for training.

        Args:
            features: [T, N, F]
            targets: [T, N]

        Returns:
            X: [B, window, N, F]
            Y: [B, N, horizon]
        """
        window = self.window
        horizon = self.horizon

        if T < window + horizon:
            logger.warning(
                f"Not enough periods ({T}) for window={window} + horizon={horizon}. "
                "Returning single sample with padding."
            )
            # Pad to minimum
            pad_t = window + horizon - T
            features = np.pad(features, ((pad_t, 0), (0, 0), (0, 0)), mode='constant')
            targets = np.pad(targets, ((pad_t, 0), (0, 0)), mode='constant')
            T = features.shape[0]

        B = T - window - horizon + 1
        X = np.zeros((B, window, N, NUM_GNN_FEATURES), dtype=np.float32)
        Y = np.zeros((B, N, horizon), dtype=np.float32)

        for b in range(B):
            X[b] = features[b:b + window]
            Y[b] = targets[b + window:b + window + horizon].T  # [N, H]

        return X, Y

    # ========================================================================
    # TRM conversion helpers
    # ========================================================================

    def _build_trm_records(
        self, sim_result, site_names: List[str], product_ids: List[str],
        site_idx: Dict[str, int], T: int, N: int,
    ) -> Dict[str, List[TrainingRecord]]:
        """Build per-TRM-type training records from simulation decisions."""
        records: Dict[str, List[TrainingRecord]] = {}

        # Build state lookup: (period, site_name, product_id) → SiteProductState
        state_lookup = self._build_state_lookup(sim_result)

        for decision in sim_result.decisions:
            trm_type = TRM_TYPE_MAP.get(decision.decision_type, decision.decision_type)
            site_key = decision.site_name
            pid = decision.product_id
            period = decision.period

            # Build state vector
            state_vec = self._decision_to_state_vector(
                decision, state_lookup, period
            )

            # Compute reward
            reward = self._compute_reward(decision, state_lookup, period)

            # Next state (period + 1)
            next_state = self._decision_to_state_vector(
                decision, state_lookup, period + 1
            )

            record = TrainingRecord(
                trm_type=trm_type,
                site_key=site_key,
                product_id=pid,
                period=period,
                state_features=state_vec,
                action=decision.quantity,
                reward=reward,
                next_state_features=next_state,
                done=(period >= T - 1),
                expert_action=decision.quantity,  # Heuristic is the expert for BC
                confidence=decision.context.get("confidence", 1.0),
                context=decision.context,
            )

            records.setdefault(trm_type, []).append(record)

        return records

    def _build_state_lookup(self, sim_result) -> Dict[Tuple[int, str, str], Any]:
        """Build lookup: (period, site, product) → period state."""
        lookup = {}
        for ps in sim_result.period_states:
            lookup[(ps.period, ps.site_name, ps.product_id)] = ps
        return lookup

    def _decision_to_state_vector(
        self, decision, state_lookup: dict, period: int,
    ) -> np.ndarray:
        """Convert decision context + state into fixed-size feature vector."""
        vec = np.zeros(NUM_TRM_STATE, dtype=np.float32)

        # Try to find matching period state
        key = (period, decision.site_name, decision.product_id)
        ps = state_lookup.get(key)

        if ps:
            on_hand = getattr(ps, 'on_hand', 0.0)
            backlog = getattr(ps, 'backlog', 0.0)
            in_transit = getattr(ps, 'in_transit', 0.0)
            ss = getattr(ps, 'safety_stock', 0.0)
            target = getattr(ps, 'target_inventory', 0.0)
            demand = getattr(ps, 'demand', 0.0)
            fulfilled = getattr(ps, 'fulfilled', 0.0)

            # Recent averages from demand_history if available
            demand_hist = getattr(ps, 'demand_history', None)
            if demand_hist and len(demand_hist) >= 4:
                demand_avg = float(np.mean(demand_hist[-4:]))
                demand_std = float(np.std(demand_hist[-4:]))
            else:
                demand_avg = demand
                demand_std = 0.0

            order_hist = getattr(ps, 'order_history', None)
            if order_hist and len(order_hist) >= 4:
                order_avg = float(np.mean(order_hist[-4:]))
            else:
                order_avg = 0.0

            fill_rate = fulfilled / demand if demand > 0 else 1.0
            dos = on_hand / (demand_avg / 7.0) if demand_avg > 0 else 0.0
            inv_position = on_hand + in_transit - backlog

            vec[0] = on_hand
            vec[1] = backlog
            vec[2] = in_transit
            vec[3] = ss
            vec[4] = target
            vec[5] = demand_avg
            vec[6] = demand_std
            vec[7] = order_avg
            vec[8] = fill_rate
            vec[9] = dos
            vec[10] = inv_position

        # Context-specific features (from decision.context)
        ctx = decision.context
        ctx_values = list(ctx.values())[:5]
        for j, val in enumerate(ctx_values):
            if isinstance(val, (int, float)):
                vec[11 + j] = float(val)

        return vec

    def _compute_reward(
        self, decision, state_lookup: dict, period: int,
    ) -> float:
        """Compute immediate reward for a decision."""
        cfg = self.reward_config
        key = (period, decision.site_name, decision.product_id)
        ps = state_lookup.get(key)
        if not ps:
            return 0.0

        on_hand = getattr(ps, 'on_hand', 0.0)
        backlog = getattr(ps, 'backlog', 0.0)
        demand = getattr(ps, 'demand', 0.0)
        fulfilled = getattr(ps, 'fulfilled', 0.0)
        target = getattr(ps, 'target_inventory', 0.0)

        fill_rate = fulfilled / demand if demand > 0 else 1.0
        excess = max(0, on_hand - target) if target > 0 else 0

        reward = (
            fill_rate * cfg["fill_rate_weight"]
            + (backlog * cfg["backlog_penalty"] / max(demand, 1))
            + (excess * cfg["holding_penalty"] / max(target, 1))
            + (cfg["service_bonus"] if fill_rate >= 0.95 else 0)
        )

        return float(np.clip(reward, -2.0, 2.0))

    # ========================================================================
    # Persistence
    # ========================================================================

    def save_npz(self, result: ConversionResult, path: Path) -> Path:
        """Save GNN training data as NPZ file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        np.savez_compressed(
            str(path),
            X=result.X,
            A=result.A,
            Y=result.Y,
            P=result.P,
        )

        # Save metadata alongside
        meta_path = path.with_suffix('.json')
        meta = {
            "config_id": result.config_id,
            "config_name": result.config_name,
            "num_samples": result.num_samples,
            "num_sites": result.num_sites,
            "num_products": result.num_products,
            "num_periods": result.num_periods,
            "window": self.window,
            "horizon": self.horizon,
            "site_names": result.site_names,
            "product_ids": result.product_ids,
            "X_shape": list(result.X.shape),
            "A_shape": list(result.A.shape),
            "Y_shape": list(result.Y.shape),
            "trm_record_counts": {k: len(v) for k, v in result.trm_records.items()},
        }
        meta_path.write_text(json.dumps(meta, indent=2))

        logger.info(
            f"Saved GNN data: {path} "
            f"(X={result.X.shape}, A={result.A.shape}, Y={result.Y.shape})"
        )
        return path

    def save_trm_records(
        self, result: ConversionResult, output_dir: Path,
    ) -> Dict[str, Path]:
        """Save TRM training records as NPZ files grouped by TRM type."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        saved = {}

        for trm_type, records in result.trm_records.items():
            if not records:
                continue

            states = np.stack([r.state_features for r in records])
            actions = np.array([r.action for r in records], dtype=np.float32)
            rewards = np.array([r.reward for r in records], dtype=np.float32)
            next_states = np.stack([
                r.next_state_features if r.next_state_features is not None
                else np.zeros(NUM_TRM_STATE, dtype=np.float32)
                for r in records
            ])
            dones = np.array([r.done for r in records], dtype=np.bool_)
            expert_actions = np.array([
                r.expert_action if r.expert_action is not None else r.action
                for r in records
            ], dtype=np.float32)
            confidences = np.array([r.confidence for r in records], dtype=np.float32)

            path = output_dir / f"trm_{trm_type}.npz"
            np.savez_compressed(
                str(path),
                states=states,
                actions=actions,
                rewards=rewards,
                next_states=next_states,
                dones=dones,
                expert_actions=expert_actions,
                confidences=confidences,
            )

            saved[trm_type] = path
            logger.info(
                f"Saved TRM data: {trm_type} → {path} "
                f"({len(records)} records, states={states.shape})"
            )

        return saved

    async def insert_decisions_to_db(
        self, result: ConversionResult, db, config_id: int,
    ):
        """Insert simulation decisions into powell_site_agent_decisions for CDC loop.

        Args:
            result: ConversionResult with trm_records
            db: AsyncSession
            config_id: SupplyChainConfig ID
        """
        try:
            from app.models.powell_decision import SiteAgentDecision
        except ImportError:
            logger.warning("SiteAgentDecision model not available, skipping DB insert")
            return

        count = 0
        for trm_type, records in result.trm_records.items():
            for record in records:
                try:
                    decision = SiteAgentDecision(
                        config_id=config_id,
                        site_key=record.site_key,
                        decision_type=trm_type,
                        input_state={
                            "features": record.state_features.tolist(),
                            "product_id": record.product_id,
                            "period": record.period,
                        },
                        deterministic_result={"action": record.expert_action},
                        trm_adjustment={},
                        final_result={"action": record.action},
                        confidence=record.confidence,
                    )
                    db.add(decision)
                    count += 1

                    # Flush in batches
                    if count % 500 == 0:
                        await db.flush()
                except Exception as e:
                    logger.warning(f"Failed to insert decision: {e}")

        if count > 0:
            await db.flush()
            logger.info(f"Inserted {count} decisions into powell_site_agent_decisions")
