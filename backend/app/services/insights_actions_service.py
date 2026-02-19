"""
Insights & Actions Service - AIIO Framework Implementation

Central service for the insights-driven landing page with hierarchy drill-down.
Implements the Automate, Inform, Inspect, Override (AIIO) framework.

AIIO Workflow:
1. Agents call record_action() to log decisions (AUTOMATE or INFORM mode)
2. Users see actions on the insights dashboard filtered by their scope
3. Users can INSPECT any action to see explanation and alternatives
4. Users can OVERRIDE actions with a mandatory reason (for audit/learning)

Hierarchy Support:
- Actions are tagged with site_key, product_key, time_key
- Dashboard can be viewed at any hierarchy level
- Drill-down navigates from Company→Region→Country→Site
- User scope restricts visibility based on assigned hierarchy nodes
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from collections import defaultdict

from sqlalchemy import select, and_, or_, func, desc, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent_action import (
    AgentAction, ActionMode, ActionCategory, ExecutionResult
)
from app.models.planning_hierarchy import (
    SiteHierarchyLevel, ProductHierarchyLevel, TimeBucketType,
    SiteHierarchyNode, ProductHierarchyNode
)
from app.models.user import User
from app.schemas.insights import (
    HierarchyContext, HierarchyBreadcrumb, HierarchyBreadcrumbs,
    ActionCreate, ActionSummary, ActionDetail, ActionFilters,
    ActionCountsByMode, ActionCountsByCategory, ActionCountsByStatus,
    DashboardSummary, DrillDownChild
)

logger = logging.getLogger(__name__)


# Hierarchy level ordering for drill-down
SITE_LEVEL_ORDER = [
    SiteHierarchyLevel.COMPANY,
    SiteHierarchyLevel.REGION,
    SiteHierarchyLevel.COUNTRY,
    SiteHierarchyLevel.STATE,
    SiteHierarchyLevel.SITE
]

PRODUCT_LEVEL_ORDER = [
    ProductHierarchyLevel.CATEGORY,
    ProductHierarchyLevel.FAMILY,
    ProductHierarchyLevel.GROUP,
    ProductHierarchyLevel.PRODUCT
]

TIME_BUCKET_ORDER = [
    TimeBucketType.YEAR,
    TimeBucketType.QUARTER,
    TimeBucketType.MONTH,
    TimeBucketType.WEEK,
    TimeBucketType.DAY,
    TimeBucketType.HOUR
]


class InsightsActionsService:
    """
    Service for managing agent actions and the insights dashboard.

    Provides:
    1. Dashboard summary at any hierarchy level
    2. Action queries with filtering and user scope
    3. Action recording for agents
    4. Acknowledge/Override workflows
    5. Hierarchy drill-down navigation
    """

    def __init__(self, db: AsyncSession, group_id: int, user: Optional[User] = None):
        """
        Initialize the service.

        Args:
            db: Database session
            group_id: Group ID for filtering
            user: Current user (for scope filtering)
        """
        self.db = db
        self.group_id = group_id
        self.user = user

        # Cache for hierarchy lookups
        self._site_hierarchy: Dict[str, Dict] = {}
        self._product_hierarchy: Dict[str, Dict] = {}
        self._hierarchies_loaded = False

    # =========================================================================
    # Hierarchy Loading
    # =========================================================================

    async def _load_hierarchies(self):
        """Load site and product hierarchies for breadcrumb building."""
        if self._hierarchies_loaded:
            return

        # Load site hierarchy
        result = await self.db.execute(
            select(SiteHierarchyNode).where(
                SiteHierarchyNode.group_id == self.group_id
            )
        )
        for node in result.scalars().all():
            self._site_hierarchy[node.code] = {
                'code': node.code,
                'name': node.name,
                'level': node.hierarchy_level,
                'path': node.hierarchy_path,
                'parent_id': node.parent_id
            }

        # Load product hierarchy
        result = await self.db.execute(
            select(ProductHierarchyNode).where(
                ProductHierarchyNode.group_id == self.group_id
            )
        )
        for node in result.scalars().all():
            self._product_hierarchy[node.code] = {
                'code': node.code,
                'name': node.name,
                'level': node.hierarchy_level,
                'path': node.hierarchy_path,
                'parent_id': node.parent_id
            }

        self._hierarchies_loaded = True

    def _build_breadcrumbs(self, context: HierarchyContext) -> HierarchyBreadcrumbs:
        """Build breadcrumb trails for the current context."""
        site_crumbs = []
        product_crumbs = []
        time_crumbs = []

        # Site breadcrumbs
        current_level_idx = SITE_LEVEL_ORDER.index(context.site_level)
        for i, level in enumerate(SITE_LEVEL_ORDER[:current_level_idx + 1]):
            is_current = (i == current_level_idx)
            site_crumbs.append(HierarchyBreadcrumb(
                level=level.value,
                key=context.site_key if is_current else f"all_{level.value}",
                label=context.site_key if is_current and context.site_key else f"All {level.value.title()}s",
                is_current=is_current
            ))

        # Product breadcrumbs
        current_level_idx = PRODUCT_LEVEL_ORDER.index(context.product_level)
        for i, level in enumerate(PRODUCT_LEVEL_ORDER[:current_level_idx + 1]):
            is_current = (i == current_level_idx)
            product_crumbs.append(HierarchyBreadcrumb(
                level=level.value,
                key=context.product_key if is_current else f"all_{level.value}",
                label=context.product_key if is_current and context.product_key else f"All {level.value.title()}s",
                is_current=is_current
            ))

        # Time breadcrumbs
        current_bucket_idx = TIME_BUCKET_ORDER.index(context.time_bucket)
        for i, bucket in enumerate(TIME_BUCKET_ORDER[:current_bucket_idx + 1]):
            is_current = (i == current_bucket_idx)
            time_crumbs.append(HierarchyBreadcrumb(
                level=bucket.value,
                key=context.time_key if is_current else f"all_{bucket.value}",
                label=context.time_key if is_current and context.time_key else f"All {bucket.value.title()}s",
                is_current=is_current
            ))

        return HierarchyBreadcrumbs(
            site=site_crumbs,
            product=product_crumbs,
            time=time_crumbs
        )

    # =========================================================================
    # User Scope Filtering
    # =========================================================================

    def _get_scope_filter(self):
        """
        Build SQLAlchemy filter clause based on user's scope.

        GROUP_ADMIN has full access.
        Other users are filtered by their site_scope and product_scope.
        """
        filters = [AgentAction.group_id == self.group_id]

        if not self.user:
            return and_(*filters)

        # GROUP_ADMIN has full access
        if self.user.has_full_scope:
            return and_(*filters)

        # Apply site scope filter
        if self.user.site_scope and len(self.user.site_scope) > 0:
            filters.append(AgentAction.site_key.in_(self.user.site_scope))

        # Apply product scope filter
        if self.user.product_scope and len(self.user.product_scope) > 0:
            filters.append(AgentAction.product_key.in_(self.user.product_scope))

        return and_(*filters)

    def _apply_hierarchy_filter(self, context: HierarchyContext):
        """Build filter clause for hierarchy context."""
        filters = []

        if context.site_key:
            filters.append(AgentAction.site_key == context.site_key)

        if context.product_key:
            filters.append(AgentAction.product_key == context.product_key)

        if context.time_key:
            filters.append(AgentAction.time_key == context.time_key)

        return and_(*filters) if filters else None

    # =========================================================================
    # Dashboard Summary
    # =========================================================================

    async def get_dashboard_summary(
        self,
        context: Optional[HierarchyContext] = None,
        recent_limit: int = 10
    ) -> DashboardSummary:
        """
        Get dashboard summary at the specified hierarchy level.

        Args:
            context: Hierarchy context for filtering
            recent_limit: Number of recent actions to include

        Returns:
            DashboardSummary with counts and recent actions
        """
        await self._load_hierarchies()

        if context is None:
            context = HierarchyContext()

        # Build base filter with scope
        base_filter = self._get_scope_filter()

        # Add hierarchy filter
        hierarchy_filter = self._apply_hierarchy_filter(context)
        if hierarchy_filter is not None:
            query_filter = and_(base_filter, hierarchy_filter)
        else:
            query_filter = base_filter

        # Get total count
        total_result = await self.db.execute(
            select(func.count(AgentAction.id)).where(query_filter)
        )
        total_actions = total_result.scalar() or 0

        # Get counts by mode
        mode_counts = await self.db.execute(
            select(
                AgentAction.action_mode,
                func.count(AgentAction.id)
            ).where(query_filter).group_by(AgentAction.action_mode)
        )
        by_mode = ActionCountsByMode()
        for mode, count in mode_counts.all():
            if mode == ActionMode.AUTOMATE:
                by_mode.automate = count
            elif mode == ActionMode.INFORM:
                by_mode.inform = count
        by_mode.total = by_mode.automate + by_mode.inform

        # Get counts by category
        category_counts = await self.db.execute(
            select(
                AgentAction.category,
                func.count(AgentAction.id)
            ).where(query_filter).group_by(AgentAction.category)
        )
        by_category = ActionCountsByCategory()
        for category, count in category_counts.all():
            setattr(by_category, category.value, count)

        # Get counts by status
        status_result = await self.db.execute(
            select(
                AgentAction.is_acknowledged,
                AgentAction.is_overridden,
                func.count(AgentAction.id)
            ).where(query_filter).group_by(
                AgentAction.is_acknowledged,
                AgentAction.is_overridden
            )
        )
        by_status = ActionCountsByStatus()
        for is_ack, is_over, count in status_result.all():
            if is_over:
                by_status.overridden += count
            elif is_ack:
                by_status.acknowledged += count
            else:
                by_status.pending_acknowledgment += count

        # Get recent actions
        recent_result = await self.db.execute(
            select(AgentAction)
            .where(query_filter)
            .order_by(desc(AgentAction.executed_at))
            .limit(recent_limit)
        )
        recent_actions = [
            ActionSummary(**action.to_summary_dict())
            for action in recent_result.scalars().all()
        ]

        # Build breadcrumbs
        breadcrumbs = self._build_breadcrumbs(context)

        return DashboardSummary(
            hierarchy_context=context,
            breadcrumbs=breadcrumbs,
            total_actions=total_actions,
            by_mode=by_mode,
            by_category=by_category,
            by_status=by_status,
            recent_actions=recent_actions,
            user_has_full_scope=self.user.has_full_scope if self.user else True,
            user_site_scope=self.user.site_scope if self.user else None,
            user_product_scope=self.user.product_scope if self.user else None
        )

    # =========================================================================
    # Action Queries
    # =========================================================================

    async def get_actions(
        self,
        filters: ActionFilters,
        context: Optional[HierarchyContext] = None
    ) -> Tuple[List[ActionSummary], int]:
        """
        Get actions with filtering and pagination.

        Args:
            filters: Query filters
            context: Hierarchy context

        Returns:
            Tuple of (actions list, total count)
        """
        # Build base filter with scope
        base_filter = self._get_scope_filter()

        # Add hierarchy filter
        if context:
            hierarchy_filter = self._apply_hierarchy_filter(context)
            if hierarchy_filter is not None:
                base_filter = and_(base_filter, hierarchy_filter)

        # Add filter conditions
        filter_conditions = [base_filter]

        if filters.mode:
            filter_conditions.append(AgentAction.action_mode == filters.mode)
        if filters.category:
            filter_conditions.append(AgentAction.category == filters.category)
        if filters.action_type:
            filter_conditions.append(AgentAction.action_type == filters.action_type)
        if filters.acknowledged is not None:
            filter_conditions.append(AgentAction.is_acknowledged == filters.acknowledged)
        if filters.overridden is not None:
            filter_conditions.append(AgentAction.is_overridden == filters.overridden)
        if filters.agent_id:
            filter_conditions.append(AgentAction.agent_id == filters.agent_id)
        if filters.execution_result:
            filter_conditions.append(AgentAction.execution_result == filters.execution_result)
        if filters.date_from:
            filter_conditions.append(AgentAction.executed_at >= filters.date_from)
        if filters.date_to:
            filter_conditions.append(AgentAction.executed_at <= filters.date_to)

        query_filter = and_(*filter_conditions)

        # Get total count
        total_result = await self.db.execute(
            select(func.count(AgentAction.id)).where(query_filter)
        )
        total = total_result.scalar() or 0

        # Get actions with pagination
        result = await self.db.execute(
            select(AgentAction)
            .where(query_filter)
            .order_by(desc(AgentAction.executed_at))
            .offset(filters.offset)
            .limit(filters.limit)
        )
        actions = [
            ActionSummary(**action.to_summary_dict())
            for action in result.scalars().all()
        ]

        return actions, total

    async def get_action_detail(self, action_id: int) -> Optional[ActionDetail]:
        """
        Get full action detail for INSPECT workflow.

        Args:
            action_id: Action ID

        Returns:
            ActionDetail or None if not found/not accessible
        """
        result = await self.db.execute(
            select(AgentAction).where(
                and_(
                    AgentAction.id == action_id,
                    self._get_scope_filter()
                )
            )
        )
        action = result.scalar_one_or_none()

        if not action:
            return None

        return ActionDetail(**action.to_dict())

    # =========================================================================
    # Action Recording (for agents)
    # =========================================================================

    async def record_action(
        self,
        action_data: ActionCreate
    ) -> AgentAction:
        """
        Record a new action taken by an agent.

        Called by TRM, GNN, LLM agents when they make decisions.

        Args:
            action_data: Action creation data

        Returns:
            Created AgentAction record
        """
        action = AgentAction(
            group_id=self.group_id,
            action_mode=action_data.action_mode,
            action_type=action_data.action_type,
            category=action_data.category,
            title=action_data.title,
            description=action_data.description,
            explanation=action_data.explanation,
            reasoning_chain=[s.dict() for s in action_data.reasoning_chain] if action_data.reasoning_chain else None,
            alternatives_considered=[a.dict() for a in action_data.alternatives_considered] if action_data.alternatives_considered else None,
            site_hierarchy_level=action_data.site_hierarchy_level,
            site_key=action_data.site_key,
            product_hierarchy_level=action_data.product_hierarchy_level,
            product_key=action_data.product_key,
            time_bucket=action_data.time_bucket,
            time_key=action_data.time_key,
            metric_name=action_data.metric_name,
            metric_before=action_data.metric_before,
            metric_after=action_data.metric_after,
            estimated_impact=action_data.estimated_impact.dict() if action_data.estimated_impact else None,
            execution_result=action_data.execution_result,
            execution_details=action_data.execution_details,
            agent_id=action_data.agent_id,
            agent_version=action_data.agent_version,
            related_entity_type=action_data.related_entity_type,
            related_entity_id=action_data.related_entity_id,
            executed_at=datetime.utcnow()
        )

        self.db.add(action)
        await self.db.commit()
        await self.db.refresh(action)

        logger.info(f"Recorded agent action: {action.id} - {action.title}")
        return action

    # =========================================================================
    # Acknowledge (for INFORM actions)
    # =========================================================================

    async def acknowledge_action(
        self,
        action_id: int,
        user_id: int
    ) -> Optional[AgentAction]:
        """
        Acknowledge an INFORM action.

        Args:
            action_id: Action ID
            user_id: User performing acknowledgment

        Returns:
            Updated AgentAction or None if not found
        """
        result = await self.db.execute(
            select(AgentAction).where(
                and_(
                    AgentAction.id == action_id,
                    self._get_scope_filter()
                )
            )
        )
        action = result.scalar_one_or_none()

        if not action:
            return None

        action.is_acknowledged = True
        action.acknowledged_by = user_id
        action.acknowledged_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(action)

        logger.info(f"Action {action_id} acknowledged by user {user_id}")
        return action

    # =========================================================================
    # Override (with required reason)
    # =========================================================================

    async def override_action(
        self,
        action_id: int,
        user_id: int,
        reason: str,
        override_action: Optional[Dict[str, Any]] = None
    ) -> Optional[AgentAction]:
        """
        Override an action with a mandatory reason.

        The reason is required for:
        1. Audit trail - compliance and accountability
        2. Learning - improve agent decisions over time

        Args:
            action_id: Action ID
            user_id: User performing override
            reason: REQUIRED reason for the override
            override_action: Optional structured data about what user did instead

        Returns:
            Updated AgentAction or None if not found
        """
        if not reason or len(reason.strip()) < 10:
            raise ValueError("Override reason is required and must be at least 10 characters")

        result = await self.db.execute(
            select(AgentAction).where(
                and_(
                    AgentAction.id == action_id,
                    self._get_scope_filter()
                )
            )
        )
        action = result.scalar_one_or_none()

        if not action:
            return None

        action.is_overridden = True
        action.overridden_by = user_id
        action.overridden_at = datetime.utcnow()
        action.override_reason = reason.strip()
        action.override_action = override_action

        # Also mark as acknowledged if not already
        if not action.is_acknowledged:
            action.is_acknowledged = True
            action.acknowledged_by = user_id
            action.acknowledged_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(action)

        logger.info(f"Action {action_id} overridden by user {user_id}: {reason[:50]}...")
        return action

    # =========================================================================
    # Drill-Down Navigation
    # =========================================================================

    async def get_drill_down_children(
        self,
        context: HierarchyContext,
        dimension: str  # "site", "product", or "time"
    ) -> List[DrillDownChild]:
        """
        Get children for drill-down navigation.

        Args:
            context: Current hierarchy context
            dimension: Which dimension to drill down

        Returns:
            List of DrillDownChild items
        """
        base_filter = self._get_scope_filter()
        hierarchy_filter = self._apply_hierarchy_filter(context)
        if hierarchy_filter is not None:
            query_filter = and_(base_filter, hierarchy_filter)
        else:
            query_filter = base_filter

        if dimension == "site":
            # Get next level down
            current_idx = SITE_LEVEL_ORDER.index(context.site_level)
            if current_idx >= len(SITE_LEVEL_ORDER) - 1:
                return []  # Already at lowest level

            # Group by site_key at current level
            result = await self.db.execute(
                select(
                    AgentAction.site_key,
                    func.count(AgentAction.id).label('total'),
                    func.sum(
                        func.cast(~AgentAction.is_acknowledged, Integer)
                    ).label('pending')
                ).where(query_filter)
                .group_by(AgentAction.site_key)
                .order_by(desc('total'))
            )

            children = []
            for site_key, total, pending in result.all():
                children.append(DrillDownChild(
                    key=site_key,
                    label=site_key,
                    action_count=total,
                    pending_count=pending or 0,
                    can_drill_down=current_idx < len(SITE_LEVEL_ORDER) - 2
                ))
            return children

        elif dimension == "product":
            current_idx = PRODUCT_LEVEL_ORDER.index(context.product_level)
            if current_idx >= len(PRODUCT_LEVEL_ORDER) - 1:
                return []

            result = await self.db.execute(
                select(
                    AgentAction.product_key,
                    func.count(AgentAction.id).label('total'),
                    func.sum(
                        func.cast(~AgentAction.is_acknowledged, Integer)
                    ).label('pending')
                ).where(query_filter)
                .group_by(AgentAction.product_key)
                .order_by(desc('total'))
            )

            children = []
            for product_key, total, pending in result.all():
                children.append(DrillDownChild(
                    key=product_key,
                    label=product_key,
                    action_count=total,
                    pending_count=pending or 0,
                    can_drill_down=current_idx < len(PRODUCT_LEVEL_ORDER) - 2
                ))
            return children

        elif dimension == "time":
            current_idx = TIME_BUCKET_ORDER.index(context.time_bucket)
            if current_idx >= len(TIME_BUCKET_ORDER) - 1:
                return []

            result = await self.db.execute(
                select(
                    AgentAction.time_key,
                    func.count(AgentAction.id).label('total'),
                    func.sum(
                        func.cast(~AgentAction.is_acknowledged, Integer)
                    ).label('pending')
                ).where(query_filter)
                .group_by(AgentAction.time_key)
                .order_by(desc(AgentAction.time_key))
            )

            children = []
            for time_key, total, pending in result.all():
                children.append(DrillDownChild(
                    key=time_key,
                    label=time_key,
                    action_count=total,
                    pending_count=pending or 0,
                    can_drill_down=current_idx < len(TIME_BUCKET_ORDER) - 2
                ))
            return children

        return []

    def drill_down(
        self,
        context: HierarchyContext,
        dimension: str,
        target_key: str
    ) -> HierarchyContext:
        """
        Navigate down one level in a hierarchy dimension.

        Args:
            context: Current context
            dimension: Which dimension to drill down
            target_key: Key to drill into

        Returns:
            New HierarchyContext at the lower level
        """
        new_context = HierarchyContext(
            site_level=context.site_level,
            site_key=context.site_key,
            product_level=context.product_level,
            product_key=context.product_key,
            time_bucket=context.time_bucket,
            time_key=context.time_key
        )

        if dimension == "site":
            current_idx = SITE_LEVEL_ORDER.index(context.site_level)
            if current_idx < len(SITE_LEVEL_ORDER) - 1:
                new_context.site_level = SITE_LEVEL_ORDER[current_idx + 1]
                new_context.site_key = target_key

        elif dimension == "product":
            current_idx = PRODUCT_LEVEL_ORDER.index(context.product_level)
            if current_idx < len(PRODUCT_LEVEL_ORDER) - 1:
                new_context.product_level = PRODUCT_LEVEL_ORDER[current_idx + 1]
                new_context.product_key = target_key

        elif dimension == "time":
            current_idx = TIME_BUCKET_ORDER.index(context.time_bucket)
            if current_idx < len(TIME_BUCKET_ORDER) - 1:
                new_context.time_bucket = TIME_BUCKET_ORDER[current_idx + 1]
                new_context.time_key = target_key

        return new_context

    def drill_up(
        self,
        context: HierarchyContext,
        dimension: str
    ) -> HierarchyContext:
        """
        Navigate up one level in a hierarchy dimension.

        Args:
            context: Current context
            dimension: Which dimension to drill up

        Returns:
            New HierarchyContext at the higher level
        """
        new_context = HierarchyContext(
            site_level=context.site_level,
            site_key=context.site_key,
            product_level=context.product_level,
            product_key=context.product_key,
            time_bucket=context.time_bucket,
            time_key=context.time_key
        )

        if dimension == "site":
            current_idx = SITE_LEVEL_ORDER.index(context.site_level)
            if current_idx > 0:
                new_context.site_level = SITE_LEVEL_ORDER[current_idx - 1]
                new_context.site_key = None  # Clear specific key when going up

        elif dimension == "product":
            current_idx = PRODUCT_LEVEL_ORDER.index(context.product_level)
            if current_idx > 0:
                new_context.product_level = PRODUCT_LEVEL_ORDER[current_idx - 1]
                new_context.product_key = None

        elif dimension == "time":
            current_idx = TIME_BUCKET_ORDER.index(context.time_bucket)
            if current_idx > 0:
                new_context.time_bucket = TIME_BUCKET_ORDER[current_idx - 1]
                new_context.time_key = None

        return new_context


# ============================================================================
# Convenience Factory
# ============================================================================

def create_insights_service(
    db: AsyncSession,
    group_id: int,
    user: Optional[User] = None
) -> InsightsActionsService:
    """Create an insights actions service instance."""
    return InsightsActionsService(db, group_id, user)
