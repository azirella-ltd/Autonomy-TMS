"""
SAP Data Ingestion Monitoring Service

Provides monitoring, insights, and actions for ongoing SAP data ingestion:
1. Track extraction job status and history
2. Monitor data quality metrics
3. Detect anomalies and data drift
4. Generate insights and recommendations
5. Support remediation actions

Key Features:
- Real-time job monitoring with progress tracking
- Data quality scoring and trend analysis
- Anomaly detection for unexpected data patterns
- AI-powered insights and recommendations
- Action management for data issues
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Status of an ingestion job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"  # Completed with some failures


class JobType(str, Enum):
    """Type of ingestion job."""
    FULL_EXTRACT = "full_extract"
    DELTA_EXTRACT = "delta_extract"
    INCREMENTAL = "incremental"
    VALIDATION = "validation"
    RECONCILIATION = "reconciliation"


class DataQualityDimension(str, Enum):
    """Dimensions of data quality."""
    COMPLETENESS = "completeness"      # All required fields present
    ACCURACY = "accuracy"              # Values are valid/correct
    CONSISTENCY = "consistency"        # Data matches across sources
    TIMELINESS = "timeliness"         # Data is up-to-date
    UNIQUENESS = "uniqueness"         # No unexpected duplicates
    VALIDITY = "validity"             # Data conforms to rules


class InsightSeverity(str, Enum):
    """Severity level for insights."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ActionStatus(str, Enum):
    """Status of a remediation action."""
    SUGGESTED = "suggested"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class ActionType(str, Enum):
    """Type of remediation action."""
    MANUAL_REVIEW = "manual_review"
    AUTO_FIX = "auto_fix"
    RERUN_JOB = "rerun_job"
    UPDATE_MAPPING = "update_mapping"
    CONTACT_SAP_TEAM = "contact_sap_team"
    ADJUST_THRESHOLD = "adjust_threshold"


@dataclass
class IngestionJob:
    """Represents a data ingestion job."""
    id: Optional[int] = None
    group_id: int = 0
    connection_id: int = 0

    job_type: JobType = JobType.FULL_EXTRACT
    status: JobStatus = JobStatus.PENDING

    # Tables being extracted
    tables: List[str] = field(default_factory=list)
    current_table: Optional[str] = None
    table_progress: Dict[str, int] = field(default_factory=dict)  # table -> rows processed

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None

    # Metrics
    total_rows_expected: int = 0
    total_rows_processed: int = 0
    total_rows_failed: int = 0
    total_rows_skipped: int = 0

    # Error tracking
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "connection_id": self.connection_id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "tables": self.tables,
            "current_table": self.current_table,
            "table_progress": self.table_progress,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "estimated_completion": self.estimated_completion.isoformat() if self.estimated_completion else None,
            "total_rows_expected": self.total_rows_expected,
            "total_rows_processed": self.total_rows_processed,
            "total_rows_failed": self.total_rows_failed,
            "total_rows_skipped": self.total_rows_skipped,
            "errors": self.errors,
            "warnings": self.warnings,
            "progress_percent": self.progress_percent,
            "duration_seconds": self.duration_seconds,
        }

    @property
    def progress_percent(self) -> float:
        if self.total_rows_expected == 0:
            return 0.0
        return min(100.0, (self.total_rows_processed / self.total_rows_expected) * 100)

    @property
    def duration_seconds(self) -> Optional[float]:
        if not self.started_at:
            return None
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()


@dataclass
class DataQualityScore:
    """Quality score for a dimension."""
    dimension: DataQualityDimension
    score: float  # 0-100
    sample_size: int = 0
    issues_found: int = 0
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "score": self.score,
            "sample_size": self.sample_size,
            "issues_found": self.issues_found,
            "details": self.details,
        }


