"""
SAP Integration Module for Supply Chain.

Complete integration suite with AI assistance and incremental loading:

Core Components:
- S4HANAConnector: Direct RFC connection to S/4HANA
- APOConnector: APO connection (CSV primary, RFC fallback)
- CSVDataLoader: Load from CSV extracts
- SupplyChainMapper: Map to Supply Chain Data Model
- PlanWriter: Write optimization results back to SAP

AI-Enhanced Components:
- SAPSchemaValidator: Schema validation with Claude AI
- ClaudeSchemaAssistant: AI assistant for Z-fields and missing data
- IntelligentSAPLoader: Unified loader with AI assistance

Delta Loading Components:
- DeltaLoadTracker: Track incremental load state
- SAPDeltaLoader: Extract changed records only
- SAPDeltaExtractor: High-level delta extraction

Supports:
- Initial loads (full extraction with validation)
- Daily loads (net change/delta only)
- Z-fields (custom SAP extensions)
- Missing field handling
- Auto-fixing data quality issues
- Bidirectional data sync
"""

# Core connectors
from .s4hana_connector import (
    S4HANAConnector,
    S4HANAConnectionConfig,
)

from .apo_connector import (
    APOConnector,
    APOConnectionConfig,
)

from .csv_loader import CSVDataLoader

# Data mapping
from .data_mapper import SupplyChainMapper

# Plan writing
from .plan_writer import (
    PlanWriter,
    PlanWriteResult,
)

# Schema validation with AI
from .schema_validator import (
    SAPSchemaValidator,
    ClaudeSchemaAssistant,
    SchemaAnalysis,
    ValidationIssue,
)

# Delta loading
from .delta_loader import (
    DeltaLoadConfig,
    DeltaLoadResult,
    DeltaLoadTracker,
    SAPDeltaLoader,
    SAPDeltaExtractor,
)

# Intelligent loader (combines all features)
from .intelligent_loader import (
    IntelligentSAPLoader,
    LoadConfig,
    LoadResult,
    create_intelligent_loader,
)

# ATP/CTP Bridge (Phase 1 - SAP ATP Integration)
from .sap_atp_bridge import (
    SAPATPBridge,
    SAPATPConfig,
    SAPATPResult,
    SAPCTPResult,
    SyncResult,
)

# Unified extractors (OData, HANA DB, RFC)
from .extractors import (
    SAPTableExtractor,
    ODataExtractor,
    HANADBExtractor,
    RFCExtractor,
    create_extractor,
)

__all__ = [
    # Core connectors
    "S4HANAConnector",
    "S4HANAConnectionConfig",
    "APOConnector",
    "APOConnectionConfig",
    "CSVDataLoader",

    # Data mapping
    "SupplyChainMapper",

    # Plan writing
    "PlanWriter",
    "PlanWriteResult",

    # Schema validation
    "SAPSchemaValidator",
    "ClaudeSchemaAssistant",
    "SchemaAnalysis",
    "ValidationIssue",

    # Delta loading
    "DeltaLoadConfig",
    "DeltaLoadResult",
    "DeltaLoadTracker",
    "SAPDeltaLoader",
    "SAPDeltaExtractor",

    # Intelligent loader
    "IntelligentSAPLoader",
    "LoadConfig",
    "LoadResult",
    "create_intelligent_loader",

    # ATP/CTP Bridge
    "SAPATPBridge",
    "SAPATPConfig",
    "SAPATPResult",
    "SAPCTPResult",
    "SyncResult",

    # Unified extractors
    "SAPTableExtractor",
    "ODataExtractor",
    "HANADBExtractor",
    "RFCExtractor",
    "create_extractor",
]

__version__ = "2.0.0"  # Updated for ATP/CTP integration
