"""Smoke tests for the AD-12 Phase 1 TMS cross-plane heuristics.

These exercise the direct-call API ported from ``azirella-tms-stub``
into ``app.heuristics.cross_plane``. Phase 2's dispatcher tests will
sit alongside this file once that PR lands.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.heuristics.cross_plane import (
    HEURISTIC_HANDLERS,
    HEURISTIC_PRODUCER_SIGNATURE,
    HEURISTIC_WRITE_SKILLS,
    HeuristicWriteRefused,
    estimate_lane_eta,
    evaluate_consolidation,
    recommend_carrier,
    refuse_write,
)
from app.heuristics.cross_plane._eta import BUILT_IN_DEFAULTS


# ---------------------------------------------------------------------------
# Four-place warning regime
# ---------------------------------------------------------------------------
# Every read-skill response must carry these four markers so consumer
# planes know they're consuming heuristic data, not real planning.

REQUIRED_MARKERS = {
    "producer_tier",
    "producer_signature",
    "heuristic_warning",
    "heuristic_plane",
}


def _assert_markers(payload: dict, expected_skill_id: str) -> None:
    assert REQUIRED_MARKERS.issubset(payload.keys()), (
        f"missing markers: {REQUIRED_MARKERS - set(payload.keys())}"
    )
    assert payload["producer_tier"] == "HEURISTIC"
    assert payload["producer_signature"].startswith(
        HEURISTIC_PRODUCER_SIGNATURE,
    )
    assert "AZIRELLA-STUB-WARNING" in payload["heuristic_warning"]
    assert expected_skill_id in payload["heuristic_warning"]
    assert payload["heuristic_plane"] == "autonomy-tms-heuristics"


# ---------------------------------------------------------------------------
# transport.lane.estimate_eta
# ---------------------------------------------------------------------------


def test_estimate_lane_eta_with_explicit_coords() -> None:
    """Caller supplies lat/lon → handler computes haversine + speed
    model + dispatch buffer and returns a stamped response."""
    response = estimate_lane_eta(
        tenant_id=1,
        plane_config=BUILT_IN_DEFAULTS,
        inp={
            "from_site_id": "S001",
            "to_site_id": "S002",
            "departure_at": datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc),
            "from_lat": 41.8781,
            "from_lon": -87.6298,  # Chicago
            "to_lat": 32.7767,
            "to_lon": -96.7970,    # Dallas
        },
    )

    _assert_markers(response, "transport.lane.estimate_eta")
    assert response["from_site_id"] == "S001"
    assert response["to_site_id"] == "S002"
    assert response["p50_days"] >= 1.0  # minimum_transit_days_p50 floor
    assert response["p50_days"] < response["p90_days"]
    assert response["p10_days"] < response["p50_days"]
    assert "eta_band" in response
    band = response["eta_band"]
    assert band["producer_tier"] == "STUB"  # ConformalBand still uses STUB enum value


def test_estimate_lane_eta_missing_required_field_raises() -> None:
    with pytest.raises(ValueError, match="missing required input"):
        estimate_lane_eta(
            tenant_id=1,
            plane_config=BUILT_IN_DEFAULTS,
            inp={"from_site_id": "S001"},  # missing to_site_id, departure_at
        )


def test_estimate_lane_eta_no_coords_uses_default_transit_days() -> None:
    """When neither call-time coords nor configured site_coordinates
    resolve, falls back to ``default_transit_days_p50`` (3.0)."""
    response = estimate_lane_eta(
        tenant_id=1,
        plane_config=BUILT_IN_DEFAULTS,
        inp={
            "from_site_id": "S_unknown",
            "to_site_id": "S_also_unknown",
            "departure_at": "2026-05-04T08:00:00Z",
        },
    )
    assert response["p50_days"] == BUILT_IN_DEFAULTS["default_transit_days_p50"]


# ---------------------------------------------------------------------------
# transport.load.evaluate_consolidation
# ---------------------------------------------------------------------------


def test_evaluate_consolidation_always_ship_as_is() -> None:
    response = evaluate_consolidation(
        tenant_id=1,
        plane_config=BUILT_IN_DEFAULTS,
        inp={
            "config_id": 7,
            "shipment_ids": ["SH-001", "SH-002", "SH-003"],
        },
    )
    _assert_markers(response, "transport.load.evaluate_consolidation")
    assert response["recommend_consolidation"] is False
    assert response["score"] == 0.0
    assert response["shipment_count"] == 3
    assert response["consolidation_cost_savings_estimate"] is None


def test_evaluate_consolidation_missing_required_raises() -> None:
    with pytest.raises(ValueError, match="missing required input"):
        evaluate_consolidation(
            tenant_id=1,
            plane_config=BUILT_IN_DEFAULTS,
            inp={"config_id": 7},  # missing shipment_ids
        )


# ---------------------------------------------------------------------------
# transport.carrier.recommend
# ---------------------------------------------------------------------------


def test_recommend_carrier_uses_tenant_default() -> None:
    response = recommend_carrier(
        tenant_id=1,
        plane_config={**BUILT_IN_DEFAULTS, "default_carrier_id": "carrier:fleet-A"},
        inp={"config_id": 7, "load_id": "L-99"},
    )
    _assert_markers(response, "transport.carrier.recommend")
    assert response["recommendations"][0]["carrier_id"] == "carrier:fleet-A"
    assert response["recommendations"][0]["score"] == 0.5


def test_recommend_carrier_no_default_returns_unknown() -> None:
    response = recommend_carrier(
        tenant_id=1,
        plane_config=BUILT_IN_DEFAULTS,
        inp={"config_id": 7, "load_id": "L-99"},
    )
    _assert_markers(response, "transport.carrier.recommend")
    assert response["recommendations"][0]["carrier_id"] == "unknown"
    assert response["recommendations"][0]["score"] == 0.0


# ---------------------------------------------------------------------------
# Write-side refusal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_id", sorted(HEURISTIC_WRITE_SKILLS))
def test_refuse_write_raises(skill_id: str) -> None:
    with pytest.raises(HeuristicWriteRefused) as exc_info:
        refuse_write(skill_id)
    assert exc_info.value.skill_id == skill_id
    assert "HEURISTIC tier" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


def test_handler_registry_keys_match_skill_ids() -> None:
    expected = {
        "transport.lane.estimate_eta",
        "transport.load.evaluate_consolidation",
        "transport.carrier.recommend",
    }
    assert set(HEURISTIC_HANDLERS.keys()) == expected


def test_write_skill_set_is_disjoint_from_handler_registry() -> None:
    """A handler is never a write skill; a write skill is never a
    handler. The dispatcher branches on this disjointness."""
    assert not (set(HEURISTIC_HANDLERS.keys()) & HEURISTIC_WRITE_SKILLS)
