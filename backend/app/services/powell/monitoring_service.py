"""
Powell Monitoring Service

Provides background monitoring capabilities for Powell TRM services:
- Periodic exception detection on active orders
- Inventory position monitoring for PO recommendations
- Rebalancing opportunity detection

This service is designed to be called by:
- Scheduled background tasks (e.g., Celery, APScheduler)
- API endpoints for on-demand checks
- Beer Game execution engine for round-based monitoring

Powell Philosophy:
- TRMs make NARROW execution decisions
- Fast feedback loops (minutes/hours, not weeks)
- Small state space for effective RL training
- All decisions logged for training data collection
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, date
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.purchase_order import PurchaseOrder
from app.models.transfer_order import TransferOrder
from app.models.sc_entities import InvLevel

logger = logging.getLogger(__name__)


@dataclass
class MonitoringConfig:
    """Configuration for monitoring behavior."""

    # Exception detection
    exception_check_interval_minutes: int = 60
    critical_exception_alert_threshold: int = 3

    # PO monitoring
    po_check_interval_minutes: int = 240  # 4 hours
    low_inventory_threshold_dos: float = 3.0  # Days of supply

    # Rebalancing
    rebalance_check_interval_minutes: int = 1440  # 24 hours
    imbalance_threshold_percent: float = 30.0

    # Logging
    log_all_checks: bool = True


@dataclass
class MonitoringResult:
    """Result from a monitoring check."""

    check_type: str
    timestamp: str
    config_id: int
    findings_count: int
    critical_count: int
    findings: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)


class PowellMonitoringService:
    """
    Background monitoring service for Powell TRM operations.

    Provides periodic checks for:
    1. Order exceptions (late, shortage, stuck)
    2. Low inventory positions requiring PO
    3. Inventory imbalances requiring rebalancing
    """

    def __init__(
        self,
        db: AsyncSession,
        config: Optional[MonitoringConfig] = None,
    ):
        self.db = db
        self.config = config or MonitoringConfig()
        self._last_exception_check: Optional[datetime] = None
        self._last_po_check: Optional[datetime] = None
        self._last_rebalance_check: Optional[datetime] = None

    async def run_all_checks(
        self,
        config_id: int,
        game_id: Optional[int] = None,
    ) -> Dict[str, MonitoringResult]:
        """
        Run all monitoring checks.

        Args:
            config_id: Supply chain configuration ID
            game_id: Optional game ID for Beer Game context

        Returns:
            Dictionary of check_type -> MonitoringResult
        """
        results = {}

        # Exception detection
        exception_result = await self.check_order_exceptions(config_id, game_id)
        results["exceptions"] = exception_result

        # PO recommendations
        po_result = await self.check_inventory_positions(config_id, game_id)
        results["po_recommendations"] = po_result

        # Rebalancing opportunities
        rebalance_result = await self.check_rebalancing_opportunities(config_id, game_id)
        results["rebalancing"] = rebalance_result

        return results

    async def check_order_exceptions(
        self,
        config_id: int,
        game_id: Optional[int] = None,
    ) -> MonitoringResult:
        """
        Check for order exceptions using OrderTrackingTRM.

        Scans active POs and TOs for:
        - Late delivery risk
        - Quantity shortages
        - Stuck in transit
        - Missing confirmations

        Args:
            config_id: Supply chain configuration ID
            game_id: Optional game ID

        Returns:
            MonitoringResult with detected exceptions
        """
        try:
            from app.services.powell.integration_service import PowellIntegrationService

            integration = PowellIntegrationService(self.db)
            result = await integration.detect_order_exceptions(config_id, game_id)

            findings = []
            recommendations = []
            critical_count = 0

            if result.success and result.recommendation:
                for detection in result.recommendation:
                    finding = {
                        "order_id": detection.order_id,
                        "exception_type": detection.exception_type.value,
                        "severity": detection.severity.value,
                        "description": detection.description,
                        "confidence": detection.confidence,
                    }
                    findings.append(finding)

                    if detection.severity.value == "critical":
                        critical_count += 1

                    recommendations.append({
                        "order_id": detection.order_id,
                        "action": detection.recommended_action.value,
                        "impact_assessment": detection.impact_assessment,
                    })

            self._last_exception_check = datetime.utcnow()

            return MonitoringResult(
                check_type="order_exceptions",
                timestamp=datetime.utcnow().isoformat(),
                config_id=config_id,
                findings_count=len(findings),
                critical_count=critical_count,
                findings=findings,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Exception check failed: {e}", exc_info=True)
            return MonitoringResult(
                check_type="order_exceptions",
                timestamp=datetime.utcnow().isoformat(),
                config_id=config_id,
                findings_count=0,
                critical_count=0,
                findings=[{"error": str(e)}],
            )

    async def check_inventory_positions(
        self,
        config_id: int,
        game_id: Optional[int] = None,
    ) -> MonitoringResult:
        """
        Check inventory positions for PO recommendations.

        Identifies items where:
        - Inventory position < reorder point
        - Days of supply < threshold
        - Upcoming demand exceeds available ATP

        Args:
            config_id: Supply chain configuration ID
            game_id: Optional game ID

        Returns:
            MonitoringResult with PO recommendations
        """
        try:
            from app.services.powell.integration_service import PowellIntegrationService

            integration = PowellIntegrationService(self.db)

            # Get all sites
            sites = await self._get_config_sites(config_id)

            all_recommendations = []
            critical_count = 0

            for site_id in sites:
                result = await integration.get_po_recommendations(
                    config_id=config_id,
                    site_id=site_id,
                )

                if result.success and result.recommendation:
                    for rec in result.recommendation:
                        finding = {
                            "site_id": site_id,
                            "product_id": rec.product_id,
                            "supplier_id": rec.supplier.supplier_id,
                            "recommended_qty": rec.recommended_qty,
                            "urgency": rec.urgency.value,
                            "trigger_reason": rec.trigger_reason.value,
                            "confidence": rec.confidence,
                        }
                        all_recommendations.append(finding)

                        if rec.urgency.value in ("critical", "high"):
                            critical_count += 1

            self._last_po_check = datetime.utcnow()

            return MonitoringResult(
                check_type="po_recommendations",
                timestamp=datetime.utcnow().isoformat(),
                config_id=config_id,
                findings_count=len(all_recommendations),
                critical_count=critical_count,
                findings=all_recommendations,
                recommendations=all_recommendations,
            )

        except Exception as e:
            logger.error(f"Inventory position check failed: {e}", exc_info=True)
            return MonitoringResult(
                check_type="po_recommendations",
                timestamp=datetime.utcnow().isoformat(),
                config_id=config_id,
                findings_count=0,
                critical_count=0,
                findings=[{"error": str(e)}],
            )

    async def check_rebalancing_opportunities(
        self,
        config_id: int,
        game_id: Optional[int] = None,
    ) -> MonitoringResult:
        """
        Check for inventory rebalancing opportunities.

        Identifies:
        - Sites with excess inventory
        - Sites at risk of stockout
        - Transfer opportunities that improve overall network position

        Args:
            config_id: Supply chain configuration ID
            game_id: Optional game ID

        Returns:
            MonitoringResult with rebalancing recommendations
        """
        try:
            from app.services.powell.integration_service import PowellIntegrationService

            integration = PowellIntegrationService(self.db)
            result = await integration.get_rebalancing_recommendations(config_id)

            findings = []
            critical_count = 0

            if result.success and result.recommendation:
                for rec in result.recommendation:
                    finding = {
                        "from_site": rec.from_site,
                        "to_site": rec.to_site,
                        "product_id": rec.product_id,
                        "recommended_qty": rec.recommended_qty,
                        "reason": rec.reason.value,
                        "urgency": rec.urgency,
                        "confidence": rec.confidence,
                        "expected_benefit": {
                            "source_dos_change": rec.source_dos_after - rec.source_dos_before,
                            "dest_dos_change": rec.dest_dos_after - rec.dest_dos_before,
                            "estimated_cost": rec.estimated_cost,
                        },
                    }
                    findings.append(finding)

                    if rec.urgency >= 0.8:  # High urgency
                        critical_count += 1

            self._last_rebalance_check = datetime.utcnow()

            return MonitoringResult(
                check_type="rebalancing",
                timestamp=datetime.utcnow().isoformat(),
                config_id=config_id,
                findings_count=len(findings),
                critical_count=critical_count,
                findings=findings,
                recommendations=findings,
            )

        except Exception as e:
            logger.error(f"Rebalancing check failed: {e}", exc_info=True)
            return MonitoringResult(
                check_type="rebalancing",
                timestamp=datetime.utcnow().isoformat(),
                config_id=config_id,
                findings_count=0,
                critical_count=0,
                findings=[{"error": str(e)}],
            )

    async def get_monitoring_status(
        self,
        config_id: int,
    ) -> Dict[str, Any]:
        """
        Get current monitoring status and last check times.

        Args:
            config_id: Supply chain configuration ID

        Returns:
            Dictionary with monitoring status
        """
        return {
            "config_id": config_id,
            "last_exception_check": self._last_exception_check.isoformat() if self._last_exception_check else None,
            "last_po_check": self._last_po_check.isoformat() if self._last_po_check else None,
            "last_rebalance_check": self._last_rebalance_check.isoformat() if self._last_rebalance_check else None,
            "config": {
                "exception_interval_minutes": self.config.exception_check_interval_minutes,
                "po_interval_minutes": self.config.po_check_interval_minutes,
                "rebalance_interval_minutes": self.config.rebalance_check_interval_minutes,
            },
        }

    async def should_run_check(
        self,
        check_type: str,
    ) -> bool:
        """
        Determine if a check should run based on interval.

        Args:
            check_type: 'exceptions', 'po', or 'rebalancing'

        Returns:
            True if check should run
        """
        now = datetime.utcnow()

        if check_type == "exceptions":
            if self._last_exception_check is None:
                return True
            elapsed = (now - self._last_exception_check).total_seconds() / 60
            return elapsed >= self.config.exception_check_interval_minutes

        elif check_type == "po":
            if self._last_po_check is None:
                return True
            elapsed = (now - self._last_po_check).total_seconds() / 60
            return elapsed >= self.config.po_check_interval_minutes

        elif check_type == "rebalancing":
            if self._last_rebalance_check is None:
                return True
            elapsed = (now - self._last_rebalance_check).total_seconds() / 60
            return elapsed >= self.config.rebalance_check_interval_minutes

        return False

    # =========================================================================
    # Beer Game Integration
    # =========================================================================

    async def run_round_end_checks(
        self,
        config_id: int,
        game_id: int,
        round_number: int,
    ) -> Dict[str, MonitoringResult]:
        """
        Run monitoring checks at the end of a Beer Game round.

        This is called by the Beer Game execution engine to:
        1. Detect any order exceptions that occurred this round
        2. Check if POs should be created for next round
        3. Identify rebalancing opportunities

        Args:
            config_id: Supply chain configuration ID
            game_id: Beer Game ID
            round_number: Completed round number

        Returns:
            Dictionary of monitoring results
        """
        logger.info(f"Running round-end monitoring for game {game_id}, round {round_number}")

        results = {}

        # Always check exceptions at round end
        results["exceptions"] = await self.check_order_exceptions(config_id, game_id)

        # Check PO recommendations (for next round planning)
        results["po_recommendations"] = await self.check_inventory_positions(config_id, game_id)

        # Check rebalancing (less frequent in Beer Game, but useful)
        if round_number % 4 == 0:  # Every 4 rounds
            results["rebalancing"] = await self.check_rebalancing_opportunities(config_id, game_id)

        return results

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_config_sites(self, config_id: int) -> List[int]:
        """Get all site IDs for a configuration."""
        from app.models.supply_chain_config import Node

        result = await self.db.execute(
            select(Node.id).where(
                Node.config_id == config_id,
                Node.master_type.in_(["INVENTORY", "MANUFACTURER"]),
            )
        )
        return [row[0] for row in result.fetchall()]


# Factory function for dependency injection
async def get_powell_monitoring_service(
    db: AsyncSession,
    config: Optional[MonitoringConfig] = None,
) -> PowellMonitoringService:
    """Factory function to create PowellMonitoringService."""
    return PowellMonitoringService(db, config)
