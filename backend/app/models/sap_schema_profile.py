"""
SAP Schema Profile — Pydantic models for schema discovery results.

Stores the mapping between expected AWS SC DM fields and discovered SAP fields,
including confidence scores, join paths, and custom Z-field discoveries.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MatchType(str, Enum):
    """How a field match was determined."""
    EXACT = "exact"
    SYNONYM = "synonym"
    DESCRIPTION = "description"
    JOIN_PATH = "join_path"
    LLM_RESOLVED = "llm_resolved"
    SAMPLE_VALIDATED = "sample_validated"
    NOT_FOUND = "not_found"


class JoinStep(BaseModel):
    """A single step in a multi-table join path."""
    from_table: str
    from_field: str
    to_table: str
    to_field: str
    join_type: str = "INNER"  # INNER, LEFT


class FieldMatch(BaseModel):
    """Result of matching one expected field to a discovered SAP field."""
    expected_field: str = Field(..., description="AWS SC DM field name")
    matched_table: str = Field("", description="SAP table where field was found")
    matched_field: str = Field("", description="SAP field name matched")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Match confidence 0-1")
    match_type: MatchType = Field(MatchType.NOT_FOUND)
    join_path: Optional[List[JoinStep]] = Field(None, description="Join path if field is in another table")
    sample_values: Optional[List[str]] = Field(None, description="Sample values from the field")
    description: str = Field("", description="SAP field description from DD04T")
    candidates: Optional[List[Dict[str, Any]]] = Field(
        None, description="Alternative candidates considered"
    )
    user_confirmed: bool = Field(False, description="Whether a user has confirmed this match")


class CustomFieldDiscovery(BaseModel):
    """A discovered Z-field (custom extension)."""
    table_name: str
    field_name: str
    data_type: str = ""
    length: int = 0
    description: str = ""
    suggested_aws_sc_field: Optional[str] = None
    suggested_entity: Optional[str] = None
    confidence: float = 0.0


class MissingField(BaseModel):
    """An expected field that could not be found."""
    entity: str
    field_name: str
    sap_field_hint: str = ""
    required: bool = False
    reason: str = ""


class EntityProfile(BaseModel):
    """Schema profile for a single AWS SC DM entity."""
    entity_name: str
    primary_table: str
    primary_table_exists: bool = False
    field_matches: Dict[str, FieldMatch] = Field(default_factory=dict)
    coverage_pct: float = Field(0.0, description="Percentage of expected fields matched")
    required_coverage_pct: float = Field(0.0, description="Percentage of required fields matched")


class SchemaProfile(BaseModel):
    """Complete schema discovery profile for an SAP connection."""
    sap_release: str = Field("", description="SAP system release version if discoverable")
    discovery_date: datetime = Field(default_factory=datetime.utcnow)
    entities: Dict[str, EntityProfile] = Field(default_factory=dict)
    custom_fields: List[CustomFieldDiscovery] = Field(default_factory=list)
    missing_fields: List[MissingField] = Field(default_factory=list)
    confidence_score: float = Field(0.0, description="Overall weighted confidence")
    tables_scanned: int = 0
    fields_scanned: int = 0
    discovery_duration_seconds: float = 0.0

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
