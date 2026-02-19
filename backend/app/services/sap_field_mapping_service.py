"""
SAP Z-Table/Z-Field Mapping Service with Fuzzy Matching

Provides intelligent mapping of custom SAP tables (Z-tables) and fields (Z-fields)
to AWS Supply Chain entities using:
1. Fuzzy string matching for field names
2. AI-powered semantic analysis for complex mappings
3. Pattern recognition for common SAP naming conventions
4. Learning from user-confirmed mappings

Key Features:
- Auto-detect Z-tables and Z-fields from SAP metadata
- Fuzzy matching using Levenshtein distance and token-based similarity
- Claude AI-powered suggestions for ambiguous mappings
- Mapping history and learning from corrections
- Batch mapping with confidence scoring
"""

import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json
import asyncio
from difflib import SequenceMatcher

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MatchConfidence(str, Enum):
    """Confidence level for field mapping."""
    HIGH = "high"        # >90% confidence - auto-map
    MEDIUM = "medium"    # 70-90% - suggest with review
    LOW = "low"          # 50-70% - needs user input
    NONE = "none"        # <50% - no suggestion


class MappingSource(str, Enum):
    """Source of the mapping decision."""
    AUTO_EXACT = "auto_exact"         # Exact name match
    AUTO_FUZZY = "auto_fuzzy"         # Fuzzy string match
    AUTO_PATTERN = "auto_pattern"     # Pattern-based match
    AI_SUGGESTED = "ai_suggested"     # AI/Claude suggested
    USER_CONFIRMED = "user_confirmed" # User manually confirmed
    USER_CREATED = "user_created"     # User manually created
    LEARNED = "learned"               # Learned from history


@dataclass
class FieldMatchResult:
    """Result of matching a SAP field to AWS SC field."""
    sap_field: str
    sap_field_description: str
    sap_field_type: str
    is_z_field: bool

    # Best match
    aws_sc_entity: Optional[str] = None
    aws_sc_field: Optional[str] = None
    aws_sc_field_type: Optional[str] = None

    # Match quality
    confidence: MatchConfidence = MatchConfidence.NONE
    confidence_score: float = 0.0
    match_source: MappingSource = MappingSource.AUTO_FUZZY

    # Alternative matches
    alternatives: List[Dict[str, Any]] = field(default_factory=list)

    # AI analysis
    ai_rationale: Optional[str] = None
    ai_transform_suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sap_field": self.sap_field,
            "sap_field_description": self.sap_field_description,
            "sap_field_type": self.sap_field_type,
            "is_z_field": self.is_z_field,
            "aws_sc_entity": self.aws_sc_entity,
            "aws_sc_field": self.aws_sc_field,
            "aws_sc_field_type": self.aws_sc_field_type,
            "confidence": self.confidence.value,
            "confidence_score": self.confidence_score,
            "match_source": self.match_source.value,
            "alternatives": self.alternatives,
            "ai_rationale": self.ai_rationale,
            "ai_transform_suggestion": self.ai_transform_suggestion,
        }


@dataclass
class ZTableAnalysis:
    """Analysis of a Z-table for mapping purposes."""
    table_name: str
    description: str
    field_count: int
    z_field_count: int

    # Suggested target
    suggested_entity: Optional[str] = None
    entity_confidence: float = 0.0

    # Field mappings
    field_mappings: List[FieldMatchResult] = field(default_factory=list)

    # Completeness
    mappable_fields: int = 0
    mapped_fields: int = 0
    unmapped_required: int = 0

    # AI analysis
    ai_purpose_analysis: Optional[str] = None
    ai_integration_guidance: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "description": self.description,
            "field_count": self.field_count,
            "z_field_count": self.z_field_count,
            "suggested_entity": self.suggested_entity,
            "entity_confidence": self.entity_confidence,
            "field_mappings": [f.to_dict() for f in self.field_mappings],
            "mappable_fields": self.mappable_fields,
            "mapped_fields": self.mapped_fields,
            "unmapped_required": self.unmapped_required,
            "ai_purpose_analysis": self.ai_purpose_analysis,
            "ai_integration_guidance": self.ai_integration_guidance,
        }


