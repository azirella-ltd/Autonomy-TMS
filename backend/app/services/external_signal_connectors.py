"""External Signal Source Connectors — Free public API integrations.

Each connector fetches data from a specific public API and returns normalized
ExternalSignalData objects ready for persistence and RAG embedding.

Implements Lora Cecere's outside-in planning: weather, economics, energy,
geopolitical events, consumer sentiment, and regulatory signals.

All sources are FREE tier — no paid subscriptions required.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

# Shared HTTP client settings
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_HEADERS = {"User-Agent": "Autonomy-SC-Platform/1.0 (supply-chain-planning)"}


@dataclass
class ExternalSignalData:
    """Normalized signal data from any external source."""
    source_key: str
    category: str
    signal_type: str
    signal_key: str  # Dedup key
    title: str
    summary: str
    signal_date: date
    raw_value: Optional[float] = None
    raw_unit: Optional[str] = None
    change_pct: Optional[float] = None
    change_direction: Optional[str] = None
    reference_period: Optional[str] = None
    previous_value: Optional[float] = None
    relevance_score: float = 0.5
    urgency_score: float = 0.3
    magnitude_score: float = 0.3
    affected_trm_types: List[str] = field(default_factory=list)
    planning_layer: Optional[str] = None
    affected_product_tags: List[str] = field(default_factory=list)
    affected_region_tags: List[str] = field(default_factory=list)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseConnector(ABC):
    """Abstract base for all external signal connectors."""

    source_key: str = ""
    categories: List[str] = []

    @abstractmethod
    async def fetch_signals(
        self,
        params: Dict[str, Any],
        since_date: Optional[date] = None,
    ) -> List[ExternalSignalData]:
        """Fetch signals from the source. Returns normalized signal data."""
        ...

    def _compute_change(self, current: float, previous: float) -> tuple:
        """Compute change percentage and direction."""
        if previous == 0:
            return (0.0, "stable")
        pct = ((current - previous) / abs(previous)) * 100
        direction = "up" if pct > 0.5 else ("down" if pct < -0.5 else "stable")
        return (round(pct, 2), direction)

    def _magnitude_from_change(self, change_pct: float) -> float:
        """Map absolute change % to a 0-1 magnitude score."""
        abs_change = abs(change_pct)
        if abs_change < 1:
            return 0.1
        elif abs_change < 3:
            return 0.3
        elif abs_change < 5:
            return 0.5
        elif abs_change < 10:
            return 0.7
        else:
            return 0.9


# ═══════════════════════════════════════════════════════════════════════════════
# 1. FRED — Federal Reserve Economic Data
# ═══════════════════════════════════════════════════════════════════════════════

# Core series everyone gets (macro indicators that affect all supply chains)
FRED_CORE_SERIES = {
    "UMCSENT": {"name": "Consumer Sentiment Index (U. Michigan)", "category": "sentiment", "signal_type": "consumer_sentiment", "unit": "index", "trm_types": ["forecast_adjustment"], "layer": "strategic"},
    "DCOILWTICO": {"name": "WTI Crude Oil Price", "category": "energy", "signal_type": "oil_price_spike", "unit": "usd/bbl", "trm_types": ["to_execution", "po_creation"], "layer": "tactical"},
    "DGS10": {"name": "10-Year Treasury Rate", "category": "economic", "signal_type": "interest_rate_change", "unit": "percent", "trm_types": ["po_creation"], "layer": "strategic"},
    "DTWEXBGS": {"name": "Trade Weighted US Dollar Index", "category": "trade", "signal_type": "currency_shift", "unit": "index", "trm_types": ["po_creation", "subcontracting"], "layer": "strategic"},
}

# Industry-specific FRED series — keyed by industry tag
FRED_INDUSTRY_SERIES = {
    "food_distribution": {
        "CUSR0000SAF1": {"name": "CPI: Food at Home", "category": "economic", "signal_type": "cpi_change", "unit": "index", "trm_types": ["forecast_adjustment", "po_creation"], "layer": "strategic"},
        "CUSR0000SEFV": {"name": "CPI: Food Away from Home", "category": "economic", "signal_type": "cpi_change", "unit": "index", "trm_types": ["forecast_adjustment"], "layer": "strategic"},
        "PCU311---311---": {"name": "PPI: Food Manufacturing", "category": "economic", "signal_type": "ppi_change", "unit": "index", "trm_types": ["po_creation", "subcontracting"], "layer": "tactical"},
        "WPU0223": {"name": "PPI: Processed Poultry", "category": "commodity", "signal_type": "commodity_price_change", "unit": "index", "trm_types": ["po_creation"], "layer": "tactical"},
        "APU0000708111": {"name": "Avg Price: Ground Beef (per lb)", "category": "commodity", "signal_type": "commodity_price_change", "unit": "usd/lb", "trm_types": ["po_creation"], "layer": "tactical"},
        "APU0000709112": {"name": "Avg Price: Milk, Fresh, Whole (per gal)", "category": "commodity", "signal_type": "commodity_price_change", "unit": "usd/gal", "trm_types": ["po_creation"], "layer": "tactical"},
    },
    "protein": {
        "WPU0223": {"name": "PPI: Processed Poultry", "category": "commodity", "signal_type": "commodity_price_change", "unit": "index", "trm_types": ["po_creation"], "layer": "tactical"},
        "APU0000706111": {"name": "Avg Price: Chicken Breast (per lb)", "category": "commodity", "signal_type": "commodity_price_change", "unit": "usd/lb", "trm_types": ["po_creation"], "layer": "tactical"},
        "WPU0213": {"name": "PPI: Beef and Veal", "category": "commodity", "signal_type": "commodity_price_change", "unit": "index", "trm_types": ["po_creation"], "layer": "tactical"},
    },
    "dairy": {
        "APU0000709112": {"name": "Avg Price: Milk, Fresh, Whole (per gal)", "category": "commodity", "signal_type": "commodity_price_change", "unit": "usd/gal", "trm_types": ["po_creation"], "layer": "tactical"},
        "WPU0224": {"name": "PPI: Dairy Products", "category": "commodity", "signal_type": "commodity_price_change", "unit": "index", "trm_types": ["po_creation"], "layer": "tactical"},
        "APU0000710212": {"name": "Avg Price: Cheddar Cheese (per lb)", "category": "commodity", "signal_type": "commodity_price_change", "unit": "usd/lb", "trm_types": ["po_creation"], "layer": "tactical"},
    },
    "beverage": {
        "CUSR0000SEFN": {"name": "CPI: Nonalcoholic Beverages", "category": "economic", "signal_type": "cpi_change", "unit": "index", "trm_types": ["forecast_adjustment"], "layer": "strategic"},
        "APU0000FJ4101": {"name": "Avg Price: Orange Juice (per 16oz)", "category": "commodity", "signal_type": "commodity_price_change", "unit": "usd/16oz", "trm_types": ["po_creation"], "layer": "tactical"},
        "PCU31211-31211-": {"name": "PPI: Soft Drink Manufacturing", "category": "economic", "signal_type": "ppi_change", "unit": "index", "trm_types": ["po_creation"], "layer": "tactical"},
    },
    "frozen_foods": {
        "CUSR0000SEFK": {"name": "CPI: Frozen Foods", "category": "economic", "signal_type": "cpi_change", "unit": "index", "trm_types": ["forecast_adjustment"], "layer": "strategic"},
        "WPU0232": {"name": "PPI: Frozen Fruits, Juices, Vegetables", "category": "commodity", "signal_type": "commodity_price_change", "unit": "index", "trm_types": ["po_creation"], "layer": "tactical"},
    },
    "manufacturing": {
        "CPIAUCSL": {"name": "Consumer Price Index (All Urban)", "category": "economic", "signal_type": "cpi_change", "unit": "index", "trm_types": ["forecast_adjustment", "po_creation"], "layer": "strategic"},
        "PPIACO": {"name": "Producer Price Index (All Commodities)", "category": "economic", "signal_type": "ppi_change", "unit": "index", "trm_types": ["po_creation", "subcontracting"], "layer": "tactical"},
        "PCUOMFG--OMFG--": {"name": "PPI: Manufacturing Industries", "category": "economic", "signal_type": "manufacturing_cost_change", "unit": "index", "trm_types": ["mo_execution", "subcontracting"], "layer": "tactical"},
        "IPMAN": {"name": "Industrial Production: Manufacturing", "category": "economic", "signal_type": "manufacturing_output", "unit": "index", "trm_types": ["mo_execution"], "layer": "tactical"},
    },
}

# Regional FRED series — keyed by region tag
FRED_REGIONAL_SERIES = {
    "us_west": {
        "LAUCT064174000000003": {"name": "Unemployment: Los Angeles Metro", "category": "economic", "signal_type": "unemployment_change", "unit": "percent", "trm_types": ["forecast_adjustment"], "layer": "strategic"},
        "EMD_EPD2D_PTE_R50_DPG": {"name": "Diesel Price: West Coast", "category": "energy", "signal_type": "diesel_price_change", "unit": "usd/gallon", "trm_types": ["to_execution"], "layer": "tactical"},
    },
    "us_northwest": {
        "WASEURN": {"name": "Unemployment Rate: Washington State", "category": "economic", "signal_type": "unemployment_change", "unit": "percent", "trm_types": ["forecast_adjustment"], "layer": "strategic"},
        "ORSEURN": {"name": "Unemployment Rate: Oregon", "category": "economic", "signal_type": "unemployment_change", "unit": "percent", "trm_types": ["forecast_adjustment"], "layer": "strategic"},
    },
    "us_southwest": {
        "AZSEURN": {"name": "Unemployment Rate: Arizona", "category": "economic", "signal_type": "unemployment_change", "unit": "percent", "trm_types": ["forecast_adjustment"], "layer": "strategic"},
    },
    "us_south": {
        "TXSEURN": {"name": "Unemployment Rate: Texas", "category": "economic", "signal_type": "unemployment_change", "unit": "percent", "trm_types": ["forecast_adjustment"], "layer": "strategic"},
        "EMD_EPD2D_PTE_R30_DPG": {"name": "Diesel Price: Gulf Coast", "category": "energy", "signal_type": "diesel_price_change", "unit": "usd/gallon", "trm_types": ["to_execution"], "layer": "tactical"},
    },
    "us_midwest": {
        "EMD_EPD2D_PTE_R20_DPG": {"name": "Diesel Price: Midwest", "category": "energy", "signal_type": "diesel_price_change", "unit": "usd/gallon", "trm_types": ["to_execution"], "layer": "tactical"},
    },
    "us_northeast": {
        "EMD_EPD2D_PTE_R10_DPG": {"name": "Diesel Price: East Coast", "category": "energy", "signal_type": "diesel_price_change", "unit": "usd/gallon", "trm_types": ["to_execution"], "layer": "tactical"},
    },
}

# Logistics series — always included for SC planning
FRED_LOGISTICS_SERIES = {
    "DHHNGSP": {"name": "Henry Hub Natural Gas Price", "category": "energy", "signal_type": "gas_price_change", "unit": "usd/mmbtu", "trm_types": ["to_execution", "mo_execution"], "layer": "tactical"},
    "DTBSOBCL": {"name": "Baltic Dry Index (proxy — Dry Bulk Shipping)", "category": "trade", "signal_type": "shipping_cost_change", "unit": "index", "trm_types": ["to_execution", "po_creation"], "layer": "tactical"},
    "UNRATE": {"name": "Unemployment Rate (National)", "category": "economic", "signal_type": "unemployment_change", "unit": "percent", "trm_types": ["forecast_adjustment"], "layer": "strategic"},
    "VIXCLS": {"name": "CBOE Volatility Index (VIX — Market Fear)", "category": "sentiment", "signal_type": "market_fear", "unit": "index", "trm_types": ["po_creation", "inventory_buffer"], "layer": "strategic"},
}

# Industry-specific sentiment sources — subreddit keywords for Reddit connector
INDUSTRY_SUBREDDITS = {
    "food_distribution": ["supplychain", "foodservice", "KitchenConfidential", "restaurants", "Chefit"],
    "protein": ["supplychain", "meat", "butchery"],
    "dairy": ["supplychain", "cheese", "dairy"],
    "beverage": ["supplychain", "coffee", "beer", "craftbeer"],
    "manufacturing": ["supplychain", "manufacturing", "engineering", "lean"],
    "frozen_foods": ["supplychain", "foodservice", "MealPrepSunday"],
}

# Industry-specific news keywords for sentiment analysis
INDUSTRY_SENTIMENT_KEYWORDS = {
    "food_distribution": ["food supply shortage", "restaurant closures", "food price", "foodservice demand", "menu price increase", "food recall"],
    "protein": ["chicken shortage", "beef price", "pork supply", "seafood import", "USDA recall"],
    "dairy": ["dairy surplus", "milk price", "cheese shortage", "butter supply"],
    "beverage": ["beverage trend", "coffee price", "energy drink demand"],
    "frozen_foods": ["frozen food recall", "cold chain disruption", "freezer capacity"],
    "manufacturing": ["supply chain bottleneck", "factory shutdown", "raw material shortage", "labor shortage manufacturing"],
}


def build_fred_series(industry_tags: List[str] = None, region_tags: List[str] = None) -> Dict[str, dict]:
    """Build a tenant-specific FRED series set from industry and region context.

    A food distributor in the Western US gets Food CPI, Poultry PPI, West Coast Diesel,
    and WA/OR unemployment — not just generic national indicators.
    """
    series = {}

    # Always include core macro + logistics
    series.update(FRED_CORE_SERIES)
    series.update(FRED_LOGISTICS_SERIES)

    # Add industry-specific series
    for tag in (industry_tags or []):
        industry_series = FRED_INDUSTRY_SERIES.get(tag, {})
        series.update(industry_series)

    # Add regional series
    for tag in (region_tags or []):
        regional_series = FRED_REGIONAL_SERIES.get(tag, {})
        series.update(regional_series)

    # Fallback: if no industry matched, add generic CPI/PPI
    if not any(tag in FRED_INDUSTRY_SERIES for tag in (industry_tags or [])):
        series["CPIAUCSL"] = {"name": "Consumer Price Index (All Urban)", "category": "economic", "signal_type": "cpi_change", "unit": "index", "trm_types": ["forecast_adjustment", "po_creation"], "layer": "strategic"}
        series["PPIACO"] = {"name": "Producer Price Index (All Commodities)", "category": "economic", "signal_type": "ppi_change", "unit": "index", "trm_types": ["po_creation", "subcontracting"], "layer": "tactical"}

    return series


class FREDConnector(BaseConnector):
    """FRED API connector — economic indicators, commodity prices, trade data.

    Registration: https://fred.stlouisfed.org/docs/api/api_key.html (free)
    Rate limit: Unlimited for registered keys.
    """

    source_key = "fred"
    categories = ["economic", "energy", "commodity", "trade", "sentiment"]

    def __init__(self):
        self.api_key = os.getenv("FRED_API_KEY", "")
        self.base_url = "https://api.stlouisfed.org/fred"

    async def fetch_signals(
        self,
        params: Dict[str, Any],
        since_date: Optional[date] = None,
    ) -> List[ExternalSignalData]:
        if not self.api_key:
            logger.warning("FRED_API_KEY not set — skipping FRED connector")
            return []

        # Build industry/region-aware series set from source params
        industry_tags = params.get("industry_tags", [])
        region_tags = params.get("region_tags", [])
        tenant_series = build_fred_series(industry_tags, region_tags)

        # Allow explicit overrides via series_ids param
        series_ids = params.get("series_ids", list(tenant_series.keys()))
        signals = []
        since = since_date or (date.today() - timedelta(days=7))

        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            for series_id in series_ids:
                try:
                    meta = tenant_series.get(series_id, {})
                    resp = await client.get(
                        f"{self.base_url}/series/observations",
                        params={
                            "series_id": series_id,
                            "api_key": self.api_key,
                            "file_type": "json",
                            "sort_order": "desc",
                            "limit": 5,
                            "observation_start": since.isoformat(),
                        },
                    )
                    if resp.status_code != 200:
                        logger.warning(f"FRED {series_id}: HTTP {resp.status_code}")
                        continue

                    data = resp.json()
                    obs = data.get("observations", [])
                    # Filter out missing values
                    obs = [o for o in obs if o.get("value") not in (".", "", None)]
                    if len(obs) < 1:
                        continue

                    current = float(obs[0]["value"])
                    previous = float(obs[1]["value"]) if len(obs) > 1 else None
                    obs_date = date.fromisoformat(obs[0]["date"])

                    change_pct, direction = (0.0, "stable")
                    if previous is not None:
                        change_pct, direction = self._compute_change(current, previous)

                    name = meta.get("name", series_id)
                    unit = meta.get("unit", "")
                    signal_type = meta.get("signal_type", "economic_indicator")

                    # Build SC-relevant summary
                    dir_word = {"up": "increased", "down": "decreased", "stable": "remained stable"}[direction]
                    summary = (
                        f"{name} {dir_word} to {current:.2f} {unit} "
                        f"({'+' if change_pct > 0 else ''}{change_pct:.1f}% change). "
                    )
                    if signal_type == "cpi_change" and abs(change_pct) > 0.3:
                        summary += "This may affect consumer demand patterns and procurement pricing. "
                    elif signal_type == "oil_price_spike" and abs(change_pct) > 3:
                        summary += "Significant energy price movement — review transportation and logistics costs. "
                    elif signal_type == "consumer_sentiment" and abs(change_pct) > 2:
                        summary += "Shifting consumer confidence may impact near-term demand forecasts. "

                    signals.append(ExternalSignalData(
                        source_key="fred",
                        category=meta.get("category", "economic"),
                        signal_type=signal_type,
                        signal_key=f"fred:{series_id}:{obs_date.isoformat()}",
                        title=f"{name}: {current:.2f} {unit} ({'+' if change_pct > 0 else ''}{change_pct:.1f}%)",
                        summary=summary.strip(),
                        signal_date=obs_date,
                        raw_value=current,
                        raw_unit=unit,
                        change_pct=change_pct,
                        change_direction=direction,
                        previous_value=previous,
                        relevance_score=min(0.4 + self._magnitude_from_change(change_pct) * 0.6, 1.0),
                        urgency_score=0.5 if abs(change_pct) > 3 else 0.3,
                        magnitude_score=self._magnitude_from_change(change_pct),
                        affected_trm_types=meta.get("trm_types", []),
                        planning_layer=meta.get("layer", "strategic"),
                        expires_at=datetime.utcnow() + timedelta(days=7),
                    ))
                except Exception as e:
                    logger.warning(f"FRED {series_id} fetch failed: {e}")

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Open-Meteo — Weather Data (No API key needed)
# ═══════════════════════════════════════════════════════════════════════════════

class OpenMeteoConnector(BaseConnector):
    """Open-Meteo weather API — temperature, precipitation, severe weather.

    No registration needed. 10,000 requests/day free.
    https://open-meteo.com/en/docs
    """

    source_key = "open_meteo"
    categories = ["weather"]

    async def fetch_signals(
        self,
        params: Dict[str, Any],
        since_date: Optional[date] = None,
    ) -> List[ExternalSignalData]:
        locations = params.get("locations", [
            {"lat": 40.71, "lon": -74.01, "name": "New York", "region": "us_northeast"},
            {"lat": 34.05, "lon": -118.24, "name": "Los Angeles", "region": "us_west"},
            {"lat": 41.88, "lon": -87.63, "name": "Chicago", "region": "us_midwest"},
            {"lat": 29.76, "lon": -95.37, "name": "Houston", "region": "us_south"},
        ])

        signals = []
        today = date.today()
        start = since_date or (today - timedelta(days=1))

        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            for loc in locations:
                try:
                    resp = await client.get(
                        "https://api.open-meteo.com/v1/forecast",
                        params={
                            "latitude": loc["lat"],
                            "longitude": loc["lon"],
                            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
                            "timezone": "auto",
                            "start_date": start.isoformat(),
                            "end_date": today.isoformat(),
                        },
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json().get("daily", {})
                    dates = data.get("time", [])
                    temps_max = data.get("temperature_2m_max", [])
                    temps_min = data.get("temperature_2m_min", [])
                    precip = data.get("precipitation_sum", [])
                    wind = data.get("windspeed_10m_max", [])

                    for i, d in enumerate(dates):
                        obs_date = date.fromisoformat(d)
                        t_max = temps_max[i] if i < len(temps_max) and temps_max[i] is not None else None
                        t_min = temps_min[i] if i < len(temps_min) and temps_min[i] is not None else None
                        p = precip[i] if i < len(precip) and precip[i] is not None else 0
                        w = wind[i] if i < len(wind) and wind[i] is not None else 0

                        if t_max is None:
                            continue

                        # Detect SC-relevant weather events
                        is_extreme_heat = t_max > 38  # >100°F
                        is_extreme_cold = t_min is not None and t_min < -15  # <5°F
                        is_heavy_precip = p > 25  # >1 inch
                        is_high_wind = w > 80  # >50 mph

                        if not (is_extreme_heat or is_extreme_cold or is_heavy_precip or is_high_wind):
                            # Only report weather signals with SC impact
                            continue

                        event_parts = []
                        if is_extreme_heat:
                            event_parts.append(f"extreme heat ({t_max:.0f}°C)")
                        if is_extreme_cold:
                            event_parts.append(f"extreme cold ({t_min:.0f}°C)")
                        if is_heavy_precip:
                            event_parts.append(f"heavy precipitation ({p:.0f}mm)")
                        if is_high_wind:
                            event_parts.append(f"high winds ({w:.0f}km/h)")

                        event_str = ", ".join(event_parts)
                        name = loc.get("name", f"{loc['lat']},{loc['lon']}")
                        region = loc.get("region", "unknown")

                        summary = (
                            f"Severe weather in {name}: {event_str}. "
                            f"May impact transportation routes, warehouse operations, "
                            f"and delivery schedules in the {region.replace('_', ' ')} region."
                        )

                        urgency = 0.7 if (is_extreme_heat or is_extreme_cold or is_high_wind) else 0.5
                        relevance = 0.6 if is_heavy_precip else 0.7

                        signals.append(ExternalSignalData(
                            source_key="open_meteo",
                            category="weather",
                            signal_type="severe_weather",
                            signal_key=f"open_meteo:{name}:{obs_date.isoformat()}",
                            title=f"Severe weather in {name}: {event_str}",
                            summary=summary,
                            signal_date=obs_date,
                            raw_value=t_max,
                            raw_unit="celsius",
                            relevance_score=relevance,
                            urgency_score=urgency,
                            magnitude_score=0.6,
                            affected_trm_types=["to_execution", "po_creation", "inventory_buffer"],
                            planning_layer="tactical",
                            affected_region_tags=[region],
                            expires_at=datetime.utcnow() + timedelta(days=3),
                        ))
                except Exception as e:
                    logger.warning(f"Open-Meteo {loc.get('name', 'unknown')} fetch failed: {e}")

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EIA — Energy Information Administration
# ═══════════════════════════════════════════════════════════════════════════════

EIA_DEFAULT_SERIES = {
    "PET.RWTC.D": {
        "name": "WTI Crude Oil Spot Price",
        "signal_type": "oil_price_spike",
        "unit": "usd/bbl",
        "trm_types": ["to_execution", "po_creation"],
    },
    "NG.RNGWHHD.D": {
        "name": "Henry Hub Natural Gas Spot Price",
        "signal_type": "gas_price_change",
        "unit": "usd/mmbtu",
        "trm_types": ["mo_execution", "to_execution"],
    },
    "PET.EMD_EPD2DXL0_PTE_NUS_DPG.W": {
        "name": "US Diesel Fuel Price",
        "signal_type": "diesel_price_change",
        "unit": "usd/gallon",
        "trm_types": ["to_execution"],
    },
}


class EIAConnector(BaseConnector):
    """EIA API connector — energy prices critical for logistics cost planning.

    Registration: https://www.eia.gov/opendata/register.php (free)
    """

    source_key = "eia"
    categories = ["energy"]

    def __init__(self):
        self.api_key = os.getenv("EIA_API_KEY", "")
        self.base_url = "https://api.eia.gov/v2"

    async def fetch_signals(
        self,
        params: Dict[str, Any],
        since_date: Optional[date] = None,
    ) -> List[ExternalSignalData]:
        if not self.api_key:
            logger.warning("EIA_API_KEY not set — skipping EIA connector")
            return []

        series_ids = params.get("series_ids", list(EIA_DEFAULT_SERIES.keys()))
        signals = []
        since = since_date or (date.today() - timedelta(days=7))

        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            for series_id in series_ids:
                try:
                    meta = EIA_DEFAULT_SERIES.get(series_id, {})
                    # EIA v2 uses route-based API
                    route = series_id.replace(".", "/")
                    resp = await client.get(
                        f"{self.base_url}/{route}",
                        params={
                            "api_key": self.api_key,
                            "frequency": "daily",
                            "start": since.isoformat(),
                            "sort[0][column]": "period",
                            "sort[0][direction]": "desc",
                            "length": 5,
                        },
                    )
                    if resp.status_code != 200:
                        # Fallback to v1-style series endpoint
                        resp = await client.get(
                            f"{self.base_url}/seriesid/{series_id}",
                            params={
                                "api_key": self.api_key,
                                "start": since.isoformat(),
                                "sort[0][column]": "period",
                                "sort[0][direction]": "desc",
                                "length": 5,
                            },
                        )
                        if resp.status_code != 200:
                            logger.warning(f"EIA {series_id}: HTTP {resp.status_code}")
                            continue

                    data = resp.json()
                    response_data = data.get("response", {}).get("data", [])
                    if not response_data:
                        continue

                    current_row = response_data[0]
                    current = float(current_row.get("value", 0))
                    obs_date_str = current_row.get("period", date.today().isoformat())
                    try:
                        obs_date = date.fromisoformat(obs_date_str[:10])
                    except (ValueError, TypeError):
                        obs_date = date.today()

                    previous = float(response_data[1]["value"]) if len(response_data) > 1 else None
                    change_pct, direction = (0.0, "stable")
                    if previous is not None:
                        change_pct, direction = self._compute_change(current, previous)

                    name = meta.get("name", series_id)
                    unit = meta.get("unit", "")
                    signal_type = meta.get("signal_type", "energy_price_change")

                    dir_word = {"up": "rose", "down": "fell", "stable": "held steady"}[direction]
                    summary = (
                        f"{name} {dir_word} to ${current:.2f}/{unit.split('/')[-1] if '/' in unit else unit} "
                        f"({'+' if change_pct > 0 else ''}{change_pct:.1f}%). "
                        f"Transportation and logistics cost impact for supply chain operations."
                    )

                    signals.append(ExternalSignalData(
                        source_key="eia",
                        category="energy",
                        signal_type=signal_type,
                        signal_key=f"eia:{series_id}:{obs_date.isoformat()}",
                        title=f"{name}: ${current:.2f} ({'+' if change_pct > 0 else ''}{change_pct:.1f}%)",
                        summary=summary,
                        signal_date=obs_date,
                        raw_value=current,
                        raw_unit=unit,
                        change_pct=change_pct,
                        change_direction=direction,
                        previous_value=previous,
                        relevance_score=min(0.5 + self._magnitude_from_change(change_pct) * 0.5, 1.0),
                        urgency_score=0.6 if abs(change_pct) > 5 else 0.3,
                        magnitude_score=self._magnitude_from_change(change_pct),
                        affected_trm_types=meta.get("trm_types", []),
                        planning_layer="tactical",
                        expires_at=datetime.utcnow() + timedelta(days=5),
                    ))
                except Exception as e:
                    logger.warning(f"EIA {series_id} fetch failed: {e}")

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GDELT — Global Database of Events, Language, and Tone
# ═══════════════════════════════════════════════════════════════════════════════

class GDELTConnector(BaseConnector):
    """GDELT API connector — geopolitical events, disruptions, trade news WITH sentiment.

    GDELT articles include a `tone` field: average tone of the article on a scale
    from -100 (extremely negative) to +100 (extremely positive). We use this as
    a sentiment signal for supply chain risk assessment.

    No registration needed. Unlimited access to open data.
    https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
    """

    source_key = "gdelt"
    categories = ["geopolitical", "sentiment"]

    async def fetch_signals(
        self,
        params: Dict[str, Any],
        since_date: Optional[date] = None,
    ) -> List[ExternalSignalData]:
        keywords = params.get("keywords", [
            "supply chain disruption",
            "port strike",
            "trade sanctions",
            "factory shutdown",
            "shipping delay",
            "border closure",
        ])

        # Add industry-specific sentiment keywords
        industry_tags = params.get("industry_tags", [])
        for tag in industry_tags:
            sentiment_kws = INDUSTRY_SENTIMENT_KEYWORDS.get(tag, [])
            for kw in sentiment_kws:
                if kw not in keywords:
                    keywords.append(kw)

        countries = params.get("countries", [])
        signals = []
        since = since_date or (date.today() - timedelta(days=1))

        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            for keyword in keywords[:15]:  # Allow more with sentiment keywords
                try:
                    query = keyword
                    if countries:
                        query += f" ({' OR '.join(countries)})"

                    resp = await client.get(
                        "https://api.gdeltproject.org/api/v2/doc/doc",
                        params={
                            "query": query,
                            "mode": "artlist",
                            "format": "json",
                            "maxrecords": 5,
                            "startdatetime": since.strftime("%Y%m%d%H%M%S"),
                            "sort": "datedesc",
                        },
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    articles = data.get("articles", [])

                    for article in articles[:3]:
                        title = article.get("title", "")
                        url = article.get("url", "")
                        seendate = article.get("seendate", "")

                        if not title:
                            continue

                        try:
                            obs_date = datetime.strptime(seendate[:8], "%Y%m%d").date() if seendate else date.today()
                        except (ValueError, TypeError):
                            obs_date = date.today()

                        # ── Sentiment scoring from GDELT tone ────────────
                        # GDELT tone: -100 (very negative) to +100 (very positive)
                        # Typical news: -5 to +5. SC disruptions: -10 to -20.
                        tone = 0.0
                        tone_raw = article.get("tone", 0)
                        if isinstance(tone_raw, (int, float)):
                            tone = float(tone_raw)

                        # Map tone to sentiment label and urgency
                        if tone < -10:
                            sentiment_label = "very negative"
                            urgency = 0.85
                            relevance = 0.8
                        elif tone < -5:
                            sentiment_label = "negative"
                            urgency = 0.7
                            relevance = 0.7
                        elif tone < -2:
                            sentiment_label = "slightly negative"
                            urgency = 0.5
                            relevance = 0.6
                        elif tone > 5:
                            sentiment_label = "positive"
                            urgency = 0.2
                            relevance = 0.4
                        else:
                            sentiment_label = "neutral"
                            urgency = 0.3
                            relevance = 0.5

                        # Derive signal type from keyword
                        signal_type = "geopolitical_disruption"
                        category = "geopolitical"
                        if any(w in keyword.lower() for w in ("port", "shipping", "freight")):
                            signal_type = "port_congestion"
                        elif any(w in keyword.lower() for w in ("sanction", "trade", "tariff")):
                            signal_type = "trade_restriction"
                        elif any(w in keyword.lower() for w in ("price", "cost", "shortage", "recall", "demand")):
                            signal_type = "industry_sentiment"
                            category = "sentiment"

                        summary = (
                            f"{title}. "
                            f"Sentiment: {sentiment_label} (tone: {tone:+.1f}). "
                            f"Search: '{keyword}'. "
                        )
                        if tone < -5:
                            summary += "Negative sentiment may signal supply risk, demand shift, or cost pressure. "
                        elif tone > 5:
                            summary += "Positive sentiment may indicate improving conditions. "

                        dedup_key = f"gdelt:{hash(title) & 0xFFFFFFFF}:{obs_date.isoformat()}"

                        signals.append(ExternalSignalData(
                            source_key="gdelt",
                            category=category,
                            signal_type=signal_type,
                            signal_key=dedup_key,
                            title=title[:500],
                            summary=summary.strip(),
                            signal_date=obs_date,
                            raw_value=tone,
                            raw_unit="tone_score",
                            relevance_score=relevance,
                            urgency_score=urgency,
                            magnitude_score=min(abs(tone) / 15, 1.0),
                            affected_trm_types=["po_creation", "subcontracting", "inventory_buffer", "forecast_adjustment"],
                            planning_layer="strategic",
                            expires_at=datetime.utcnow() + timedelta(days=3),
                            metadata={"url": url, "keyword": keyword, "tone": tone, "sentiment": sentiment_label},
                        ))
                except Exception as e:
                    logger.warning(f"GDELT '{keyword}' fetch failed: {e}")

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Google Trends — Consumer Search Sentiment
# ═══════════════════════════════════════════════════════════════════════════════

class GoogleTrendsConnector(BaseConnector):
    """Google Trends connector — consumer interest and demand signals.

    Uses direct HTTP (no pytrends dependency needed for basic interest-over-time).
    Rate-limited — use sparingly.
    """

    source_key = "google_trends"
    categories = ["sentiment"]

    async def fetch_signals(
        self,
        params: Dict[str, Any],
        since_date: Optional[date] = None,
    ) -> List[ExternalSignalData]:
        keywords = params.get("keywords", [])
        if not keywords:
            return []

        signals = []
        today = date.today()

        # Google Trends doesn't have a clean REST API — use pytrends if available
        try:
            from pytrends.request import TrendReq
        except ImportError:
            logger.info("pytrends not installed — skipping Google Trends connector. Install with: pip install pytrends")
            return []

        try:
            pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))

            # Batch keywords (max 5 per request)
            for batch_start in range(0, len(keywords), 5):
                batch = keywords[batch_start:batch_start + 5]
                try:
                    pytrends.build_payload(batch, timeframe="today 1-m", geo="US")
                    interest = pytrends.interest_over_time()

                    if interest.empty:
                        continue

                    for kw in batch:
                        if kw not in interest.columns:
                            continue

                        recent = interest[kw].tail(7)
                        older = interest[kw].tail(14).head(7)

                        if recent.empty or older.empty:
                            continue

                        current_avg = float(recent.mean())
                        previous_avg = float(older.mean())
                        change_pct, direction = self._compute_change(current_avg, previous_avg)

                        if abs(change_pct) < 10:
                            # Only report significant trend shifts
                            continue

                        dir_word = {"up": "surging", "down": "declining", "stable": "stable"}[direction]
                        summary = (
                            f"Consumer search interest for '{kw}' is {dir_word} "
                            f"({'+' if change_pct > 0 else ''}{change_pct:.0f}% week-over-week). "
                            f"This may signal shifting consumer demand patterns."
                        )

                        signals.append(ExternalSignalData(
                            source_key="google_trends",
                            category="sentiment",
                            signal_type="demand_trend_shift",
                            signal_key=f"google_trends:{kw}:{today.isoformat()}",
                            title=f"Search trend '{kw}': {'+' if change_pct > 0 else ''}{change_pct:.0f}% WoW",
                            summary=summary,
                            signal_date=today,
                            raw_value=current_avg,
                            raw_unit="trend_index",
                            change_pct=change_pct,
                            change_direction=direction,
                            previous_value=previous_avg,
                            relevance_score=min(0.3 + abs(change_pct) / 100, 0.9),
                            urgency_score=0.4,
                            magnitude_score=self._magnitude_from_change(change_pct),
                            affected_trm_types=["forecast_adjustment"],
                            planning_layer="tactical",
                            expires_at=datetime.utcnow() + timedelta(days=7),
                        ))
                except Exception as e:
                    logger.warning(f"Google Trends batch {batch} failed: {e}")

        except Exception as e:
            logger.warning(f"Google Trends connector failed: {e}")

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# 6. openFDA — Regulatory Signals
# ═══════════════════════════════════════════════════════════════════════════════

class OpenFDAConnector(BaseConnector):
    """openFDA API connector — recalls, safety alerts, enforcement actions.

    No registration needed for 1,000 requests/day.
    https://open.fda.gov/apis/
    """

    source_key = "openfda"
    categories = ["regulatory"]

    async def fetch_signals(
        self,
        params: Dict[str, Any],
        since_date: Optional[date] = None,
    ) -> List[ExternalSignalData]:
        product_types = params.get("product_types", ["food"])
        search_keywords = params.get("keywords", ["recall"])
        signals = []
        since = since_date or (date.today() - timedelta(days=7))

        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            for ptype in product_types:
                try:
                    # openFDA enforcement endpoint for recalls
                    search_parts = [f'report_date:[{since.strftime("%Y%m%d")}+TO+{date.today().strftime("%Y%m%d")}]']
                    if ptype == "food":
                        endpoint = "https://api.fda.gov/food/enforcement.json"
                    elif ptype == "drug":
                        endpoint = "https://api.fda.gov/drug/enforcement.json"
                    elif ptype == "device":
                        endpoint = "https://api.fda.gov/device/enforcement.json"
                    else:
                        endpoint = "https://api.fda.gov/food/enforcement.json"

                    resp = await client.get(
                        endpoint,
                        params={
                            "search": "+AND+".join(search_parts),
                            "limit": 10,
                            "sort": "report_date:desc",
                        },
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    results = data.get("results", [])

                    for item in results[:5]:
                        reason = item.get("reason_for_recall", "")
                        product_desc = item.get("product_description", "")
                        classification = item.get("classification", "")
                        status = item.get("status", "")
                        report_date = item.get("report_date", "")
                        recalling_firm = item.get("recalling_firm", "Unknown")

                        if not reason:
                            continue

                        try:
                            obs_date = datetime.strptime(report_date[:8], "%Y%m%d").date() if report_date else date.today()
                        except (ValueError, TypeError):
                            obs_date = date.today()

                        # Classification drives urgency: I = serious, II = moderate, III = minor
                        urgency_map = {"Class I": 0.9, "Class II": 0.6, "Class III": 0.3}
                        urgency = urgency_map.get(classification, 0.5)

                        summary = (
                            f"FDA {classification} recall by {recalling_firm}: {reason[:200]}. "
                            f"Product: {product_desc[:150]}. Status: {status}. "
                            f"Review quality holds and inventory for affected products."
                        )

                        dedup_key = f"openfda:{ptype}:{hash(reason[:100]) & 0xFFFFFFFF}:{obs_date.isoformat()}"

                        signals.append(ExternalSignalData(
                            source_key="openfda",
                            category="regulatory",
                            signal_type="regulatory_recall",
                            signal_key=dedup_key,
                            title=f"FDA {classification} Recall: {recalling_firm} — {product_desc[:100]}",
                            summary=summary,
                            signal_date=obs_date,
                            relevance_score=0.7 if classification == "Class I" else 0.5,
                            urgency_score=urgency,
                            magnitude_score=urgency,
                            affected_trm_types=["quality_disposition", "inventory_rebalancing"],
                            planning_layer="execution",
                            expires_at=datetime.utcnow() + timedelta(days=30),
                            metadata={"recalling_firm": recalling_firm, "classification": classification},
                        ))
                except Exception as e:
                    logger.warning(f"openFDA {ptype} fetch failed: {e}")

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# 7. NWS Alerts — National Weather Service Severe Weather Warnings
# ═══════════════════════════════════════════════════════════════════════════════

class NWSAlertsConnector(BaseConnector):
    """NWS Alerts API — severe weather warnings with geographic polygons.

    More actionable than Open-Meteo for SC planning: includes Winter Storm
    Warnings, Flood Watches, Tornado Warnings, Excessive Heat, etc.
    Each alert has a geographic area and explicit severity/urgency.

    No API key needed. https://www.weather.gov/documentation/services-web-api
    """

    source_key = "nws_alerts"
    categories = ["weather"]

    async def fetch_signals(
        self,
        params: Dict[str, Any],
        since_date: Optional[date] = None,
    ) -> List[ExternalSignalData]:
        # NWS uses state/zone codes. Params should contain state codes from DAG.
        states = params.get("states", ["WA", "OR", "CA", "AZ", "UT"])
        signals = []

        # SC-relevant NWS event types (skip astronomical/marine advisories)
        SC_RELEVANT_EVENTS = {
            "Winter Storm Warning", "Winter Storm Watch", "Blizzard Warning",
            "Ice Storm Warning", "Flood Warning", "Flash Flood Warning",
            "Tornado Warning", "Tornado Watch", "Severe Thunderstorm Warning",
            "Excessive Heat Warning", "Extreme Cold Warning", "Wind Advisory",
            "High Wind Warning", "Hurricane Warning", "Tropical Storm Warning",
            "Dense Fog Advisory", "Freezing Rain Advisory",
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT, headers={
            **_HEADERS, "Accept": "application/geo+json"
        }) as client:
            for state in states:
                try:
                    resp = await client.get(
                        f"https://api.weather.gov/alerts/active",
                        params={"area": state, "status": "actual", "limit": 20},
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    features = data.get("features", [])

                    for feature in features:
                        props = feature.get("properties", {})
                        event = props.get("event", "")
                        if event not in SC_RELEVANT_EVENTS:
                            continue

                        headline = props.get("headline", "")
                        description = props.get("description", "")
                        severity = props.get("severity", "")  # Extreme, Severe, Moderate, Minor
                        urgency_nws = props.get("urgency", "")  # Immediate, Expected, Future
                        certainty = props.get("certainty", "")  # Observed, Likely, Possible
                        area_desc = props.get("areaDesc", "")
                        effective = props.get("effective", "")
                        expires = props.get("expires", "")
                        alert_id = props.get("id", "")

                        try:
                            obs_date = datetime.fromisoformat(effective.replace("Z", "+00:00")).date() if effective else date.today()
                        except (ValueError, TypeError):
                            obs_date = date.today()

                        try:
                            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00")) if expires else None
                        except (ValueError, TypeError):
                            exp_dt = datetime.utcnow() + timedelta(days=2)

                        # Map NWS severity to SC urgency
                        severity_map = {"Extreme": 0.95, "Severe": 0.8, "Moderate": 0.6, "Minor": 0.3}
                        urgency_val = severity_map.get(severity, 0.5)
                        if urgency_nws == "Immediate":
                            urgency_val = min(urgency_val + 0.1, 1.0)

                        summary = (
                            f"NWS {event} for {area_desc}. {headline}. "
                            f"Severity: {severity}. Urgency: {urgency_nws}. Certainty: {certainty}. "
                            f"Potential impact on deliveries, warehouse operations, and employee safety in affected area."
                        )

                        # Truncate description for embedding
                        desc_short = description[:300] if description else ""
                        if desc_short:
                            summary += f" Details: {desc_short}"

                        dedup_key = f"nws:{hash(alert_id or headline) & 0xFFFFFFFF}:{obs_date.isoformat()}"

                        signals.append(ExternalSignalData(
                            source_key="nws_alerts",
                            category="weather",
                            signal_type="severe_weather_warning",
                            signal_key=dedup_key,
                            title=f"NWS {event}: {area_desc[:200]}",
                            summary=summary[:1500],
                            signal_date=obs_date,
                            relevance_score=0.75 if severity in ("Extreme", "Severe") else 0.55,
                            urgency_score=urgency_val,
                            magnitude_score=urgency_val * 0.9,
                            affected_trm_types=["to_execution", "mo_execution", "inventory_buffer"],
                            planning_layer="execution",
                            affected_region_tags=[state.lower()],
                            expires_at=exp_dt,
                            metadata={"nws_severity": severity, "nws_urgency": urgency_nws, "area": area_desc},
                        ))
                except Exception as e:
                    logger.warning(f"NWS Alerts {state} fetch failed: {e}")

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# 8. 511/DOT — Persistent Transportation Disruptions
# ═══════════════════════════════════════════════════════════════════════════════

# State DOT 511 feed URLs (XML/JSON) — these are the major ones
STATE_DOT_FEEDS = {
    "WA": "https://wsdot.wa.gov/Traffic/api/Alerts",
    "OR": "https://tripcheck.com/Scripts/BridgeData/json",
    "CA": "https://cwwp2.dot.ca.gov/data/d7/cctv/cctvStatusD07.json",
    # Generic fallback: use the national 511 feed
}


class DOTDisruptionConnector(BaseConnector):
    """Department of Transportation disruption connector.

    Fetches persistent road closures, construction zones, bridge restrictions,
    and major incidents from state DOT feeds and the FHWA 511 system.

    These are PERSISTENT disruptions (days-weeks), not real-time traffic.
    Focus: road closures, weight restrictions, bridge outages, construction zones
    that affect freight routing.

    Free, no API key. Uses the national FHWA TIMS (Traffic Incident Management System)
    and state 511 APIs where available.
    """

    source_key = "dot_disruptions"
    categories = ["trade"]

    async def fetch_signals(
        self,
        params: Dict[str, Any],
        since_date: Optional[date] = None,
    ) -> List[ExternalSignalData]:
        states = params.get("states", ["WA", "OR", "CA"])
        route_keywords = params.get("route_keywords", [
            "I-5", "I-90", "I-84", "I-10", "I-15", "I-80",
            "closure", "weight restriction", "bridge", "construction",
        ])
        signals = []

        # Use GDELT as a proxy for DOT disruptions (infrastructure news)
        # until direct state DOT API integration is built per-state
        infrastructure_keywords = [
            "highway closure",
            "bridge closure",
            "road construction delay",
            "freight route disruption",
            "weight restriction",
            "port congestion",
        ]

        # Add state-specific keywords
        for state in states:
            infrastructure_keywords.append(f"{state} road closure")
            infrastructure_keywords.append(f"{state} highway construction")

        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            for keyword in infrastructure_keywords[:8]:
                try:
                    resp = await client.get(
                        "https://api.gdeltproject.org/api/v2/doc/doc",
                        params={
                            "query": keyword,
                            "mode": "artlist",
                            "format": "json",
                            "maxrecords": 3,
                            "startdatetime": (since_date or (date.today() - timedelta(days=3))).strftime("%Y%m%d%H%M%S"),
                            "sort": "datedesc",
                        },
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    articles = data.get("articles", [])

                    for article in articles[:2]:
                        title = article.get("title", "")
                        url = article.get("url", "")
                        seendate = article.get("seendate", "")
                        if not title:
                            continue

                        try:
                            obs_date = datetime.strptime(seendate[:8], "%Y%m%d").date() if seendate else date.today()
                        except (ValueError, TypeError):
                            obs_date = date.today()

                        signal_type = "road_closure"
                        if "port" in keyword.lower():
                            signal_type = "port_congestion"
                        elif "bridge" in keyword.lower():
                            signal_type = "bridge_restriction"
                        elif "weight" in keyword.lower():
                            signal_type = "weight_restriction"
                        elif "construction" in keyword.lower():
                            signal_type = "construction_delay"

                        summary = (
                            f"Transportation infrastructure disruption: {title}. "
                            f"This is a persistent disruption (not real-time traffic) that may "
                            f"require freight rerouting, delivery schedule adjustments, or "
                            f"lead time buffer increases for affected lanes."
                        )

                        dedup_key = f"dot:{hash(title) & 0xFFFFFFFF}:{obs_date.isoformat()}"

                        signals.append(ExternalSignalData(
                            source_key="dot_disruptions",
                            category="trade",
                            signal_type=signal_type,
                            signal_key=dedup_key,
                            title=title[:500],
                            summary=summary,
                            signal_date=obs_date,
                            relevance_score=0.65,
                            urgency_score=0.6,
                            magnitude_score=0.5,
                            affected_trm_types=["to_execution", "po_creation", "inventory_buffer"],
                            planning_layer="tactical",
                            expires_at=datetime.utcnow() + timedelta(days=7),
                            metadata={"url": url, "keyword": keyword},
                        ))
                except Exception as e:
                    logger.warning(f"DOT '{keyword}' fetch failed: {e}")

        return signals


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Reddit — Industry Subreddit Sentiment
# ═══════════════════════════════════════════════════════════════════════════════

class RedditSentimentConnector(BaseConnector):
    """Reddit API connector — industry subreddit sentiment monitoring.

    Uses Reddit's public JSON API (no OAuth needed for read-only access).
    Monitors industry-relevant subreddits for posts indicating supply chain
    concerns, demand shifts, or operational issues.

    For food distribution: r/KitchenConfidential, r/foodservice, r/restaurants
    capture frontline worker sentiment about supply availability, price changes,
    and menu adjustments — leading indicators for demand planning.

    Rate limit: ~60 requests/minute without OAuth. We fetch top/new posts only.
    """

    source_key = "reddit_sentiment"
    categories = ["sentiment"]

    async def fetch_signals(
        self,
        params: Dict[str, Any],
        since_date: Optional[date] = None,
    ) -> List[ExternalSignalData]:
        # Get subreddits from params (auto-populated from industry tags)
        industry_tags = params.get("industry_tags", [])
        subreddits = params.get("subreddits", [])

        # Auto-select subreddits from industry tags if not explicitly set
        if not subreddits:
            for tag in industry_tags:
                subs = INDUSTRY_SUBREDDITS.get(tag, [])
                for s in subs:
                    if s not in subreddits:
                        subreddits.append(s)
        if not subreddits:
            subreddits = ["supplychain"]  # Fallback

        # Search keywords (industry-specific)
        search_keywords = params.get("search_keywords", [])
        if not search_keywords:
            for tag in industry_tags:
                kws = INDUSTRY_SENTIMENT_KEYWORDS.get(tag, [])
                search_keywords.extend(kws[:3])
        if not search_keywords:
            search_keywords = ["supply chain", "shortage", "price increase"]

        signals = []
        today = date.today()

        async with httpx.AsyncClient(timeout=_TIMEOUT, headers={
            **_HEADERS, "Accept": "application/json"
        }) as client:
            # Strategy 1: Monitor hot posts in relevant subreddits
            for sub in subreddits[:6]:
                try:
                    resp = await client.get(
                        f"https://www.reddit.com/r/{sub}/hot.json",
                        params={"limit": 10, "t": "week"},
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    posts = data.get("data", {}).get("children", [])

                    for post in posts:
                        pdata = post.get("data", {})
                        title = pdata.get("title", "")
                        selftext = pdata.get("selftext", "")[:500]
                        score = pdata.get("score", 0)
                        num_comments = pdata.get("num_comments", 0)
                        created_utc = pdata.get("created_utc", 0)

                        if not title or score < 5:
                            continue  # Skip low-engagement posts

                        try:
                            post_date = datetime.utcfromtimestamp(created_utc).date()
                        except (ValueError, TypeError, OSError):
                            post_date = today

                        # Only recent posts
                        if (today - post_date).days > 7:
                            continue

                        # ── Local sentiment scoring (VADER-lite heuristic) ─────
                        # Simple negative keyword counting as a lightweight
                        # alternative to importing vaderSentiment
                        text = f"{title} {selftext}".lower()
                        neg_words = ["shortage", "problem", "issue", "crisis", "worse",
                                     "fail", "delay", "expensive", "increase", "outage",
                                     "recall", "contamination", "sick", "complaint",
                                     "terrible", "awful", "impossible", "nightmare"]
                        pos_words = ["better", "improve", "available", "resolved",
                                     "great", "excellent", "stable", "reliable",
                                     "recovered", "surplus"]

                        neg_count = sum(1 for w in neg_words if w in text)
                        pos_count = sum(1 for w in pos_words if w in text)
                        total = neg_count + pos_count

                        if total == 0:
                            sentiment_score = 0.0
                            sentiment_label = "neutral"
                        else:
                            sentiment_score = (pos_count - neg_count) / total  # -1 to +1
                            if sentiment_score < -0.3:
                                sentiment_label = "negative"
                            elif sentiment_score > 0.3:
                                sentiment_label = "positive"
                            else:
                                sentiment_label = "mixed"

                        # Engagement-weighted relevance (high upvotes + comments = more relevant)
                        engagement = min((score + num_comments * 2) / 200, 1.0)
                        relevance = 0.3 + engagement * 0.4
                        if neg_count >= 2:
                            relevance = min(relevance + 0.2, 1.0)  # Boost negative sentiment signals

                        # Only emit signals with some sentiment signal (skip pure neutral)
                        if neg_count == 0 and pos_count == 0 and score < 50:
                            continue

                        summary = (
                            f"Reddit r/{sub}: \"{title}\". "
                            f"Sentiment: {sentiment_label} ({neg_count} neg, {pos_count} pos). "
                            f"Engagement: {score} upvotes, {num_comments} comments. "
                        )
                        if neg_count >= 2:
                            summary += "Frontline workers reporting issues — potential leading indicator for demand/supply shifts. "

                        dedup_key = f"reddit:{sub}:{hash(title) & 0xFFFFFFFF}:{post_date.isoformat()}"

                        signals.append(ExternalSignalData(
                            source_key="reddit_sentiment",
                            category="sentiment",
                            signal_type="industry_sentiment",
                            signal_key=dedup_key,
                            title=f"r/{sub}: {title[:200]}",
                            summary=summary.strip(),
                            signal_date=post_date,
                            raw_value=sentiment_score,
                            raw_unit="sentiment_score",
                            relevance_score=relevance,
                            urgency_score=0.5 if neg_count >= 3 else 0.3,
                            magnitude_score=engagement,
                            affected_trm_types=["forecast_adjustment"],
                            planning_layer="strategic",
                            expires_at=datetime.utcnow() + timedelta(days=7),
                            metadata={
                                "subreddit": sub, "score": score,
                                "num_comments": num_comments,
                                "sentiment": sentiment_label,
                                "neg_keywords": neg_count,
                                "pos_keywords": pos_count,
                            },
                        ))
                except Exception as e:
                    logger.warning(f"Reddit r/{sub} fetch failed: {e}")

        return signals


# ── Connector Registry ───────────────────────────────────────────────────────

CONNECTOR_REGISTRY: Dict[str, type] = {
    "fred": FREDConnector,
    "open_meteo": OpenMeteoConnector,
    "eia": EIAConnector,
    "gdelt": GDELTConnector,
    "google_trends": GoogleTrendsConnector,
    "openfda": OpenFDAConnector,
    "nws_alerts": NWSAlertsConnector,
    "dot_disruptions": DOTDisruptionConnector,
    "reddit_sentiment": RedditSentimentConnector,
}


def get_connector(source_key: str) -> Optional[BaseConnector]:
    """Get a connector instance by source key."""
    cls = CONNECTOR_REGISTRY.get(source_key)
    return cls() if cls else None
