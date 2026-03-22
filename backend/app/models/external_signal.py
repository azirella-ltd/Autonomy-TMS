"""External Signal models — Outside-in planning intelligence from public data sources.

Implements Lora Cecere's outside-in planning methodology: weather, economic indicators,
commodity prices, geopolitical events, consumer sentiment, and regulatory signals are
ingested daily and injected into Azirella's RAG context for supply chain decision support.

Sources are tenant-configurable by industry, region, and product relevance.
All data comes from free, public APIs — no paid subscriptions required.

Signal categories (aligned with Cecere's demand-sensing framework):
- economic: CPI, PPI, unemployment, GDP, interest rates (FRED)
- weather: Temperature, precipitation, severe events (Open-Meteo)
- energy: Crude oil, natural gas, electricity prices (EIA)
- geopolitical: Disruption events, trade tensions, conflicts (GDELT)
- sentiment: Consumer search trends, product interest (Google Trends)
- regulatory: FDA recalls, safety alerts, compliance changes (openFDA)
- commodity: Agricultural, metals, chemical prices (World Bank/FRED)
- trade: Import/export volumes, tariffs, port congestion (Census/FRED)
"""

from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Date, JSON,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.sql import func

from app.models.base import Base


# ── Signal Categories ────────────────────────────────────────────────────────

SIGNAL_CATEGORIES = [
    "economic",      # CPI, PPI, unemployment, GDP, interest rates
    "weather",       # Temperature anomalies, precipitation, severe events
    "energy",        # Oil, gas, electricity prices and supply
    "geopolitical",  # Disruption events, trade tensions, sanctions
    "sentiment",     # Consumer search trends, social media sentiment
    "regulatory",    # FDA recalls, safety alerts, trade compliance
    "commodity",     # Agricultural, metals, chemical spot prices
    "trade",         # Import/export, tariffs, port congestion
]

# ── Source Registry ──────────────────────────────────────────────────────────

SOURCE_REGISTRY = {
    "fred": {
        "name": "FRED (Federal Reserve Economic Data)",
        "base_url": "https://api.stlouisfed.org/fred",
        "categories": ["economic", "commodity", "trade"],
        "requires_key": True,
        "key_env_var": "FRED_API_KEY",
        "free_tier": "Unlimited (free registration)",
        "refresh_cadence": "daily",
    },
    "open_meteo": {
        "name": "Open-Meteo Weather API",
        "base_url": "https://api.open-meteo.com/v1",
        "categories": ["weather"],
        "requires_key": False,
        "free_tier": "10,000 requests/day (no key needed)",
        "refresh_cadence": "daily",
    },
    "eia": {
        "name": "EIA (Energy Information Administration)",
        "base_url": "https://api.eia.gov/v2",
        "categories": ["energy"],
        "requires_key": True,
        "key_env_var": "EIA_API_KEY",
        "free_tier": "Unlimited (free registration)",
        "refresh_cadence": "daily",
    },
    "gdelt": {
        "name": "GDELT Project (Global Events Database)",
        "base_url": "https://api.gdeltproject.org/api/v2",
        "categories": ["geopolitical"],
        "requires_key": False,
        "free_tier": "Unlimited (open data)",
        "refresh_cadence": "daily",
    },
    "google_trends": {
        "name": "Google Trends (via pytrends)",
        "base_url": "https://trends.google.com",
        "categories": ["sentiment"],
        "requires_key": False,
        "free_tier": "Rate-limited (no key, use pytrends library)",
        "refresh_cadence": "daily",
    },
    "openfda": {
        "name": "openFDA (FDA Open Data)",
        "base_url": "https://api.fda.gov",
        "categories": ["regulatory"],
        "requires_key": False,
        "free_tier": "1,000 requests/day (no key), 120K with key",
        "refresh_cadence": "daily",
    },
    "nws_alerts": {
        "name": "NWS Severe Weather Alerts",
        "base_url": "https://api.weather.gov",
        "categories": ["weather"],
        "requires_key": False,
        "free_tier": "Unlimited (no key needed, US government open data)",
        "refresh_cadence": "daily",
        "description": "Persistent severe weather warnings (Winter Storm, Flood, Tornado, etc.) with geographic area and severity. More actionable than Open-Meteo for delivery disruptions.",
    },
    "reddit_sentiment": {
        "name": "Reddit Industry Sentiment",
        "base_url": "https://www.reddit.com",
        "categories": ["sentiment"],
        "requires_key": False,
        "free_tier": "~60 requests/min (public JSON API, no OAuth needed)",
        "refresh_cadence": "daily",
        "description": "Frontline worker sentiment from industry subreddits (r/KitchenConfidential, r/supplychain, etc.). Leading indicator for demand shifts and supply issues.",
    },
    "dot_disruptions": {
        "name": "DOT Transportation Disruptions",
        "base_url": "https://api.gdeltproject.org/api/v2",
        "categories": ["trade"],
        "requires_key": False,
        "free_tier": "Unlimited (uses GDELT infrastructure news feed)",
        "refresh_cadence": "daily",
        "description": "Persistent road closures, bridge restrictions, port congestion, construction zones — not real-time traffic, but days/weeks-long freight routing disruptions.",
    },
}