# Common SAP field name patterns and their AWS SC equivalents
SAP_FIELD_PATTERNS = {
    # Material/Product patterns
    r"^(Z_)?MAT(NR|ERIAL)?$": ("product", "product_id"),
    r"^(Z_)?MAKTX?$": ("product", "product_name"),
    r"^(Z_)?MATKL$": ("product", "product_group"),
    r"^(Z_)?MEINS$": ("product", "base_uom"),

    # Plant/Site patterns
    r"^(Z_)?WERKS?$": ("site", "site_id"),
    r"^(Z_)?PLANT$": ("site", "site_id"),
    r"^(Z_)?NAME1?$": ("site", "site_name"),
    r"^(Z_)?LAND1?$": ("site", "country"),

    # Quantity/Inventory patterns
    r"^(Z_)?LABST$": ("inv_level", "quantity"),
    r"^(Z_)?(QUAN|QTY|MENGE)$": ("inv_level", "quantity"),
    r"^(Z_)?STOCK$": ("inv_level", "quantity"),
    r"^(Z_)?LGORT$": ("inv_level", "storage_location"),

    # Vendor/Customer patterns
    r"^(Z_)?LIFNR$": ("trading_partner", "partner_id"),
    r"^(Z_)?KUNNR$": ("trading_partner", "partner_id"),
    r"^(Z_)?VENDOR$": ("trading_partner", "partner_id"),
    r"^(Z_)?CUSTOMER$": ("trading_partner", "partner_id"),

    # Order patterns
    r"^(Z_)?EBELN$": ("inbound_order", "order_id"),
    r"^(Z_)?VBELN$": ("outbound_order", "order_id"),
    r"^(Z_)?AUFNR$": ("production_order", "order_id"),
    r"^(Z_)?BSTNR$": ("inbound_order", "customer_po"),

    # Date patterns
    r"^(Z_)?(ERDAT|AEDAT|BEDAT)$": ("*", "order_date"),
    r"^(Z_)?LFDAT$": ("*", "delivery_date"),
    r"^(Z_)?EINDT$": ("*", "requested_date"),

    # Company patterns
    r"^(Z_)?BUKRS$": ("company", "company_id"),
    r"^(Z_)?VKORG$": ("company", "sales_org"),
}

