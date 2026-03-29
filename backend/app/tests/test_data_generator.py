import numpy as np
import pytest

from app.rl.data_generator import (
    action_idx_to_order_units,
    assemble_node_features,
    order_units_to_action_idx,
    site_type_onehot,
)
from app.rl.config import SimulationParams, ACTION_LEVELS, NODE_FEATURES


def test_order_units_roundtrip():
    """Action indexing helpers should roundtrip for exact ACTION_LEVEL values."""
    for units in ACTION_LEVELS:
        idx = order_units_to_action_idx(units)
        assert action_idx_to_order_units(idx) == units


def test_site_type_onehot_known():
    """site_type_onehot should produce a valid one-hot vector for known master_types."""
    for mt in ["vendor", "customer", "inventory", "manufacturer"]:
        oh = site_type_onehot(mt)
        assert len(oh) == 4
        assert sum(oh) == 1.0
        assert max(oh) == 1.0


def test_site_type_onehot_unknown():
    """Unknown master_type should default to 'inventory' encoding."""
    oh = site_type_onehot("unknown_type")
    # Default is 'inventory' (index 2)
    assert oh[2] == 1.0
    assert sum(oh) == 1.0


def test_assemble_node_features_shape():
    """assemble_node_features should return an array with len == len(NODE_FEATURES)."""
    params = SimulationParams(order_leadtime=1, supply_leadtime=2)
    feat = assemble_node_features(
        master_type="inventory",
        inventory=10,
        backlog=2,
        incoming_orders=4,
        incoming_shipments=4,
        on_order=8,
        params=params,
    )
    assert feat.shape == (len(NODE_FEATURES),)
    assert np.isfinite(feat).all()