@dataclass
class DataQualityReport:
    """Overall data quality report for an entity."""
    entity: str
    table: str
    timestamp: datetime

    # Overall score
    overall_score: float = 0.0

    # Dimension scores
    dimension_scores: List[DataQualityScore] = field(default_factory=list)

    # Record counts
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0

    # Specific issues
    null_counts: Dict[str, int] = field(default_factory=dict)
    type_violations: Dict[str, int] = field(default_factory=dict)
    range_violations: Dict[str, int] = field(default_factory=dict)
    duplicate_count: int = 0

    # Trends
    score_trend: str = "stable"  # improving, declining, stable
    previous_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity": self.entity,
            "table": self.table,
            "timestamp": self.timestamp.isoformat(),
            "overall_score": self.overall_score,
            "dimension_scores": [d.to_dict() for d in self.dimension_scores],
            "total_records": self.total_records,
            "valid_records": self.valid_records,
            "invalid_records": self.invalid_records,
            "null_counts": self.null_counts,
            "type_violations": self.type_violations,
            "range_violations": self.range_violations,
            "duplicate_count": self.duplicate_count,
            "score_trend": self.score_trend,
            "previous_score": self.previous_score,
        }


@dataclass
class DataInsight:
    """An insight or recommendation from data analysis."""
    id: Optional[int] = None
    group_id: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Classification
    severity: InsightSeverity = InsightSeverity.INFO
    category: str = ""  # e.g., "data_quality", "mapping", "performance"

    # Content
    title: str = ""
    description: str = ""
    affected_entity: Optional[str] = None
    affected_table: Optional[str] = None
    affected_field: Optional[str] = None

    # Metrics
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    metric_threshold: Optional[float] = None

    # Actions
    suggested_actions: List[Dict[str, Any]] = field(default_factory=list)

    # Status
    is_acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "affected_entity": self.affected_entity,
            "affected_table": self.affected_table,
            "affected_field": self.affected_field,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "metric_threshold": self.metric_threshold,
            "suggested_actions": self.suggested_actions,
            "is_acknowledged": self.is_acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        }


@dataclass
class RemediationAction:
    """A remediation action for a data issue."""
    id: Optional[int] = None
    group_id: int = 0
    insight_id: Optional[int] = None

    # Action details
    action_type: ActionType = ActionType.MANUAL_REVIEW
    status: ActionStatus = ActionStatus.SUGGESTED

    title: str = ""
    description: str = ""
    instructions: str = ""

    # Target
    affected_entity: Optional[str] = None
    affected_table: Optional[str] = None
    affected_records: int = 0

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Assignment
    assigned_to: Optional[str] = None

    # Result
    result: Optional[str] = None
    records_fixed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "insight_id": self.insight_id,
            "action_type": self.action_type.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "instructions": self.instructions,
            "affected_entity": self.affected_entity,
            "affected_table": self.affected_table,
            "affected_records": self.affected_records,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "assigned_to": self.assigned_to,
            "result": self.result,
            "records_fixed": self.records_fixed,
        }


