from types import SimpleNamespace
import sys
import json

import pytest


class _FakeBaseModel:
    def __init__(self, *args, **kwargs):  # pragma: no cover - stub
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def model_validate(cls, value, *args, **kwargs):  # pragma: no cover - stub
        if isinstance(value, cls):
            return value
        instance = cls()
        if isinstance(value, dict):
            for key, val in value.items():
                setattr(instance, key, val)
        return instance

    def model_dump(self, *args, **kwargs):  # pragma: no cover - stub
        return dict(self.__dict__)

    @classmethod
    def update_forward_refs(cls, *args, **kwargs):  # pragma: no cover - stub
        return None


sys.modules.setdefault(
    "pydantic",
    SimpleNamespace(
        BaseModel=_FakeBaseModel,
        BaseSettings=_FakeBaseModel,
        EmailStr=str,
        Field=lambda *args, **kwargs: None,
        ConfigDict=dict,
        ValidationError=Exception,
        validator=lambda *args, **kwargs: (lambda func: func),
        root_validator=lambda *args, **kwargs: (lambda func: func),
    ),
)

from app.models.supply_chain_config import (
    ProductSiteConfig,
    Lane,
    Market,
    MarketDemand,
    Site as Node,
    NodeType,
    SupplyChainConfig,
)
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat
from app.services.supply_chain_config_service import SupplyChainConfigService


class QueryStub:
    def __init__(self, results):
        self._results = list(results)

    def filter(self, *args, **kwargs):  # pragma: no cover - deterministic helper
        return self

    def all(self):
        return list(self._results)

    def first(self):
        return self._results[0] if self._results else None


class DummySession:
    def __init__(self, mapping):
        self._mapping = mapping

    def query(self, model):  # pragma: no cover - exercised indirectly
        return QueryStub(self._mapping.get(model, []))


def _make_node(site_id: int, name: str, node_type: NodeType, attributes=None):
    return SimpleNamespace(id=site_id, name=name, type=node_type, attributes=attributes or {})


def _make_lane(upstream, downstream, capacity: int = 10, lead_time_days=1, order_lead=0):
    if isinstance(lead_time_days, dict):
        lead_payload = lead_time_days
        supply_value = lead_time_days.get("min") or lead_time_days.get("max") or 1
    else:
        supply_value = lead_time_days
        lead_payload = {"min": lead_time_days, "max": lead_time_days}
    return SimpleNamespace(
        config_id=1,
        from_site_id=upstream.id,
        upstream_node=upstream,
        to_site_id=downstream.id,
        downstream_node=downstream,
        capacity=capacity,
        lead_time_days=lead_payload,
        demand_lead_time={"type": "deterministic", "value": order_lead},
        supply_lead_time={"type": "deterministic", "value": supply_value},
    )


def _make_product_site_config(site_id: int):
    return SimpleNamespace(
        site_id=site_id,
        initial_inventory_range={"min": 10, "max": 14},
        holding_cost_range={"min": 0.4, "max": 0.6},
        backlog_cost_range={"min": 1.0, "max": 1.2},
        selling_price_range={"min": 10.0, "max": 12.0},
    )


def _make_market(market_id: int, name: str = "Default Market"):
    return SimpleNamespace(id=market_id, name=name, description="")


def test_supply_chain_snapshot_preserves_zero_demand_lead_time():
    retailer = _make_node(1, "Retailer", NodeType.RETAILER)
    wholesaler = _make_node(2, "Wholesaler", NodeType.WHOLESALER)

    market = _make_market(1)

    mapping = {
        SupplyChainConfig: [SimpleNamespace(id=1, name="Config", description="")],
        Item: [],
        Node: [retailer, wholesaler],
        Lane: [_make_lane(wholesaler, retailer)],
        ProductSiteConfig: [
            _make_product_site_config(retailer.id),
            _make_product_site_config(wholesaler.id),
        ],
        Market: [market],
        MarketDemand: [],
    }

    session = DummySession(mapping)
    service = SupplyChainConfigService(session)

    snapshot = service.create_game_from_config(1, {"name": "Test"})

    node_policies = snapshot["node_policies"]
    assert node_policies["retailer"]["order_leadtime"] == 0
    assert node_policies["wholesaler"]["order_leadtime"] == 0

    sim_params = snapshot["simulation_parameters"]
    assert sim_params["demand_lead_time"] == 0

    system_cfg = snapshot["system_config"]
    assert system_cfg["order_leadtime"]["min"] == 0
    md_payload = snapshot["market_demands"]
    assert md_payload == []
    assert snapshot["bill_of_materials"] == {}


