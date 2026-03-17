# SAP Integration with Claude AI Assistance
## Intelligent Data Loading for Beer Game Supply Chain

**Version**: 2.0 (AI-Enhanced)
**Date**: 2026-01-16
**Status**: Production Ready with AI Features

---

## Table of Contents

1. [Overview](#overview)
2. [AI-Enhanced Features](#ai-enhanced-features)
3. [Claude AI Integration](#claude-ai-integration)
4. [Delta/Net Change Loading](#delta-net-change-loading)
5. [Z-Field Handling](#z-field-handling)
6. [Initial Load vs Daily Load](#initial-load-vs-daily-load)
7. [Usage Examples](#usage-examples)
8. [Configuration](#configuration)
9. [Troubleshooting](#troubleshooting)

---

## Overview

This enhanced SAP integration uses **Claude AI (Sonnet 4.5)** to intelligently handle:

- **Z-fields** (custom SAP extensions) - automatic interpretation
- **Missing required fields** - suggested derivations or defaults
- **Data type mismatches** - transformation recommendations
- **Delta loading** - extract only changed records (net change)
- **Auto-fixing** - apply AI recommendations automatically

### Key Improvements

| Feature | Without AI | With AI |
|---------|------------|---------|
| Z-field handling | Manual mapping required | **Automatic interpretation** |
| Missing fields | Hard-coded defaults | **Intelligent derivation** |
| Data quality issues | Manual fixes | **Auto-correction** |
| Schema changes | Code updates needed | **Adaptive mapping** |
| Daily loads | Full reload | **Delta/net change only** |

---

## AI-Enhanced Features

### 1. Automatic Z-Field Interpretation

SAP implementations use Z-fields extensively for custom requirements. Claude AI automatically:

**Analyzes Z-field purpose:**
```
Z-field: ZCUSTLEAD
Sample values: ['14', '21', '7', '10']

Claude interprets:
→ Purpose: "Custom lead time in days"
→ AWS Mapping: "lead_time_days in SupplyPlan"
→ Transformation: "Convert string to integer"
→ Confidence: HIGH
```

**Maps to standard models:**
- Z-fields → AWS Supply Chain entities
- Custom extensions → Beer Game concepts
- Vendor-specific fields → Standard supply chain attributes

### 2. Missing Field Handling

When required fields are missing, Claude suggests:

**Example: Missing "SAFETY_STOCK" field**
```
Claude recommendation:
{
  "strategy": "derive",
  "derivation": "safety_stock = demand_avg * 0.5 + lead_time * demand_std",
  "alternative_fields": ["EISBE", "MINBE", "SSTOCK"],
  "default_value": "demand_avg * 2.0",
  "confidence": "HIGH"
}
```

**Strategies:**
- **Derive**: Calculate from other fields
- **Lookup**: Find alternative field names
- **Default**: Use intelligent default values
- **Skip**: Mark as optional if non-critical

### 3. Data Quality Auto-Fixing

Claude identifies and fixes data issues:

**Type Mismatches:**
```python
Field: DELIVERY_DATE
Expected: datetime
Actual: ['20260116', '2026-01-16', '16.01.2026']  # Mixed formats

Claude suggestion:
→ Try multiple date parsers
→ Convert DD.MM.YYYY → YYYY-MM-DD
→ Validate result
```

**Value Validation:**
```python
Field: QUANTITY
Values: ['100', 'NEG', '50.5']  # Contains invalid entry

Claude recommendation:
→ Convert to numeric, coerce errors to NaN
→ Flag 'NEG' as potential backlog indicator
→ Log invalid values for review
```

### 4. Delta Loading (Net Change)

Extracts only changed records for daily loads:

**Change Detection Methods:**
1. **Date-based**: Uses SAP change date fields (AEDAT, etc.)
2. **Hash-based**: Compares record content hashes
3. **Key-based**: Tracks record keys across loads

**Efficiency:**
```
Initial Load:   100,000 records  → 100% loaded
Daily Load #1:      500 records  → 0.5% loaded (99.5% skipped)
Daily Load #2:      350 records  → 0.35% loaded
Daily Load #3:      420 records  → 0.42% loaded
```

---

## Claude AI Integration

### Setup

**1. Get Anthropic API Key:**
```bash
# Sign up at https://console.anthropic.com
# Create API key

export ANTHROPIC_API_KEY="sk-ant-..."
```

**2. Install Python Package:**
```bash
pip install anthropic
```

**3. Enable in Code:**
```python
from app.integrations.sap import create_intelligent_loader

loader = create_intelligent_loader(
    mode="initial",
    connection_type="csv",
    use_claude=True,  # Enable Claude AI
    claude_api_key=os.getenv("ANTHROPIC_API_KEY")
)
```

### How Claude is Used

#### Phase 1: Schema Validation
```python
# Validator calls Claude when it finds issues
validator = SAPSchemaValidator(claude_api_key)

analysis = validator.validate_dataframe(
    df=materials_df,
    table_name="MARA",
    expected_schema={...},
    required_fields={"MATNR", "MEINS"}
)

# Claude analyzes:
# - Z-fields found
# - Missing required fields
# - Type mismatches
```

#### Phase 2: Z-Field Analysis
```python
# Claude interprets each Z-field
z_recommendations = claude.analyze_z_fields(
    table_name="MARA",
    z_fields={"ZCUSTLEAD", "ZVENDMAT", "ZSAFETYSTK"},
    sample_data={
        "ZCUSTLEAD": ["14", "21", "7"],
        "ZVENDMAT": ["V123", "V456"],
        "ZSAFETYSTK": ["100", "200"]
    }
)

# Returns structured recommendations:
{
  "ZCUSTLEAD": {
    "purpose": "Custom lead time in days",
    "aws_mapping": "lead_time_days",
    "transformation": "int(value)",
    "confidence": "HIGH"
  },
  ...
}
```

#### Phase 3: Missing Field Derivation
```python
# Claude suggests how to handle missing fields
suggestion = claude.suggest_missing_field_mapping(
    table_name="MARC",
    missing_field="SAFETY_STOCK",
    available_fields=["EISBE", "DISPO", "DISMM", ...],
    sample_data={...}
)

# Returns derivation strategy:
{
  "strategy": "lookup",
  "alternative_fields": ["EISBE"],
  "explanation": "EISBE is safety stock in MARC table"
}
```

#### Phase 4: Auto-Fixing
```python
# Apply Claude's recommendations
df_fixed, fixes_applied = validator.auto_fix_dataframe(
    df=materials_df,
    analysis=validation_analysis,
    apply_claude_suggestions=True
)

# Automatically applied:
# - Mapped EISBE → SAFETY_STOCK
# - Converted ZCUSTLEAD to integer
# - Added default for missing REORDER_POINT
```

### Claude API Usage

**Rate Limits:**
- ~50 requests per minute (Anthropic standard)
- Intelligent batching reduces calls
- Cached results for repeated runs

**Cost Optimization:**
```python
# Validation runs once per table per schema
# Results cached for subsequent loads

# Typical daily load:
# - Initial validation: 3-5 Claude calls
# - Subsequent loads: 0 calls (uses cache)
```

**Token Usage:**
- Z-field analysis: ~500-1000 tokens/request
- Missing field suggestions: ~300-600 tokens/request
- Total per initial load: ~5,000-10,000 tokens
- Daily loads: Minimal (cached)

---

## Delta/Net Change Loading

### How It Works

**1. State Tracking:**
```python
# Tracks last load timestamp and record keys
{
  "MARA": {
    "last_load_timestamp": "2026-01-16T08:00:00",
    "record_keys": ["MAT001", "MAT002", ...],
    "last_result": {
      "total_records": 100000,
      "new_records": 500,
      "changed_records": 200
    }
  }
}
```

**2. Change Detection:**
```python
# Method 1: Date-based (preferred)
changed_records = df[df['AEDAT'] >= last_load_date]

# Method 2: Hash-based (fallback)
for record in df:
    current_hash = md5(record.to_json())
    if current_hash != cached_hash:
        changed_records.append(record)
```

**3. Delta Extraction:**
```python
delta_df, result = delta_extractor.extract_delta(
    full_data=current_materials_df,
    table_name="MARA"
)

# Result:
# New: 500 records
# Changed: 200 records
# Deleted: 50 records
# Unchanged: 99,250 records (skipped)
```

### Configuration

**Standard Delta Configs:**
```python
DELTA_CONFIGS = {
    "MARA": {
        "key_fields": ["MATNR"],
        "change_date_field": "AEDAT",
        "lookback_days": 2  # Safety margin
    },
    "EKKO": {
        "key_fields": ["EBELN"],
        "change_date_field": "AEDAT",
        "lookback_days": 7  # POs can change for a week
    },
    "VBAK": {
        "key_fields": ["VBELN"],
        "change_date_field": "ERDAT",
        "lookback_days": 30  # Orders stay open longer
    }
}
```

**Custom Configuration:**
```python
custom_config = DeltaLoadConfig(
    table_name="ZCUSTOM_TABLE",
    key_fields=["ZKEY1", "ZKEY2"],
    change_date_field="ZCHANGE_DATE",
    track_deletes=True,
    lookback_days=1
)
```

### Performance Impact

**Initial Load:**
```
Without Delta: 10 tables × 100K records = 1M records
Execution Time: ~15 minutes
```

**Daily Load (with Delta):**
```
With Delta: 10 tables × 500 avg changed = 5K records
Execution Time: ~45 seconds
Performance Gain: 20x faster
```

---

## Z-Field Handling

### Common Z-Field Patterns

**Manufacturing:**
```
ZPRODLEAD  → Production lead time
ZCAPACITY  → Production capacity
ZSETUPTIME → Setup time
ZYIELD     → Expected yield percentage
```

**Supply Chain:**
```
ZCUSTLEAD  → Custom lead time
ZSAFETYSTK → Safety stock override
ZREORDPT   → Reorder point
ZMINORDER  → Minimum order quantity
ZMAXORDER  → Maximum order quantity
```

**Vendor/Customer:**
```
ZVENDMAT   → Vendor material number
ZCUSTMAT   → Customer material number
ZVENDLEAD  → Vendor-specific lead time
ZPRICECAT  → Pricing category
```

### Automatic Mapping Examples

**Example 1: Lead Time Z-field**
```python
# Input
Z-field: ZCUSTLEAD
Samples: ['14', '21', '7', '10', '28']

# Claude Analysis
{
  "purpose": "Custom replenishment lead time in days",
  "aws_mapping": "SupplyPlan.lead_time_days",
  "transformation": "pd.to_numeric(df['ZCUSTLEAD'], errors='coerce')",
  "confidence": "HIGH",
  "notes": "Appears to override standard PLIFZ from MARC"
}

# Applied Automatically
supply_plan["lead_time_days"] = pd.to_numeric(
    marc_df["ZCUSTLEAD"].fillna(marc_df["PLIFZ"]),
    errors="coerce"
)
```

**Example 2: Safety Stock Override**
```python
# Input
Z-field: ZSAFETYSTK
Samples: ['100', '200', '50', '0', '']

# Claude Analysis
{
  "purpose": "Custom safety stock override",
  "aws_mapping": "InventoryLevel.safety_stock_quantity",
  "transformation": "Use ZSAFETYSTK if present, else EISBE",
  "confidence": "HIGH",
  "notes": "Empty/zero values should fallback to EISBE"
}

# Applied Automatically
inventory["safety_stock_quantity"] = (
    pd.to_numeric(marc_df["ZSAFETYSTK"], errors="coerce")
    .fillna(pd.to_numeric(marc_df["EISBE"], errors="coerce"))
    .fillna(0)
)
```

**Example 3: Vendor Material Number**
```python
# Input
Z-field: ZVENDMAT
Samples: ['V-MAT-12345', 'VM789', 'VENDOR_SKU_001']

# Claude Analysis
{
  "purpose": "Vendor-specific material identifier",
  "aws_mapping": "Products.supplier_sku or external_id",
  "transformation": "Store as string, use for vendor communications",
  "confidence": "MEDIUM",
  "notes": "Keep for vendor purchase orders, not critical for optimization"
}

# Applied Automatically
products["supplier_sku"] = marc_df["ZVENDMAT"].fillna("")
```

---

## Initial Load vs Daily Load

### Initial Load (Full Extraction)

**Purpose**: Complete data bootstrap with comprehensive validation

**Process:**
```python
loader = create_intelligent_loader(
    mode="initial",
    connection_type="csv",
    use_claude=True,
    enable_delta=False  # Not applicable for initial
)

results = loader.load_multiple_tables(
    table_names=["MARA", "MARC", "MARD", "EKKO", "EKPO"],
    data_source=csv_loader
)
```

**What Happens:**
1. ✅ Load complete dataset
2. ✅ Full schema validation
3. ✅ Claude analyzes ALL Z-fields
4. ✅ Comprehensive data quality checks
5. ✅ Generate detailed validation reports
6. ✅ Apply auto-fixes
7. ✅ Save delta state for future

**Output:**
- All records loaded
- Validation reports with Claude insights
- Z-field mapping recommendations
- Baseline for delta loads

### Daily Load (Delta/Net Change)

**Purpose**: Incremental update with only changed data

**Process:**
```python
loader = create_intelligent_loader(
    mode="daily",
    connection_type="csv",
    use_claude=True,  # For new Z-fields only
    enable_delta=True  # Extract changes only
)

results = loader.load_multiple_tables(
    table_names=["MARA", "MARC", "MARD", "EKKO", "EKPO"],
    data_source=csv_loader
)
```

**What Happens:**
1. ✅ Extract full dataset
2. ✅ Compare with previous load state
3. ✅ Identify changed/new records
4. ✅ Quick validation (cached schema)
5. ✅ Claude for NEW Z-fields only
6. ✅ Apply known auto-fixes
7. ✅ Return delta only

**Output:**
- Only changed records
- Delta metrics (new/changed/deleted)
- Validation for new issues only
- Updated delta state

**Comparison:**

| Aspect | Initial Load | Daily Load (Delta) |
|--------|--------------|-------------------|
| **Records** | All (100%) | Changed only (~0.5%) |
| **Time** | 15 min | 45 sec |
| **Validation** | Full | Incremental |
| **Claude Calls** | 10-15 | 0-2 |
| **Reports** | Comprehensive | Delta summary |
| **Use Case** | First time, major changes | Daily updates |

---

## Usage Examples

### Example 1: Initial Load with Full AI Assistance

```python
#!/usr/bin/env python3
"""Initial load with comprehensive validation."""

from app.integrations.sap import create_intelligent_loader, CSVDataLoader
import os

# Configure loader
loader = create_intelligent_loader(
    mode="initial",
    connection_type="csv",
    use_claude=True,
    enable_delta=False,
    claude_api_key=os.getenv("ANTHROPIC_API_KEY"),
    report_dir="./reports/initial",
    auto_fix=True,
    save_reports=True
)

# Load from CSV
csv_loader = CSVDataLoader("/data/sap/csv")

# Load all standard tables
tables = ["MARA", "MARC", "MARD", "EKKO", "EKPO", "VBAK", "VBAP"]
results = loader.load_multiple_tables(tables, csv_loader)

# Review Z-fields found
for table, (df, result) in results.items():
    if result.z_fields_found > 0:
        print(f"\n{table}: {result.z_fields_found} Z-fields")

        # Get Claude recommendations
        if result.validation_analysis:
            z_recs = result.validation_analysis.claude_suggestions.get("z_fields", {})
            for field, rec in z_recs.items():
                print(f"  {field}: {rec.get('purpose')} (Confidence: {rec.get('confidence')})")
```

### Example 2: Daily Delta Load

```python
#!/usr/bin/env python3
"""Daily incremental load with delta extraction."""

from app.integrations.sap import create_intelligent_loader, CSVDataLoader

# Configure for daily delta
loader = create_intelligent_loader(
    mode="daily",
    connection_type="csv",
    use_claude=True,  # Only for new issues
    enable_delta=True,
    delta_state_dir="./delta_state",
    report_dir="./reports/daily"
)

csv_loader = CSVDataLoader("/data/sap/csv_daily")

# Load delta only
tables = ["MARA", "MARC", "EKKO", "VBAK"]
results = loader.load_multiple_tables(tables, csv_loader)

# Print delta summary
for table, (df, result) in results.items():
    if result.delta_result:
        dr = result.delta_result
        print(f"{table}: {dr.new_records} new, {dr.changed_records} changed")
        print(f"  Efficiency: {len(df)}/{dr.total_records} = " +
              f"{(len(df)/dr.total_records)*100:.1f}% loaded")
```

### Example 3: Handle Custom Z-Fields

```python
#!/usr/bin/env python3
"""Focus on Z-field interpretation."""

from app.integrations.sap import (
    SAPSchemaValidator,
    CSVDataLoader
)

# Load data with Z-fields
loader = CSVDataLoader("/data/sap/csv")
materials = loader.load_table("MARC")

# Validate and analyze Z-fields
validator = SAPSchemaValidator(claude_api_key=os.getenv("ANTHROPIC_API_KEY"))

analysis = validator.validate_dataframe(
    df=materials,
    table_name="MARC",
    expected_schema={
        "MATNR": str,
        "WERKS": str,
        "EISBE": float,
    },
    required_fields={"MATNR", "WERKS"},
    allow_z_fields=True
)

# Get Z-field recommendations
if analysis.z_fields:
    print(f"Found {len(analysis.z_fields)} Z-fields")

    z_recs = analysis.claude_suggestions.get("z_fields", {})
    for field, rec in z_recs.items():
        print(f"\n{field}:")
        print(f"  Purpose: {rec.get('purpose')}")
        print(f"  AWS Mapping: {rec.get('aws_mapping')}")
        print(f"  Transformation: {rec.get('transformation')}")
        print(f"  Confidence: {rec.get('confidence')}")

# Apply recommendations
materials_fixed, fixes = validator.auto_fix_dataframe(
    df=materials,
    analysis=analysis,
    apply_claude_suggestions=True
)

print(f"\nApplied {len(fixes)} fixes")
```

### Example 4: Command Line Usage

```bash
# Initial load with AI
python backend/scripts/intelligent_sap_load.py \
    --mode initial \
    --source csv \
    --csv-dir /data/sap/csv \
    --claude \
    --report-dir ./reports/initial

# Daily delta load
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir /data/sap/csv_daily \
    --claude \
    --report-dir ./reports/daily \
    --delta-state-dir ./delta_state

# Load specific tables only
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir /data/sap/csv \
    --tables MARA MARC EKKO \
    --claude

# Reset delta state (force full reload)
python backend/scripts/intelligent_sap_load.py \
    --mode daily \
    --source csv \
    --csv-dir /data/sap/csv \
    --reset-delta
```

---

## Configuration

### Environment Variables

```bash
# Claude AI
export ANTHROPIC_API_KEY="sk-ant-..."

# SAP Connection (RFC mode)
export S4HANA_HOST="sap-s4hana.company.com"
export S4HANA_SYSNR="00"
export S4HANA_CLIENT="100"
export S4HANA_USER="BEERGAME"
export S4HANA_PASSWORD="..."

# Directories
export SAP_CSV_DIR="/data/sap/csv"
export SAP_REPORT_DIR="/data/sap/reports"
export SAP_DELTA_STATE_DIR="/data/sap/delta_state"
```

### Loader Configuration

```python
config = LoadConfig(
    mode="daily",  # "initial" or "daily"
    connection_type="csv",  # "rfc" or "csv"

    # AI features
    use_claude_ai=True,
    auto_fix_issues=True,

    # Delta loading
    enable_delta=True,

    # Reporting
    save_validation_report=True,
    report_directory="./reports"
)

loader = IntelligentSAPLoader(
    config=config,
    claude_api_key=os.getenv("ANTHROPIC_API_KEY"),
    delta_state_dir="./delta_state"
)
```

---

## Troubleshooting

### Issue: Claude API Errors

**Error:** `anthropic.APIError: Rate limit exceeded`

**Solution:**
```python
# Reduce API calls by caching
# Batch Z-field analysis
# Space out loads across time
```

### Issue: Delta Not Working

**Error:** Daily load still loads all records

**Solution:**
```python
# Check delta state file exists
delta_extractor.delta_loader.tracker.state

# Verify change date field
config = DeltaLoadConfig(
    table_name="MARA",
    key_fields=["MATNR"],
    change_date_field="AEDAT",  # Must exist in data
    lookback_days=2
)

# Reset if corrupted
loader.delta_extractor.reset_delta_state("MARA")
```

### Issue: Z-Fields Not Interpreted

**Error:** Z-fields found but no Claude recommendations

**Solution:**
```python
# Verify API key
print(os.getenv("ANTHROPIC_API_KEY"))

# Check validator initialization
validator = SAPSchemaValidator(claude_api_key="...")
print(validator.claude.client)  # Should not be None

# Check sample data provided
# Claude needs samples to interpret fields
```

### Issue: Auto-Fixes Not Applied

**Error:** Validation issues detected but not fixed

**Solution:**
```python
# Ensure auto_fix enabled
config.auto_fix_issues = True

# Check Claude suggestions exist
print(analysis.claude_suggestions)

# Manually apply if needed
df_fixed, fixes = validator.auto_fix_dataframe(
    df=df,
    analysis=analysis,
    apply_claude_suggestions=True
)
```

---

## Appendix: API Reference

### ClaudeSchemaAssistant

```python
assistant = ClaudeSchemaAssistant(api_key="...")

# Analyze Z-fields
recommendations = assistant.analyze_z_fields(
    table_name="MARC",
    z_fields={"ZCUSTLEAD", "ZSAFETYSTK"},
    sample_data={...}
)

# Suggest missing field mapping
suggestion = assistant.suggest_missing_field_mapping(
    table_name="MARA",
    missing_field="SAFETY_STOCK",
    available_fields=["EISBE", "MINBE"],
    sample_data={...}
)

# Suggest data transformation
transformation = assistant.suggest_data_transformation(
    field_name="DELIVERY_DATE",
    expected_type="datetime",
    actual_values=["20260116", "16.01.2026"],
    table_name="EKKO"
)
```

### SAPDeltaExtractor

```python
extractor = SAPDeltaExtractor(state_directory="./delta_state")

# Extract delta
delta_df, result = extractor.extract_delta(
    full_data=current_df,
    table_name="MARA"
)

# Get load history
history = extractor.get_load_history("MARA")

# Reset delta state
extractor.reset_delta_state()  # All tables
extractor.reset_delta_state("MARA")  # Specific table
```

---

**Document Version**: 2.0 (AI-Enhanced)
**Last Updated**: 2026-01-16
**Status**: Production Ready