# ── SC Impact Mapping ────────────────────────────────────────────────────────
# Maps signal types to which TRM agents and planning layers are affected

SIGNAL_SC_IMPACT = {
    "cpi_change": {
        "trm_types": ["forecast_adjustment", "po_creation"],
        "planning_layer": "strategic",
        "description": "Consumer price changes affect demand patterns and procurement costs",
    },
    "severe_weather": {
        "trm_types": ["to_execution", "po_creation", "inventory_buffer"],
        "planning_layer": "tactical",
        "description": "Weather disruptions affect logistics, supply lead times, and safety stock needs",
    },
    "oil_price_spike": {
        "trm_types": ["to_execution", "po_creation"],
        "planning_layer": "tactical",
        "description": "Energy price changes affect transportation and raw material costs",
    },
    "geopolitical_disruption": {
        "trm_types": ["po_creation", "subcontracting", "inventory_buffer"],
        "planning_layer": "strategic",
        "description": "Geopolitical events affect supplier reliability and sourcing strategy",
    },
    "demand_trend_shift": {
        "trm_types": ["forecast_adjustment"],
        "planning_layer": "tactical",
        "description": "Consumer interest shifts affect demand forecasts",
    },
    "regulatory_recall": {
        "trm_types": ["quality_disposition", "inventory_rebalancing"],
        "planning_layer": "execution",
        "description": "Regulatory actions require immediate quality and inventory response",
    },
    "commodity_price_change": {
        "trm_types": ["po_creation", "subcontracting"],
        "planning_layer": "tactical",
        "description": "Raw material price movements affect procurement timing and make-vs-buy",
    },
    "port_congestion": {
        "trm_types": ["to_execution", "po_creation", "inventory_buffer"],
        "planning_layer": "tactical",
        "description": "Port delays affect inbound lead times and safety stock requirements",
    },
}


class ExternalSignalSource(Base):
    """Tenant-configurable external data source for outside-in planning signals.

    Each tenant activates specific sources and configures relevance filters
    based on their industry, geography, and product portfolio.
    """
    __tablename__ = "external_signal_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="SET NULL"), nullable=True)

    # Source identification
    source_key = Column(String(50), nullable=False)  # "fred", "open_meteo", "eia", etc.
    source_name = Column(String(255), nullable=False)  # Human-readable name
    is_active = Column(Boolean, default=True, nullable=False)

    # Source-specific configuration
    api_key_encrypted = Column(Text, nullable=True)  # Encrypted API key (if required)
    source_params = Column(JSON, nullable=True)  # Source-specific parameters:
    # FRED: {"series_ids": ["CPIAUCSL", "UNRATE", "GDP"]}
    # Open-Meteo: {"locations": [{"lat": 40.7, "lon": -74.0, "name": "NYC"}]}
    # EIA: {"series_ids": ["PET.RWTC.D", "NG.RNGWHHD.D"]}
    # GDELT: {"keywords": ["supply chain", "port strike"], "countries": ["US", "CN"]}
    # Google Trends: {"keywords": ["beer", "craft beer", "energy drinks"]}
    # openFDA: {"product_types": ["food", "drug"], "keywords": ["recall"]}

    # Relevance filters (tenant-specific)
    industry_tags = Column(JSON, nullable=True)  # ["food_distribution", "beverage", "fmcg"]
    region_tags = Column(JSON, nullable=True)  # ["north_america", "us_east", "europe"]
    product_tags = Column(JSON, nullable=True)  # ["frozen", "beverages", "dairy"]

    # Refresh configuration
    refresh_cadence = Column(String(20), default="daily")  # "daily", "hourly", "weekly"
    last_refresh_at = Column(DateTime, nullable=True)
    last_refresh_status = Column(String(20), nullable=True)  # "success", "error", "partial"
    last_refresh_error = Column(Text, nullable=True)
    signals_collected = Column(Integer, default=0)  # Running count

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "source_key", "config_id", name="uq_ext_signal_source_tenant_key"),
        Index("ix_ext_signal_source_tenant", "tenant_id"),
        Index("ix_ext_signal_source_active", "is_active"),
    )


