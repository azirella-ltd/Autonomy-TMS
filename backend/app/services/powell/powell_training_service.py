"""
Powell Training Service

Integrated training pipeline for all Powell framework AI models:
1. Generate unified training data from supply chain config
2. Aggregate data to S&OP hierarchy level for GraphSAGE
3. Train S&OP GraphSAGE on aggregated topology
4. Train Execution tGNN with S&OP embeddings
5. Train each TRM type with role-specific data

Key Insight: One data generation process creates both:
- Detailed data for tGNN (site × product × day)
- Aggregated data for GraphSAGE (region × family × month)

The Group Admin configures hierarchy levels via PlanningHierarchyConfig.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

import numpy as np

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.powell_training_config import (
    PowellTrainingConfig,
    TRMTrainingConfig,
    TRMSiteTrainingConfig,
    TRMBaseModel,
    TrainingRun,
    TRMType,
    TrainingStatus,
    LearningPhase,
    PhaseStatus,
    TRM_APPLICABILITY,
)
from app.models.planning_hierarchy import (
    PlanningHierarchyConfig,
    SiteHierarchyLevel,
    ProductHierarchyLevel,
    TimeBucketType,
    PlanningType
)
from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane
Node = Site  # backward compat alias for existing code in this file

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(__file__).parent.parent.parent.parent / "checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True)


@dataclass
class TrainingData:
    """Container for unified training data."""
    # Detailed level (for tGNN and TRM)
    node_features: np.ndarray  # [samples, nodes, features]
    edge_index: np.ndarray  # [2, edges]
    edge_features: np.ndarray  # [samples, edges, features]
    temporal_sequences: np.ndarray  # [samples, window, nodes, features]
    order_targets: np.ndarray  # [samples, nodes]
    demand_targets: np.ndarray  # [samples, nodes]

    # Aggregated level (for S&OP GraphSAGE)
    agg_node_features: np.ndarray  # Aggregated node features
    agg_edge_index: np.ndarray  # Aggregated edges
    agg_edge_features: np.ndarray
    agg_targets: Dict[str, np.ndarray]  # criticality, bottleneck, etc.

    # Mapping
    node_to_agg_node: Dict[int, int]  # Maps detailed node to aggregated
    product_to_agg_product: Dict[int, int]

    # TRM-specific data
    atp_data: Dict[str, np.ndarray]
    rebalancing_data: Dict[str, np.ndarray]
    po_creation_data: Dict[str, np.ndarray]
    order_tracking_data: Dict[str, np.ndarray]


class PowellTrainingService:
    """
    Orchestrates the complete Powell training pipeline.

    Usage:
        service = PowellTrainingService(db, powell_config_id)
        await service.train()
    """

    def __init__(
        self,
        db: AsyncSession,
        powell_config_id: int,
        training_run_id: Optional[int] = None
    ):
        self.db = db
        self.powell_config_id = powell_config_id
        self.training_run_id = training_run_id

        # Will be loaded
        self.config: Optional[PowellTrainingConfig] = None
        self.sc_config: Optional[SupplyChainConfig] = None
        self.sop_hierarchy: Optional[PlanningHierarchyConfig] = None
        self.exec_hierarchy: Optional[PlanningHierarchyConfig] = None
        self.trm_configs: List[TRMTrainingConfig] = []

        # Device
        self.device = "cpu"
        try:
            import torch
            if torch.cuda.is_available():
                self.device = "cuda"
        except ImportError:
            pass

    async def load_config(self):
        """Load all configuration from database."""
        # Load Powell config
        result = await self.db.execute(
            select(PowellTrainingConfig).where(
                PowellTrainingConfig.id == self.powell_config_id
            )
        )
        self.config = result.scalar_one_or_none()
        if not self.config:
            raise ValueError(f"Powell config {self.powell_config_id} not found")

        # Load supply chain config
        result = await self.db.execute(
            select(SupplyChainConfig).where(
                SupplyChainConfig.id == self.config.config_id
            )
        )
        self.sc_config = result.scalar_one_or_none()
        if not self.sc_config:
            raise ValueError(f"Supply chain config {self.config.config_id} not found")

        # Load hierarchy configs
        if self.config.sop_hierarchy_config_id:
            result = await self.db.execute(
                select(PlanningHierarchyConfig).where(
                    PlanningHierarchyConfig.id == self.config.sop_hierarchy_config_id
                )
            )
            self.sop_hierarchy = result.scalar_one_or_none()

        if self.config.execution_hierarchy_config_id:
            result = await self.db.execute(
                select(PlanningHierarchyConfig).where(
                    PlanningHierarchyConfig.id == self.config.execution_hierarchy_config_id
                )
            )
            self.exec_hierarchy = result.scalar_one_or_none()

        # Load TRM configs
        result = await self.db.execute(
            select(TRMTrainingConfig).where(
                TRMTrainingConfig.powell_config_id == self.powell_config_id
            )
        )
        self.trm_configs = list(result.scalars().all())

        logger.info(f"Loaded config: {self.config.name}")
        logger.info(f"SC Config: {self.sc_config.name}")
        logger.info(f"S&OP Hierarchy: {self.sop_hierarchy.name if self.sop_hierarchy else 'default'}")
        logger.info(f"TRM configs: {len(self.trm_configs)}")

    async def update_progress(self, phase: str, progress: float, **kwargs):
        """Update training run progress."""
        if not self.training_run_id:
            return

        result = await self.db.execute(
            select(TrainingRun).where(TrainingRun.id == self.training_run_id)
        )
        run = result.scalar_one_or_none()
        if run:
            run.current_phase = phase
            run.progress_percent = progress
            for key, value in kwargs.items():
                if hasattr(run, key):
                    setattr(run, key, value)
            await self.db.commit()

    async def train(self) -> Dict[str, Any]:
        """
        Execute the full training pipeline.

        Returns:
            Dictionary with training results for each model
        """
        results = {
            "success": False,
            "data_generation": {},
            "sop_graphsage": {},
            "execution_tgnn": {},
            "trm": {}
        }

        try:
            # Load configuration
            await self.load_config()
            await self.update_progress("loading_config", 5.0)

            # Step 1: Generate training data
            logger.info("Step 1: Generating training data...")
            await self.update_progress("generating_data", 10.0, status=TrainingStatus.GENERATING_DATA)

            training_data = await self.generate_training_data()
            results["data_generation"] = {
                "samples": len(training_data.node_features),
                "nodes": training_data.node_features.shape[1] if training_data.node_features.ndim > 1 else 0,
                "agg_nodes": len(training_data.agg_node_features) if training_data.agg_node_features is not None else 0
            }
            await self.update_progress(
                "data_generated", 25.0,
                samples_generated=results["data_generation"]["samples"]
            )

            # Step 2: Train S&OP GraphSAGE
            if self.config.train_sop_graphsage:
                logger.info("Step 2: Training S&OP GraphSAGE...")
                await self.update_progress("training_sop", 30.0, status=TrainingStatus.TRAINING_SOP)

                sop_results = await self.train_sop_graphsage(training_data)
                results["sop_graphsage"] = sop_results

                await self.update_progress(
                    "sop_complete", 50.0,
                    sop_epochs_completed=sop_results.get("epochs"),
                    sop_final_loss=sop_results.get("final_loss"),
                    sop_checkpoint_path=sop_results.get("checkpoint_path")
                )
            else:
                logger.info("Step 2: S&OP GraphSAGE training disabled")
                await self.update_progress("sop_skipped", 50.0)

            # Step 3: Train Execution tGNN
            if self.config.train_execution_tgnn:
                logger.info("Step 3: Training Execution tGNN...")
                await self.update_progress("training_tgnn", 55.0, status=TrainingStatus.TRAINING_TGNN)

                tgnn_results = await self.train_execution_tgnn(
                    training_data,
                    sop_embeddings=results["sop_graphsage"].get("embeddings")
                )
                results["execution_tgnn"] = tgnn_results

                await self.update_progress(
                    "tgnn_complete", 75.0,
                    tgnn_epochs_completed=tgnn_results.get("epochs"),
                    tgnn_final_loss=tgnn_results.get("final_loss"),
                    tgnn_checkpoint_path=tgnn_results.get("checkpoint_path")
                )
            else:
                logger.info("Step 3: Execution tGNN training disabled")
                await self.update_progress("tgnn_skipped", 75.0)

            # Step 4: Train TRM models
            logger.info("Step 4: Training TRM models...")
            await self.update_progress("training_trm", 80.0, status=TrainingStatus.TRAINING_TRM)

            trm_results = await self.train_trm_models(training_data)
            results["trm"] = trm_results

            await self.update_progress(
                "trm_complete", 95.0,
                trm_results=trm_results
            )

            # Complete
            results["success"] = True
            await self.update_progress(
                "completed", 100.0,
                status=TrainingStatus.COMPLETED,
                completed_at=datetime.utcnow()
            )

            # Update main config
            self.config.last_training_completed = datetime.utcnow()
            self.config.last_training_status = "completed"
            await self.db.commit()

            logger.info("Training pipeline completed successfully")

        except Exception as e:
            logger.error(f"Training failed: {e}", exc_info=True)
            results["error"] = str(e)

            await self.update_progress(
                "failed", 0.0,
                status=TrainingStatus.FAILED,
                error_message=str(e),
                error_phase="pipeline"
            )

            if self.config:
                self.config.last_training_status = "failed"
                self.config.last_training_error = str(e)
                await self.db.commit()

        return results

    async def generate_training_data(self) -> TrainingData:
        """
        Generate unified training data from SC config.

        Creates both detailed and aggregated data in one pass.
        """
        from app.models.gnn.large_sc_data_generator import (
            load_config_from_db,
            LargeSupplyChainSimulator
        )

        # Load SC config as LargeSupplyChainConfig
        sc_config = load_config_from_db(self.config.config_id)

        simulator = LargeSupplyChainSimulator(sc_config)
        num_nodes = sc_config.num_nodes()

        # Generate simulation data
        all_node_features = []
        all_temporal = []
        all_order_targets = []
        all_demand_targets = []

        # TRM-specific data
        atp_data = {"features": [], "labels": []}
        rebalancing_data = {"features": [], "labels": []}
        po_data = {"features": [], "labels": []}
        tracking_data = {"features": [], "labels": []}

        demand_patterns = self.config.demand_patterns or {
            "random": 0.3, "seasonal": 0.3, "step": 0.2, "trend": 0.2
        }
        patterns = list(demand_patterns.keys())
        pattern_weights = list(demand_patterns.values())

        for run_idx in range(self.config.num_simulation_runs):
            # Random parameters
            pattern = np.random.choice(patterns, p=np.array(pattern_weights) / sum(pattern_weights))
            base_demand = np.random.uniform(30, 100)
            volatility = np.random.uniform(0.1, 0.3)

            # Run simulation
            result = simulator.simulate(
                num_timesteps=self.config.timesteps_per_run,
                demand_pattern=pattern,
                base_demand=base_demand,
                volatility=volatility
            )

            # Extract windows for temporal data
            window = self.config.history_window
            valid_range = list(range(window, self.config.timesteps_per_run - self.config.forecast_horizon))

            for t in np.random.choice(valid_range, min(5, len(valid_range)), replace=False):
                # Node features at time t
                node_feat = self._extract_node_features(result, t, num_nodes)
                all_node_features.append(node_feat)

                # Temporal sequence
                temporal_seq = []
                for t_offset in range(t - window, t):
                    temporal_seq.append(self._extract_node_features(result, t_offset, num_nodes))
                all_temporal.append(np.stack(temporal_seq))

                # Targets
                all_order_targets.append(result['orders'][t])
                all_demand_targets.append(result['incoming_orders'][t])

                # TRM-specific data extraction
                self._extract_trm_data(
                    result, t, num_nodes,
                    atp_data, rebalancing_data, po_data, tracking_data
                )

            if (run_idx + 1) % 20 == 0:
                logger.info(f"Generated {run_idx + 1}/{self.config.num_simulation_runs} simulation runs")

        # Convert to arrays
        node_features = np.array(all_node_features)
        temporal_sequences = np.array(all_temporal)
        order_targets = np.array(all_order_targets)
        demand_targets = np.array(all_demand_targets)

        # Build edge data
        edge_index, edge_features = self._build_edge_data(sc_config)

        # Aggregate to S&OP level
        agg_data = await self._aggregate_to_sop_level(
            sc_config, node_features, edge_index, edge_features
        )

        return TrainingData(
            node_features=node_features,
            edge_index=edge_index,
            edge_features=edge_features,
            temporal_sequences=temporal_sequences,
            order_targets=order_targets,
            demand_targets=demand_targets,
            agg_node_features=agg_data.get("node_features"),
            agg_edge_index=agg_data.get("edge_index"),
            agg_edge_features=agg_data.get("edge_features"),
            agg_targets=agg_data.get("targets", {}),
            node_to_agg_node=agg_data.get("node_mapping", {}),
            product_to_agg_product=agg_data.get("product_mapping", {}),
            atp_data={k: np.array(v) for k, v in atp_data.items()},
            rebalancing_data={k: np.array(v) for k, v in rebalancing_data.items()},
            po_creation_data={k: np.array(v) for k, v in po_data.items()},
            order_tracking_data={k: np.array(v) for k, v in tracking_data.items()}
        )

    def _extract_node_features(self, result: Dict, t: int, num_nodes: int) -> np.ndarray:
        """Extract node features at timestep t (12 dimensions to match S&OP model)."""
        features = np.stack([
            result['inventory'][t] / (result['inventory'].max() + 1e-6),          # avg_lead_time proxy
            result['backlog'][t] / (result['backlog'].max() + 1e-6),              # lead_time_cv proxy
            result['incoming_orders'][t] / (result['incoming_orders'].max() + 1e-6),  # capacity proxy
            result['orders'][t] / (result['orders'].max() + 1e-6),               # capacity_utilization proxy
            np.random.uniform(0.8, 1.2, num_nodes),                               # unit_cost proxy
            np.random.uniform(0.85, 0.99, num_nodes),                             # reliability
            np.random.uniform(1, 5, num_nodes),                                   # num_suppliers
            np.random.uniform(1, 5, num_nodes),                                   # num_customers
            np.random.uniform(4, 20, num_nodes),                                  # inventory_turns
            np.random.uniform(0.90, 0.99, num_nodes),                             # service_level
            result['inventory'][t] / (result['inventory'].max() + 1e-6) * 0.1,   # holding_cost proxy
            np.linspace(0, 1, num_nodes),                                         # position
        ], axis=1)
        return features

    def _extract_trm_data(
        self,
        result: Dict,
        t: int,
        num_nodes: int,
        atp_data: Dict,
        rebalancing_data: Dict,
        po_data: Dict,
        tracking_data: Dict
    ):
        """Extract TRM-specific training data."""
        # ATP data
        for node_idx in range(num_nodes):
            inventory = result['inventory'][t, node_idx]
            backlog = result['backlog'][t, node_idx]
            demand = result['incoming_orders'][t, node_idx]
            pipeline = np.random.uniform(20, 80)

            atp_data["features"].append([
                inventory / 100, pipeline / 100, backlog / 100, demand / 100,
                np.random.randint(30, 100) / 100,  # requested_qty
                np.random.randint(1, 6) / 5  # priority
            ])
            # Label: can fulfill if inventory + pipeline > demand
            atp_data["labels"].append(1 if inventory + pipeline > demand else 0)

        # Rebalancing data
        for node_idx in range(num_nodes):
            inventory = result['inventory'][t, node_idx]
            avg_inv = result['inventory'][t].mean()

            rebalancing_data["features"].append([
                inventory / 100,
                avg_inv / 100,
                (inventory - avg_inv) / 100,
                result['backlog'][t, node_idx] / 100
            ])
            # Label: should transfer out if excess, transfer in if short
            rebalancing_data["labels"].append(
                1 if inventory > avg_inv * 1.5 else (-1 if inventory < avg_inv * 0.5 else 0)
            )

        # PO creation data
        for node_idx in range(num_nodes):
            inventory = result['inventory'][t, node_idx]
            demand = result['incoming_orders'][t, node_idx]
            backlog = result['backlog'][t, node_idx]

            po_data["features"].append([
                inventory / 100,
                demand / 100,
                backlog / 100,
                np.random.uniform(0.8, 1.0),  # supplier_reliability
                np.random.uniform(0.1, 0.3),  # lead_time_variability
            ])
            # Label: order now if inventory low
            po_data["labels"].append(1 if inventory < demand * 2 else 0)

        # Order tracking data
        for node_idx in range(num_nodes):
            tracking_data["features"].append([
                result['orders'][t, node_idx] / 100,
                result['inventory'][t, node_idx] / 100,
                np.random.uniform(0, 5),  # days_since_order
                np.random.uniform(0.8, 1.0),  # expected_delivery_prob
            ])
            # Label: exception type (0=none, 1=late, 2=short, 3=quality)
            tracking_data["labels"].append(np.random.choice([0, 0, 0, 1, 2]))

    def _build_edge_data(self, sc_config) -> Tuple[np.ndarray, np.ndarray]:
        """Build edge index and features."""
        node_index = {n.id: i for i, n in enumerate(sc_config.nodes)}

        edge_index = []
        edge_features = []

        for lane in sc_config.lanes:
            src = node_index.get(lane.source_id)
            tgt = node_index.get(lane.target_id)
            if src is not None and tgt is not None:
                edge_index.append([src, tgt])
                edge_index.append([tgt, src])  # Bidirectional

                feat = [
                    lane.lead_time / 10.0,
                    lane.cost_per_unit / 10.0,
                    lane.capacity / 1000.0,
                    lane.reliability,
                    np.random.uniform(0.5, 2.0),  # lead_time_std
                    np.random.uniform(0.5, 1.0),  # relationship_strength
                ]
                edge_features.append(feat)
                edge_features.append(feat)

        return np.array(edge_index).T, np.array(edge_features)

    async def _aggregate_to_sop_level(
        self,
        sc_config,
        node_features: np.ndarray,
        edge_index: np.ndarray,
        edge_features: np.ndarray
    ) -> Dict[str, Any]:
        """
        Aggregate data to S&OP hierarchy level.

        Uses the hierarchy config to determine aggregation level.
        """
        if not self.sop_hierarchy:
            # Default: no aggregation, use as-is
            logger.info("No S&OP hierarchy config, using unaggregated data")
            return {
                "node_features": node_features.mean(axis=0),  # Average across samples
                "edge_index": edge_index,
                "edge_features": edge_features,
                "targets": self._compute_sop_targets(node_features, sc_config),
                "node_mapping": {i: i for i in range(len(sc_config.nodes))},
                "product_mapping": {}
            }

        # Get hierarchy levels
        site_level = self.sop_hierarchy.site_hierarchy_level
        product_level = self.sop_hierarchy.product_hierarchy_level

        logger.info(f"Aggregating to S&OP level: {site_level.value} × {product_level.value}")

        # For now, simple aggregation - group nodes by type
        # In full implementation, would use HierarchyAggregationService
        # to properly aggregate based on site/product hierarchies

        node_type_groups = {}
        for i, node in enumerate(sc_config.nodes):
            node_type = node.node_type
            if node_type not in node_type_groups:
                node_type_groups[node_type] = []
            node_type_groups[node_type].append(i)

        # Aggregate features by node type
        agg_features = []
        node_mapping = {}
        agg_idx = 0

        for node_type, node_indices in node_type_groups.items():
            # Average features across nodes of this type
            type_features = node_features[:, node_indices, :].mean(axis=(0, 1))
            agg_features.append(type_features)

            for ni in node_indices:
                node_mapping[ni] = agg_idx
            agg_idx += 1

        # Build aggregated edge index
        agg_edges = set()
        for i in range(edge_index.shape[1]):
            src, tgt = edge_index[:, i]
            agg_src = node_mapping.get(src)
            agg_tgt = node_mapping.get(tgt)
            if agg_src is not None and agg_tgt is not None and agg_src != agg_tgt:
                agg_edges.add((agg_src, agg_tgt))

        agg_edge_index = np.array(list(agg_edges)).T if agg_edges else np.zeros((2, 0))

        return {
            "node_features": np.array(agg_features),
            "edge_index": agg_edge_index,
            "edge_features": np.ones((len(agg_edges), 4)),  # Placeholder
            "targets": self._compute_sop_targets(node_features, sc_config),
            "node_mapping": node_mapping,
            "product_mapping": {}
        }

    def _compute_sop_targets(self, node_features: np.ndarray, sc_config) -> Dict[str, np.ndarray]:
        """Compute S&OP-level target labels (criticality, bottleneck, etc.)."""
        # Average features across samples
        avg_features = node_features.mean(axis=0)  # [nodes, features]

        num_nodes = len(sc_config.nodes)
        node_index = {n.id: i for i, n in enumerate(sc_config.nodes)}

        # Count suppliers and customers per node
        num_suppliers = np.zeros(num_nodes)
        num_customers = np.zeros(num_nodes)

        for lane in sc_config.lanes:
            src = node_index.get(lane.source_id)
            tgt = node_index.get(lane.target_id)
            if tgt is not None:
                num_suppliers[tgt] += 1
            if src is not None:
                num_customers[src] += 1

        # Criticality: few suppliers + many customers = critical
        criticality = (1 - num_suppliers / (num_suppliers.max() + 1)) * (num_customers / (num_customers.max() + 1))

        # Bottleneck: high utilization
        bottleneck = avg_features[:, 5] if avg_features.shape[1] > 5 else np.random.uniform(0.3, 0.9, num_nodes)

        # Concentration risk: few suppliers
        concentration = 1 - num_suppliers / (num_suppliers.max() + 1)

        # Resilience: reliability * supplier diversity
        resilience = (num_suppliers / (num_suppliers.max() + 1))

        return {
            "criticality": criticality,
            "bottleneck": bottleneck,
            "concentration": concentration,
            "resilience": resilience
        }

    async def train_sop_graphsage(self, data: TrainingData) -> Dict[str, Any]:
        """Train S&OP GraphSAGE on aggregated data."""
        try:
            import torch
            from app.models.gnn.planning_execution_gnn import create_sop_model
        except ImportError:
            logger.warning("PyTorch not available, skipping S&OP training")
            return {"skipped": True, "reason": "PyTorch not available"}

        logger.info("Training S&OP GraphSAGE...")

        # Create model
        model = create_sop_model(
            hidden_dim=self.config.sop_hidden_dim,
            embedding_dim=self.config.sop_embedding_dim,
            num_layers=self.config.sop_num_layers
        )
        model = model.to(self.device)

        # Prepare data
        node_features = torch.tensor(data.agg_node_features, dtype=torch.float32).to(self.device)
        edge_index = torch.tensor(data.agg_edge_index, dtype=torch.long).to(self.device)
        edge_features = torch.tensor(data.agg_edge_features, dtype=torch.float32).to(self.device)

        targets = {k: torch.tensor(v, dtype=torch.float32).to(self.device) for k, v in data.agg_targets.items()}

        # Training
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.config.sop_learning_rate, weight_decay=0.01)

        best_loss = float('inf')
        loss_history = []

        for epoch in range(self.config.sop_epochs):
            model.train()
            optimizer.zero_grad()

            outputs = model(node_features, edge_index, edge_features)

            # Map target names to actual model output keys
            _SOP_OUTPUT_KEYS = {
                "criticality": "criticality_score",
                "bottleneck": "bottleneck_risk",
                "concentration": "concentration_risk",
                "resilience": "resilience_score",
            }
            loss = sum([
                torch.nn.functional.mse_loss(outputs[out_key].squeeze(), targets[k])
                for k, out_key in _SOP_OUTPUT_KEYS.items()
                if out_key in outputs and k in targets
            ]) / 4.0

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            loss_val = loss.item()
            loss_history.append(loss_val)

            if loss_val < best_loss:
                best_loss = loss_val

            if (epoch + 1) % 10 == 0:
                logger.info(f"S&OP Epoch {epoch + 1}/{self.config.sop_epochs}: loss={loss_val:.4f}")

        # Save checkpoint
        checkpoint_path = CHECKPOINT_DIR / f"sop_graphsage_{self.config.config_id}.pt"
        torch.save({
            "model_state_dict": model.state_dict(),
            "config": {
                "hidden_dim": self.config.sop_hidden_dim,
                "embedding_dim": self.config.sop_embedding_dim,
                "num_layers": self.config.sop_num_layers
            },
            "loss_history": loss_history
        }, checkpoint_path)

        # Get embeddings for tGNN
        model.eval()
        with torch.no_grad():
            outputs = model(node_features, edge_index, edge_features)
            embeddings = outputs["structural_embeddings"].cpu().numpy()

        logger.info(f"S&OP training complete. Best loss: {best_loss:.4f}")

        return {
            "epochs": self.config.sop_epochs,
            "final_loss": best_loss,
            "checkpoint_path": str(checkpoint_path),
            "embeddings": embeddings
        }

    async def train_execution_tgnn(
        self,
        data: TrainingData,
        sop_embeddings: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """Train Execution tGNN with S&OP embeddings."""
        try:
            import torch
            from app.models.gnn.planning_execution_gnn import create_execution_model
        except ImportError:
            logger.warning("PyTorch not available, skipping tGNN training")
            return {"skipped": True, "reason": "PyTorch not available"}

        logger.info("Training Execution tGNN...")

        # Create model
        edge_feat_dim = data.edge_features.shape[1] if len(data.edge_features) > 0 else 6
        trans_feat_dim = data.temporal_sequences.shape[-1] if data.temporal_sequences.ndim == 4 else 12
        model = create_execution_model(
            transactional_features=trans_feat_dim,
            structural_embedding_dim=self.config.sop_embedding_dim if sop_embeddings is not None else 0,
            hidden_dim=self.config.tgnn_hidden_dim,
            window_size=self.config.tgnn_window_size,
            edge_features=edge_feat_dim,
            num_gnn_layers=self.config.tgnn_num_layers,
            num_temporal_layers=self.config.tgnn_num_layers,
        )
        model = model.to(self.device)

        # Prepare data
        X = torch.tensor(data.temporal_sequences, dtype=torch.float32).to(self.device)
        Y = torch.tensor(data.order_targets, dtype=torch.float32).to(self.device)
        edge_index = torch.tensor(data.edge_index, dtype=torch.long).to(self.device)
        edge_features = torch.tensor(data.edge_features, dtype=torch.float32).to(self.device)

        if sop_embeddings is not None:
            structural_emb = torch.tensor(sop_embeddings, dtype=torch.float32).to(self.device)
        else:
            structural_emb = None

        # Training
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.config.tgnn_learning_rate, weight_decay=0.01)

        best_loss = float('inf')
        loss_history = []
        batch_size = self.config.tgnn_batch_size
        num_samples = len(X)

        for epoch in range(self.config.tgnn_epochs):
            model.train()
            total_loss = 0
            num_batches = 0

            indices = np.random.permutation(num_samples)

            for i in range(0, num_samples, batch_size):
                batch_idx = indices[i:i + batch_size]
                x_batch = X[batch_idx]
                y_batch = Y[batch_idx]

                optimizer.zero_grad()

                outputs = model(x_batch, structural_emb, edge_index, edge_features)
                loss = torch.nn.functional.huber_loss(
                    outputs["order_recommendation"].squeeze(-1),
                    y_batch
                )

                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

                total_loss += loss.item()
                num_batches += 1

            avg_loss = total_loss / num_batches
            loss_history.append(avg_loss)

            if avg_loss < best_loss:
                best_loss = avg_loss

            if (epoch + 1) % 20 == 0:
                logger.info(f"tGNN Epoch {epoch + 1}/{self.config.tgnn_epochs}: loss={avg_loss:.4f}")

        # Save checkpoint
        checkpoint_path = CHECKPOINT_DIR / f"execution_tgnn_{self.config.config_id}.pt"
        torch.save({
            "model_state_dict": model.state_dict(),
            "config": {
                "hidden_dim": self.config.tgnn_hidden_dim,
                "window_size": self.config.tgnn_window_size,
                "num_layers": self.config.tgnn_num_layers
            },
            "loss_history": loss_history
        }, checkpoint_path)

        logger.info(f"tGNN training complete. Best loss: {best_loss:.4f}")

        return {
            "epochs": self.config.tgnn_epochs,
            "final_loss": best_loss,
            "checkpoint_path": str(checkpoint_path)
        }

    async def train_trm_models(self, data: TrainingData) -> Dict[str, Any]:
        """Train each enabled TRM type."""
        results = {}

        for trm_config in self.trm_configs:
            if not trm_config.enabled:
                results[trm_config.trm_type.value] = {"skipped": True, "reason": "disabled"}
                continue

            logger.info(f"Training TRM: {trm_config.trm_type.value}")

            # Get appropriate training data
            if trm_config.trm_type == TRMType.ATP_EXECUTOR:
                trm_data = data.atp_data
            elif trm_config.trm_type == TRMType.REBALANCING:
                trm_data = data.rebalancing_data
            elif trm_config.trm_type == TRMType.PO_CREATION:
                trm_data = data.po_creation_data
            elif trm_config.trm_type == TRMType.ORDER_TRACKING:
                trm_data = data.order_tracking_data
            else:
                trm_data = {}

            if len(trm_data.get("features", [])) < trm_config.min_training_samples:
                results[trm_config.trm_type.value] = {
                    "skipped": True,
                    "reason": f"insufficient samples ({len(trm_data.get('features', []))} < {trm_config.min_training_samples})"
                }
                continue

            try:
                trm_result = await self._train_single_trm(trm_config, trm_data)
                results[trm_config.trm_type.value] = trm_result

                # Update TRM config record
                trm_config.last_trained = datetime.utcnow()
                trm_config.last_training_samples = len(trm_data["features"])
                trm_config.last_training_loss = trm_result.get("final_loss")
                trm_config.model_checkpoint_path = trm_result.get("checkpoint_path")
                await self.db.commit()

            except Exception as e:
                logger.error(f"TRM {trm_config.trm_type.value} training failed: {e}")
                results[trm_config.trm_type.value] = {"error": str(e)}

        return results

    # =========================================================================
    # Per-Site TRM Training (Learning-Depth Curriculum)
    # =========================================================================

    async def train_trm_per_site(
        self,
        site_ids: Optional[List[int]] = None,
        trm_types: Optional[List[str]] = None,
        phases: Optional[List[int]] = None,
        epochs_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Train TRM models per-site using the 3-phase learning-depth curriculum.

        Args:
            site_ids: Specific sites to train (None = all operational sites)
            trm_types: Specific TRM types (None = all applicable)
            phases: Specific phases to run (None = all eligible)
            epochs_override: Override epoch count for all phases
        """
        from app.services.powell.trm_site_trainer import TRMSiteTrainer

        # 1. Load operational sites for this config
        sites = await self._load_operational_sites(site_ids)
        if not sites:
            return {"error": "No operational sites found"}

        # 2. Auto-populate TRMSiteTrainingConfig records
        await self._populate_site_configs(sites)

        # 3. Train each (site, trm_type) pair
        results = {}
        total = 0
        completed = 0

        for site in sites:
            site_key = f"site_{site.id}_{site.name}"
            results[site_key] = {}
            applicable = self._get_applicable_trm_types(site.master_type)

            if trm_types:
                applicable = [t for t in applicable if t.value in trm_types]

            for trm_type in applicable:
                total += 1
                trm_key = trm_type.value

                # Load or create site config record
                site_config = await self._get_site_config(site.id, trm_type)
                if site_config and not site_config.enabled:
                    results[site_key][trm_key] = {"skipped": True, "reason": "disabled"}
                    continue

                try:
                    trainer = TRMSiteTrainer(
                        trm_type=trm_key,
                        site_id=site.id,
                        site_name=site.name,
                        master_type=site.master_type or "INVENTORY",
                        group_id=self.config.group_id,
                        config_id=self.config.config_id,
                        device=str(self.device),
                    )

                    # Try to load existing checkpoint
                    from app.services.powell.trm_site_trainer import find_best_checkpoint
                    existing = find_best_checkpoint(
                        trm_key, site.id,
                        master_type=site.master_type or "INVENTORY",
                        config_id=self.config.config_id,
                    )
                    if existing:
                        trainer.from_checkpoint(existing)

                    site_result = {}

                    # Phase 1: Engine Imitation (always available)
                    if phases is None or 1 in phases:
                        if site_config:
                            site_config.phase1_status = PhaseStatus.TRAINING.value
                            await self.db.commit()

                        p1 = await trainer.train_phase1(
                            epochs=epochs_override or (site_config.phase1_epochs_target if site_config else 20)
                        )
                        site_result["phase1"] = p1

                        if site_config and not p1.get("skipped"):
                            site_config.phase1_status = PhaseStatus.COMPLETED.value
                            site_config.phase1_epochs_completed = p1.get("epochs", 0)
                            site_config.phase1_loss = p1.get("final_loss")
                            await self.db.commit()

                    # Phase 2: Context Learning (if enough expert data)
                    if phases is None or 2 in phases:
                        if site_config:
                            site_config.phase2_status = PhaseStatus.TRAINING.value
                            await self.db.commit()

                        p2 = await trainer.train_phase2(
                            self.db,
                            epochs=epochs_override or (site_config.phase2_epochs_target if site_config else 50),
                            min_samples=site_config.phase2_min_samples if site_config else 500,
                        )
                        site_result["phase2"] = p2

                        if site_config:
                            if p2.get("skipped"):
                                site_config.phase2_status = PhaseStatus.PENDING.value
                                site_config.phase2_expert_samples = p2.get("expert_samples", 0)
                            else:
                                site_config.phase2_status = PhaseStatus.COMPLETED.value
                                site_config.phase2_epochs_completed = p2.get("epochs", 0)
                                site_config.phase2_loss = p2.get("final_loss")
                                site_config.phase2_expert_samples = p2.get("expert_samples", 0)
                            await self.db.commit()

                    # Phase 3: Outcome Optimization (if enough replay data)
                    if phases is None or 3 in phases:
                        if site_config:
                            site_config.phase3_status = PhaseStatus.TRAINING.value
                            await self.db.commit()

                        p3 = await trainer.train_phase3(
                            self.db,
                            epochs=epochs_override or (site_config.phase3_epochs_target if site_config else 80),
                            min_samples=site_config.phase3_min_samples if site_config else 1000,
                        )
                        site_result["phase3"] = p3

                        if site_config:
                            if p3.get("skipped"):
                                site_config.phase3_status = PhaseStatus.PENDING.value
                                site_config.phase3_outcome_samples = p3.get("outcome_samples", 0)
                            else:
                                site_config.phase3_status = PhaseStatus.COMPLETED.value
                                site_config.phase3_epochs_completed = p3.get("epochs", 0)
                                site_config.phase3_loss = p3.get("final_loss")
                                site_config.phase3_reward_mean = p3.get("reward_mean")
                                site_config.phase3_outcome_samples = p3.get("outcome_samples", 0)
                            await self.db.commit()

                    # Save checkpoint
                    version = (site_config.model_version + 1) if site_config else 1
                    ckpt_path = trainer.save_checkpoint(version)
                    site_result["checkpoint_path"] = ckpt_path

                    if site_config:
                        site_config.model_checkpoint_path = ckpt_path
                        site_config.model_version = version
                        site_config.last_trained_at = datetime.utcnow()
                        await self.db.commit()

                    results[site_key][trm_key] = site_result
                    completed += 1

                except Exception as e:
                    logger.error(f"Training {trm_key}@site{site.id} failed: {e}")
                    results[site_key][trm_key] = {"error": str(e)}
                    if site_config:
                        # Mark current phase as failed
                        for p in ["phase1_status", "phase2_status", "phase3_status"]:
                            if getattr(site_config, p) == PhaseStatus.TRAINING.value:
                                setattr(site_config, p, PhaseStatus.FAILED.value)
                        await self.db.commit()

        return {
            "total_pairs": total,
            "completed": completed,
            "sites": results,
        }

    async def _load_operational_sites(
        self, site_ids: Optional[List[int]] = None
    ) -> List[Site]:
        """Load sites that can have TRMs (inventory and manufacturer types)."""
        query = select(Site).where(
            Site.config_id == self.config.config_id,
            Site.master_type.in_(["INVENTORY", "MANUFACTURER"]),
        )
        if site_ids:
            query = query.where(Site.id.in_(site_ids))

        result = await self.db.execute(query)
        return list(result.scalars().all())

    def _get_applicable_trm_types(self, master_type: str) -> List[TRMType]:
        """Return which TRM types apply to this master_type."""
        return TRM_APPLICABILITY.get(master_type or "INVENTORY", [])

    async def _populate_site_configs(self, sites: List[Site]):
        """Auto-create TRMSiteTrainingConfig records for new sites."""
        for site in sites:
            applicable = self._get_applicable_trm_types(site.master_type)
            for trm_type in applicable:
                existing = await self._get_site_config(site.id, trm_type)
                if not existing:
                    config = TRMSiteTrainingConfig(
                        powell_config_id=self.config.id,
                        site_id=site.id,
                        site_name=site.name,
                        master_type=site.master_type or "INVENTORY",
                        trm_type=trm_type,
                        enabled=True,
                    )
                    self.db.add(config)
        await self.db.commit()

    async def _get_site_config(
        self, site_id: int, trm_type: TRMType
    ) -> Optional[TRMSiteTrainingConfig]:
        """Load TRMSiteTrainingConfig for a specific (site, trm_type) pair."""
        result = await self.db.execute(
            select(TRMSiteTrainingConfig).where(
                TRMSiteTrainingConfig.powell_config_id == self.config.id,
                TRMSiteTrainingConfig.site_id == site_id,
                TRMSiteTrainingConfig.trm_type == trm_type,
            )
        )
        return result.scalar_one_or_none()

    async def _train_single_trm(
        self,
        trm_config: TRMTrainingConfig,
        trm_data: Dict[str, np.ndarray]
    ) -> Dict[str, Any]:
        """Train a single TRM using per-TRM model architecture and curriculum."""
        try:
            import torch
        except ImportError:
            return {"skipped": True, "reason": "PyTorch not available"}

        from app.models.trm import MODEL_REGISTRY
        from app.services.powell.trm_curriculum import CURRICULUM_REGISTRY, SCConfigData

        trm_type_key = trm_config.trm_type.value
        if trm_type_key not in MODEL_REGISTRY:
            return {"skipped": True, "reason": f"Unknown TRM type: {trm_type_key}"}

        model_cls, state_dim = MODEL_REGISTRY[trm_type_key]
        model = model_cls(state_dim=state_dim).to(self.device)

        # Per-TRM loss function
        from app.services.powell.trm_curriculum import CurriculumData  # noqa: F811
        loss_fn = self._create_trm_loss(trm_type_key).to(self.device)

        # Generate curriculum data (3 phases, progressive)
        sc_config = SCConfigData()
        curriculum_cls = CURRICULUM_REGISTRY[trm_type_key]
        curriculum = curriculum_cls(sc_config)

        epochs = trm_config.epochs or self.config.trm_bc_epochs + self.config.trm_rl_epochs
        lr = trm_config.learning_rate or self.config.trm_learning_rate
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)

        best_loss = float('inf')
        num_samples = trm_config.min_training_samples or 5000

        for phase in [1, 2, 3]:
            logger.info(f"  TRM {trm_type_key} phase {phase}...")
            data = curriculum.generate(phase=phase, num_samples=num_samples)

            states_t = torch.tensor(data.state_vectors, dtype=torch.float32).to(self.device)
            act_disc_t = torch.tensor(data.action_discrete, dtype=torch.long).to(self.device)
            act_cont_t = torch.tensor(data.action_continuous, dtype=torch.float32).to(self.device)
            rewards_t = torch.tensor(data.rewards, dtype=torch.float32).to(self.device)

            phase_epochs = max(1, epochs // 3)
            for epoch in range(phase_epochs):
                model.train()
                optimizer.zero_grad()

                outputs = model(states_t)
                targets = {
                    "action_discrete": act_disc_t,
                    "action_continuous": act_cont_t,
                    "rewards": rewards_t,
                }
                loss = loss_fn(outputs, targets)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

                if loss.item() < best_loss:
                    best_loss = loss.item()

        # Save checkpoint
        checkpoint_path = CHECKPOINT_DIR / f"trm_{trm_type_key}_{self.config.config_id}.pt"
        torch.save({
            "model_state_dict": model.state_dict(),
            "trm_type": trm_type_key,
            "state_dim": state_dim,
            "model_class": model_cls.__name__,
            "config_id": self.config.config_id,
        }, checkpoint_path)

        return {
            "epochs": epochs,
            "final_loss": best_loss,
            "samples": num_samples * 3,
            "checkpoint_path": str(checkpoint_path),
            "model_class": model_cls.__name__,
        }

    def _create_trm_loss(self, trm_type_key: str):
        """Create the appropriate loss function for a TRM type."""
        import torch.nn as nn

        class _MultiHeadLoss(nn.Module):
            """Generic multi-head loss: CE(discrete) + MSE(continuous) + MSE(value)."""
            def __init__(self, discrete_key="action_logits", use_bce=False):
                super().__init__()
                self.ce = nn.CrossEntropyLoss()
                self.bce = nn.BCEWithLogitsLoss()
                self.mse = nn.MSELoss()
                self.discrete_key = discrete_key
                self.use_bce = use_bce

            def forward(self, outputs, targets):
                if self.use_bce:
                    disc_loss = self.bce(
                        outputs[self.discrete_key].squeeze(-1),
                        targets["action_discrete"].float()
                    )
                else:
                    disc_loss = self.ce(outputs[self.discrete_key], targets["action_discrete"])
                value_loss = self.mse(outputs["value"].squeeze(-1), targets["rewards"])
                return disc_loss + 0.3 * value_loss

        if trm_type_key == "rebalancing":
            return _MultiHeadLoss(discrete_key="transfer_logit", use_bce=True)
        elif trm_type_key == "order_tracking":
            # Order tracking has 3 classification heads
            class _OTLoss(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.ce = nn.CrossEntropyLoss()
                    self.mse = nn.MSELoss()
                def forward(self, outputs, targets):
                    exc = self.ce(outputs["exception_logits"], targets["action_discrete"])
                    sev = self.ce(outputs["severity_logits"], targets["action_continuous"][:, 0].long())
                    act = self.ce(outputs["action_logits"], targets["action_continuous"][:, 1].long())
                    val = self.mse(outputs["value"].squeeze(-1), targets["rewards"])
                    return exc + 0.7 * sev + 0.8 * act + 0.3 * val
            return _OTLoss()
        else:
            return _MultiHeadLoss(discrete_key="action_logits")


async def execute_training_pipeline(run_id: int, config_id: int):
    """
    Background task entry point for training pipeline.

    Called from API endpoint.
    """
    from app.db.session import async_session_factory

    async with async_session_factory() as db:
        service = PowellTrainingService(db, config_id, run_id)
        await service.train()