# AWS SC entity field definitions (expanded)
AWS_SC_FIELDS = {
    "product": {
        "product_id": {"type": "string", "required": True, "description": "Unique product identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "product_name": {"type": "string", "required": False, "description": "Product name/description"},
        "description": {"type": "string", "required": False, "description": "Long description"},
        "product_group": {"type": "string", "required": False, "description": "Product group/category"},
        "base_uom": {"type": "string", "required": False, "description": "Base unit of measure"},
        "status": {"type": "string", "required": False, "description": "Product status"},
        "weight": {"type": "decimal", "required": False, "description": "Product weight"},
        "volume": {"type": "decimal", "required": False, "description": "Product volume"},
    },
    "site": {
        "site_id": {"type": "string", "required": True, "description": "Unique site identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "site_name": {"type": "string", "required": False, "description": "Site name"},
        "site_type": {"type": "string", "required": False, "description": "Type of site (DC, Plant, etc.)"},
        "address": {"type": "string", "required": False, "description": "Street address"},
        "city": {"type": "string", "required": False, "description": "City"},
        "country": {"type": "string", "required": False, "description": "Country code"},
        "region": {"type": "string", "required": False, "description": "Region/state"},
    },
    "inv_level": {
        "site_id": {"type": "string", "required": True, "description": "Site identifier"},
        "product_id": {"type": "string", "required": True, "description": "Product identifier"},
        "quantity": {"type": "decimal", "required": True, "description": "Inventory quantity"},
        "uom": {"type": "string", "required": False, "description": "Unit of measure"},
        "storage_location": {"type": "string", "required": False, "description": "Storage location"},
        "snapshot_date": {"type": "date", "required": True, "description": "Snapshot date"},
        "lot_number": {"type": "string", "required": False, "description": "Lot/batch number"},
    },
    "trading_partner": {
        "partner_id": {"type": "string", "required": True, "description": "Partner identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "partner_type": {"type": "string", "required": True, "description": "Vendor or Customer"},
        "partner_name": {"type": "string", "required": False, "description": "Partner name"},
        "address": {"type": "string", "required": False, "description": "Address"},
        "country": {"type": "string", "required": False, "description": "Country"},
    },
    "inbound_order": {
        "order_id": {"type": "string", "required": True, "description": "Order identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "order_type": {"type": "string", "required": True, "description": "Order type (PO, STO, etc.)"},
        "supplier_id": {"type": "string", "required": True, "description": "Supplier identifier"},
        "site_id": {"type": "string", "required": True, "description": "Receiving site"},
        "order_date": {"type": "date", "required": True, "description": "Order creation date"},
        "delivery_date": {"type": "date", "required": False, "description": "Expected delivery"},
        "customer_po": {"type": "string", "required": False, "description": "Customer PO reference"},
    },
    "outbound_order": {
        "order_id": {"type": "string", "required": True, "description": "Order identifier"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "customer_id": {"type": "string", "required": True, "description": "Customer identifier"},
        "ship_from_site_id": {"type": "string", "required": True, "description": "Shipping site"},
        "order_date": {"type": "date", "required": True, "description": "Order creation date"},
        "requested_date": {"type": "date", "required": False, "description": "Customer requested date"},
    },
    "forecast": {
        "site_id": {"type": "string", "required": True, "description": "Site identifier"},
        "product_id": {"type": "string", "required": True, "description": "Product identifier"},
        "forecast_date": {"type": "date", "required": True, "description": "Forecast period date"},
        "forecast_quantity": {"type": "decimal", "required": True, "description": "Forecasted quantity"},
        "forecast_p10": {"type": "decimal", "required": False, "description": "10th percentile"},
        "forecast_p50": {"type": "decimal", "required": False, "description": "50th percentile (median)"},
        "forecast_p90": {"type": "decimal", "required": False, "description": "90th percentile"},
    },
    "production_order": {
        "order_id": {"type": "string", "required": True, "description": "Production order number"},
        "company_id": {"type": "string", "required": True, "description": "Company identifier"},
        "site_id": {"type": "string", "required": True, "description": "Production site"},
        "product_id": {"type": "string", "required": True, "description": "Product being produced"},
        "order_quantity": {"type": "decimal", "required": True, "description": "Order quantity"},
        "start_date": {"type": "date", "required": False, "description": "Planned start"},
        "end_date": {"type": "date", "required": False, "description": "Planned finish"},
    },
}


class SAPFieldMappingService:
    """
    Service for intelligent mapping of SAP fields to AWS SC entities.

    Uses multiple strategies:
    1. Exact match - Direct field name matching
    2. Pattern match - Regex patterns for common SAP conventions
    3. Fuzzy match - String similarity for variations
    4. AI analysis - Claude for complex/ambiguous cases
    """

    def __init__(self, db: AsyncSession, group_id: int):
        self.db = db
        self.group_id = group_id
        self._mapping_history: Dict[str, str] = {}  # sap_field -> aws_field
        self._learned_mappings: Dict[str, Tuple[str, str]] = {}  # sap_field -> (entity, field)
        self._openai_client = None

    async def _get_openai_client(self):
        """Get or create OpenAI client for AI-powered suggestions."""
        if self._openai_client is None:
            try:
                from openai import AsyncOpenAI
                import os
                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    self._openai_client = AsyncOpenAI(api_key=api_key)
            except ImportError:
                logger.warning("OpenAI not available for AI-powered field mapping")
        return self._openai_client

    # -------------------------------------------------------------------------
    # Fuzzy String Matching
    # -------------------------------------------------------------------------

    def _levenshtein_ratio(self, s1: str, s2: str) -> float:
        """Calculate Levenshtein similarity ratio between two strings."""
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    def _token_similarity(self, s1: str, s2: str) -> float:
        """Calculate token-based similarity."""
        # Split by underscores, camelCase, or other separators
        def tokenize(s: str) -> set:
            # Handle camelCase and underscore separation
            tokens = re.split(r'[_\s]', s.lower())
            # Also split camelCase
            expanded = []
            for t in tokens:
                expanded.extend(re.findall(r'[a-z]+|[A-Z][a-z]*|\d+', t))
            return set(t.lower() for t in expanded if len(t) > 1)

        tokens1 = tokenize(s1)
        tokens2 = tokenize(s2)

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        return len(intersection) / len(union) if union else 0.0

    def _combined_similarity(self, sap_field: str, aws_field: str,
                            sap_desc: str = "", aws_desc: str = "") -> float:
        """Calculate combined similarity score."""
        # Field name similarity (weighted higher)
        name_sim = self._levenshtein_ratio(sap_field, aws_field)
        token_sim = self._token_similarity(sap_field, aws_field)

        # Description similarity if available
        desc_sim = 0.0
        if sap_desc and aws_desc:
            desc_sim = self._token_similarity(sap_desc, aws_desc)

        # Weighted combination
        if desc_sim > 0:
            return 0.4 * name_sim + 0.3 * token_sim + 0.3 * desc_sim
        else:
            return 0.5 * name_sim + 0.5 * token_sim

    # -------------------------------------------------------------------------
    # Pattern Matching
    # -------------------------------------------------------------------------

    def _match_by_pattern(self, sap_field: str) -> Optional[Tuple[str, str, float]]:
        """Try to match SAP field using known patterns."""
        for pattern, (entity, field) in SAP_FIELD_PATTERNS.items():
            if re.match(pattern, sap_field, re.IGNORECASE):
                return entity, field, 0.95
        return None

    def _is_z_field(self, field_name: str) -> bool:
        """Check if a field is a Z-field (custom SAP field)."""
        return field_name.upper().startswith(('Z_', 'ZZ_', 'Y_'))

    def _is_z_table(self, table_name: str) -> bool:
        """Check if a table is a Z-table (custom SAP table)."""
        return table_name.upper().startswith(('Z', 'Y'))

    # -------------------------------------------------------------------------
    # Field Matching
    # -------------------------------------------------------------------------

    async def match_field(
        self,
        sap_field: str,
        sap_field_type: str = "",
        sap_field_description: str = "",
        target_entity: Optional[str] = None,
        use_ai: bool = True
    ) -> FieldMatchResult:
        """
        Match a single SAP field to the best AWS SC field.

        Args:
            sap_field: SAP field name
            sap_field_type: SAP data type
            sap_field_description: Field description from SAP
            target_entity: If specified, only match to fields in this entity
            use_ai: Whether to use AI for difficult mappings

        Returns:
            FieldMatchResult with best match and alternatives
        """
        result = FieldMatchResult(
            sap_field=sap_field,
            sap_field_description=sap_field_description,
            sap_field_type=sap_field_type,
            is_z_field=self._is_z_field(sap_field),
        )

        # Check learned mappings first
        if sap_field in self._learned_mappings:
            entity, field = self._learned_mappings[sap_field]
            result.aws_sc_entity = entity
            result.aws_sc_field = field
            result.confidence = MatchConfidence.HIGH
            result.confidence_score = 0.98
            result.match_source = MappingSource.LEARNED
            return result

        # Try pattern matching
        pattern_match = self._match_by_pattern(sap_field)
        if pattern_match:
            entity, field, score = pattern_match
            if entity != "*" and (target_entity is None or target_entity == entity):
                result.aws_sc_entity = entity
                result.aws_sc_field = field
                result.confidence = MatchConfidence.HIGH
                result.confidence_score = score
                result.match_source = MappingSource.AUTO_PATTERN
                return result

        # Fuzzy match against all entities or target entity
        entities_to_check = AWS_SC_FIELDS.keys() if target_entity is None else [target_entity]

        all_matches = []
        for entity in entities_to_check:
            if entity not in AWS_SC_FIELDS:
                continue

            for aws_field, field_info in AWS_SC_FIELDS[entity].items():
                # Calculate similarity
                score = self._combined_similarity(
                    sap_field, aws_field,
                    sap_field_description, field_info.get("description", "")
                )

                if score > 0.3:  # Minimum threshold
                    all_matches.append({
                        "entity": entity,
                        "field": aws_field,
                        "field_type": field_info["type"],
                        "score": score,
                        "required": field_info.get("required", False),
                    })

        # Sort by score
        all_matches.sort(key=lambda x: x["score"], reverse=True)

        if all_matches:
            best = all_matches[0]
            result.aws_sc_entity = best["entity"]
            result.aws_sc_field = best["field"]
            result.aws_sc_field_type = best["field_type"]
            result.confidence_score = best["score"]

            # Set confidence level
            if best["score"] >= 0.9:
                result.confidence = MatchConfidence.HIGH
            elif best["score"] >= 0.7:
                result.confidence = MatchConfidence.MEDIUM
            elif best["score"] >= 0.5:
                result.confidence = MatchConfidence.LOW
            else:
                result.confidence = MatchConfidence.NONE

            result.match_source = MappingSource.AUTO_FUZZY

            # Add alternatives
            result.alternatives = all_matches[1:5]  # Top 4 alternatives

        # If confidence is low and AI is enabled, get AI suggestion
        if result.confidence in (MatchConfidence.LOW, MatchConfidence.NONE) and use_ai:
            ai_suggestion = await self._get_ai_suggestion(
                sap_field, sap_field_type, sap_field_description, target_entity
            )
            if ai_suggestion:
                result.ai_rationale = ai_suggestion.get("rationale")
                result.ai_transform_suggestion = ai_suggestion.get("transform")

                if ai_suggestion.get("entity") and ai_suggestion.get("field"):
                    result.aws_sc_entity = ai_suggestion["entity"]
                    result.aws_sc_field = ai_suggestion["field"]
                    result.confidence = MatchConfidence.MEDIUM
                    result.confidence_score = ai_suggestion.get("confidence", 0.75)
                    result.match_source = MappingSource.AI_SUGGESTED

        return result

    async def match_fields_batch(
        self,
        fields: List[Dict[str, str]],
        target_entity: Optional[str] = None,
        use_ai: bool = True
    ) -> List[FieldMatchResult]:
        """
        Match multiple fields in batch.

        Args:
            fields: List of dicts with 'name', 'type', 'description'
            target_entity: Optional entity to constrain matches
            use_ai: Whether to use AI for difficult mappings

        Returns:
            List of FieldMatchResult
        """
        results = []

        for field_info in fields:
            result = await self.match_field(
                sap_field=field_info.get("name", ""),
                sap_field_type=field_info.get("type", ""),
                sap_field_description=field_info.get("description", ""),
                target_entity=target_entity,
                use_ai=use_ai
            )
            results.append(result)

        return results

    # -------------------------------------------------------------------------
    # Z-Table Analysis
    # -------------------------------------------------------------------------

    async def analyze_z_table(
        self,
        table_name: str,
        table_description: str,
        fields: List[Dict[str, str]],
        use_ai: bool = True
    ) -> ZTableAnalysis:
        """
        Analyze a Z-table and suggest entity mapping and field mappings.

        Args:
            table_name: SAP table name (e.g., ZSCM_CUSTOM)
            table_description: Table description
            fields: List of field definitions
            use_ai: Whether to use AI for analysis

        Returns:
            ZTableAnalysis with suggested mappings
        """
        analysis = ZTableAnalysis(
            table_name=table_name,
            description=table_description,
            field_count=len(fields),
            z_field_count=sum(1 for f in fields if self._is_z_field(f.get("name", ""))),
        )

        # First, determine the likely target entity
        entity_scores = await self._infer_target_entity(fields, table_description)

        if entity_scores:
            best_entity = max(entity_scores, key=entity_scores.get)
            analysis.suggested_entity = best_entity
            analysis.entity_confidence = entity_scores[best_entity]

        # Match all fields
        field_results = await self.match_fields_batch(
            fields,
            target_entity=analysis.suggested_entity,
            use_ai=use_ai
        )
        analysis.field_mappings = field_results

        # Calculate completeness
        if analysis.suggested_entity and analysis.suggested_entity in AWS_SC_FIELDS:
            required_fields = {f for f, info in AWS_SC_FIELDS[analysis.suggested_entity].items()
                             if info.get("required")}
            mapped_required = {r.aws_sc_field for r in field_results
                             if r.confidence in (MatchConfidence.HIGH, MatchConfidence.MEDIUM)}

            analysis.mappable_fields = len(AWS_SC_FIELDS[analysis.suggested_entity])
            analysis.mapped_fields = len(mapped_required & set(AWS_SC_FIELDS[analysis.suggested_entity].keys()))
            analysis.unmapped_required = len(required_fields - mapped_required)

        # Get AI analysis if enabled
        if use_ai:
            ai_analysis = await self._get_ai_table_analysis(
                table_name, table_description, fields, analysis.suggested_entity
            )
            if ai_analysis:
                analysis.ai_purpose_analysis = ai_analysis.get("purpose")
                analysis.ai_integration_guidance = ai_analysis.get("guidance")

        return analysis

    async def _infer_target_entity(
        self,
        fields: List[Dict[str, str]],
        table_description: str
    ) -> Dict[str, float]:
        """Infer the most likely target entity based on field patterns."""
        entity_scores: Dict[str, float] = {entity: 0.0 for entity in AWS_SC_FIELDS}

        for field_info in fields:
            field_name = field_info.get("name", "")

            # Check pattern matches
            pattern_match = self._match_by_pattern(field_name)
            if pattern_match and pattern_match[0] != "*":
                entity_scores[pattern_match[0]] += pattern_match[2]

            # Fuzzy match contribution
            for entity, entity_fields in AWS_SC_FIELDS.items():
                for aws_field in entity_fields:
                    score = self._levenshtein_ratio(field_name, aws_field)
                    if score > 0.6:
                        entity_scores[entity] += score * 0.5

        # Add description-based scoring
        desc_keywords = {
            "product": ["material", "item", "product", "sku", "article"],
            "site": ["plant", "location", "warehouse", "dc", "site"],
            "inv_level": ["stock", "inventory", "quantity", "level"],
            "trading_partner": ["vendor", "supplier", "customer", "partner"],
            "inbound_order": ["purchase", "po", "procurement", "inbound"],
            "outbound_order": ["sales", "so", "order", "shipment", "outbound"],
            "forecast": ["forecast", "demand", "prediction", "plan"],
            "production_order": ["production", "manufacturing", "work order"],
        }

        desc_lower = table_description.lower()
        for entity, keywords in desc_keywords.items():
            for keyword in keywords:
                if keyword in desc_lower:
                    entity_scores[entity] += 1.0

        # Normalize scores
        max_score = max(entity_scores.values()) if entity_scores else 1.0
        if max_score > 0:
            entity_scores = {k: v / max_score for k, v in entity_scores.items()}

        return {k: v for k, v in entity_scores.items() if v > 0.1}

    # -------------------------------------------------------------------------
    # AI-Powered Analysis
    # -------------------------------------------------------------------------

    async def _get_ai_suggestion(
        self,
        sap_field: str,
        sap_field_type: str,
        sap_field_description: str,
        target_entity: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Get AI suggestion for a field mapping."""
        client = await self._get_openai_client()
        if not client:
            return None

        try:
            # Build available fields context
            if target_entity and target_entity in AWS_SC_FIELDS:
                available_fields = AWS_SC_FIELDS[target_entity]
            else:
                available_fields = {f"{e}.{f}": info for e, fields in AWS_SC_FIELDS.items()
                                   for f, info in fields.items()}

            prompt = f"""Analyze this SAP field and suggest the best AWS Supply Chain field mapping:

SAP Field: {sap_field}
Type: {sap_field_type}
Description: {sap_field_description}
Is Custom (Z-field): {self._is_z_field(sap_field)}

Available target fields:
{json.dumps(available_fields, indent=2)}

Respond in JSON format:
{{
    "entity": "entity_name or null",
    "field": "field_name or null",
    "confidence": 0.0-1.0,
    "rationale": "explanation of why this mapping makes sense",
    "transform": "any transformation needed (e.g., 'uppercase', 'date_format:YYYYMMDD', 'lookup:table_name')"
}}
"""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an SAP-to-AWS Supply Chain field mapping expert."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
            )

            return json.loads(response.choices[0].message.content)

        except Exception as e:
            logger.warning(f"AI suggestion failed: {e}")
            return None

    async def _get_ai_table_analysis(
        self,
        table_name: str,
        table_description: str,
        fields: List[Dict[str, str]],
        suggested_entity: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Get AI analysis of a Z-table's purpose and integration guidance."""
        client = await self._get_openai_client()
        if not client:
            return None

        try:
            field_summary = "\n".join([
                f"- {f.get('name', '')}: {f.get('type', '')} - {f.get('description', '')}"
                for f in fields[:20]  # Limit to first 20 fields
            ])

            prompt = f"""Analyze this custom SAP table (Z-table) for AWS Supply Chain integration:

Table: {table_name}
Description: {table_description}
Suggested Entity: {suggested_entity or 'Unknown'}

Fields:
{field_summary}

Provide analysis in JSON format:
{{
    "purpose": "Brief description of what this table likely stores and its business purpose",
    "guidance": "Specific guidance for integrating this table with AWS Supply Chain, including any data transformations or special handling needed for Z-fields"
}}
"""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an SAP integration expert helping migrate data to AWS Supply Chain."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
            )

            return json.loads(response.choices[0].message.content)

        except Exception as e:
            logger.warning(f"AI table analysis failed: {e}")
            return None

    # -------------------------------------------------------------------------
    # Learning and Feedback
    # -------------------------------------------------------------------------

    async def confirm_mapping(
        self,
        sap_field: str,
        aws_entity: str,
        aws_field: str
    ) -> None:
        """
        Confirm a mapping, adding it to learned mappings.

        This allows the system to learn from user corrections.
        """
        self._learned_mappings[sap_field] = (aws_entity, aws_field)
        logger.info(f"Learned mapping: {sap_field} -> {aws_entity}.{aws_field}")

    async def reject_mapping(self, sap_field: str) -> None:
        """Reject a learned mapping."""
        if sap_field in self._learned_mappings:
            del self._learned_mappings[sap_field]

    async def get_mapping_statistics(self) -> Dict[str, Any]:
        """Get statistics about current mappings."""
        return {
            "learned_mappings_count": len(self._learned_mappings),
            "pattern_count": len(SAP_FIELD_PATTERNS),
            "supported_entities": list(AWS_SC_FIELDS.keys()),
            "total_aws_fields": sum(len(fields) for fields in AWS_SC_FIELDS.values()),
        }

    async def export_mappings(self) -> Dict[str, Any]:
        """Export all learned mappings for persistence."""
        return {
            "version": "1.0",
            "group_id": self.group_id,
            "timestamp": datetime.utcnow().isoformat(),
            "learned_mappings": {
                k: {"entity": v[0], "field": v[1]}
                for k, v in self._learned_mappings.items()
            },
        }

    async def import_mappings(self, data: Dict[str, Any]) -> int:
        """Import previously exported mappings."""
        imported = 0
        mappings = data.get("learned_mappings", {})

        for sap_field, mapping in mappings.items():
            entity = mapping.get("entity")
            field = mapping.get("field")
            if entity and field:
                self._learned_mappings[sap_field] = (entity, field)
                imported += 1

        logger.info(f"Imported {imported} learned mappings")
        return imported


# Convenience function
def create_field_mapping_service(db: AsyncSession, group_id: int) -> SAPFieldMappingService:
    """Create a field mapping service for a group."""
    return SAPFieldMappingService(db, group_id)