class SAPIngestionMonitoringService:
    """
    Service for monitoring SAP data ingestion and generating insights.

    Provides:
    1. Job tracking and status monitoring
    2. Data quality assessment
    3. Anomaly detection
    4. Insight generation
    5. Action management
    """

    def __init__(self, db: AsyncSession, group_id: int):
        self.db = db
        self.group_id = group_id
        self._jobs: Dict[int, IngestionJob] = {}
        self._quality_history: Dict[str, List[DataQualityReport]] = defaultdict(list)
        self._insights: List[DataInsight] = []
        self._actions: List[RemediationAction] = []
        self._next_job_id = 1
        self._next_insight_id = 1
        self._next_action_id = 1

    # -------------------------------------------------------------------------
    # Job Management
    # -------------------------------------------------------------------------

    async def create_job(
        self,
        connection_id: int,
        job_type: JobType,
        tables: List[str]
    ) -> IngestionJob:
        """Create a new ingestion job."""
        job = IngestionJob(
            id=self._next_job_id,
            group_id=self.group_id,
            connection_id=connection_id,
            job_type=job_type,
            tables=tables,
            status=JobStatus.PENDING,
        )
        self._jobs[job.id] = job
        self._next_job_id += 1

        logger.info(f"Created ingestion job {job.id} for {len(tables)} tables")
        return job

    async def start_job(self, job_id: int) -> IngestionJob:
        """Start an ingestion job."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()

        if job.tables:
            job.current_table = job.tables[0]

        logger.info(f"Started ingestion job {job_id}")
        return job

    async def update_job_progress(
        self,
        job_id: int,
        table: str,
        rows_processed: int,
        rows_failed: int = 0,
        errors: Optional[List[Dict[str, Any]]] = None
    ) -> IngestionJob:
        """Update job progress for a table."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")

        job.table_progress[table] = rows_processed
        job.total_rows_processed = sum(job.table_progress.values())
        job.total_rows_failed += rows_failed

        if errors:
            job.errors.extend(errors)

        # Estimate completion
        if job.total_rows_expected > 0 and job.started_at:
            elapsed = (datetime.utcnow() - job.started_at).total_seconds()
            if job.total_rows_processed > 0:
                rate = job.total_rows_processed / elapsed
                remaining = job.total_rows_expected - job.total_rows_processed
                seconds_remaining = remaining / rate if rate > 0 else 0
                job.estimated_completion = datetime.utcnow() + timedelta(seconds=seconds_remaining)

        return job

    async def complete_job(
        self,
        job_id: int,
        status: JobStatus = JobStatus.COMPLETED
    ) -> IngestionJob:
        """Mark a job as completed."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")

        job.status = status
        job.completed_at = datetime.utcnow()
        job.current_table = None

        # Generate insights based on job results
        await self._generate_job_insights(job)

        logger.info(f"Completed ingestion job {job_id} with status {status.value}")
        return job

    async def get_job(self, job_id: int) -> Optional[IngestionJob]:
        """Get a specific job."""
        return self._jobs.get(job_id)

    async def get_active_jobs(self) -> List[IngestionJob]:
        """Get all active (running/pending) jobs."""
        return [j for j in self._jobs.values()
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)]

    async def get_recent_jobs(self, limit: int = 10) -> List[IngestionJob]:
        """Get recent jobs ordered by start time."""
        jobs = sorted(
            self._jobs.values(),
            key=lambda j: j.started_at or datetime.min,
            reverse=True
        )
        return jobs[:limit]

    # -------------------------------------------------------------------------
    # Data Quality Assessment
    # -------------------------------------------------------------------------

    async def assess_data_quality(
        self,
        entity: str,
        table: str,
        sample_data: List[Dict[str, Any]],
        field_definitions: Dict[str, Dict[str, Any]]
    ) -> DataQualityReport:
        """
        Assess data quality for a set of records.

        Args:
            entity: AWS SC entity name
            table: Source SAP table
            sample_data: Sample of extracted records
            field_definitions: Expected field types and constraints

        Returns:
            DataQualityReport with scores and issues
        """
        report = DataQualityReport(
            entity=entity,
            table=table,
            timestamp=datetime.utcnow(),
            total_records=len(sample_data),
        )

        if not sample_data:
            report.overall_score = 0.0
            return report

        # Assess each dimension
        completeness = await self._assess_completeness(sample_data, field_definitions)
        accuracy = await self._assess_accuracy(sample_data, field_definitions)
        consistency = await self._assess_consistency(sample_data)
        uniqueness = await self._assess_uniqueness(sample_data, field_definitions)
        validity = await self._assess_validity(sample_data, field_definitions)

        report.dimension_scores = [completeness, accuracy, consistency, uniqueness, validity]

        # Calculate overall score (weighted average)
        weights = {
            DataQualityDimension.COMPLETENESS: 0.25,
            DataQualityDimension.ACCURACY: 0.20,
            DataQualityDimension.CONSISTENCY: 0.15,
            DataQualityDimension.UNIQUENESS: 0.20,
            DataQualityDimension.VALIDITY: 0.20,
        }

        total_weight = sum(weights.values())
        report.overall_score = sum(
            score.score * weights.get(score.dimension, 0.2)
            for score in report.dimension_scores
        ) / total_weight

        # Count valid/invalid records
        report.valid_records = int(len(sample_data) * report.overall_score / 100)
        report.invalid_records = len(sample_data) - report.valid_records

        # Track null counts per field
        for field_name in field_definitions:
            null_count = sum(1 for row in sample_data if row.get(field_name) is None)
            if null_count > 0:
                report.null_counts[field_name] = null_count

        # Calculate trend
        history = self._quality_history.get(f"{entity}:{table}", [])
        if history:
            report.previous_score = history[-1].overall_score
            if report.overall_score > report.previous_score + 5:
                report.score_trend = "improving"
            elif report.overall_score < report.previous_score - 5:
                report.score_trend = "declining"

        # Store in history
        self._quality_history[f"{entity}:{table}"].append(report)
        if len(self._quality_history[f"{entity}:{table}"]) > 30:
            self._quality_history[f"{entity}:{table}"] = self._quality_history[f"{entity}:{table}"][-30:]

        # Generate quality insights
        await self._generate_quality_insights(report)

        return report

    async def _assess_completeness(
        self,
        data: List[Dict[str, Any]],
        field_definitions: Dict[str, Dict[str, Any]]
    ) -> DataQualityScore:
        """Assess completeness - all required fields present."""
        required_fields = [f for f, info in field_definitions.items() if info.get("required")]
        if not required_fields:
            return DataQualityScore(
                dimension=DataQualityDimension.COMPLETENESS,
                score=100.0,
                sample_size=len(data),
            )

        complete_count = 0
        issues = 0

        for row in data:
            row_complete = all(
                row.get(field) is not None and str(row.get(field)).strip() != ""
                for field in required_fields
            )
            if row_complete:
                complete_count += 1
            else:
                issues += 1

        score = (complete_count / len(data)) * 100 if data else 0

        return DataQualityScore(
            dimension=DataQualityDimension.COMPLETENESS,
            score=score,
            sample_size=len(data),
            issues_found=issues,
            details=f"Required fields: {', '.join(required_fields)}",
        )

    async def _assess_accuracy(
        self,
        data: List[Dict[str, Any]],
        field_definitions: Dict[str, Dict[str, Any]]
    ) -> DataQualityScore:
        """Assess accuracy - values are valid for their types."""
        issues = 0

        for row in data:
            for field_name, field_info in field_definitions.items():
                value = row.get(field_name)
                if value is None:
                    continue

                expected_type = field_info.get("type", "string")

                # Type validation
                if expected_type == "decimal" and not isinstance(value, (int, float)):
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        issues += 1

                elif expected_type == "integer" and not isinstance(value, int):
                    try:
                        int(value)
                    except (ValueError, TypeError):
                        issues += 1

                elif expected_type == "date":
                    if isinstance(value, str):
                        # Simple date format check
                        import re
                        if not re.match(r'\d{4}-\d{2}-\d{2}', value):
                            issues += 1

        total_checks = len(data) * len(field_definitions)
        score = ((total_checks - issues) / total_checks) * 100 if total_checks > 0 else 100

        return DataQualityScore(
            dimension=DataQualityDimension.ACCURACY,
            score=score,
            sample_size=len(data),
            issues_found=issues,
            details=f"Type validation across {len(field_definitions)} fields",
        )

    async def _assess_consistency(self, data: List[Dict[str, Any]]) -> DataQualityScore:
        """Assess consistency - data patterns are consistent."""
        # Simple consistency check: look for inconsistent formatting
        issues = 0

        if len(data) < 2:
            return DataQualityScore(
                dimension=DataQualityDimension.CONSISTENCY,
                score=100.0,
                sample_size=len(data),
            )

        # Check for inconsistent casing, formatting patterns
        for field_name in data[0].keys():
            values = [str(row.get(field_name, "")) for row in data if row.get(field_name)]
            if not values:
                continue

            # Check if some values are uppercase and some lowercase
            upper_count = sum(1 for v in values if v.isupper())
            lower_count = sum(1 for v in values if v.islower())

            if upper_count > 0 and lower_count > 0:
                # Mixed casing
                if min(upper_count, lower_count) / max(upper_count, lower_count) > 0.1:
                    issues += 1

        score = max(0, 100 - (issues * 10))

        return DataQualityScore(
            dimension=DataQualityDimension.CONSISTENCY,
            score=score,
            sample_size=len(data),
            issues_found=issues,
            details="Checked formatting consistency",
        )

    async def _assess_uniqueness(
        self,
        data: List[Dict[str, Any]],
        field_definitions: Dict[str, Dict[str, Any]]
    ) -> DataQualityScore:
        """Assess uniqueness - no unexpected duplicates."""
        # Identify key fields
        key_fields = [f for f, info in field_definitions.items() if info.get("key")]
        if not key_fields:
            # Use first field as pseudo-key
            key_fields = list(data[0].keys())[:1] if data else []

        if not key_fields or not data:
            return DataQualityScore(
                dimension=DataQualityDimension.UNIQUENESS,
                score=100.0,
                sample_size=len(data),
            )

        # Count duplicates
        seen = set()
        duplicates = 0

        for row in data:
            key = tuple(str(row.get(f, "")) for f in key_fields)
            if key in seen:
                duplicates += 1
            seen.add(key)

        score = ((len(data) - duplicates) / len(data)) * 100 if data else 100

        return DataQualityScore(
            dimension=DataQualityDimension.UNIQUENESS,
            score=score,
            sample_size=len(data),
            issues_found=duplicates,
            details=f"Key fields: {', '.join(key_fields)}",
        )

    async def _assess_validity(
        self,
        data: List[Dict[str, Any]],
        field_definitions: Dict[str, Dict[str, Any]]
    ) -> DataQualityScore:
        """Assess validity - data conforms to business rules."""
        issues = 0

        for row in data:
            for field_name, field_info in field_definitions.items():
                value = row.get(field_name)
                if value is None:
                    continue

                # Range validation
                min_val = field_info.get("min")
                max_val = field_info.get("max")

                if min_val is not None or max_val is not None:
                    try:
                        num_value = float(value)
                        if min_val is not None and num_value < min_val:
                            issues += 1
                        if max_val is not None and num_value > max_val:
                            issues += 1
                    except (ValueError, TypeError):
                        pass

                # Enum validation
                allowed_values = field_info.get("allowed_values")
                if allowed_values and value not in allowed_values:
                    issues += 1

        total_checks = len(data) * len(field_definitions)
        score = ((total_checks - issues) / total_checks) * 100 if total_checks > 0 else 100

        return DataQualityScore(
            dimension=DataQualityDimension.VALIDITY,
            score=score,
            sample_size=len(data),
            issues_found=issues,
            details="Business rule validation",
        )

    # -------------------------------------------------------------------------
    # Insight Generation
    # -------------------------------------------------------------------------

    async def _generate_job_insights(self, job: IngestionJob) -> None:
        """Generate insights from a completed job."""
        # Check for high failure rate
        if job.total_rows_processed > 0:
            failure_rate = job.total_rows_failed / job.total_rows_processed
            if failure_rate > 0.1:
                await self._create_insight(
                    severity=InsightSeverity.ERROR if failure_rate > 0.25 else InsightSeverity.WARNING,
                    category="job_quality",
                    title=f"High failure rate in job {job.id}",
                    description=f"{failure_rate*100:.1f}% of records failed to process. "
                               f"({job.total_rows_failed}/{job.total_rows_processed} records)",
                    metric_name="failure_rate",
                    metric_value=failure_rate,
                    metric_threshold=0.1,
                    suggested_actions=[
                        {
                            "type": ActionType.MANUAL_REVIEW.value,
                            "title": "Review failed records",
                            "description": "Examine error logs to identify common failure patterns",
                        },
                        {
                            "type": ActionType.UPDATE_MAPPING.value,
                            "title": "Update field mappings",
                            "description": "Check if field mappings need adjustment",
                        },
                    ],
                )

        # Check for long running job
        if job.duration_seconds and job.duration_seconds > 3600:  # > 1 hour
            await self._create_insight(
                severity=InsightSeverity.WARNING,
                category="performance",
                title=f"Long running job {job.id}",
                description=f"Job took {job.duration_seconds/60:.1f} minutes to complete. "
                           "Consider optimizing extraction or using delta loads.",
                metric_name="duration_seconds",
                metric_value=job.duration_seconds,
                metric_threshold=3600,
                suggested_actions=[
                    {
                        "type": ActionType.ADJUST_THRESHOLD.value,
                        "title": "Switch to delta extraction",
                        "description": "Configure delta extraction to reduce processing time",
                    },
                ],
            )

        # Check for common errors
        if job.errors:
            error_types = defaultdict(int)
            for error in job.errors:
                error_types[error.get("type", "unknown")] += 1

            for error_type, count in error_types.items():
                if count > 5:
                    await self._create_insight(
                        severity=InsightSeverity.WARNING,
                        category="data_errors",
                        title=f"Recurring error: {error_type}",
                        description=f"Error '{error_type}' occurred {count} times during job {job.id}",
                        metric_name="error_count",
                        metric_value=count,
                        suggested_actions=[
                            {
                                "type": ActionType.MANUAL_REVIEW.value,
                                "title": "Investigate error cause",
                                "description": f"Review records with {error_type} errors",
                            },
                        ],
                    )

    async def _generate_quality_insights(self, report: DataQualityReport) -> None:
        """Generate insights from a quality report."""
        # Low overall quality
        if report.overall_score < 70:
            await self._create_insight(
                severity=InsightSeverity.ERROR if report.overall_score < 50 else InsightSeverity.WARNING,
                category="data_quality",
                title=f"Low data quality for {report.entity}",
                description=f"Data quality score is {report.overall_score:.1f}% for table {report.table}",
                affected_entity=report.entity,
                affected_table=report.table,
                metric_name="quality_score",
                metric_value=report.overall_score,
                metric_threshold=70,
                suggested_actions=[
                    {
                        "type": ActionType.MANUAL_REVIEW.value,
                        "title": "Review data quality issues",
                        "description": "Examine specific quality dimensions to identify root causes",
                    },
                ],
            )

        # Declining quality trend
        if report.score_trend == "declining" and report.previous_score:
            decline = report.previous_score - report.overall_score
            if decline > 10:
                await self._create_insight(
                    severity=InsightSeverity.WARNING,
                    category="data_quality",
                    title=f"Quality declining for {report.entity}",
                    description=f"Data quality dropped from {report.previous_score:.1f}% to "
                               f"{report.overall_score:.1f}% (down {decline:.1f}%)",
                    affected_entity=report.entity,
                    affected_table=report.table,
                    metric_name="quality_decline",
                    metric_value=decline,
                    suggested_actions=[
                        {
                            "type": ActionType.CONTACT_SAP_TEAM.value,
                            "title": "Contact SAP data team",
                            "description": "Quality decline may indicate source data issues",
                        },
                    ],
                )

        # High null counts on required fields
        for field, count in report.null_counts.items():
            if count > report.total_records * 0.2:  # More than 20% nulls
                await self._create_insight(
                    severity=InsightSeverity.WARNING,
                    category="data_completeness",
                    title=f"High null rate for {field}",
                    description=f"Field {field} has {count} null values out of {report.total_records} records "
                               f"({count/report.total_records*100:.1f}%)",
                    affected_entity=report.entity,
                    affected_table=report.table,
                    affected_field=field,
                    metric_name="null_rate",
                    metric_value=count / report.total_records,
                    metric_threshold=0.2,
                    suggested_actions=[
                        {
                            "type": ActionType.UPDATE_MAPPING.value,
                            "title": "Check field mapping",
                            "description": f"Verify {field} is correctly mapped from SAP",
                        },
                    ],
                )

    async def _create_insight(
        self,
        severity: InsightSeverity,
        category: str,
        title: str,
        description: str,
        affected_entity: Optional[str] = None,
        affected_table: Optional[str] = None,
        affected_field: Optional[str] = None,
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        metric_threshold: Optional[float] = None,
        suggested_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> DataInsight:
        """Create a new insight."""
        insight = DataInsight(
            id=self._next_insight_id,
            group_id=self.group_id,
            timestamp=datetime.utcnow(),
            severity=severity,
            category=category,
            title=title,
            description=description,
            affected_entity=affected_entity,
            affected_table=affected_table,
            affected_field=affected_field,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_threshold=metric_threshold,
            suggested_actions=suggested_actions or [],
        )

        self._insights.append(insight)
        self._next_insight_id += 1

        # Create actions from suggestions
        for action_info in suggested_actions or []:
            action = RemediationAction(
                id=self._next_action_id,
                group_id=self.group_id,
                insight_id=insight.id,
                action_type=ActionType(action_info.get("type", ActionType.MANUAL_REVIEW.value)),
                title=action_info.get("title", ""),
                description=action_info.get("description", ""),
                affected_entity=affected_entity,
                affected_table=affected_table,
                affected_records=0,
            )
            self._actions.append(action)
            self._next_action_id += 1

        logger.info(f"Created insight: {title} ({severity.value})")
        return insight

    # -------------------------------------------------------------------------
    # Insight and Action Queries
    # -------------------------------------------------------------------------

    async def get_insights(
        self,
        severity: Optional[InsightSeverity] = None,
        category: Optional[str] = None,
        unacknowledged_only: bool = False,
        limit: int = 50
    ) -> List[DataInsight]:
        """Get insights with optional filtering."""
        results = self._insights.copy()

        if severity:
            results = [i for i in results if i.severity == severity]

        if category:
            results = [i for i in results if i.category == category]

        if unacknowledged_only:
            results = [i for i in results if not i.is_acknowledged]

        # Sort by severity and timestamp
        severity_order = {
            InsightSeverity.CRITICAL: 0,
            InsightSeverity.ERROR: 1,
            InsightSeverity.WARNING: 2,
            InsightSeverity.INFO: 3,
        }
        results.sort(key=lambda i: (severity_order.get(i.severity, 4), -i.timestamp.timestamp()))

        return results[:limit]

    async def acknowledge_insight(self, insight_id: int, user: str) -> Optional[DataInsight]:
        """Acknowledge an insight."""
        for insight in self._insights:
            if insight.id == insight_id:
                insight.is_acknowledged = True
                insight.acknowledged_by = user
                insight.acknowledged_at = datetime.utcnow()
                return insight
        return None

    async def get_actions(
        self,
        status: Optional[ActionStatus] = None,
        action_type: Optional[ActionType] = None,
        limit: int = 50
    ) -> List[RemediationAction]:
        """Get remediation actions with optional filtering."""
        results = self._actions.copy()

        if status:
            results = [a for a in results if a.status == status]

        if action_type:
            results = [a for a in results if a.action_type == action_type]

        results.sort(key=lambda a: a.created_at, reverse=True)
        return results[:limit]

    async def update_action_status(
        self,
        action_id: int,
        status: ActionStatus,
        user: Optional[str] = None,
        result: Optional[str] = None,
        records_fixed: int = 0
    ) -> Optional[RemediationAction]:
        """Update the status of an action."""
        for action in self._actions:
            if action.id == action_id:
                action.status = status

                if status == ActionStatus.IN_PROGRESS:
                    action.started_at = datetime.utcnow()
                    action.assigned_to = user

                if status in (ActionStatus.COMPLETED, ActionStatus.DISMISSED):
                    action.completed_at = datetime.utcnow()
                    action.result = result
                    action.records_fixed = records_fixed

                return action
        return None

    # -------------------------------------------------------------------------
    # Dashboard Summary
    # -------------------------------------------------------------------------

    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get a summary for the monitoring dashboard."""
        active_jobs = await self.get_active_jobs()
        recent_jobs = await self.get_recent_jobs(5)
        unacked_insights = await self.get_insights(unacknowledged_only=True, limit=100)
        pending_actions = await self.get_actions(status=ActionStatus.SUGGESTED, limit=100)

        # Calculate averages
        completed_jobs = [j for j in self._jobs.values() if j.status == JobStatus.COMPLETED]
        avg_duration = sum(j.duration_seconds or 0 for j in completed_jobs) / len(completed_jobs) if completed_jobs else 0

        # Quality trends
        latest_quality = {}
        for key, reports in self._quality_history.items():
            if reports:
                latest_quality[key] = reports[-1].overall_score

        return {
            "active_jobs": len(active_jobs),
            "jobs_running": [j.to_dict() for j in active_jobs],
            "recent_jobs": [j.to_dict() for j in recent_jobs],
            "total_jobs_completed": len(completed_jobs),
            "average_job_duration_seconds": avg_duration,
            "unacknowledged_insights": len(unacked_insights),
            "insights_by_severity": {
                "critical": len([i for i in unacked_insights if i.severity == InsightSeverity.CRITICAL]),
                "error": len([i for i in unacked_insights if i.severity == InsightSeverity.ERROR]),
                "warning": len([i for i in unacked_insights if i.severity == InsightSeverity.WARNING]),
                "info": len([i for i in unacked_insights if i.severity == InsightSeverity.INFO]),
            },
            "pending_actions": len(pending_actions),
            "latest_quality_scores": latest_quality,
        }


# Convenience function
def create_ingestion_monitoring_service(db: AsyncSession, group_id: int) -> SAPIngestionMonitoringService:
    """Create an ingestion monitoring service for a group."""
    return SAPIngestionMonitoringService(db, group_id)
