import pytest

from app.core import demand_patterns
from app.core.demand_patterns import DemandGenerator, estimate_demand_stats


def test_generate_lognormal_non_negative_and_integer(monkeypatch):
    draws = [1.2, 5.8, 0.49, 10.51]

    def fake_lognormvariate(mu, sigma):
        return draws.pop(0)

    monkeypatch.setattr(demand_patterns.random, "lognormvariate", fake_lognormvariate)

    samples = DemandGenerator.generate_lognormal(
        num_rounds=4,
        mean=8.0,
        cov=1.0,
        min_demand=None,
        max_demand=None,
    )

    assert samples == [1, 6, 0, 11]
    assert all(isinstance(value, int) for value in samples)
    assert all(value >= 0 for value in samples)


def test_generate_lognormal_with_invalid_draws(monkeypatch):
    def fake_lognormvariate(mu, sigma):
        return float("nan")

    monkeypatch.setattr(demand_patterns.random, "lognormvariate", fake_lognormvariate)

    samples = DemandGenerator.generate_lognormal(num_rounds=3, mean=8.0, cov=1.0)

    assert samples == [8, 8, 8]


def test_estimate_demand_stats_lognormal():
    mean, variance = estimate_demand_stats(
        {
            "type": "lognormal",
            "params": {"mean": 8.0, "cov": 0.5},
        }
    )

    assert mean == pytest.approx(8.0)
    assert variance == pytest.approx((8.0 * 0.5) ** 2)
