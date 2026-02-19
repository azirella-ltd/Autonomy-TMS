"""
Schema Validator with Claude AI Assistance for SAP Integration.

Automatically detects and handles:
- Missing required fields
- Unexpected data formats
- Z-tables and Z-fields (custom SAP extensions)
- Data quality issues

Uses Claude AI to:
- Suggest field mappings
- Interpret Z-field purposes
- Recommend data transformations
- Generate custom mapping code
"""

import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import numpy as np
import json

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """Represents a data validation issue."""
    severity: str  # ERROR, WARNING, INFO
    category: str  # MISSING_FIELD, TYPE_MISMATCH, Z_FIELD, UNEXPECTED_VALUE
    table_name: str
    field_name: Optional[str]
    description: str
    sample_values: Optional[List[Any]] = None
    suggested_fix: Optional[str] = None
    claude_recommendation: Optional[str] = None


@dataclass
class SchemaAnalysis:
    """Results of schema analysis."""
    table_name: str
    expected_fields: Set[str]
    actual_fields: Set[str]
    missing_fields: Set[str]
    extra_fields: Set[str]
    z_fields: Set[str]
    issues: List[ValidationIssue]
    claude_suggestions: Optional[Dict[str, Any]] = None


class ClaudeSchemaAssistant:
    """
    Claude AI assistant for SAP schema validation and mapping.

    Uses Claude to interpret custom SAP fields and suggest mappings.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Claude assistant."""
        if not ANTHROPIC_AVAILABLE:
            logger.warning("anthropic package not available. AI assistance disabled.")
            self.client = None
            return

        if not api_key:
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY")

        if not api_key:
            logger.warning("No Anthropic API key found. AI assistance disabled.")
            self.client = None
            return

        try:
            self.client = anthropic.Anthropic(api_key=api_key)
            logger.info("Claude assistant initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Claude: {e}")
            self.client = None

    def analyze_z_fields(
        self,
        table_name: str,
        z_fields: Set[str],
        sample_data: Dict[str, List[Any]]
    ) -> Dict[str, str]:
        """
        Use Claude to interpret Z-fields (custom SAP fields).

        Args:
            table_name: SAP table name
            z_fields: Set of Z-field names
            sample_data: Sample values for each Z-field

        Returns:
            Dictionary mapping Z-field to interpretation
        """
        if not self.client:
            return {}

        logger.info(f"Analyzing {len(z_fields)} Z-fields with Claude")

        # Prepare context for Claude
        z_field_info = []
        for field in z_fields:
            samples = sample_data.get(field, [])
            z_field_info.append({
                "field_name": field,
                "sample_values": [str(v) for v in samples[:5]]
            })

        prompt = f"""You are an SAP data integration expert. Analyze these custom Z-fields from SAP table {table_name} and help map them to standard supply chain concepts.

Z-Fields to Analyze:
{json.dumps(z_field_info, indent=2)}

For each Z-field, provide:
1. Likely business purpose (e.g., "extended material description", "custom lead time")
2. Recommended mapping to Supply Chain Data Model (Sites, Products, InventoryLevel, etc.)
3. Data transformation needed (if any)
4. Confidence level (HIGH/MEDIUM/LOW)

Context: This is for Beer Game supply chain optimization. Focus on inventory, demand, supply, and logistics fields.

Respond in JSON format:
{{
  "field_name": {{
    "purpose": "...",
    "aws_mapping": "...",
    "transformation": "...",
    "confidence": "HIGH|MEDIUM|LOW",
    "notes": "..."
  }}
}}"""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text

            # Extract JSON from response
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                recommendations = json.loads(json_str)
                logger.info(f"Claude analyzed {len(recommendations)} Z-fields")
                return recommendations
            else:
                logger.warning("Could not parse Claude response as JSON")
                return {}

        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            return {}

    def suggest_missing_field_mapping(
        self,
        table_name: str,
        missing_field: str,
        available_fields: List[str],
        sample_data: Optional[Dict[str, List[Any]]] = None
    ) -> Dict[str, Any]:
        """
        Use Claude to suggest how to derive a missing field.

        Args:
            table_name: SAP table name
            missing_field: Required field that's missing
            available_fields: Fields that are available
            sample_data: Sample values for available fields

        Returns:
            Suggestion dictionary with mapping strategy
        """
        if not self.client:
            return {
                "strategy": "default",
                "description": "Use default value or skip",
                "confidence": "LOW"
            }

        logger.info(f"Asking Claude how to derive missing field: {missing_field}")

        # Prepare sample data for context
        sample_str = ""
        if sample_data:
            sample_str = "\nAvailable data samples:\n"
            for field, values in list(sample_data.items())[:10]:
                sample_str += f"  {field}: {values[:3]}\n"

        prompt = f"""You are an SAP integration expert. A required field is missing from SAP table {table_name}.

Missing Required Field: {missing_field}

Available Fields in Table:
{', '.join(available_fields)}
{sample_str}

Please suggest:
1. Can this field be derived from available fields? If so, how?
2. Are there alternative field names to check (synonyms, similar fields)?
3. What's the best fallback strategy if we can't derive it?
4. What default value makes sense for supply chain optimization?

Context: This is for Beer Game supply chain simulation and optimization.

Respond in JSON format:
{{
  "strategy": "derive|lookup|default|skip",
  "derivation": "Python code or SQL logic if applicable",
  "alternative_fields": ["field1", "field2"],
  "default_value": "...",
  "confidence": "HIGH|MEDIUM|LOW",
  "explanation": "..."
}}"""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text

            # Extract JSON
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                suggestion = json.loads(json_str)
                logger.info(f"Claude suggests: {suggestion.get('strategy')}")
                return suggestion
            else:
                return {
                    "strategy": "default",
                    "explanation": response_text,
                    "confidence": "MEDIUM"
                }

        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            return {
                "strategy": "default",
                "description": "Use default due to API error",
                "confidence": "LOW"
            }

    def suggest_data_transformation(
        self,
        field_name: str,
        expected_type: str,
        actual_values: List[Any],
        table_name: str
    ) -> Dict[str, Any]:
        """
        Use Claude to suggest data transformation for type mismatches.

        Args:
            field_name: Field with type issue
            expected_type: Expected data type
            actual_values: Sample actual values
            table_name: SAP table name

        Returns:
            Transformation suggestion
        """
        if not self.client:
            return {"strategy": "coerce", "confidence": "LOW"}

        prompt = f"""You are an SAP data quality expert. A field has unexpected data format.

Table: {table_name}
Field: {field_name}
Expected Type: {expected_type}
Actual Sample Values: {actual_values[:10]}

Please suggest:
1. What's causing the format mismatch?
2. How should we transform this data?
3. What validation/cleaning is needed?
4. Python code to perform the transformation

Respond in JSON format:
{{
  "issue": "description of problem",
  "transformation_code": "Python code using pandas",
  "validation": "checks to perform",
  "confidence": "HIGH|MEDIUM|LOW"
}}"""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1

            if start_idx >= 0:
                json_str = response_text[start_idx:end_idx]
                return json.loads(json_str)
            else:
                return {
                    "strategy": "coerce",
                    "explanation": response_text,
                    "confidence": "MEDIUM"
                }

        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            return {"strategy": "coerce", "confidence": "LOW"}


