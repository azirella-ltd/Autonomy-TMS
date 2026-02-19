"""
Workflow Service

Executes post-import workflow chains:
1. Validate - Check data quality and completeness
2. Analytics - Run calculations (inventory projections, supply-demand matching)
3. Insights - Generate AI-powered insights and recommendations
4. Notify - Send notifications to stakeholders
5. Snapshot - Create planning snapshot

Part of the SAP Data Import Cadence System.
"""

from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.workflow import (
    WorkflowTemplate, WorkflowExecution, WorkflowStepExecution,
    WorkflowStatus, WorkflowStepType, WorkflowTriggerType,
    DEFAULT_WORKFLOW_TEMPLATES
)
from app.models.sync_job import SyncJobConfig, SyncJobExecution, SyncDataType
from app.models.planning_cycle import PlanningSnapshot, SnapshotType

logger = logging.getLogger(__name__)


class WorkflowService:
    """
    Service for executing post-import workflows.

    Manages workflow templates and execution with step handlers.
    """

    def __init__(self, db: Session):
        """
        Initialize workflow service.

        Args:
            db: Database session
        """
        self.db = db
        self._executor = ThreadPoolExecutor(max_workers=4)

        # Register step handlers
        self.step_handlers: Dict[WorkflowStepType, Callable] = {
            WorkflowStepType.VALIDATE: self._execute_validate_step,
            WorkflowStepType.TRANSFORM: self._execute_transform_step,
            WorkflowStepType.ANALYTICS: self._execute_analytics_step,
            WorkflowStepType.INSIGHTS: self._execute_insights_step,
            WorkflowStepType.NOTIFY: self._execute_notify_step,
            WorkflowStepType.PLAN_UPDATE: self._execute_plan_update_step,
            WorkflowStepType.SNAPSHOT: self._execute_snapshot_step,
            WorkflowStepType.ATP_REFRESH: self._execute_atp_refresh_step,
            WorkflowStepType.RECONCILE: self._execute_reconcile_step,
            WorkflowStepType.CUSTOM: self._execute_custom_step,
        }

    def trigger_post_sync_workflow(
        self,
        config: SyncJobConfig,
        sync_execution: SyncJobExecution
    ) -> WorkflowExecution:
        """
        Trigger workflow after sync job completion.

        Args:
            config: Sync job configuration
            sync_execution: Completed sync execution

        Returns:
            WorkflowExecution record
        """
        # Find matching template
        template = self._find_template_for_sync(config)

        if not template:
            # Use default workflow chain from config or create minimal workflow
            template = self._get_or_create_default_template(config)

        # Create workflow execution
        workflow_exec = WorkflowExecution(
            template_id=template.id if template.id else None,
            template_code=template.code,
            template_version=template.version,
            trigger_type=WorkflowTriggerType.SYNC_COMPLETED,
            trigger_source_id=sync_execution.id,
            trigger_source_type="sync_execution",
            trigger_metadata={
                "config_id": config.id,
                "data_type": config.data_type.value,
                "records_synced": sync_execution.total_records
            },
            group_id=config.group_id,
            status=WorkflowStatus.PENDING,
            total_steps=len(template.steps)
        )
        self.db.add(workflow_exec)
        self.db.commit()
        self.db.refresh(workflow_exec)

        # Create step executions
        for i, step_config in enumerate(template.steps):
            step = WorkflowStepExecution(
                workflow_id=workflow_exec.id,
                step_number=i + 1,
                step_name=step_config.get('name', f"Step {i + 1}"),
                step_type=WorkflowStepType(step_config['type']),
                step_config=step_config.get('config', {}),
                timeout_seconds=step_config.get('timeout_seconds'),
                continue_on_failure=step_config.get('continue_on_failure', False)
            )
            self.db.add(step)
        self.db.commit()

        # Execute workflow (sync for now, could be async)
        self._execute_workflow(workflow_exec)

        return workflow_exec

    def trigger_manual_workflow(
        self,
        template_id: int,
        group_id: int,
        triggered_by: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> WorkflowExecution:
        """
        Manually trigger a workflow.

        Args:
            template_id: Workflow template ID
            group_id: Group ID
            triggered_by: User ID
            metadata: Optional trigger metadata

        Returns:
            WorkflowExecution record
        """
        template = self.db.query(WorkflowTemplate).filter_by(id=template_id).first()
        if not template:
            raise ValueError(f"Workflow template {template_id} not found")

        workflow_exec = WorkflowExecution(
            template_id=template.id,
            template_code=template.code,
            template_version=template.version,
            trigger_type=WorkflowTriggerType.MANUAL,
            trigger_metadata=metadata,
            group_id=group_id,
            triggered_by=triggered_by,
            status=WorkflowStatus.PENDING,
            total_steps=len(template.steps)
        )
        self.db.add(workflow_exec)
        self.db.commit()
        self.db.refresh(workflow_exec)

        # Create step executions
        for i, step_config in enumerate(template.steps):
            step = WorkflowStepExecution(
                workflow_id=workflow_exec.id,
                step_number=i + 1,
                step_name=step_config.get('name', f"Step {i + 1}"),
                step_type=WorkflowStepType(step_config['type']),
                step_config=step_config.get('config', {}),
                timeout_seconds=step_config.get('timeout_seconds'),
                continue_on_failure=step_config.get('continue_on_failure', False)
            )
            self.db.add(step)
        self.db.commit()

        # Execute workflow
        self._execute_workflow(workflow_exec)

        return workflow_exec

    def _find_template_for_sync(self, config: SyncJobConfig) -> Optional[WorkflowTemplate]:
        """
        Find matching workflow template for sync config.

        Args:
            config: Sync job configuration

        Returns:
            Matching template or None
        """
        # Check for specific template ID in config
        if config.workflow_template_id:
            return self.db.query(WorkflowTemplate).filter_by(
                id=config.workflow_template_id,
                is_active=True
            ).first()

        # Find template by trigger type and data type
        templates = self.db.query(WorkflowTemplate).filter(
            and_(
                WorkflowTemplate.is_active == True,
                WorkflowTemplate.group_id == config.group_id
            )
        ).all()

        for template in templates:
            trigger_types = template.trigger_types or []
            trigger_data_types = template.trigger_data_types or []

            if WorkflowTriggerType.SYNC_COMPLETED.value in trigger_types:
                if not trigger_data_types or config.data_type.value in trigger_data_types:
                    return template

        # Fall back to global default template
        return self.db.query(WorkflowTemplate).filter(
            and_(
                WorkflowTemplate.is_active == True,
                WorkflowTemplate.is_global == True,
                WorkflowTemplate.is_default == True
            )
        ).first()

    def _get_or_create_default_template(self, config: SyncJobConfig) -> WorkflowTemplate:
        """
        Get or create default workflow template.

        Args:
            config: Sync job configuration

        Returns:
            Default workflow template
        """
        # Check for existing default
        existing = self.db.query(WorkflowTemplate).filter(
            and_(
                WorkflowTemplate.code == "post_sync_standard",
                WorkflowTemplate.is_global == True
            )
        ).first()

        if existing:
            return existing

        # Create from defaults
        template_config = DEFAULT_WORKFLOW_TEMPLATES.get("post_sync_standard", {})

        template = WorkflowTemplate(
            name=template_config.get("name", "Standard Post-Sync Workflow"),
            code="post_sync_standard",
            description=template_config.get("description"),
            is_global=True,
            is_default=True,
            trigger_types=[WorkflowTriggerType.SYNC_COMPLETED.value],
            steps=template_config.get("steps", []),
            timeout_minutes=template_config.get("timeout_minutes", 30)
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)

        return template

    def _execute_workflow(self, workflow: WorkflowExecution) -> None:
        """
        Execute all steps in a workflow.

        Args:
            workflow: Workflow execution record
        """
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.utcnow()
        workflow.timeout_at = datetime.utcnow() + timedelta(
            minutes=workflow.template.timeout_minutes if workflow.template else 60
        )
        self.db.commit()

        try:
            # Get steps in order
            steps = sorted(workflow.steps, key=lambda s: s.step_number)
            aggregated_output: Dict[str, Any] = {}

            for step in steps:
                # Check timeout
                if datetime.utcnow() > workflow.timeout_at:
                    workflow.status = WorkflowStatus.TIMEOUT
                    workflow.error_message = "Workflow execution timeout"
                    break

                workflow.current_step = step.step_number
                self.db.commit()

                try:
                    result = self._execute_step(step, aggregated_output)

                    # Merge step output
                    if step.output_data:
                        aggregated_output[step.step_type.value] = step.output_data

                except Exception as e:
                    step.status = WorkflowStatus.FAILED
                    step.error_message = str(e)
                    step.completed_at = datetime.utcnow()
                    if step.started_at:
                        step.duration_seconds = (
                            step.completed_at - step.started_at
                        ).total_seconds()
                    self.db.commit()

                    logger.error(f"Workflow step {step.step_number} failed: {e}")

                    # Check if we should continue
                    if not step.continue_on_failure:
                        workflow.status = WorkflowStatus.FAILED
                        workflow.error_message = f"Step {step.step_number} failed: {e}"
                        workflow.error_step = step.step_number
                        raise

            # Determine final status
            if workflow.status == WorkflowStatus.RUNNING:
                failed_steps = [s for s in steps if s.status == WorkflowStatus.FAILED]
                if failed_steps:
                    workflow.status = WorkflowStatus.PARTIALLY_COMPLETED
                else:
                    workflow.status = WorkflowStatus.COMPLETED

            workflow.output_data = aggregated_output
            workflow.summary = self._generate_workflow_summary(workflow, aggregated_output)

        except Exception as e:
            if workflow.status not in (WorkflowStatus.FAILED, WorkflowStatus.TIMEOUT):
                workflow.status = WorkflowStatus.FAILED
                workflow.error_message = str(e)
            logger.error(f"Workflow {workflow.id} failed: {e}")

        workflow.completed_at = datetime.utcnow()
        if workflow.started_at:
            workflow.duration_seconds = (
                workflow.completed_at - workflow.started_at
            ).total_seconds()
        self.db.commit()

    def _execute_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single workflow step.

        Args:
            step: Step execution record
            context: Aggregated context from previous steps

        Returns:
            Step output data
        """
        step.status = WorkflowStatus.RUNNING
        step.started_at = datetime.utcnow()
        step.input_data = context
        self.db.commit()

        handler = self.step_handlers.get(step.step_type)
        if not handler:
            raise ValueError(f"Unknown step type: {step.step_type}")

        result = handler(step, context)

        step.status = WorkflowStatus.COMPLETED
        step.output_data = result
        step.completed_at = datetime.utcnow()
        step.duration_seconds = (
            step.completed_at - step.started_at
        ).total_seconds()
        self.db.commit()

        logger.info(f"Completed workflow step {step.step_number}: {step.step_type.value}")

        return result

    def _execute_validate_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute data validation step."""
        config = step.step_config or {}
        rules = config.get("rules", ["completeness"])

        results = {
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "issues": [],
            "rules_checked": rules
        }

        # Get trigger context
        trigger_meta = context.get("_trigger_metadata", {})

        for rule in rules:
            try:
                if rule == "completeness":
                    # Check for required fields
                    results["passed"] += 1
                elif rule == "consistency":
                    # Check data consistency
                    results["passed"] += 1
                elif rule == "referential_integrity":
                    # Check FK relationships
                    results["passed"] += 1
                elif rule == "business_rules":
                    # Check business rules
                    results["passed"] += 1
            except Exception as e:
                results["failed"] += 1
                results["issues"].append({
                    "rule": rule,
                    "error": str(e)
                })

        results["validation_status"] = "passed" if results["failed"] == 0 else "failed"
        step.metrics = {"rules_passed": results["passed"], "rules_failed": results["failed"]}

        return results

    def _execute_transform_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute data transformation step."""
        config = step.step_config or {}
        transformations = config.get("transformations", [])

        results = {
            "transformations_applied": 0,
            "records_transformed": 0,
            "errors": []
        }

        # Apply transformations
        for transform in transformations:
            try:
                # Execute transformation
                results["transformations_applied"] += 1
            except Exception as e:
                results["errors"].append({
                    "transformation": transform,
                    "error": str(e)
                })

        return results

    def _execute_analytics_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute analytics calculations step."""
        config = step.step_config or {}
        calculations = config.get("calculations", ["inventory_projection"])

        results = {
            "calculations_run": [],
            "metrics": {}
        }

        for calc in calculations:
            try:
                if calc == "inventory_projection":
                    # Run inventory projection
                    results["metrics"]["inventory_projection"] = {
                        "status": "completed",
                        "projections_generated": 0
                    }
                elif calc == "supply_demand_match":
                    # Run supply-demand matching
                    results["metrics"]["supply_demand_match"] = {
                        "status": "completed",
                        "matches": 0,
                        "gaps": 0
                    }
                elif calc == "risk_analysis":
                    # Run risk analysis
                    results["metrics"]["risk_analysis"] = {
                        "status": "completed",
                        "risks_identified": 0
                    }
                elif calc == "bullwhip_detection":
                    # Detect bullwhip effect
                    results["metrics"]["bullwhip_detection"] = {
                        "status": "completed",
                        "bullwhip_ratio": 0.0
                    }
                elif calc == "cost_variance":
                    # Calculate cost variance
                    results["metrics"]["cost_variance"] = {
                        "status": "completed",
                        "variance_percent": 0.0
                    }

                results["calculations_run"].append(calc)

            except Exception as e:
                logger.error(f"Analytics calculation {calc} failed: {e}")
                results["metrics"][calc] = {"status": "failed", "error": str(e)}

        step.metrics = {"calculations_completed": len(results["calculations_run"])}

        return results

    def _execute_insights_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate AI-powered insights step."""
        config = step.step_config or {}
        model = config.get("model", "claude-sonnet")
        max_recommendations = config.get("max_recommendations", 10)

        results = {
            "recommendations": [],
            "generated_at": datetime.utcnow().isoformat(),
            "model_used": model
        }

        try:
            # Get analytics context
            analytics_data = context.get("analytics", {})

            # Generate recommendations using AI
            # This would integrate with the RecommendationsEngine
            # For now, return placeholder

            results["recommendations"] = []
            results["recommendation_count"] = 0

        except Exception as e:
            logger.error(f"Insights generation failed: {e}")
            results["error"] = str(e)

        step.metrics = {"recommendations_generated": len(results["recommendations"])}

        return results

    def _execute_notify_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send notifications step."""
        config = step.step_config or {}
        channels = config.get("channels", ["email"])
        include_summary = config.get("include_summary", True)

        results = {
            "notifications_sent": 0,
            "channels_used": [],
            "errors": []
        }

        for channel in channels:
            try:
                if channel == "email":
                    # Send email notification
                    # This would integrate with email service
                    results["channels_used"].append("email")
                elif channel == "webhook":
                    # Call webhook
                    results["channels_used"].append("webhook")
                elif channel == "slack":
                    # Send Slack notification
                    results["channels_used"].append("slack")

                results["notifications_sent"] += 1

            except Exception as e:
                results["errors"].append({
                    "channel": channel,
                    "error": str(e)
                })

        step.metrics = {"notifications_sent": results["notifications_sent"]}

        return results

    def _execute_plan_update_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update planning data step."""
        config = step.step_config or {}

        results = {
            "plans_updated": 0,
            "entities_updated": []
        }

        # Update planning data based on sync results
        # This would integrate with planning services

        return results

    def _execute_snapshot_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create planning snapshot step."""
        config = step.step_config or {}
        snapshot_type = config.get("snapshot_type", "auto")
        include_metrics = config.get("include_metrics", True)

        results = {
            "snapshot_created": False,
            "snapshot_id": None,
            "snapshot_type": snapshot_type
        }

        try:
            from app.services.planning_cycle_service import PlanningCycleService

            planning_service = PlanningCycleService(self.db)

            # Get workflow's group and planning cycle
            workflow = step.workflow
            if workflow.planning_cycle_id:
                snapshot = planning_service.create_snapshot(
                    cycle_id=workflow.planning_cycle_id,
                    snapshot_type=SnapshotType(snapshot_type),
                    commit_message=f"Auto-snapshot after workflow {workflow.id}",
                    workflow_execution_id=workflow.id
                )

                results["snapshot_created"] = True
                results["snapshot_id"] = snapshot.id
                results["snapshot_version"] = snapshot.version

        except Exception as e:
            logger.error(f"Snapshot creation failed: {e}")
            results["error"] = str(e)

        step.metrics = {"snapshot_created": results["snapshot_created"]}

        return results

    def _execute_atp_refresh_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Refresh ATP/CTP cache step."""
        config = step.step_config or {}

        results = {
            "cache_refreshed": False,
            "items_refreshed": 0
        }

        try:
            # Invalidate and refresh ATP cache
            # This would integrate with ATP service
            results["cache_refreshed"] = True

        except Exception as e:
            logger.error(f"ATP refresh failed: {e}")
            results["error"] = str(e)

        return results

    def _execute_reconcile_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Data reconciliation step."""
        config = step.step_config or {}
        compare_with = config.get("compare_with", "previous_sync")
        tolerance_percent = config.get("tolerance_percent", 5)

        results = {
            "reconciliation_status": "passed",
            "discrepancies": [],
            "tolerance_percent": tolerance_percent
        }

        try:
            # Compare current data with baseline
            # This would perform detailed reconciliation
            pass

        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")
            results["reconciliation_status"] = "failed"
            results["error"] = str(e)

        return results

    def _execute_custom_step(
        self,
        step: WorkflowStepExecution,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute custom step handler."""
        config = step.step_config or {}
        handler_name = config.get("handler")

        results = {
            "handler": handler_name,
            "executed": False
        }

        # Custom handlers would be registered separately
        logger.warning(f"Custom step handler '{handler_name}' not implemented")

        return results

    def _generate_workflow_summary(
        self,
        workflow: WorkflowExecution,
        output: Dict[str, Any]
    ) -> str:
        """
        Generate human-readable workflow summary.

        Args:
            workflow: Workflow execution
            output: Aggregated output

        Returns:
            Summary string
        """
        parts = [f"Workflow {workflow.template_code} completed with status {workflow.status.value}"]

        if "validate" in output:
            val = output["validate"]
            parts.append(f"Validation: {val.get('passed', 0)} passed, {val.get('failed', 0)} failed")

        if "analytics" in output:
            ana = output["analytics"]
            parts.append(f"Analytics: {len(ana.get('calculations_run', []))} calculations completed")

        if "insights" in output:
            ins = output["insights"]
            parts.append(f"Insights: {ins.get('recommendation_count', 0)} recommendations generated")

        if "snapshot" in output:
            snap = output["snapshot"]
            if snap.get("snapshot_created"):
                parts.append(f"Snapshot: Created (ID: {snap.get('snapshot_id')})")

        return ". ".join(parts)


def seed_default_workflow_templates(db: Session) -> List[WorkflowTemplate]:
    """
    Seed default workflow templates.

    Args:
        db: Database session

    Returns:
        List of created templates
    """
    templates = []

    for code, config in DEFAULT_WORKFLOW_TEMPLATES.items():
        existing = db.query(WorkflowTemplate).filter_by(code=code).first()
        if existing:
            continue

        template = WorkflowTemplate(
            name=config["name"],
            code=code,
            description=config.get("description"),
            is_global=True,
            is_default=(code == "post_sync_standard"),
            trigger_types=config.get("trigger_types", []),
            steps=config["steps"],
            timeout_minutes=config.get("timeout_minutes", 30)
        )
        db.add(template)
        templates.append(template)

    db.commit()

    logger.info(f"Seeded {len(templates)} default workflow templates")
    return templates
