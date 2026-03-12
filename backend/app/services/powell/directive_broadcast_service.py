"""
Directive Broadcast Service — Inter-Hive Signal Orchestration (Layer 3)

Bridges the gap between tGNN inference and SiteAgent directive consumption:
1. Gathers supply chain state from DB
2. Generates inter-hive signals from tGNN outputs
3. Builds per-site tGNNSiteDirectives
4. Broadcasts directives to SiteAgents
5. Collects feedback features for next tGNN cycle

This is the "nervous system" connecting hives across the network.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.powell.inter_hive_signal import (
    InterHiveSignal,
    InterHiveSignalType,
    tGNNSiteDirective,
)
from app.services.powell.hive_signal import HiveSignalBus
from app.services.powell.hive_health import HiveHealthMetrics
from app.services.powell.site_agent import SiteAgent

logger = logging.getLogger(__name__)

# Module-level registry so other services (e.g. DirectiveService) can
# access the active broadcast service and its registered SiteAgents.
_active_broadcast_service: Optional["DirectiveBroadcastService"] = None


class DirectiveBroadcastService:
    """Orchestrates inter-hive directive generation and broadcasting.

    Lifecycle:
        1. collect_site_state()   — gather inventory, signals, health per site
        2. generate_directives()  — build tGNNSiteDirective per site from tGNN output
        3. broadcast()            — push directives to SiteAgents
        4. collect_feedback()     — aggregate HiveFeedbackFeatures for next tGNN cycle
    """

    def __init__(self, site_agents: Optional[Dict[str, SiteAgent]] = None):
        global _active_broadcast_service
        self._site_agents: Dict[str, SiteAgent] = site_agents or {}
        self._directive_history: List[Dict[str, Any]] = []
        self._last_broadcast: Optional[datetime] = None
        # Register as active singleton so DirectiveService can find us
        _active_broadcast_service = self

    def register_site(self, site_key: str, agent: SiteAgent) -> None:
        """Register a SiteAgent for directive delivery."""
        self._site_agents[site_key] = agent

    @property
    def registered_sites(self) -> List[str]:
        return list(self._site_agents.keys())

    # =========================================================================
    # Step 1: Collect site state for tGNN input
    # =========================================================================

    def collect_site_state(self) -> Dict[str, Dict[str, Any]]:
        """Gather per-site state for tGNN feature extraction.

        Returns:
            Dict[site_key, {urgency_vector, signal_summary, hive_health, ...}]
        """
        state: Dict[str, Dict[str, Any]] = {}

        for site_key, agent in self._site_agents.items():
            bus = agent.signal_bus
            if bus is None:
                continue

            urgency_snap = bus.urgency.snapshot() if bus.urgency else {}
            signal_summary = bus.signal_summary()
            bus_stats = bus.stats()

            health = HiveHealthMetrics.from_signal_bus(bus, site_key=site_key)

            state[site_key] = {
                "urgency_vector": urgency_snap.get("values", {}),
                "urgency_directions": urgency_snap.get("directions", {}),
                "signal_summary": signal_summary,
                "bus_stats": bus_stats,
                "hive_health": health.to_dict(),
                "registered_trms": list(agent._registered_trms.keys()),
            }

        return state

    # =========================================================================
    # Step 2: Generate directives from tGNN outputs
    # =========================================================================

    def generate_directives_from_gnn(
        self,
        gnn_outputs: Dict[str, Dict[str, Any]],
        network_topology: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, tGNNSiteDirective]:
        """Build per-site directives from tGNN inference results.

        Args:
            gnn_outputs: {site_key: {criticality_score, bottleneck_risk, ...}}
            network_topology: {site_key: [neighbor_site_keys]} for signal routing

        Returns:
            Dict[site_key, tGNNSiteDirective]
        """
        directives: Dict[str, tGNNSiteDirective] = {}
        inter_hive_signals = self._generate_inter_hive_signals(
            gnn_outputs, network_topology or {}
        )

        for site_key, output in gnn_outputs.items():
            # Collect signals targeted at this site
            site_signals = [s for s in inter_hive_signals if s.target_site == site_key]

            directive = tGNNSiteDirective.from_gnn_output(
                site_key=site_key,
                gnn_embeddings=output,
                inter_hive_signals=site_signals,
            )
            directives[site_key] = directive

        return directives

    def _generate_inter_hive_signals(
        self,
        gnn_outputs: Dict[str, Dict[str, Any]],
        topology: Dict[str, List[str]],
    ) -> List[InterHiveSignal]:
        """Generate inter-hive signals based on tGNN exception/risk thresholds.

        Signal generation rules:
        - exception_probability > 0.6 → NETWORK_SHORTAGE to downstream neighbors
        - bottleneck_risk > 0.7      → BOTTLENECK_RISK to all neighbors
        - surplus detected            → NETWORK_SURPLUS to upstream neighbors
        - demand_forecast spike       → DEMAND_PROPAGATION to upstream
        """
        signals: List[InterHiveSignal] = []
        THRESHOLD = 0.6

        for source_site, output in gnn_outputs.items():
            exception_prob = output.get("exception_probability", 0.0)
            bottleneck_risk = output.get("bottleneck_risk", 0.0)
            demand_forecast = output.get("demand_forecast", 0.0)

            neighbors = topology.get(source_site, [])

            # Shortage signal
            if exception_prob > THRESHOLD:
                for target in neighbors:
                    signals.append(InterHiveSignal(
                        signal_type=InterHiveSignalType.NETWORK_SHORTAGE,
                        source_site=source_site,
                        target_site=target,
                        urgency=min(1.0, exception_prob),
                        direction="shortage",
                        magnitude=demand_forecast * exception_prob,
                        confidence=output.get("confidence", 0.8),
                    ))

            # Bottleneck risk
            if bottleneck_risk > 0.7:
                for target in neighbors:
                    signals.append(InterHiveSignal(
                        signal_type=InterHiveSignalType.BOTTLENECK_RISK,
                        source_site=source_site,
                        target_site=target,
                        urgency=min(1.0, bottleneck_risk),
                        direction="risk",
                        magnitude=bottleneck_risk * 100.0,
                        confidence=output.get("confidence", 0.8),
                    ))

            # Surplus signal
            inv_ratio = output.get("inventory_ratio", 1.0)
            if inv_ratio > 1.5:  # >150% of target
                for target in neighbors:
                    signals.append(InterHiveSignal(
                        signal_type=InterHiveSignalType.NETWORK_SURPLUS,
                        source_site=source_site,
                        target_site=target,
                        urgency=min(1.0, (inv_ratio - 1.0) / 2.0),
                        direction="surplus",
                        magnitude=demand_forecast * (inv_ratio - 1.0),
                        confidence=output.get("confidence", 0.8),
                    ))

        return signals

    # =========================================================================
    # Step 3: Broadcast directives to SiteAgents
    # =========================================================================

    def broadcast(
        self,
        directives: Dict[str, tGNNSiteDirective],
    ) -> Dict[str, Dict[str, Any]]:
        """Push directives to registered SiteAgents.

        Args:
            directives: {site_key: tGNNSiteDirective}

        Returns:
            {site_key: apply_directive() summary}
        """
        results: Dict[str, Dict[str, Any]] = {}
        delivered = 0
        skipped = 0

        for site_key, directive in directives.items():
            agent = self._site_agents.get(site_key)
            if agent is None:
                logger.warning(f"No SiteAgent for {site_key} — skipping directive")
                skipped += 1
                continue

            try:
                summary = agent.apply_directive(directive)
                results[site_key] = summary
                delivered += 1
            except Exception as e:
                logger.error(f"Failed to apply directive to {site_key}: {e}")
                results[site_key] = {"error": str(e)}
                skipped += 1

        self._last_broadcast = datetime.now(timezone.utc)
        self._directive_history.append({
            "timestamp": self._last_broadcast.isoformat(),
            "sites_delivered": delivered,
            "sites_skipped": skipped,
            "total_signals": sum(
                len(d.inter_hive_signals) for d in directives.values()
            ),
        })

        logger.info(
            f"Broadcast complete: {delivered} sites, "
            f"{skipped} skipped, "
            f"{sum(len(d.inter_hive_signals) for d in directives.values())} signals"
        )

        return results

    # =========================================================================
    # Step 4: Collect feedback for next tGNN cycle
    # =========================================================================

    def collect_feedback(self) -> Dict[str, Dict[str, Any]]:
        """Aggregate HiveFeedbackFeatures from all registered sites.

        Returns:
            {site_key: feedback_features_dict}
        """
        feedback: Dict[str, Dict[str, Any]] = {}

        for site_key, agent in self._site_agents.items():
            bus = agent.signal_bus
            if bus is None:
                continue

            health = HiveHealthMetrics.from_signal_bus(bus, site_key=site_key)
            health_dict = health.to_dict()

            # Compute feedback features
            urgency_snap = bus.urgency.snapshot()
            urgency_values = urgency_snap.get("values", [])
            net_urgency = sum(urgency_values) / max(len(urgency_values), 1)

            signal_summary = bus.signal_summary()
            shortage_count = sum(
                v for k, v in signal_summary.items()
                if "shortage" in k.lower() or "shortage" in k.lower()
            )
            total_signals = sum(signal_summary.values())
            shortage_density = shortage_count / max(total_signals, 1)

            feedback[site_key] = {
                "net_urgency_avg": round(net_urgency, 4),
                "shortage_signal_density": round(shortage_density, 4),
                "total_active_signals": total_signals,
                "urgency_values": urgency_values,
                "hive_health": health_dict,
            }

        return feedback

    # =========================================================================
    # Full orchestration cycle
    # =========================================================================

    def run_cycle(
        self,
        gnn_outputs: Dict[str, Dict[str, Any]],
        network_topology: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """Execute a full directive broadcast cycle.

        1. Generate directives from tGNN outputs
        2. Broadcast to all registered SiteAgents
        3. Collect feedback features
        4. Return comprehensive summary

        Args:
            gnn_outputs: {site_key: {criticality_score, bottleneck_risk, ...}}
            network_topology: {site_key: [neighbor_site_keys]}

        Returns:
            Cycle summary with broadcast results and feedback
        """
        # Generate directives
        directives = self.generate_directives_from_gnn(gnn_outputs, network_topology)

        # Broadcast
        broadcast_results = self.broadcast(directives)

        # Collect feedback
        feedback = self.collect_feedback()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "directives_generated": len(directives),
            "broadcast_results": broadcast_results,
            "feedback": feedback,
            "total_inter_hive_signals": sum(
                len(d.inter_hive_signals) for d in directives.values()
            ),
        }

    # =========================================================================
    # Status / History
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Return current service status."""
        return {
            "registered_sites": self.registered_sites,
            "last_broadcast": self._last_broadcast.isoformat() if self._last_broadcast else None,
            "broadcast_count": len(self._directive_history),
            "history": self._directive_history[-10:],  # Last 10 cycles
        }
