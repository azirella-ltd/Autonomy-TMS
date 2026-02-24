from typing import Any, Dict, List, Optional, Tuple
import math
import random
from enum import Enum


class DemandPatternType(str, Enum):
    CLASSIC = "classic"
    RANDOM = "random"
    SEASONAL = "seasonal"
    CONSTANT = "constant"
    LOGNORMAL = "lognormal"


DEFAULT_CLASSIC_PARAMS = {
    "initial_demand": 4,
    "change_week": 6,
    "final_demand": 8,
}

DEFAULT_LOGNORMAL_PARAMS = {
    "mean": 8.0,
    "cov": 1.0,
}


def _safe_int(value: Any, default: int) -> int:
    """Convert a value to an integer, falling back to the provided default."""
    try:
        if value is None:
            raise ValueError("None")
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float, *, minimum: Optional[float] = None) -> float:
    """Convert a value to a float with optional minimum enforcement."""

    try:
        if value is None:
            raise ValueError("None")
        result = float(value)
    except (TypeError, ValueError):
        result = default

    if minimum is not None:
        result = max(minimum, result)
    return result


def _safe_optional_float(value: Any) -> Optional[float]:
    """Convert a value to a float or return None if conversion fails."""

    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_classic_params(params: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """Normalize classic demand parameters to the {initial, change_week, final} schema."""
    params = params or {}

    initial = _safe_int(
        params.get("initial_demand", params.get("base_demand")),
        DEFAULT_CLASSIC_PARAMS["initial_demand"],
    )

    if "change_week" in params:
        change_week = _safe_int(params.get("change_week"), DEFAULT_CLASSIC_PARAMS["change_week"])
    else:
        stable_period = params.get("stable_period")
        change_week = (
            _safe_int(stable_period, DEFAULT_CLASSIC_PARAMS["change_week"] - 1) + 1
            if stable_period is not None
            else DEFAULT_CLASSIC_PARAMS["change_week"]
        )

    change_week = max(1, change_week)

    if "final_demand" in params:
        final = _safe_int(params.get("final_demand"), DEFAULT_CLASSIC_PARAMS["final_demand"])
    else:
        step_increase = params.get("step_increase")
        final = (
            initial + _safe_int(step_increase, DEFAULT_CLASSIC_PARAMS["final_demand"] - initial)
            if step_increase is not None
            else DEFAULT_CLASSIC_PARAMS["final_demand"]
        )

    initial = max(0, initial)
    final = max(0, final)

    return {
        "initial_demand": initial,
        "change_week": change_week,
        "final_demand": final,
    }


def normalize_lognormal_params(params: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Normalize lognormal demand parameters to a stable schema."""

    params = params or {}

    mean = _safe_float(params.get("mean"), DEFAULT_LOGNORMAL_PARAMS["mean"], minimum=1e-6)
    cov = _safe_float(params.get("cov"), DEFAULT_LOGNORMAL_PARAMS["cov"], minimum=1e-6)
    stddev = mean * cov

    clip_min = _safe_optional_float(params.get("min_demand"))
    if clip_min is None:
        clip_min = _safe_optional_float(params.get("clip_min"))
    clip_max = _safe_optional_float(params.get("max_demand"))
    if clip_max is None:
        clip_max = _safe_optional_float(params.get("clip_max"))

    approx_min = max(0.0, mean - 3.0 * stddev)
    approx_max = mean + 3.0 * stddev

    if clip_min is None:
        clip_min = approx_min
    else:
        clip_min = max(0.0, clip_min)

    if clip_max is None:
        clip_max = max(clip_min, approx_max)
    else:
        clip_max = max(clip_min, clip_max)

    raw_seed = params.get("seed")
    try:
        seed = int(raw_seed) if raw_seed is not None else None
    except (TypeError, ValueError):
        seed = None

    return {
        "mean": mean,
        "cov": cov,
        "stddev": stddev,
        "min_demand": clip_min,
        "max_demand": clip_max,
        "seed": seed,
    }


def normalize_demand_pattern(pattern_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a normalized demand pattern dictionary with sanitized parameters."""
    pattern = dict(pattern_config or {})
    raw_type = pattern.get("type", DemandPatternType.CLASSIC)
    try:
        pattern_type = DemandPatternType(raw_type)
    except ValueError:
        pattern_type = DemandPatternType.CLASSIC

    params = pattern.get("params", {}) if isinstance(pattern.get("params", {}), dict) else {}

    if pattern_type == DemandPatternType.CLASSIC:
        params = normalize_classic_params(params)
    elif pattern_type == DemandPatternType.LOGNORMAL:
        params = normalize_lognormal_params(params)

    normalized = {
        key: value
        for key, value in pattern.items()
        if key not in {"type", "params"}
    }
    normalized.update({
        "type": pattern_type.value,
        "params": params,
    })
    return normalized


def estimate_demand_stats(pattern_config: Optional[Dict[str, Any]]) -> Tuple[float, float]:
    """Estimate the mean and variance of a demand pattern."""

    normalized = normalize_demand_pattern(pattern_config or DEFAULT_DEMAND_PATTERN)
    params = normalized.get("params", {})

    try:
        pattern_type = DemandPatternType(normalized.get("type", DemandPatternType.CLASSIC.value))
    except ValueError:
        pattern_type = DemandPatternType.CLASSIC

    mean = float(DEFAULT_CLASSIC_PARAMS["initial_demand"])
    variance = 0.0

    if pattern_type == DemandPatternType.LOGNORMAL:
        params = normalize_lognormal_params(params)
        mean = float(params.get("mean", DEFAULT_LOGNORMAL_PARAMS["mean"]))
        stddev = float(params.get("stddev", mean * params.get("cov", DEFAULT_LOGNORMAL_PARAMS["cov"])))
        variance = max(0.0, stddev ** 2)
    elif pattern_type == DemandPatternType.RANDOM:
        try:
            min_demand = float(params.get("min_demand", 0.0))
        except (TypeError, ValueError):
            min_demand = 0.0
        try:
            max_demand = float(params.get("max_demand", min_demand))
        except (TypeError, ValueError):
            max_demand = min_demand
        if max_demand < min_demand:
            max_demand = min_demand
        mean = 0.5 * (min_demand + max_demand)
        span = max_demand - min_demand
        variance = max(0.0, span ** 2 / 12.0)
    elif pattern_type == DemandPatternType.SEASONAL:
        try:
            base = float(params.get("base_demand", DEFAULT_CLASSIC_PARAMS["initial_demand"]))
        except (TypeError, ValueError):
            base = float(DEFAULT_CLASSIC_PARAMS["initial_demand"])
        try:
            amplitude = abs(float(params.get("amplitude", 0.0)))
        except (TypeError, ValueError):
            amplitude = 0.0
        mean = max(0.0, base)
        variance = max(0.0, (amplitude ** 2) / 2.0)
    elif pattern_type == DemandPatternType.CONSTANT:
        candidate = None
        for key in ("demand", "value", "mean"):
            candidate = params.get(key)
            if candidate is not None:
                break
        try:
            mean = max(0.0, float(candidate)) if candidate is not None else float(DEFAULT_CLASSIC_PARAMS["initial_demand"])
        except (TypeError, ValueError):
            mean = float(DEFAULT_CLASSIC_PARAMS["initial_demand"])
        variance = 0.0
    else:
        try:
            mean = max(0.0, float(params.get("initial_demand", DEFAULT_CLASSIC_PARAMS["initial_demand"])))
        except (TypeError, ValueError):
            mean = float(DEFAULT_CLASSIC_PARAMS["initial_demand"])
        variance = 0.0

    return mean, variance


class DemandGenerator:
    """Generates different types of demand patterns for simulation scenarios."""

    @staticmethod
    def generate_classic(
        num_rounds: int = 52,
        initial_demand: Optional[int] = None,
        change_week: Optional[int] = None,
        final_demand: Optional[int] = None,
        stable_period: Optional[int] = None,
        step_increase: Optional[int] = None,
    ) -> List[int]:
        """Generate a classic demand pattern with a single step change."""
        if num_rounds <= 0:
            return []

        normalized = normalize_classic_params(
            {
                "initial_demand": initial_demand,
                "change_week": change_week,
                "final_demand": final_demand,
                "stable_period": stable_period,
                "step_increase": step_increase,
            }
        )

        initial = normalized["initial_demand"]
        final = normalized["final_demand"]
        change_at = normalized["change_week"]

        demand: List[int] = []
        for week in range(1, num_rounds + 1):
            demand.append(final if week >= change_at else initial)

        return demand

    @staticmethod
    def generate_random(num_rounds: int, min_demand: int = 1, max_demand: int = 10) -> List[int]:
        """Generate random demand values within a specified range."""
        return [random.randint(min_demand, max_demand) for _ in range(num_rounds)]

    @staticmethod
    def generate_seasonal(num_rounds: int, base_demand: int = 4, amplitude: int = 2, period: int = 12) -> List[int]:
        """Generate a seasonal demand pattern."""
        import math

        return [
            max(1, int(base_demand + amplitude * math.sin(2 * math.pi * (i % period) / period)))
            for i in range(num_rounds)
        ]

    @staticmethod
    def generate_constant(num_rounds: int, demand: int = 4) -> List[int]:
        """Generate a constant demand pattern."""
        return [demand] * num_rounds

    @staticmethod
    def generate_lognormal(
        num_rounds: int,
        mean: float,
        cov: float,
        *,
        min_demand: Optional[float] = None,
        max_demand: Optional[float] = None,
        stddev: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> List[int]:
        """Generate lognormal demand samples rounded to whole units."""

        if num_rounds <= 0:
            return []

        mean = max(mean, 1e-6)
        cov = max(cov, 1e-6)
        stddev = stddev if stddev is not None else mean * cov

        sigma = math.sqrt(math.log(1.0 + (stddev / mean) ** 2)) if mean > 0 else 0.0
        mu = math.log(mean) - 0.5 * sigma ** 2 if mean > 0 else 0.0

        rng = random.Random(seed) if seed is not None else random

        samples: List[int] = []
        for _ in range(num_rounds):
            draw = rng.lognormvariate(mu, sigma) if sigma > 0 else mean
            if not math.isfinite(draw):
                draw = mean
            if min_demand is not None:
                draw = max(min_demand, draw)
            if max_demand is not None:
                draw = min(max_demand, draw)
            draw = max(0.0, draw)
            rounded = int(round(draw))
            samples.append(rounded if rounded >= 0 else 0)

        return samples

    @classmethod
    def generate(
        cls,
        pattern_type: DemandPatternType,
        num_rounds: int,
        **kwargs,
    ) -> List[int]:
        """Generate demand pattern based on the specified type."""
        if pattern_type == DemandPatternType.CLASSIC:
            return cls.generate_classic(num_rounds, **kwargs)
        if pattern_type == DemandPatternType.RANDOM:
            return cls.generate_random(num_rounds, **kwargs)
        if pattern_type == DemandPatternType.SEASONAL:
            return cls.generate_seasonal(num_rounds, **kwargs)
        if pattern_type == DemandPatternType.CONSTANT:
            return cls.generate_constant(num_rounds, **kwargs)
        if pattern_type == DemandPatternType.LOGNORMAL:
            return cls.generate_lognormal(num_rounds, **kwargs)
        raise ValueError(f"Unknown demand pattern type: {pattern_type}")


DEFAULT_DEMAND_PATTERN = {
    "type": DemandPatternType.CLASSIC.value,
    "params": DEFAULT_CLASSIC_PARAMS.copy(),
}


def get_demand_pattern(
    pattern_config: Optional[Dict] = None,
    num_rounds: int = 52,
) -> List[int]:
    """Get a demand pattern based on the provided configuration."""
    normalized = normalize_demand_pattern(pattern_config or DEFAULT_DEMAND_PATTERN)

    try:
        pattern_type = DemandPatternType(normalized.get("type", DemandPatternType.CLASSIC))
    except ValueError:
        pattern_type = DemandPatternType.CLASSIC

    params = normalized.get("params", {})

    return DemandGenerator.generate(pattern_type, num_rounds, **params)
