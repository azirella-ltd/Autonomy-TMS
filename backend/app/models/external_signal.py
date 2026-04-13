"""External Signal — TMS-specific extensions of the canonical Context Engine.

Imports base categories, source registry, and model schemas from the
canonical `azirella_data_model.context_engine` subpackage in Core.
Extends with TMS-specific:

- 5 categories: freight_market, carrier_intelligence, visibility,
  ocean_intelligence, sustainability
- 8 sources: FMCSA SaferWeb, DOE diesel index, CBP border wait,
  EPA SmartWay (free), DAT RateView, FreightWaves SONAR, Greenscreens,
  MarineTraffic (commercial stubs)
- SIGNAL_TMS_IMPACT — routes signals to the 11 TMS TRM agents

Same shim pattern as tenant/master/governance/powell — Core defines the
canonical schema, TMS extends with domain-specific entries.
"""

# Re-export model classes from the canonical schema. Existing imports
# like `from app.models.external_signal import ExternalSignalSource`
# keep working unchanged.
from azirella_data_model.context_engine import (
    BASE_SIGNAL_CATEGORIES,
    BASE_SOURCE_REGISTRY,
    ExternalSignal,
    ExternalSignalSource,
)

__all__ = [
    "ExternalSignalSource",
    "ExternalSignal",
    "SIGNAL_CATEGORIES",
    "SOURCE_REGISTRY",
    "SIGNAL_TMS_IMPACT",
    "SIGNAL_SC_IMPACT",
]


# ── Signal Categories ────────────────────────────────────────────────────────
# Base categories (8) come from Core. TMS adds 5 domain-specific ones.

SIGNAL_CATEGORIES = BASE_SIGNAL_CATEGORIES + [
    "freight_market",        # Spot rates, tender rejection, capacity indices
    "carrier_intelligence",  # Safety ratings, inspection data, authority status
    "visibility",            # p44 aggregate: tracking coverage, exception rates
    "ocean_intelligence",    # AIS vessel data, port dwell, congestion heat maps
    "sustainability",        # Emissions data, SmartWay scores, carbon intensity
]

# ── Source Registry ──────────────────────────────────────────────────────────
# Base 9 free public sources come from Core (FRED, Open-Meteo, EIA, GDELT,
# Google Trends, openFDA, NWS, Reddit, DOT Disruptions). TMS adds 8 more:
# 4 free public sources useful only for TMS, plus 4 commercial stubs that
# require paid subscriptions.

SOURCE_REGISTRY = {
    **BASE_SOURCE_REGISTRY,
    # ── TMS free public sources ───────────────────────────────────────
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
# Stays in TMS — SCP has its own SIGNAL_SC_IMPACT routing to SCP TRM agents.

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

    # ── Freight market signals (TMS-only) ────────────────────────────
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

    # ── Carrier intelligence signals (TMS-only) ──────────────────────
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

    # ── Sustainability signals (TMS-only) ────────────────────────────
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
