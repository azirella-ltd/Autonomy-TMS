"""
Transfer Order Analytics

Provides analytical functions for Transfer Order performance metrics.

Metrics:
- On-time delivery rate
- Average lead time
- In-transit inventory levels
- Shipment volume by route
- TO throughput
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, case

from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.sc_entities import InvLevel
from app.models.supply_chain_config import Site


class TransferOrderAnalytics:
    """Analytics engine for Transfer Order performance metrics."""

    def __init__(self, db: Session):
        """
        Initialize TO analytics engine.

        Args:
            db: Database session
        """
        self.db = db

    def get_game_to_metrics(
        self,
        scenario_id: int,
        include_routes: bool = True,
        include_timeline: bool = True
    ) -> Dict:
        """
        Get comprehensive TO metrics for a game.

        Args:
            scenario_id: Game ID
            include_routes: Include route-level breakdowns
            include_timeline: Include round-by-round timeline

        Returns:
            Dictionary with TO metrics
        """
        metrics = {
            "scenario_id": scenario_id,
            "summary": self._calculate_summary_metrics(scenario_id),
            "delivery_performance": self._calculate_delivery_performance(scenario_id),
            "lead_time_analysis": self._calculate_lead_time_analysis(scenario_id),
            "in_transit_analysis": self._calculate_in_transit_analysis(scenario_id),
            "throughput": self._calculate_throughput(scenario_id)
        }

        if include_routes:
            metrics["route_analysis"] = self._calculate_route_metrics(scenario_id)

        if include_timeline:
            metrics["timeline"] = self._calculate_timeline(scenario_id)

        return metrics

    def _calculate_summary_metrics(self, scenario_id: int) -> Dict:
        """Calculate high-level summary metrics."""
        # Total TOs
        total_tos = self.db.query(func.count(TransferOrder.id)).filter(
            TransferOrder.scenario_id == scenario_id
        ).scalar() or 0

        # Status breakdown
        status_counts = self.db.query(
            TransferOrder.status,
            func.count(TransferOrder.id)
        ).filter(
            TransferOrder.scenario_id == scenario_id
        ).group_by(TransferOrder.status).all()

        status_breakdown = {status: count for status, count in status_counts}

        # Total quantity shipped
        total_quantity = self.db.query(
            func.sum(TransferOrderLineItem.shipped_quantity)
        ).join(
            TransferOrder,
            TransferOrderLineItem.to_id == TransferOrder.id
        ).filter(
            TransferOrder.scenario_id == scenario_id
        ).scalar() or 0.0

        # Average quantity per TO
        avg_quantity = total_quantity / total_tos if total_tos > 0 else 0.0

        return {
            "total_tos": total_tos,
            "status_breakdown": status_breakdown,
            "total_quantity_shipped": total_quantity,
            "avg_quantity_per_to": avg_quantity
        }

    def _calculate_delivery_performance(self, scenario_id: int) -> Dict:
        """Calculate on-time delivery metrics."""
        # Get all RECEIVED TOs
        received_tos = self.db.query(TransferOrder).filter(
            and_(
                TransferOrder.scenario_id == scenario_id,
                TransferOrder.status == "RECEIVED"
            )
        ).all()

        if not received_tos:
            return {
                "on_time_delivery_rate": 0.0,
                "total_received": 0,
                "on_time_count": 0,
                "late_count": 0,
                "early_count": 0
            }

        on_time = 0
        late = 0
        early = 0

        for to in received_tos:
            if not to.actual_delivery_date or not to.estimated_delivery_date:
                continue

            if to.actual_delivery_date == to.estimated_delivery_date:
                on_time += 1
            elif to.actual_delivery_date > to.estimated_delivery_date:
                late += 1
            else:
                early += 1

        total = len(received_tos)
        on_time_rate = (on_time / total * 100) if total > 0 else 0.0

        return {
            "on_time_delivery_rate": on_time_rate,
            "total_received": total,
            "on_time_count": on_time,
            "late_count": late,
            "early_count": early,
            "on_time_percentage": on_time_rate
        }

    def _calculate_lead_time_analysis(self, scenario_id: int) -> Dict:
        """Calculate lead time statistics."""
        # Get all TOs with shipment and delivery dates
        tos = self.db.query(TransferOrder).filter(
            TransferOrder.scenario_id == scenario_id
        ).all()

        planned_lead_times = []
        actual_lead_times = []

        for to in tos:
            # Planned lead time
            if to.shipment_date and to.estimated_delivery_date:
                planned_lt = (to.estimated_delivery_date - to.shipment_date).days
                planned_lead_times.append(planned_lt)

            # Actual lead time (for RECEIVED TOs)
            if to.status == "RECEIVED" and to.shipment_date and to.actual_delivery_date:
                actual_lt = (to.actual_delivery_date - to.shipment_date).days
                actual_lead_times.append(actual_lt)

        def calc_stats(values):
            if not values:
                return {"avg": 0.0, "min": 0.0, "max": 0.0, "median": 0.0}

            sorted_vals = sorted(values)
            n = len(sorted_vals)
            median = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2

            return {
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "median": median,
                "count": len(values)
            }

        return {
            "planned_lead_time": calc_stats(planned_lead_times),
            "actual_lead_time": calc_stats(actual_lead_times),
            "lead_time_variance": {
                "avg_difference": (
                    sum(actual_lead_times) / len(actual_lead_times) -
                    sum(planned_lead_times) / len(planned_lead_times)
                ) if actual_lead_times and planned_lead_times else 0.0
            }
        }

    def _calculate_in_transit_analysis(self, scenario_id: int) -> Dict:
        """Calculate in-transit inventory metrics."""
        # Get current in-transit by site
        tos_in_transit = self.db.query(
            TransferOrder.destination_site_id,
            func.sum(TransferOrderLineItem.shipped_quantity).label("total_qty")
        ).join(
            TransferOrderLineItem,
            TransferOrder.id == TransferOrderLineItem.to_id
        ).filter(
            and_(
                TransferOrder.scenario_id == scenario_id,
                TransferOrder.status == "IN_TRANSIT"
            )
        ).group_by(TransferOrder.destination_site_id).all()

        in_transit_by_site = {
            site_id: qty for site_id, qty in tos_in_transit
        }

        # Total in-transit
        total_in_transit = sum(in_transit_by_site.values())

        # Average in-transit over time (requires historical data)
        # For now, just current snapshot
        return {
            "current_in_transit_total": total_in_transit,
            "in_transit_by_site": in_transit_by_site,
            "num_sites_with_in_transit": len(in_transit_by_site)
        }

    def _calculate_throughput(self, scenario_id: int) -> Dict:
        """Calculate TO throughput (TOs per round)."""
        # Group TOs by order_round
        tos_by_round = self.db.query(
            TransferOrder.order_round,
            func.count(TransferOrder.id).label("to_count"),
            func.sum(TransferOrderLineItem.shipped_quantity).label("total_qty")
        ).join(
            TransferOrderLineItem,
            TransferOrder.id == TransferOrderLineItem.to_id
        ).filter(
            TransferOrder.scenario_id == scenario_id
        ).group_by(TransferOrder.order_round).all()

        throughput_by_round = {
            round_num: {"to_count": count, "quantity": qty}
            for round_num, count, qty in tos_by_round if round_num is not None
        }

        # Calculate average throughput
        total_rounds = len(throughput_by_round)
        total_tos = sum(r["to_count"] for r in throughput_by_round.values())
        avg_tos_per_round = total_tos / total_rounds if total_rounds > 0 else 0.0

        return {
            "avg_tos_per_round": avg_tos_per_round,
            "total_rounds": total_rounds,
            "throughput_by_round": throughput_by_round
        }

    def _calculate_route_metrics(self, scenario_id: int) -> Dict:
        """Calculate metrics by route (source → destination)."""
        # Group TOs by route
        route_stats = self.db.query(
            TransferOrder.source_site_id,
            TransferOrder.destination_site_id,
            func.count(TransferOrder.id).label("to_count"),
            func.sum(TransferOrderLineItem.shipped_quantity).label("total_qty"),
            func.avg(
                case(
                    (TransferOrder.status == "RECEIVED",
                     func.julianday(TransferOrder.actual_delivery_date) -
                     func.julianday(TransferOrder.shipment_date)),
                    else_=None
                )
            ).label("avg_lead_time")
        ).join(
            TransferOrderLineItem,
            TransferOrder.id == TransferOrderLineItem.to_id
        ).filter(
            TransferOrder.scenario_id == scenario_id
        ).group_by(
            TransferOrder.source_site_id,
            TransferOrder.destination_site_id
        ).all()

        routes = []
        for source, dest, count, qty, avg_lt in route_stats:
            routes.append({
                "source_site_id": source,
                "destination_site_id": dest,
                "to_count": count,
                "total_quantity": qty or 0.0,
                "avg_quantity_per_to": (qty / count) if count > 0 else 0.0,
                "avg_lead_time_days": avg_lt or 0.0
            })

        # Sort by volume (descending)
        routes.sort(key=lambda r: r["total_quantity"], reverse=True)

        return {
            "total_routes": len(routes),
            "routes": routes
        }

    def _calculate_timeline(self, scenario_id: int) -> Dict:
        """Calculate round-by-round TO timeline."""
        # Get max round
        max_round = self.db.query(
            func.max(TransferOrder.order_round)
        ).filter(
            TransferOrder.scenario_id == scenario_id
        ).scalar() or 0

        timeline = []

        for round_num in range(1, max_round + 1):
            # TOs created this round
            tos_created = self.db.query(func.count(TransferOrder.id)).filter(
                and_(
                    TransferOrder.scenario_id == scenario_id,
                    TransferOrder.order_round == round_num
                )
            ).scalar() or 0

            # TOs received this round
            tos_received = self.db.query(func.count(TransferOrder.id)).filter(
                and_(
                    TransferOrder.scenario_id == scenario_id,
                    TransferOrder.arrival_round == round_num,
                    TransferOrder.status == "RECEIVED"
                )
            ).scalar() or 0

            # Quantity created
            qty_created = self.db.query(
                func.sum(TransferOrderLineItem.shipped_quantity)
            ).join(
                TransferOrder,
                TransferOrderLineItem.to_id == TransferOrder.id
            ).filter(
                and_(
                    TransferOrder.scenario_id == scenario_id,
                    TransferOrder.order_round == round_num
                )
            ).scalar() or 0.0

            # Quantity received
            qty_received = self.db.query(
                func.sum(TransferOrderLineItem.shipped_quantity)
            ).join(
                TransferOrder,
                TransferOrderLineItem.to_id == TransferOrder.id
            ).filter(
                and_(
                    TransferOrder.scenario_id == scenario_id,
                    TransferOrder.arrival_round == round_num,
                    TransferOrder.status == "RECEIVED"
                )
            ).scalar() or 0.0

            timeline.append({
                "round": round_num,
                "tos_created": tos_created,
                "tos_received": tos_received,
                "quantity_created": qty_created,
                "quantity_received": qty_received
            })

        return {
            "max_round": max_round,
            "timeline": timeline
        }

    def export_to_metrics_summary(self, scenario_id: int) -> str:
        """
        Export TO metrics as formatted text summary.

        Args:
            scenario_id: Game ID

        Returns:
            Formatted text summary
        """
        metrics = self.get_game_to_metrics(scenario_id)

        lines = []
        lines.append("=" * 80)
        lines.append(f"TRANSFER ORDER ANALYTICS - GAME {scenario_id}")
        lines.append("=" * 80)
        lines.append("")

        # Summary
        summary = metrics["summary"]
        lines.append("📦 SUMMARY")
        lines.append("-" * 80)
        lines.append(f"Total Transfer Orders: {summary['total_tos']}")
        lines.append(f"Total Quantity Shipped: {summary['total_quantity_shipped']:.2f}")
        lines.append(f"Average Quantity per TO: {summary['avg_quantity_per_to']:.2f}")
        lines.append("")
        lines.append("Status Breakdown:")
        for status, count in summary["status_breakdown"].items():
            pct = (count / summary["total_tos"] * 100) if summary["total_tos"] > 0 else 0
            lines.append(f"  • {status}: {count} ({pct:.1f}%)")
        lines.append("")

        # Delivery Performance
        delivery = metrics["delivery_performance"]
        lines.append("🎯 DELIVERY PERFORMANCE")
        lines.append("-" * 80)
        lines.append(f"On-Time Delivery Rate: {delivery['on_time_delivery_rate']:.2f}%")
        lines.append(f"Total Received: {delivery['total_received']}")
        lines.append(f"  • On-Time: {delivery['on_time_count']}")
        lines.append(f"  • Late: {delivery['late_count']}")
        lines.append(f"  • Early: {delivery['early_count']}")
        lines.append("")

        # Lead Time
        lead_time = metrics["lead_time_analysis"]
        lines.append("⏱️  LEAD TIME ANALYSIS")
        lines.append("-" * 80)

        planned = lead_time["planned_lead_time"]
        lines.append(f"Planned Lead Time:")
        lines.append(f"  • Average: {planned['avg']:.2f} days")
        lines.append(f"  • Min: {planned['min']:.0f} days")
        lines.append(f"  • Max: {planned['max']:.0f} days")
        lines.append(f"  • Median: {planned['median']:.2f} days")

        actual = lead_time["actual_lead_time"]
        if actual["count"] > 0:
            lines.append(f"Actual Lead Time:")
            lines.append(f"  • Average: {actual['avg']:.2f} days")
            lines.append(f"  • Min: {actual['min']:.0f} days")
            lines.append(f"  • Max: {actual['max']:.0f} days")
            lines.append(f"  • Median: {actual['median']:.2f} days")
        lines.append("")

        # In-Transit
        in_transit = metrics["in_transit_analysis"]
        lines.append("🚛 IN-TRANSIT INVENTORY")
        lines.append("-" * 80)
        lines.append(f"Current In-Transit Total: {in_transit['current_in_transit_total']:.2f}")
        lines.append(f"Sites with In-Transit: {in_transit['num_sites_with_in_transit']}")
        if in_transit["in_transit_by_site"]:
            lines.append("In-Transit by Site:")
            for site_id, qty in sorted(
                in_transit["in_transit_by_site"].items(),
                key=lambda x: x[1],
                reverse=True
            ):
                lines.append(f"  • {site_id}: {qty:.2f}")
        lines.append("")

        # Throughput
        throughput = metrics["throughput"]
        lines.append("📈 THROUGHPUT")
        lines.append("-" * 80)
        lines.append(f"Average TOs per Round: {throughput['avg_tos_per_round']:.2f}")
        lines.append(f"Total Rounds: {throughput['total_rounds']}")
        lines.append("")

        # Top Routes
        if "route_analysis" in metrics:
            routes = metrics["route_analysis"]
            lines.append("🛣️  TOP ROUTES")
            lines.append("-" * 80)
            lines.append(f"Total Routes: {routes['total_routes']}")
            lines.append("")
            lines.append("Top 5 Routes by Volume:")
            for i, route in enumerate(routes["routes"][:5], 1):
                lines.append(
                    f"  {i}. {route['source_site_id']} → {route['destination_site_id']}: "
                    f"{route['total_quantity']:.2f} units "
                    f"({route['to_count']} TOs, "
                    f"avg {route['avg_lead_time_days']:.1f} days)"
                )
            lines.append("")

        lines.append("=" * 80)

        return "\n".join(lines)
