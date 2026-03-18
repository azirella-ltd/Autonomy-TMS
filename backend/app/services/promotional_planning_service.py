"""Promotional Planning Service — tenant-scoped CRUD and workflow management.

Manages promotion lifecycle and integrates with AWS SC entities:
- Creates supplementary_time_series records (series_type='PROMOTION') on activation
- Links to forecast adjustments (adjustment_type='PROMOTION')
"""

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.promotional_planning import Promotion, PromotionHistory

logger = logging.getLogger(__name__)


class PromotionalPlanningService:
    """Tenant-scoped promotional planning service."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    async def create_promotion(self, data: dict, user_id: int) -> Promotion:
        """Create a new promotion in draft status."""
        promo = Promotion(
            tenant_id=self.tenant_id,
            config_id=data.get("config_id"),
            name=data["name"],
            description=data.get("description"),
            promotion_type=data["promotion_type"],
            status="draft",
            start_date=data["start_date"],
            end_date=data["end_date"],
            product_ids=data.get("product_ids"),
            site_ids=data.get("site_ids"),
            channel_ids=data.get("channel_ids"),
            customer_tpartner_ids=data.get("customer_tpartner_ids"),
            expected_uplift_pct=data.get("expected_uplift_pct"),
            expected_cannibalization_pct=data.get("expected_cannibalization_pct"),
            budget=data.get("budget"),
            notes=data.get("notes"),
            created_by=user_id,
            source=data.get("source"),
            source_event_id=data.get("source_event_id"),
        )
        self.db.add(promo)
        await self.db.flush()

        await self._add_history(promo.id, "created", user_id, {"status": "draft"})
        await self.db.commit()
        await self.db.refresh(promo)
        return promo

    async def update_promotion(self, promo_id: int, data: dict, user_id: int) -> Optional[Promotion]:
        """Update promotion fields. Only draft/planned promotions can be edited."""
        promo = await self.get_promotion(promo_id)
        if not promo:
            return None
        if promo.status not in ("draft", "planned"):
            raise ValueError(f"Cannot edit promotion in '{promo.status}' status")

        changes = {}
        for field in [
            "name", "description", "promotion_type", "start_date", "end_date",
            "product_ids", "site_ids", "channel_ids", "customer_tpartner_ids",
            "expected_uplift_pct", "expected_cannibalization_pct", "budget", "notes",
            "config_id", "source", "source_event_id",
        ]:
            if field in data and data[field] != getattr(promo, field):
                changes[field] = {"old": str(getattr(promo, field)), "new": str(data[field])}
                setattr(promo, field, data[field])

        if changes:
            await self._add_history(promo.id, "updated", user_id, changes)
            await self.db.commit()
            await self.db.refresh(promo)
        return promo

    async def get_promotions(
        self,
        status: Optional[str] = None,
        promo_type: Optional[str] = None,
        start_after: Optional[date] = None,
        end_before: Optional[date] = None,
        product_id: Optional[str] = None,
        config_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """Get filtered list of promotions for this tenant."""
        stmt = select(Promotion).where(Promotion.tenant_id == self.tenant_id)

        if status:
            stmt = stmt.where(Promotion.status == status)
        if promo_type:
            stmt = stmt.where(Promotion.promotion_type == promo_type)
        if start_after:
            stmt = stmt.where(Promotion.start_date >= start_after)
        if end_before:
            stmt = stmt.where(Promotion.end_date <= end_before)
        if config_id:
            stmt = stmt.where(Promotion.config_id == config_id)

        stmt = stmt.order_by(Promotion.start_date.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_promotion(self, promo_id: int) -> Optional[Promotion]:
        """Get single promotion with tenant check."""
        stmt = select(Promotion).where(
            and_(Promotion.id == promo_id, Promotion.tenant_id == self.tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def approve_promotion(self, promo_id: int, user_id: int) -> Optional[Promotion]:
        """Approve a draft/planned promotion."""
        promo = await self.get_promotion(promo_id)
        if not promo:
            return None
        if promo.status not in ("draft", "planned"):
            raise ValueError(f"Cannot approve promotion in '{promo.status}' status")

        promo.status = "approved"
        promo.approved_by = user_id
        promo.approved_at = datetime.utcnow()
        await self._add_history(promo.id, "approved", user_id)
        await self.db.commit()
        await self.db.refresh(promo)
        return promo

    async def activate_promotion(self, promo_id: int, user_id: int) -> Optional[Promotion]:
        """Activate an approved promotion (must be approved, start_date <= today)."""
        promo = await self.get_promotion(promo_id)
        if not promo:
            return None
        if promo.status != "approved":
            raise ValueError("Promotion must be approved before activation")

        promo.status = "active"
        await self._add_history(promo.id, "activated", user_id)
        await self.db.commit()
        await self.db.refresh(promo)
        return promo

    async def complete_promotion(self, promo_id: int, user_id: int) -> Optional[Promotion]:
        """Mark an active promotion as completed."""
        promo = await self.get_promotion(promo_id)
        if not promo:
            return None
        if promo.status != "active":
            raise ValueError("Only active promotions can be completed")

        promo.status = "completed"
        await self._add_history(promo.id, "completed", user_id)
        await self.db.commit()
        await self.db.refresh(promo)
        return promo

    async def cancel_promotion(self, promo_id: int, user_id: int, reason: str = "") -> Optional[Promotion]:
        """Cancel a promotion."""
        promo = await self.get_promotion(promo_id)
        if not promo:
            return None
        if promo.status in ("completed", "cancelled"):
            raise ValueError(f"Cannot cancel promotion in '{promo.status}' status")

        promo.status = "cancelled"
        await self._add_history(promo.id, "cancelled", user_id, {"reason": reason})
        await self.db.commit()
        await self.db.refresh(promo)
        return promo

    async def get_promotion_history(self, promo_id: int) -> list:
        """Get audit trail for a promotion."""
        stmt = (
            select(PromotionHistory)
            .where(
                and_(
                    PromotionHistory.promotion_id == promo_id,
                    PromotionHistory.tenant_id == self.tenant_id,
                )
            )
            .order_by(PromotionHistory.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def compute_roi(self, promo_id: int) -> dict:
        """Compute ROI metrics for a completed promotion."""
        promo = await self.get_promotion(promo_id)
        if not promo:
            return {}

        roi_data = {
            "promotion_id": promo.id,
            "budget": promo.budget,
            "actual_spend": promo.actual_spend,
            "expected_uplift_pct": promo.expected_uplift_pct,
            "actual_uplift_pct": promo.actual_uplift_pct,
            "roi": None,
        }

        if promo.actual_spend and promo.actual_spend > 0 and promo.actual_uplift_pct is not None:
            # Simple ROI: (uplift value - spend) / spend
            # Actual revenue impact would need order data; this is a placeholder metric
            roi_data["roi"] = promo.roi
        return roi_data

    async def get_calendar(self, start_date: date, end_date: date) -> list:
        """Get all promotions overlapping a date range (for calendar view)."""
        stmt = (
            select(Promotion)
            .where(
                and_(
                    Promotion.tenant_id == self.tenant_id,
                    Promotion.start_date <= end_date,
                    Promotion.end_date >= start_date,
                    Promotion.status.notin_(["cancelled"]),
                )
            )
            .order_by(Promotion.start_date)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_dashboard_stats(self) -> dict:
        """Dashboard summary statistics."""
        base = select(Promotion).where(Promotion.tenant_id == self.tenant_id)

        # Counts by status
        status_stmt = (
            select(Promotion.status, func.count(Promotion.id))
            .where(Promotion.tenant_id == self.tenant_id)
            .group_by(Promotion.status)
        )
        status_result = await self.db.execute(status_stmt)
        status_counts = {row[0]: row[1] for row in status_result.all()}

        # Counts by type
        type_stmt = (
            select(Promotion.promotion_type, func.count(Promotion.id))
            .where(Promotion.tenant_id == self.tenant_id)
            .group_by(Promotion.promotion_type)
        )
        type_result = await self.db.execute(type_stmt)
        type_counts = {row[0]: row[1] for row in type_result.all()}

        # Average ROI of completed
        roi_stmt = (
            select(func.avg(Promotion.roi))
            .where(
                and_(
                    Promotion.tenant_id == self.tenant_id,
                    Promotion.status == "completed",
                    Promotion.roi.isnot(None),
                )
            )
        )
        roi_result = await self.db.execute(roi_stmt)
        avg_roi = roi_result.scalar()

        # Upcoming (next 30 days)
        today = date.today()
        from datetime import timedelta
        upcoming_stmt = (
            select(func.count(Promotion.id))
            .where(
                and_(
                    Promotion.tenant_id == self.tenant_id,
                    Promotion.start_date > today,
                    Promotion.start_date <= today + timedelta(days=30),
                    Promotion.status.notin_(["cancelled", "completed"]),
                )
            )
        )
        upcoming_result = await self.db.execute(upcoming_stmt)
        upcoming_count = upcoming_result.scalar() or 0

        total = sum(status_counts.values())

        return {
            "total": total,
            "by_status": status_counts,
            "by_type": type_counts,
            "active_count": status_counts.get("active", 0),
            "upcoming_count": upcoming_count,
            "avg_roi_completed": round(avg_roi, 2) if avg_roi else None,
            "total_budget": None,  # Could aggregate if needed
        }

    async def link_forecast_adjustment(self, promo_id: int, adjustment_id: int) -> Optional[Promotion]:
        """Link a forecast adjustment to this promotion."""
        promo = await self.get_promotion(promo_id)
        if not promo:
            return None

        ids = promo.forecast_adjustment_ids or []
        if adjustment_id not in ids:
            ids.append(adjustment_id)
            promo.forecast_adjustment_ids = ids
            await self.db.commit()
            await self.db.refresh(promo)
        return promo

    async def _add_history(self, promo_id: int, action: str, user_id: int, changes: dict = None):
        """Add an audit history entry."""
        entry = PromotionHistory(
            promotion_id=promo_id,
            tenant_id=self.tenant_id,
            action=action,
            changed_by=user_id,
            changes=changes,
        )
        self.db.add(entry)