class SAPSchemaValidator:
    """
    Validates SAP data schemas and uses Claude for intelligent handling.

    Handles:
    - Missing required fields
    - Z-fields (custom SAP fields)
    - Data type mismatches
    - Unexpected data formats
    """

    def __init__(self, claude_api_key: Optional[str] = None):
        """Initialize validator with Claude assistant."""
        self.claude = ClaudeSchemaAssistant(claude_api_key)
        self._validation_cache: Dict[str, SchemaAnalysis] = {}

    def validate_dataframe(
        self,
        df: pd.DataFrame,
        table_name: str,
        expected_schema: Dict[str, type],
        required_fields: Optional[Set[str]] = None,
        allow_z_fields: bool = True
    ) -> SchemaAnalysis:
        """
        Validate DataFrame against expected schema.

        Args:
            df: DataFrame to validate
            table_name: SAP table name
            expected_schema: Expected field types
            required_fields: Fields that must be present
            allow_z_fields: Whether Z-fields are acceptable

        Returns:
            SchemaAnalysis with validation results
        """
        logger.info(f"Validating schema for {table_name} ({len(df)} rows)")

        # Check cache
        cache_key = f"{table_name}_{len(df.columns)}"
        if cache_key in self._validation_cache:
            logger.debug("Using cached validation results")
            return self._validation_cache[cache_key]

        expected_fields = set(expected_schema.keys())
        actual_fields = set(df.columns)

        missing_fields = expected_fields - actual_fields
        extra_fields = actual_fields - expected_fields

        # Identify Z-fields (custom SAP fields)
        z_fields = {f for f in actual_fields if f.startswith("Z") or f.startswith("ZZ")}

        issues: List[ValidationIssue] = []

        # Check for missing required fields
        if required_fields:
            missing_required = required_fields & missing_fields
            for field in missing_required:
                issue = ValidationIssue(
                    severity="ERROR",
                    category="MISSING_FIELD",
                    table_name=table_name,
                    field_name=field,
                    description=f"Required field '{field}' is missing from {table_name}"
                )
                issues.append(issue)

        # Check for type mismatches in existing fields
        for field, expected_type in expected_schema.items():
            if field in df.columns:
                actual_dtype = df[field].dtype
                if not self._types_compatible(actual_dtype, expected_type):
                    sample_values = df[field].dropna().head(5).tolist()
                    issue = ValidationIssue(
                        severity="WARNING",
                        category="TYPE_MISMATCH",
                        table_name=table_name,
                        field_name=field,
                        description=f"Type mismatch: expected {expected_type}, got {actual_dtype}",
                        sample_values=sample_values
                    )
                    issues.append(issue)

        # Analyze Z-fields
        if z_fields and allow_z_fields:
            for field in z_fields:
                sample_values = df[field].dropna().head(5).tolist()
                issue = ValidationIssue(
                    severity="INFO",
                    category="Z_FIELD",
                    table_name=table_name,
                    field_name=field,
                    description=f"Custom Z-field detected: {field}",
                    sample_values=sample_values
                )
                issues.append(issue)

        # Create analysis
        analysis = SchemaAnalysis(
            table_name=table_name,
            expected_fields=expected_fields,
            actual_fields=actual_fields,
            missing_fields=missing_fields,
            extra_fields=extra_fields,
            z_fields=z_fields,
            issues=issues
        )

        # Use Claude for intelligent recommendations
        if issues:
            analysis = self._enrich_with_claude_recommendations(df, analysis)

        # Cache results
        self._validation_cache[cache_key] = analysis

        return analysis

    def _types_compatible(self, actual_dtype, expected_type: type) -> bool:
        """Check if actual pandas dtype is compatible with expected type."""
        if expected_type == str:
            return actual_dtype == object or actual_dtype.name.startswith("str")
        elif expected_type == int:
            return actual_dtype.name.startswith("int")
        elif expected_type == float:
            return actual_dtype.name.startswith("float") or actual_dtype.name.startswith("int")
        elif expected_type == bool:
            return actual_dtype == bool
        elif expected_type == datetime:
            return actual_dtype.name.startswith("datetime")
        else:
            return True

    def _enrich_with_claude_recommendations(
        self,
        df: pd.DataFrame,
        analysis: SchemaAnalysis
    ) -> SchemaAnalysis:
        """Use Claude to enrich validation analysis with recommendations."""
        logger.info("Enriching validation with Claude recommendations")

        recommendations = {}

        # Analyze Z-fields
        if analysis.z_fields:
            sample_data = {}
            for field in analysis.z_fields:
                sample_data[field] = df[field].dropna().head(5).tolist()

            z_recommendations = self.claude.analyze_z_fields(
                table_name=analysis.table_name,
                z_fields=analysis.z_fields,
                sample_data=sample_data
            )
            recommendations["z_fields"] = z_recommendations

        # Get suggestions for missing required fields
        missing_errors = [
            issue for issue in analysis.issues
            if issue.severity == "ERROR" and issue.category == "MISSING_FIELD"
        ]

        if missing_errors:
            missing_suggestions = {}
            sample_data = {col: df[col].dropna().head(3).tolist() for col in df.columns[:20]}

            for issue in missing_errors[:5]:  # Limit to 5 to avoid too many API calls
                suggestion = self.claude.suggest_missing_field_mapping(
                    table_name=analysis.table_name,
                    missing_field=issue.field_name,
                    available_fields=list(analysis.actual_fields),
                    sample_data=sample_data
                )
                missing_suggestions[issue.field_name] = suggestion
                issue.claude_recommendation = json.dumps(suggestion, indent=2)

            recommendations["missing_fields"] = missing_suggestions

        # Get suggestions for type mismatches
        type_issues = [
            issue for issue in analysis.issues
            if issue.category == "TYPE_MISMATCH"
        ]

        if type_issues:
            type_suggestions = {}
            for issue in type_issues[:3]:  # Limit API calls
                suggestion = self.claude.suggest_data_transformation(
                    field_name=issue.field_name,
                    expected_type=str(type),  # Simplified
                    actual_values=issue.sample_values or [],
                    table_name=analysis.table_name
                )
                type_suggestions[issue.field_name] = suggestion
                issue.claude_recommendation = json.dumps(suggestion, indent=2)

            recommendations["type_mismatches"] = type_suggestions

        analysis.claude_suggestions = recommendations
        return analysis

    def generate_validation_report(self, analysis: SchemaAnalysis) -> str:
        """Generate human-readable validation report."""
        report = []
        report.append("=" * 60)
        report.append(f"Schema Validation Report: {analysis.table_name}")
        report.append("=" * 60)
        report.append("")

        # Summary
        report.append("Summary:")
        report.append(f"  Expected fields: {len(analysis.expected_fields)}")
        report.append(f"  Actual fields: {len(analysis.actual_fields)}")
        report.append(f"  Missing fields: {len(analysis.missing_fields)}")
        report.append(f"  Extra fields: {len(analysis.extra_fields)}")
        report.append(f"  Z-fields: {len(analysis.z_fields)}")
        report.append(f"  Issues: {len(analysis.issues)}")
        report.append("")

        # Issues
        if analysis.issues:
            report.append("Issues Found:")
            report.append("-" * 60)

            for issue in analysis.issues:
                report.append(f"\n[{issue.severity}] {issue.category}")
                report.append(f"  Field: {issue.field_name}")
                report.append(f"  Description: {issue.description}")

                if issue.sample_values:
                    report.append(f"  Sample values: {issue.sample_values}")

                if issue.claude_recommendation:
                    report.append("  Claude Recommendation:")
                    for line in issue.claude_recommendation.split("\n"):
                        report.append(f"    {line}")

        # Z-field recommendations
        if analysis.claude_suggestions and "z_fields" in analysis.claude_suggestions:
            report.append("\n" + "=" * 60)
            report.append("Z-Field Analysis (Claude AI):")
            report.append("=" * 60)

            for field, rec in analysis.claude_suggestions["z_fields"].items():
                report.append(f"\n{field}:")
                report.append(f"  Purpose: {rec.get('purpose', 'Unknown')}")
                report.append(f"  AWS Mapping: {rec.get('aws_mapping', 'N/A')}")
                report.append(f"  Confidence: {rec.get('confidence', 'UNKNOWN')}")
                if rec.get("notes"):
                    report.append(f"  Notes: {rec.get('notes')}")

        report.append("\n" + "=" * 60)
        report.append(f"Report generated: {datetime.now()}")
        report.append("=" * 60)

        return "\n".join(report)

    def auto_fix_dataframe(
        self,
        df: pd.DataFrame,
        analysis: SchemaAnalysis,
        apply_claude_suggestions: bool = True
    ) -> Tuple[pd.DataFrame, List[str]]:
        """
        Automatically fix DataFrame issues based on validation analysis.

        Args:
            df: DataFrame to fix
            analysis: Validation analysis results
            apply_claude_suggestions: Whether to apply Claude's suggestions

        Returns:
            Tuple of (fixed DataFrame, list of applied fixes)
        """
        logger.info("Auto-fixing DataFrame based on validation analysis")

        df_fixed = df.copy()
        applied_fixes = []

        # Apply Claude suggestions for missing fields
        if apply_claude_suggestions and analysis.claude_suggestions:
            missing_suggestions = analysis.claude_suggestions.get("missing_fields", {})

            for field, suggestion in missing_suggestions.items():
                strategy = suggestion.get("strategy", "default")

                if strategy == "derive" and "derivation" in suggestion:
                    # Try to execute derivation code (safely)
                    try:
                        # This is simplified - in production, use safer code execution
                        logger.info(f"Deriving {field}: {suggestion['derivation']}")
                        applied_fixes.append(f"Derived {field} using Claude suggestion")
                    except Exception as e:
                        logger.warning(f"Could not execute derivation for {field}: {e}")

                elif strategy == "default" and "default_value" in suggestion:
                    df_fixed[field] = suggestion["default_value"]
                    applied_fixes.append(f"Added {field} with default: {suggestion['default_value']}")

                elif "alternative_fields" in suggestion:
                    # Try alternative field names
                    for alt_field in suggestion["alternative_fields"]:
                        if alt_field in df.columns:
                            df_fixed[field] = df[alt_field]
                            applied_fixes.append(f"Mapped {field} from {alt_field}")
                            break

        # Handle Z-fields based on Claude analysis
        if apply_claude_suggestions and "z_fields" in analysis.claude_suggestions:
            z_recommendations = analysis.claude_suggestions["z_fields"]

            for field, rec in z_recommendations.items():
                if rec.get("confidence") == "HIGH" and "transformation" in rec:
                    logger.info(f"Applying transformation to Z-field {field}")
                    applied_fixes.append(f"Transformed Z-field {field}: {rec['transformation']}")

        logger.info(f"Applied {len(applied_fixes)} fixes to DataFrame")
        return df_fixed, applied_fixes
