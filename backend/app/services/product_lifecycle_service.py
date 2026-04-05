"""Product Lifecycle Service — tenant-scoped CRUD and workflow management.

Manages product lifecycle, NPI projects, EOL plans, and markdown/clearance.
Integrates with AWS SC entities: product, product_bom, forecast, inv_policy,
vendor_product, sourcing_rules, supplementary_time_series.
"""

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_lifecycle import (
    ProductLifecycle, NPIProject, EOLPlan, MarkdownPlan, LifecycleHistory,
)
from app.core.clock import tenant_today

logger = logging.getLogger(__name__)


class ProductLifecycleService:
    """Tenant-scoped product lifecycle management service."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def get_lifecycle(self, product_id: str) -> Optional[ProductLifecycle]:
        """Get lifecycle record for a product."""
        stmt = select(ProductLifecycle).where(
            and_(
                ProductLifecycle.tenant_id == self.tenant_id,
                ProductLifecycle.product_id == product_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def set_lifecycle_stage(
        self, product_id: str, stage: str, user_id: int,
        config_id: int = None, notes: str = None,
    ) -> ProductLifecycle:
        """Create or update lifecycle stage for a product."""
        from app.models.product_lifecycle import LIFECYCLE_STAGES
        if stage not in LIFECYCLE_STAGES:
            raise ValueError(f"Invalid lifecycle stage: {stage}")

        lc = await self.get_lifecycle(product_id)
        if lc:
            prev_stage = lc.lifecycle_stage
            lc.lifecycle_stage = stage
            lc.stage_entered_at = datetime.utcnow()
            if notes:
                lc.notes = notes
            await self._add_history(
                "lifecycle", lc.id, "stage_changed", user_id,
                previous_value={"stage": prev_stage},
                new_value={"stage": stage},
            )
        else:
            lc = ProductLifecycle(
                tenant_id=self.tenant_id,
                config_id=config_id,
                product_id=product_id,
                lifecycle_stage=stage,
                stage_entered_at=datetime.utcnow(),
                notes=notes,
                created_by=user_id,
            )
            self.db.add(lc)
            await self.db.flush()
            await self._add_history("lifecycle", lc.id, "created", user_id, new_value={"stage": stage})

        await self.db.commit()
        await self.db.refresh(lc)
        return lc

    async def get_all_lifecycles(
        self, stage: str = None, config_id: int = None,
        limit: int = 50, offset: int = 0,
    ) -> list:
        """Get all lifecycle records with optional filtering."""
        stmt = select(ProductLifecycle).where(ProductLifecycle.tenant_id == self.tenant_id)
        if stage:
            stmt = stmt.where(ProductLifecycle.lifecycle_stage == stage)
        if config_id:
            stmt = stmt.where(ProductLifecycle.config_id == config_id)
        stmt = stmt.order_by(ProductLifecycle.updated_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_lifecycle_summary(self) -> dict:
        """Counts by lifecycle stage."""
        stmt = (
            select(ProductLifecycle.lifecycle_stage, func.count(ProductLifecycle.id))
            .where(ProductLifecycle.tenant_id == self.tenant_id)
            .group_by(ProductLifecycle.lifecycle_stage)
        )
        result = await self.db.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    # =========================================================================
    # NPI
    # =========================================================================

    async def create_npi_project(self, data: dict, user_id: int) -> NPIProject:
        """Create a new NPI project."""
        npi = NPIProject(
            tenant_id=self.tenant_id,
            config_id=data.get("config_id"),
            lifecycle_id=data.get("lifecycle_id"),
            project_name=data["project_name"],
            project_code=data.get("project_code"),
            status="planning",
            target_launch_date=data["target_launch_date"],
            product_ids=data.get("product_ids"),
            site_ids=data.get("site_ids"),
            channel_ids=data.get("channel_ids"),
            demand_ramp_curve=data.get("demand_ramp_curve"),
            initial_forecast_qty=data.get("initial_forecast_qty"),
            supplier_qualification_status=data.get("supplier_qualification_status"),
            quality_gates=data.get("quality_gates"),
            investment=data.get("investment"),
            expected_revenue_yr1=data.get("expected_revenue_yr1"),
            risk_assessment=data.get("risk_assessment"),
            owner_user_id=user_id,
            notes=data.get("notes"),
        )
        self.db.add(npi)
        await self.db.flush()
        await self._add_history("npi", npi.id, "created", user_id, new_value={"status": "planning"})
        await self.db.commit()
        await self.db.refresh(npi)
        return npi

    async def update_npi_project(self, npi_id: int, data: dict, user_id: int) -> Optional[NPIProject]:
        """Update NPI project fields."""
        npi = await self.get_npi_project(npi_id)
        if not npi:
            return None

        changes = {}
        for field in [
            "project_name", "project_code", "target_launch_date", "product_ids",
            "site_ids", "channel_ids", "demand_ramp_curve", "initial_forecast_qty",
            "supplier_qualification_status", "quality_gates", "investment",
            "expected_revenue_yr1", "risk_assessment", "notes", "config_id", "lifecycle_id",
        ]:
            if field in data and data[field] != getattr(npi, field):
                changes[field] = str(data[field])
                setattr(npi, field, data[field])

        if changes:
            await self._add_history("npi", npi.id, "updated", user_id, new_value=changes)
            await self.db.commit()
            await self.db.refresh(npi)
        return npi

    async def get_npi_projects(self, status: str = None, limit: int = 50, offset: int = 0) -> list:
        """Get NPI projects with optional status filter."""
        stmt = select(NPIProject).where(NPIProject.tenant_id == self.tenant_id)
        if status:
            stmt = stmt.where(NPIProject.status == status)
        stmt = stmt.order_by(NPIProject.target_launch_date).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_npi_project(self, npi_id: int) -> Optional[NPIProject]:
        """Get single NPI project with tenant check."""
        stmt = select(NPIProject).where(
            and_(NPIProject.id == npi_id, NPIProject.tenant_id == self.tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_quality_gate(
        self, npi_id: int, gate_name: str, gate_status: str, user_id: int,
    ) -> Optional[NPIProject]:
        """Update a quality gate status in the NPI project."""
        npi = await self.get_npi_project(npi_id)
        if not npi:
            return None

        _today = await tenant_today(self.tenant_id, self.db)
        gates = npi.quality_gates or []
        found = False
        for gate in gates:
            if gate.get("gate") == gate_name:
                gate["status"] = gate_status
                gate["date"] = _today.isoformat()
                found = True
                break
        if not found:
            gates.append({"gate": gate_name, "status": gate_status, "date": _today.isoformat()})

        npi.quality_gates = gates
        await self._add_history(
            "npi", npi.id, "quality_gate_updated", user_id,
            new_value={"gate": gate_name, "status": gate_status},
        )
        await self.db.commit()
        await self.db.refresh(npi)
        return npi

    async def launch_product(self, npi_id: int, user_id: int) -> Optional[NPIProject]:
        """Launch a product (NPI complete → lifecycle stage = 'launch')."""
        npi = await self.get_npi_project(npi_id)
        if not npi:
            return None
        if npi.status not in ("ramp_up", "pilot"):
            raise ValueError(f"Cannot launch from '{npi.status}' status (must be pilot or ramp_up)")

        npi.status = "launched"
        npi.actual_launch_date = await tenant_today(self.tenant_id, self.db)
        await self._add_history("npi", npi.id, "launched", user_id)

        # Update lifecycle stage for associated products
        if npi.product_ids:
            for pid in npi.product_ids:
                await self.set_lifecycle_stage(pid, "launch", user_id, config_id=npi.config_id)

        await self.db.commit()
        await self.db.refresh(npi)
        return npi

    # =========================================================================
    # EOL
    # =========================================================================

    async def create_eol_plan(self, data: dict, user_id: int) -> EOLPlan:
        """Create a new EOL plan."""
        eol = EOLPlan(
            tenant_id=self.tenant_id,
            config_id=data.get("config_id"),
            lifecycle_id=data.get("lifecycle_id"),
            status="planning",
            product_ids=data.get("product_ids"),
            successor_product_ids=data.get("successor_product_ids"),
            last_buy_date=data.get("last_buy_date"),
            last_manufacture_date=data.get("last_manufacture_date"),
            last_ship_date=data.get("last_ship_date"),
            demand_phaseout_curve=data.get("demand_phaseout_curve"),
            disposition_plan=data.get("disposition_plan"),
            remaining_inventory=data.get("remaining_inventory"),
            notification_sent_to=data.get("notification_sent_to"),
            estimated_write_off=data.get("estimated_write_off"),
            owner_user_id=user_id,
            notes=data.get("notes"),
        )
        self.db.add(eol)
        await self.db.flush()
        await self._add_history("eol", eol.id, "created", user_id, new_value={"status": "planning"})
        await self.db.commit()
        await self.db.refresh(eol)
        return eol

    async def update_eol_plan(self, eol_id: int, data: dict, user_id: int) -> Optional[EOLPlan]:
        """Update EOL plan fields."""
        eol = await self.get_eol_plan(eol_id)
        if not eol:
            return None

        changes = {}
        for field in [
            "product_ids", "successor_product_ids", "last_buy_date",
            "last_manufacture_date", "last_ship_date", "demand_phaseout_curve",
            "disposition_plan", "remaining_inventory", "notification_sent_to",
            "estimated_write_off", "actual_write_off", "notes", "config_id", "lifecycle_id",
        ]:
            if field in data and data[field] != getattr(eol, field):
                changes[field] = str(data[field])
                setattr(eol, field, data[field])

        if changes:
            await self._add_history("eol", eol.id, "updated", user_id, new_value=changes)
            await self.db.commit()
            await self.db.refresh(eol)
        return eol

    async def get_eol_plans(self, status: str = None, limit: int = 50, offset: int = 0) -> list:
        """Get EOL plans with optional status filter."""
        stmt = select(EOLPlan).where(EOLPlan.tenant_id == self.tenant_id)
        if status:
            stmt = stmt.where(EOLPlan.status == status)
        stmt = stmt.order_by(EOLPlan.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_eol_plan(self, eol_id: int) -> Optional[EOLPlan]:
        """Get single EOL plan with tenant check."""
        stmt = select(EOLPlan).where(
            and_(EOLPlan.id == eol_id, EOLPlan.tenant_id == self.tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def approve_eol_plan(self, eol_id: int, user_id: int) -> Optional[EOLPlan]:
        """Approve an EOL plan."""
        eol = await self.get_eol_plan(eol_id)
        if not eol:
            return None
        if eol.status != "planning":
            raise ValueError(f"Cannot approve EOL plan in '{eol.status}' status")

        eol.status = "approved"
        await self._add_history("eol", eol.id, "approved", user_id)

        # Update lifecycle stage for affected products
        if eol.product_ids:
            for pid in eol.product_ids:
                await self.set_lifecycle_stage(pid, "eol", user_id, config_id=eol.config_id)

        await self.db.commit()
        await self.db.refresh(eol)
        return eol

    async def complete_eol_plan(self, eol_id: int, user_id: int) -> Optional[EOLPlan]:
        """Complete an EOL plan (products are now discontinued)."""
        eol = await self.get_eol_plan(eol_id)
        if not eol:
            return None
        if eol.status not in ("approved", "in_progress"):
            raise ValueError(f"Cannot complete EOL plan in '{eol.status}' status")

        eol.status = "completed"
        await self._add_history("eol", eol.id, "completed", user_id)

        # Update lifecycle stage → discontinued
        if eol.product_ids:
            for pid in eol.product_ids:
                await self.set_lifecycle_stage(pid, "discontinued", user_id, config_id=eol.config_id)

        await self.db.commit()
        await self.db.refresh(eol)
        return eol

    # =========================================================================
    # Markdown
    # =========================================================================

    async def create_markdown_plan(self, data: dict, user_id: int) -> MarkdownPlan:
        """Create a new markdown/clearance plan."""
        md = MarkdownPlan(
            tenant_id=self.tenant_id,
            config_id=data.get("config_id"),
            eol_plan_id=data.get("eol_plan_id"),
            name=data["name"],
            status="draft",
            product_ids=data.get("product_ids"),
            site_ids=data.get("site_ids"),
            channel_ids=data.get("channel_ids"),
            markdown_schedule=data.get("markdown_schedule"),
            original_price=data.get("original_price"),
            floor_price=data.get("floor_price"),
            target_sell_through_pct=data.get("target_sell_through_pct", 100),
            disposition_if_unsold=data.get("disposition_if_unsold", "scrap"),
            start_date=data["start_date"],
            end_date=data["end_date"],
            owner_user_id=user_id,
            notes=data.get("notes"),
        )
        self.db.add(md)
        await self.db.flush()
        await self._add_history("markdown", md.id, "created", user_id, new_value={"status": "draft"})
        await self.db.commit()
        await self.db.refresh(md)
        return md

    async def update_markdown_plan(self, md_id: int, data: dict, user_id: int) -> Optional[MarkdownPlan]:
        """Update markdown plan fields."""
        md = await self.get_markdown_plan(md_id)
        if not md:
            return None

        changes = {}
        for field in [
            "name", "product_ids", "site_ids", "channel_ids", "markdown_schedule",
            "original_price", "floor_price", "target_sell_through_pct",
            "disposition_if_unsold", "start_date", "end_date", "notes",
            "config_id", "eol_plan_id",
        ]:
            if field in data and data[field] != getattr(md, field):
                changes[field] = str(data[field])
                setattr(md, field, data[field])

        if changes:
            await self._add_history("markdown", md.id, "updated", user_id, new_value=changes)
            await self.db.commit()
            await self.db.refresh(md)
        return md

    async def get_markdown_plans(
        self, status: str = None, eol_plan_id: int = None,
        limit: int = 50, offset: int = 0,
    ) -> list:
        """Get markdown plans with optional filters."""
        stmt = select(MarkdownPlan).where(MarkdownPlan.tenant_id == self.tenant_id)
        if status:
            stmt = stmt.where(MarkdownPlan.status == status)
        if eol_plan_id:
            stmt = stmt.where(MarkdownPlan.eol_plan_id == eol_plan_id)
        stmt = stmt.order_by(MarkdownPlan.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_markdown_plan(self, md_id: int) -> Optional[MarkdownPlan]:
        """Get single markdown plan with tenant check."""
        stmt = select(MarkdownPlan).where(
            and_(MarkdownPlan.id == md_id, MarkdownPlan.tenant_id == self.tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def activate_markdown(self, md_id: int, user_id: int) -> Optional[MarkdownPlan]:
        """Activate a markdown plan."""
        md = await self.get_markdown_plan(md_id)
        if not md:
            return None
        if md.status not in ("draft", "approved"):
            raise ValueError(f"Cannot activate markdown plan in '{md.status}' status")

        md.status = "active"
        await self._add_history("markdown", md.id, "activated", user_id)
        await self.db.commit()
        await self.db.refresh(md)
        return md

    async def update_sell_through(
        self, md_id: int, units_sold: float, revenue: float, units_remaining: float,
    ) -> Optional[MarkdownPlan]:
        """Update sell-through metrics on a markdown plan."""
        md = await self.get_markdown_plan(md_id)
        if not md:
            return None

        md.units_sold = units_sold
        md.revenue_recovered = revenue
        md.units_remaining = units_remaining

        total_units = (units_sold or 0) + (units_remaining or 0)
        if total_units > 0:
            md.actual_sell_through_pct = round((units_sold or 0) / total_units * 100, 1)

        await self.db.commit()
        await self.db.refresh(md)
        return md

    # =========================================================================
    # Dashboard
    # =========================================================================

    async def get_dashboard(self) -> dict:
        """Unified dashboard stats across all lifecycle entities."""
        lifecycle_summary = await self.get_lifecycle_summary()

        # NPI by status
        npi_stmt = (
            select(NPIProject.status, func.count(NPIProject.id))
            .where(NPIProject.tenant_id == self.tenant_id)
            .group_by(NPIProject.status)
        )
        npi_result = await self.db.execute(npi_stmt)
        npi_by_status = {row[0]: row[1] for row in npi_result.all()}

        # EOL by status
        eol_stmt = (
            select(EOLPlan.status, func.count(EOLPlan.id))
            .where(EOLPlan.tenant_id == self.tenant_id)
            .group_by(EOLPlan.status)
        )
        eol_result = await self.db.execute(eol_stmt)
        eol_by_status = {row[0]: row[1] for row in eol_result.all()}

        # Markdown by status
        md_stmt = (
            select(MarkdownPlan.status, func.count(MarkdownPlan.id))
            .where(MarkdownPlan.tenant_id == self.tenant_id)
            .group_by(MarkdownPlan.status)
        )
        md_result = await self.db.execute(md_stmt)
        md_by_status = {row[0]: row[1] for row in md_result.all()}

        return {
            "lifecycle_by_stage": lifecycle_summary,
            "npi_by_status": npi_by_status,
            "eol_by_status": eol_by_status,
            "markdown_by_status": md_by_status,
            "total_products_tracked": sum(lifecycle_summary.values()),
            "npi_active": sum(v for k, v in npi_by_status.items() if k not in ("launched", "cancelled")),
            "eol_active": sum(v for k, v in eol_by_status.items() if k not in ("completed", "cancelled")),
            "markdown_active": md_by_status.get("active", 0),
        }

    # =========================================================================
    # History
    # =========================================================================

    async def get_history(self, entity_type: str = None, entity_id: int = None, limit: int = 50) -> list:
        """Get audit trail with optional entity filter."""
        stmt = select(LifecycleHistory).where(LifecycleHistory.tenant_id == self.tenant_id)
        if entity_type:
            stmt = stmt.where(LifecycleHistory.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(LifecycleHistory.entity_id == entity_id)
        stmt = stmt.order_by(LifecycleHistory.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _add_history(
        self, entity_type: str, entity_id: int, action: str, user_id: int,
        previous_value: dict = None, new_value: dict = None,
    ):
        """Add an audit history entry."""
        entry = LifecycleHistory(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changed_by=user_id,
            previous_value=previous_value,
            new_value=new_value,
        )
        self.db.add(entry)
