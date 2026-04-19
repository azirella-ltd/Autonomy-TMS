"""
DAT-Style Freight Rate Model

Generates realistic contract and spot rates for a given lane × equipment ×
date combination, grounded in public DAT/Greenscreens-style benchmarks
observed during 2022-2025. Used to populate FreightRate rows and to price
synthesized tenders.

Model structure (bottom-up):
    linehaul_$ = base_cpm(equipment) × miles × region_multiplier × density_adj
    fsc_$     = fsc_cpm(diesel_index) × miles
    accessorials_$ = sum(applicable flats per lane/equipment)
    total_$   = linehaul + fsc + accessorials
    spot_$    = total_$ × market_tightness_multiplier × seasonal_index

Seasonal index tracks Food Dist's existing Q4 produce/holiday freight
slowdown so rates correlate with demand signals already in the history.

References (public benchmarks used to calibrate constants):
  - DAT National Van Freight Index weekly reports
  - Greenscreens dynamic pricing benchmarks
  - FreightWaves SONAR TSTOPVS.USA
  - EIA weekly diesel retail price

All constants are realistic for the 2022-2025 US truckload market; they
are not meant to reproduce any single week exactly but to produce
distributionally-correct synthetic rates for TRM training.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Dict, Optional, Tuple


# ============================================================================
# Base per-mile rate tables ($/loaded-mile, excl. FSC)
# ============================================================================

# Baseline CPM by equipment type (median of 2022-2025 DAT van linehaul excl. FSC)
_BASE_CPM: Dict[str, float] = {
    "DRY_VAN": 2.25,
    "REEFER": 2.70,
    "FLATBED": 2.95,
    "CONTAINER_45": 1.85,     # Intermodal linehaul (rail-only segment)
    "REEFER_CONTAINER": 2.30,
    "CONTAINER_40": 1.75,
    "CONTAINER_40HC": 1.75,
}

# Regional multipliers — CPM adjusts for origin/destination region pair
# Keyed by (origin_region, destination_region); symmetric values filled at lookup
_REGIONAL_MULT: Dict[Tuple[str, str], float] = {
    # Outbound from UT hub (Food Dist DC) to West Coast — competitive, lots of capacity
    ("US_MOUNTAIN", "US_WEST"): 0.95,
    ("US_MOUNTAIN", "US_SOUTHWEST"): 0.97,
    ("US_MOUNTAIN", "US_NORTHWEST"): 1.02,
    # Inbound to UT from supplier regions — thinner lanes, premium
    ("US_CENTRAL", "US_MOUNTAIN"): 1.08,
    ("US_SOUTH", "US_MOUNTAIN"): 1.10,
    ("US_SOUTHEAST", "US_MOUNTAIN"): 1.12,
    ("US_NORTHEAST", "US_MOUNTAIN"): 1.15,   # Long haul, thin
    # Generic same-region short haul
    ("US_WEST", "US_WEST"): 1.00,
    ("US_CENTRAL", "US_CENTRAL"): 0.98,
    # Default fallback
    ("*", "*"): 1.00,
}


def _regional_multiplier(origin_region: str, dest_region: str) -> float:
    if (origin_region, dest_region) in _REGIONAL_MULT:
        return _REGIONAL_MULT[(origin_region, dest_region)]
    if (dest_region, origin_region) in _REGIONAL_MULT:
        # Assume near-symmetric for reverse direction
        return _REGIONAL_MULT[(dest_region, origin_region)] * 0.97
    return _REGIONAL_MULT[("*", "*")]


# ============================================================================
# Fuel Surcharge (FSC) model — tied to synthetic diesel index
# ============================================================================

# Base diesel price where FSC kicks in ($/gal); below this no FSC applies
_FSC_BASE_DIESEL = 1.25
# $/mile FSC per $0.01 increase above base (industry standard ~0.005-0.007)
_FSC_STEP_PER_CENT = 0.006


def diesel_price_on(d: date) -> float:
    """
    Synthetic weekly US on-highway diesel retail ($/gal) matching 2022-2025 shape.
    Anchor points (approximate EIA weekly average):
      2022 peak:  ~$5.80 (Jun 2022)
      2023:       ~$4.10 average
      2024:       ~$3.75 average
      2025:       ~$3.60 average
    """
    year = d.year
    month = d.month
    # Piecewise-linear annual baseline
    baseline = {
        2022: 5.15,
        2023: 4.10,
        2024: 3.75,
        2025: 3.60,
        2026: 3.65,
    }.get(year, 3.70)
    # Seasonal: summer peak, winter dip (~±6%)
    seasonal = 1.0 + 0.06 * math.sin((month - 3) / 12 * 2 * math.pi)
    return baseline * seasonal


def fuel_surcharge_cpm(d: date) -> float:
    """Fuel surcharge per loaded mile for date d."""
    diesel = diesel_price_on(d)
    cents_over = max(0.0, (diesel - _FSC_BASE_DIESEL) * 100.0)
    return cents_over * _FSC_STEP_PER_CENT


# ============================================================================
# Seasonal index — matches Food Dist's Q4 freight slowdown
# ============================================================================

def seasonal_multiplier(d: date) -> float:
    """
    Multiplier applied to linehaul rate for market tightness by month.
    Q4 (Oct-Dec): produce + holiday surge → tighter capacity → higher rates.
    Q1 (Jan-Feb): shoulder → lower rates.
    Calibrated to +8% Q4 peak, -4% Q1 trough.
    """
    month_mult = {
        1: 0.96, 2: 0.96, 3: 0.99, 4: 1.00, 5: 1.02, 6: 1.03,
        7: 1.02, 8: 1.01, 9: 1.02, 10: 1.05, 11: 1.08, 12: 1.06,
    }
    return month_mult[d.month]


# ============================================================================
# Market tightness — feeds spot premium + tender reject rate
# ============================================================================

class MarketRegime(str, Enum):
    LOOSE = "LOOSE"          # Oversupply — carriers accept everything, low rates
    NORMAL = "NORMAL"
    TIGHT = "TIGHT"           # Capacity crunch — higher spot premium, more rejects
    EXTREME = "EXTREME"       # Major disruption


def market_regime(d: date) -> MarketRegime:
    """
    Synthetic market regime by period. Calibrated to real-world freight cycles:
      2022 H1: TIGHT (post-COVID demand surge)
      2022 H2 - 2023: LOOSE (freight recession)
      2024: NORMAL → TIGHT (late-year tightening)
      2025+: NORMAL
    """
    ym = (d.year, d.month)
    if ym < (2022, 6):
        return MarketRegime.TIGHT
    if ym < (2023, 1):
        return MarketRegime.NORMAL
    if ym < (2024, 1):
        return MarketRegime.LOOSE
    if ym < (2024, 10):
        return MarketRegime.NORMAL
    if ym < (2025, 4):
        return MarketRegime.TIGHT
    return MarketRegime.NORMAL


_REGIME_CONTRACT_MULT = {
    MarketRegime.LOOSE: 0.94,
    MarketRegime.NORMAL: 1.00,
    MarketRegime.TIGHT: 1.08,
    MarketRegime.EXTREME: 1.20,
}

_REGIME_SPOT_PREMIUM = {
    MarketRegime.LOOSE: -0.05,   # spot BELOW contract (backhaul territory)
    MarketRegime.NORMAL: 0.08,
    MarketRegime.TIGHT: 0.22,
    MarketRegime.EXTREME: 0.45,
}

_REGIME_REJECT_RATE = {
    MarketRegime.LOOSE: 0.04,
    MarketRegime.NORMAL: 0.10,
    MarketRegime.TIGHT: 0.22,
    MarketRegime.EXTREME: 0.40,
}


# ============================================================================
# Accessorials (flat fees commonly added to foodservice shipments)
# ============================================================================

@dataclass
class Accessorials:
    detention_per_hour: float = 75.0
    lumper_fee: float = 250.0         # Pallet unload at consignee
    driver_assist: float = 100.0
    multi_stop_per_stop: float = 50.0
    reefer_pretrip: float = 35.0
    temp_recording: float = 25.0


DEFAULT_ACCESSORIALS = Accessorials()


# ============================================================================
# Public rate quote API
# ============================================================================

@dataclass(frozen=True)
class RateQuote:
    miles: float
    equipment: str
    origin_region: str
    dest_region: str
    rate_date: date

    linehaul: float
    fsc: float
    accessorials: float
    contract_total: float
    spot_total: float

    # Decomposition for debugging / training features
    base_cpm: float
    fsc_cpm: float
    regional_mult: float
    seasonal_mult: float
    regime: MarketRegime
    spot_premium_pct: float

    def total(self, rate_type: str = "CONTRACT") -> float:
        if rate_type.upper() == "SPOT":
            return self.spot_total
        return self.contract_total

    def per_mile(self, rate_type: str = "CONTRACT") -> float:
        if self.miles <= 0:
            return 0.0
        return self.total(rate_type) / self.miles


def quote_rate(
    miles: float,
    equipment: str,
    origin_region: str,
    dest_region: str,
    rate_date: date,
    stops: int = 2,
    lumper: bool = True,
    reefer_pretrip: bool = False,
    temp_recording: bool = False,
    noise_stddev: float = 0.03,
    rng: Optional[random.Random] = None,
) -> RateQuote:
    """
    Produce a full rate quote for a single shipment/load.

    `noise_stddev` adds log-normal jitter (~3% by default) so repeated
    quotes on the same lane don't collapse onto one number.
    """
    rng = rng or random

    # Equipment base CPM
    base_cpm = _BASE_CPM.get(equipment, _BASE_CPM["DRY_VAN"])

    # Regional
    reg_mult = _regional_multiplier(origin_region, dest_region)

    # Seasonal
    season_mult = seasonal_multiplier(rate_date)

    # Regime
    regime = market_regime(rate_date)
    regime_mult = _REGIME_CONTRACT_MULT[regime]

    # Linehaul (with jitter)
    jitter = math.exp(rng.gauss(0, noise_stddev))
    linehaul_cpm = base_cpm * reg_mult * season_mult * regime_mult * jitter
    linehaul = linehaul_cpm * miles

    # FSC
    fsc_cpm = fuel_surcharge_cpm(rate_date)
    fsc = fsc_cpm * miles

    # Accessorials
    accessorials = 0.0
    if stops > 2:
        accessorials += (stops - 2) * DEFAULT_ACCESSORIALS.multi_stop_per_stop
    if lumper:
        accessorials += DEFAULT_ACCESSORIALS.lumper_fee
    if reefer_pretrip:
        accessorials += DEFAULT_ACCESSORIALS.reefer_pretrip
    if temp_recording:
        accessorials += DEFAULT_ACCESSORIALS.temp_recording

    contract_total = linehaul + fsc + accessorials

    # Spot premium
    spot_premium = _REGIME_SPOT_PREMIUM[regime]
    # Short haul gets higher spot premium (thinner market)
    if miles < 500:
        spot_premium += 0.04
    # Reefer adds premium in tight markets
    if equipment == "REEFER" and regime in (MarketRegime.TIGHT, MarketRegime.EXTREME):
        spot_premium += 0.05
    spot_total = contract_total * (1.0 + spot_premium)

    return RateQuote(
        miles=miles,
        equipment=equipment,
        origin_region=origin_region,
        dest_region=dest_region,
        rate_date=rate_date,
        linehaul=round(linehaul, 2),
        fsc=round(fsc, 2),
        accessorials=round(accessorials, 2),
        contract_total=round(contract_total, 2),
        spot_total=round(spot_total, 2),
        base_cpm=base_cpm,
        fsc_cpm=fsc_cpm,
        regional_mult=reg_mult,
        seasonal_mult=season_mult,
        regime=regime,
        spot_premium_pct=spot_premium,
    )


def tender_reject_probability(rate_date: date, equipment: str = "DRY_VAN") -> float:
    """
    Base probability a carrier rejects a tender on this date.
    Used by the tender waterfall simulator.
    """
    regime = market_regime(rate_date)
    base = _REGIME_REJECT_RATE[regime]
    # Reefer harder to cover in tight markets
    if equipment == "REEFER" and regime in (MarketRegime.TIGHT, MarketRegime.EXTREME):
        base *= 1.3
    return min(0.95, base)
