"""External Signal models — Outside-in intelligence from public and commercial data sources.

Implements Lora Cecere's outside-in planning methodology adapted for TMS:
weather, economic indicators, energy/fuel prices, geopolitical events, consumer
sentiment, regulatory signals, freight market indices, carrier intelligence,
and ocean/port data are ingested on configurable cadences and injected into
Azirella's RAG context and TRM agent decision support.

Sources are tenant-configurable by industry, region, and product relevance.
Core sources use free, public APIs. Commercial freight market sources
(DAT, FreightWaves SONAR, Greenscreens) are wired as stubs — activated
when the customer has a subscription.

Signal categories:
- economic: CPI, PPI, unemployment, GDP, interest rates (FRED)
- weather: Temperature, precipitation, severe events (Open-Meteo, NWS)
- energy: Crude oil, natural gas, diesel fuel index (EIA / DOE)
- geopolitical: Disruption events, trade tensions, conflicts (GDELT)
- sentiment: Consumer/shipper search trends, worker sentiment (Google Trends, Reddit)
- regulatory: FDA recalls, safety alerts, hazmat compliance (openFDA)
- commodity: Agricultural, metals, chemical spot prices (World Bank/FRED)
- trade: Border wait times, tariffs, port congestion (Census/FRED, CBP)
- freight_market: Spot rates, tender rejection indices, capacity forecasts (DAT, SONAR, Greenscreens)
- carrier_intelligence: Safety ratings, inspection data, authority status (FMCSA)
- visibility: p44 aggregate metrics — tracking coverage, exception rates, webhook health
- ocean_intelligence: AIS vessel data, port dwell, congestion heat maps (MarineTraffic)
- sustainability: Emissions data, SmartWay scores, carbon intensity (EPA)
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
    # Shared (applicable to both SCP and TMS)
    "economic",              # CPI, PPI, unemployment, GDP, interest rates
    "weather",               # Temperature anomalies, precipitation, severe events
    "energy",                # Oil, gas, diesel fuel index, electricity prices
    "geopolitical",          # Disruption events, trade tensions, sanctions
    "sentiment",             # Consumer/shipper search trends, worker sentiment
    "regulatory",            # FDA recalls, safety alerts, hazmat compliance
    "commodity",             # Agricultural, metals, chemical spot prices
    "trade",                 # Border wait times, tariffs, port congestion
    # TMS-specific
    "freight_market",        # Spot rates, tender rejection, capacity indices
    "carrier_intelligence",  # Safety ratings, inspection data, authority status
    "visibility",            # p44 aggregate: tracking coverage, exception rates
    "ocean_intelligence",    # AIS vessel data, port dwell, congestion heat maps
    "sustainability",        # Emissions data, SmartWay scores, carbon intensity
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
        "description": (
            "Persistent road closures, bridge restrictions, port "
            "congestion, construction zones — not real-time traffic, "
            "but days/weeks-long freight routing disruptions."
        ),
    },
    # ── TMS-specific sources ──────────────────────────────────────────
    "fmcsa": {
        "name": "FMCSA SaferWeb (DOT Carrier Data)",
        "base_url": "https://mobile.fmcsa.dot.gov/qc/services",
        "categories": ["carrier_intelligence"],
        "requires_key": False,
        "free_tier": "Unlimited (US federal open data)",
        "refresh_cadence": "weekly",
        "description": (
            "Carrier safety ratings, inspection summary, OOS rates, "
            "insurance status, operating authority. Critical for "
            "carrier scorecard enrichment and compliance checks."
        ),
        "source_params_example": {
            "carrier_dots": ["12345", "67890"],
            "watch_fields": [
                "safetyRating", "oosRate", "insuranceStatus",
            ],
        },
    },
    "doe_diesel": {
        "name": "DOE Weekly Retail Diesel Fuel Index",
        "base_url": "https://api.eia.gov/v2",
        "categories": ["energy"],
        "requires_key": True,
        "key_env_var": "EIA_API_KEY",
        "free_tier": "Unlimited (same EIA key as existing source)",
        "refresh_cadence": "weekly",
        "description": (
            "US average retail diesel price "
            "(PET.EMD_EPD2D_PTE_NUS_DPG.W). The standard index used "
            "in most carrier contract fuel surcharge tables."
        ),
        "source_params_example": {
            "series_ids": ["PET.EMD_EPD2D_PTE_NUS_DPG.W"],
        },
    },
    "cbp_border_wait": {
        "name": "CBP Border Wait Times",
        "base_url": "https://bwt.cbp.gov/api",
        "categories": ["trade"],
        "requires_key": False,
        "free_tier": "Unlimited (US federal open data)",
        "refresh_cadence": "hourly",
        "description": (
            "Commercial vehicle wait times at US-Mexico and "
            "US-Canada border crossings. Critical for cross-border "
            "load planning and ETA adjustment."
        ),
        "source_params_example": {
            "ports": ["Laredo", "El Paso", "Detroit"],
            "vehicle_type": "commercial",
        },
    },
    "epa_smartway": {
        "name": "EPA SmartWay Carrier Performance",
        "base_url": "https://www.epa.gov/smartway",
        "categories": ["sustainability"],
        "requires_key": False,
        "free_tier": "Unlimited (public EPA data, bulk download)",
        "refresh_cadence": "quarterly",
        "description": (
            "Carrier fuel efficiency and emissions data from the "
            "SmartWay program. Feeds carrier scorecard sustainability "
            "score and supports Scope 3 emissions reporting."
        ),
    },
    # ── Commercial freight market sources (stubs — require paid subscription)
    "dat_rateview": {
        "name": "DAT RateView (Spot & Contract Rates)",
        "base_url": "https://api.dat.com",
        "categories": ["freight_market"],
        "requires_key": True,
        "key_env_var": "DAT_API_KEY",
        "free_tier": None,
        "refresh_cadence": "daily",
        "description": (
            "Real-time spot market rates by lane/equipment type. "
            "Critical for FreightProcurementTRM rate benchmarking "
            "and BrokerRoutingTRM spot-vs-contract decisions."
        ),
        "commercial": True,
        "source_params_example": {
            "lanes": [
                {"origin": "LAX", "dest": "PHX", "equipment": "V"},
            ],
        },
    },
    "freightwaves_sonar": {
        "name": "FreightWaves SONAR",
        "base_url": "https://api.freightwaves.com",
        "categories": ["freight_market"],
        "requires_key": True,
        "key_env_var": "SONAR_API_KEY",
        "free_tier": None,
        "refresh_cadence": "daily",
        "description": (
            "Outbound Tender Volume Index (OTVI), Outbound Tender "
            "Rejection Index (OTRI), rate forecasts by lane. The "
            "single best leading indicator for US freight capacity "
            "tightness — when OTRI rises, CapacityBufferTRM and "
            "FreightProcurementTRM must react."
        ),
        "commercial": True,
        "source_params_example": {
            "indices": ["OTVI.USA", "OTRI.USA", "OTVI.LAX"],
        },
    },
    "greenscreens": {
        "name": "Greenscreens.ai (Rate Intelligence)",
        "base_url": "https://api.greenscreens.ai",
        "categories": ["freight_market"],
        "requires_key": True,
        "key_env_var": "GREENSCREENS_API_KEY",
        "free_tier": None,
        "refresh_cadence": "daily",
        "description": (
            "Predictive rate intelligence and market-rate "
            "benchmarking. Feeds FreightProcurementTRM with "
            "confidence-scored rate predictions by lane."
        ),
        "commercial": True,
    },
    "marinetraffic": {
        "name": "MarineTraffic (AIS Vessel Data)",
        "base_url": "https://services.marinetraffic.com/api",
        "categories": ["ocean_intelligence"],
        "requires_key": True,
        "key_env_var": "MARINETRAFFIC_API_KEY",
        "free_tier": "Limited (100 credits on signup)",
        "refresh_cadence": "daily",
        "description": (
            "AIS vessel position tracking, port call predictions, "
            "congestion heat maps. Extends p44 ocean visibility "
            "with raw AIS data for IntermodalTransferTRM."
        ),
        "commercial": True,
    },
}

# ── TMS Signal Impact Mapping ────────────────────────────────────────────────
# Maps signal types to which TMS TRM agents and planning layers are affected.
# TRM type keys match the 11 TMS agents in services/powell/.

SIGNAL_TMS_IMPACT = {
    # ── Shared economic / macro signals ──────────────────────────────
    "cpi_change": {
        "trm_types": ["demand_sensing", "freight_procurement"],
        "planning_layer": "strategic",
        "description": (
            "Consumer price changes shift shipping volumes and "
            "carrier rate expectations"
        ),
    },
    "demand_trend_shift": {
        "trm_types": ["demand_sensing"],
        "planning_layer": "tactical",
        "description": (
            "Consumer interest shifts affect shipping volume "
            "forecasts by lane and commodity"
        ),
    },
    "commodity_price_change": {
        "trm_types": ["freight_procurement"],
        "planning_layer": "tactical",
        "description": (
            "Commodity price moves change the value-at-risk per "
            "load and may trigger rate renegotiation"
        ),
    },

    # ── Weather / disruption signals ─────────────────────────────────
    "severe_weather": {
        "trm_types": [
            "shipment_tracking", "exception_management",
            "equipment_reposition",
        ],
        "planning_layer": "execution",
        "description": (
            "Weather disruptions cause delays, route deviations, "
            "and facility closures — triggers exception detection "
            "and equipment repositioning"
        ),
    },

    # ── Energy / fuel signals ────────────────────────────────────────
    "oil_price_spike": {
        "trm_types": ["freight_procurement", "broker_routing"],
        "planning_layer": "tactical",
        "description": (
            "Energy price spikes raise fuel surcharges across "
            "active carrier contracts"
        ),
    },
    "diesel_price_move": {
        "trm_types": ["freight_procurement"],
        "planning_layer": "tactical",
        "description": (
            "DOE diesel index move triggers fuel surcharge "
            "recalculation across active contracts"
        ),
    },

    # ── Geopolitical signals ─────────────────────────────────────────
    "geopolitical_disruption": {
        "trm_types": [
            "capacity_buffer", "intermodal_transfer",
            "broker_routing",
        ],
        "planning_layer": "strategic",
        "description": (
            "Geopolitical events (port strikes, border closures, "
            "sanctions) require capacity hedging and alternate "
            "routing"
        ),
    },

    # ── Regulatory signals ───────────────────────────────────────────
    "regulatory_recall": {
        "trm_types": [
            "exception_management", "shipment_tracking",
        ],
        "planning_layer": "execution",
        "description": (
            "Regulatory actions (recalls, hazmat reclassification) "
            "require shipment holds and exception handling"
        ),
    },

    # ── Trade / border signals ───────────────────────────────────────
    "port_congestion": {
        "trm_types": [
            "intermodal_transfer", "capacity_buffer",
            "equipment_reposition",
        ],
        "planning_layer": "tactical",
        "description": (
            "Port delays affect ocean-to-drayage handoffs, "
            "container dwell, and equipment repositioning"
        ),
    },
    "border_wait_spike": {
        "trm_types": [
            "shipment_tracking", "dock_scheduling",
            "exception_management",
        ],
        "planning_layer": "execution",
        "description": (
            "Rising border wait times delay cross-border loads — "
            "adjust ETAs and downstream dock appointments"
        ),
    },

    # ── Freight market signals (new for TMS) ─────────────────────────
    "tender_rejection_spike": {
        "trm_types": [
            "capacity_buffer", "freight_procurement",
            "broker_routing",
        ],
        "planning_layer": "tactical",
        "description": (
            "Rising tender rejection rates (OTRI) signal capacity "
            "tightening — accelerate backup carrier activation "
            "and broker overflow"
        ),
    },
    "spot_rate_divergence": {
        "trm_types": ["freight_procurement", "broker_routing"],
        "planning_layer": "tactical",
        "description": (
            "Spot rates diverging from contract rates triggers "
            "procurement strategy review and mini-bid timing"
        ),
    },
    "capacity_index_shift": {
        "trm_types": [
            "capacity_promise", "capacity_buffer",
            "demand_sensing",
        ],
        "planning_layer": "strategic",
        "description": (
            "Freight market capacity indices (OTVI) shifting "
            "affects lane-level capacity commitments and demand "
            "forecast adjustments"
        ),
    },

    # ── Carrier intelligence signals (new for TMS) ───────────────────
    "carrier_safety_downgrade": {
        "trm_types": [
            "exception_management", "freight_procurement",
        ],
        "planning_layer": "execution",
        "description": (
            "Carrier safety rating change (FMCSA) requires "
            "immediate tender reallocation and scorecard update"
        ),
    },
    "carrier_authority_change": {
        "trm_types": ["freight_procurement"],
        "planning_layer": "execution",
        "description": (
            "Carrier operating authority revocation or suspension "
            "— immediately remove from active tender waterfall"
        ),
    },
    "carrier_insurance_lapse": {
        "trm_types": [
            "freight_procurement", "exception_management",
        ],
        "planning_layer": "execution",
        "description": (
            "Carrier insurance lapse detected — block new tenders "
            "until insurance is reinstated"
        ),
    },

    # ── Sustainability signals (new for TMS) ─────────────────────────
    "smartway_score_change": {
        "trm_types": ["freight_procurement"],
        "planning_layer": "strategic",
        "description": (
            "Carrier SmartWay score change affects sustainability "
            "weighting in procurement decisions"
        ),
    },
}

# Backwards-compat alias for any code referencing the old name
SIGNAL_SC_IMPACT = SIGNAL_TMS_IMPACT


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
    source_params = Column(JSON, nullable=True)
    # Source-specific parameters:
    # FRED: {"series_ids": ["CPIAUCSL", "UNRATE", "GDP"]}
    # Open-Meteo: {"locations": [...], "sync_from_network": true}
    # EIA: {"series_ids": ["PET.RWTC.D", "NG.RNGWHHD.D"]}
    # DOE diesel: {"series_ids": ["PET.EMD_EPD2D_PTE_NUS_DPG.W"]}
    # GDELT: {"keywords": ["port strike", "freight"], "countries": ["US"]}
    # Google Trends: {"keywords": ["freight rates", "shipping delays"]}
    # openFDA: {"product_types": ["food", "drug"], "keywords": ["recall"]}
    # FMCSA: {"carrier_dots": ["12345"], "watch_fields": ["safetyRating"]}
    # CBP: {"ports": ["Laredo", "El Paso"], "vehicle_type": "commercial"}
    # DAT: {"lanes": [{"origin": "LAX", "dest": "PHX", "equipment": "V"}]}
    # SONAR: {"indices": ["OTVI.USA", "OTRI.USA"]}

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