def test_create_game_from_config_parses_string_pattern():
    retailer = _make_node(5, "Retailer", NodeType.RETAILER)
    wholesaler = _make_node(4, "Wholesaler", NodeType.WHOLESALER)
    distributor = _make_node(3, "Distributor", NodeType.DISTRIBUTOR)
    manufacturer = _make_node(2, "Manufacturer", NodeType.MANUFACTURER)
    market_supply = _make_node(1, "Market Supply", NodeType.VENDOR)

    nodes = [market_supply, manufacturer, distributor, wholesaler, retailer]

    lanes = [
        _make_lane(market_supply, manufacturer),
        _make_lane(manufacturer, distributor),
        _make_lane(distributor, wholesaler),
        _make_lane(wholesaler, retailer),
    ]

    product_site_configs = [
        _make_product_site_config(manufacturer.id),
        _make_product_site_config(distributor.id),
        _make_product_site_config(wholesaler.id),
        _make_product_site_config(retailer.id),
    ]

    lognormal_payload = {
        "type": "lognormal",
        "params": {
            "mean": 7.5,
            "cov": 0.5,
            "min_demand": 1.0,
            "max_demand": 25.0,
        },
    }

    market = _make_market(7, name="LogNormal Market")

    mapping = {
        SupplyChainConfig: [SimpleNamespace(id=42, name="Config", description="", created_by=None)],
        Item: [],
        Node: nodes,
        Lane: lanes,
        ProductSiteConfig: product_site_configs,
        Market: [market],
            MarketDemand: [
                SimpleNamespace(
                    id=1,
                    demand_pattern=json.dumps(lognormal_payload),
                    retailer=retailer,
                    market_id=market.id,
                    product_id=None,
                    market=market,
            )
        ],
    }

    session = DummySession(mapping)
    service = SupplyChainConfigService(session)

    snapshot = service.create_game_from_config(42, {"name": "LogNormal", "max_rounds": 30})

    demand_pattern = snapshot["demand_pattern"]
    assert demand_pattern["type"] == "lognormal"
    assert demand_pattern["params"]["mean"] == pytest.approx(7.5)
    assert demand_pattern["params"]["cov"] == pytest.approx(0.5)

    sim_params = snapshot["simulation_parameters"]
    assert sim_params["initial_demand"] == int(round(7.5))
    assert sim_params["new_demand"] == int(round(7.5))

    system_cfg = snapshot["system_config"]
    assert system_cfg["min_demand"] >= 1
    md_payload = snapshot["market_demands"]
    assert len(md_payload) == 1
    assert md_payload[0]["market_id"] == market.id
    assert md_payload[0]["demand_pattern"]["type"] == "lognormal"
    assert "bill_of_materials" in snapshot


def test_create_game_from_config_includes_bill_of_materials():
    supplier = _make_node(10, "Supplier Alpha", NodeType.SUPPLIER)
    manufacturer = _make_node(
        11,
        "Manufacturer",
        NodeType.MANUFACTURER,
        attributes={"bill_of_materials": {"42": {"supplier alpha": 2}}},
    )
    distributor = _make_node(12, "Distributor", NodeType.DISTRIBUTOR)
    retailer = _make_node(13, "Retailer", NodeType.RETAILER)
    market = _make_market(2)

    lanes = [
        _make_lane(supplier, manufacturer),
        _make_lane(manufacturer, distributor),
        _make_lane(distributor, retailer),
    ]
    item_configs = [
        _make_product_site_config(manufacturer.id),
        _make_product_site_config(distributor.id),
        _make_product_site_config(retailer.id),
    ]
    mapping = {
        SupplyChainConfig: [SimpleNamespace(id=1, name="Config", description="", created_by=None)],
        Item: [],
        Node: [supplier, manufacturer, distributor, retailer],
        Lane: lanes,
        ProductSiteConfig: item_configs,
        Market: [market],
        MarketDemand: [
            SimpleNamespace(
                id=99,
                demand_pattern={},
                market_id=market.id,
                product_id=None,
                market=market,
            )
        ],
    }
    session = DummySession(mapping)
    service = SupplyChainConfigService(session)

    snapshot = service.create_game_from_config(1, {"name": "BOM"})
    bom = snapshot["bill_of_materials"]
    assert bom["manufacturer"]["42"]["supplier alpha"] == 2
    md_payload = snapshot["market_demands"]
    assert len(md_payload) == 1
    assert md_payload[0]["market_id"] == market.id