class ExternalSignal(Base):
    """An individual external signal captured from a public data source.

    Signals are tenant-scoped, categorized, and scored for supply chain relevance.
    They are embedded for RAG retrieval and injected into Azirella's chat context.
    """
    __tablename__ = "external_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="SET NULL"), nullable=True)
    source_id = Column(Integer, ForeignKey("external_signal_sources.id", ondelete="CASCADE"), nullable=False)

    # Signal identification
    source_key = Column(String(50), nullable=False)  # "fred", "open_meteo", etc.
    category = Column(String(30), nullable=False)  # From SIGNAL_CATEGORIES
    signal_type = Column(String(100), nullable=False)  # Specific signal (e.g., "cpi_change", "severe_weather")
    signal_key = Column(String(255), nullable=False)  # Dedup key (e.g., "fred:CPIAUCSL:2026-03-22")

    # Signal content
    title = Column(String(500), nullable=False)  # Human-readable headline
    summary = Column(Text, nullable=False)  # SC-relevant summary for RAG injection
    raw_value = Column(Float, nullable=True)  # Numeric value if applicable
    raw_unit = Column(String(50), nullable=True)  # Unit (e.g., "percent", "usd/bbl", "celsius")
    change_pct = Column(Float, nullable=True)  # Period-over-period change percentage
    change_direction = Column(String(10), nullable=True)  # "up", "down", "stable"

    # Temporal context
    signal_date = Column(Date, nullable=False)  # Date the signal applies to
    reference_period = Column(String(50), nullable=True)  # "2026-Q1", "2026-03", "2026-W12"
    previous_value = Column(Float, nullable=True)  # For trend computation

    # Supply chain relevance scoring (0-1)
    relevance_score = Column(Float, default=0.5, nullable=False)  # Overall SC relevance
    urgency_score = Column(Float, default=0.3, nullable=False)  # Time sensitivity
    magnitude_score = Column(Float, default=0.3, nullable=False)  # Impact magnitude

    # SC impact mapping
    affected_trm_types = Column(JSON, nullable=True)  # ["forecast_adjustment", "po_creation"]
    planning_layer = Column(String(20), nullable=True)  # "execution", "tactical", "strategic"
    affected_product_tags = Column(JSON, nullable=True)  # Product categories affected
    affected_region_tags = Column(JSON, nullable=True)  # Regions affected

    # RAG embedding (filled by embedding service)
    embedding_text = Column(Text, nullable=True)  # Text used for embedding generation
    is_embedded = Column(Boolean, default=False, nullable=False)

    # Lifecycle
    expires_at = Column(DateTime, nullable=True)  # When this signal becomes stale
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "signal_key", name="uq_ext_signal_key"),
        Index("ix_ext_signal_tenant", "tenant_id"),
        Index("ix_ext_signal_category", "category"),
        Index("ix_ext_signal_date", "signal_date"),
        Index("ix_ext_signal_active", "is_active", "tenant_id"),
        Index("ix_ext_signal_source", "source_id"),
        Index("ix_ext_signal_relevance", "tenant_id", "relevance_score"),
    )
