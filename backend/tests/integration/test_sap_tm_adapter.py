"""Unit tests for the SAP TM extraction/injection adapter.

These tests exercise the pure-Python mapping, status/mode translation,
appointment derivation, and BAPI orchestration paths with a mocked
S/4HANA connector. They do NOT require a live SAP system.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.integrations.sap.tms_extractor import (
    SAPTMAdapter,
    SAPTMConnectionConfig,
)


def _row(**kwargs):
    """Build a dict-ish row object that mimics a DataFrame row's `.get`."""
    return SimpleNamespace(get=lambda k, default=None: kwargs.get(k, default))


@pytest.fixture
def adapter():
    cfg = SAPTMConnectionConfig(preferred_method="rfc", ashost="host")
    return SAPTMAdapter(cfg)


# ── Value mapping ──────────────────────────────────────────────────────

def test_map_sap_status_known_and_unknown():
    assert SAPTMAdapter._map_sap_status("0003") == "IN_TRANSIT"
    assert SAPTMAdapter._map_sap_status("0007") == "DELIVERED"
    assert SAPTMAdapter._map_sap_status("9999") == "DRAFT"
    assert SAPTMAdapter._map_sap_status("") == "DRAFT"


def test_map_sap_mode_covers_all_modes():
    assert SAPTMAdapter._map_sap_mode("01") == "FTL"
    assert SAPTMAdapter._map_sap_mode("04") == "FCL"
    assert SAPTMAdapter._map_sap_mode("06") == "LTL"
    assert SAPTMAdapter._map_sap_mode("99") == "FTL"  # unknown → default


def test_parse_sap_date_handles_nulls():
    assert SAPTMAdapter._parse_sap_date("00000000") is None
    assert SAPTMAdapter._parse_sap_date("") is None
    assert SAPTMAdapter._parse_sap_date(None) is None
    assert SAPTMAdapter._parse_sap_date("20260101") == datetime(2026, 1, 1)


def test_parse_sap_datetime_merges_date_and_time():
    dt = SAPTMAdapter._parse_sap_datetime("20260315", "143025")
    assert dt == datetime(2026, 3, 15, 14, 30, 25)
    # date alone still works
    assert SAPTMAdapter._parse_sap_datetime("20260315", "000000") == datetime(2026, 3, 15)


# ── Mapping ────────────────────────────────────────────────────────────

def test_map_freight_orders_maps_sap_to_tms(adapter):
    df = MagicMock()
    df.iterrows.return_value = iter([
        (0, _row(
            TKNUM="4711", STTRG="0003", VSART="01", TDLNR="V100",
            DTABF="20260301", UZABF="080000",
            DTANK="20260302", UZANK="170000",
            DTEFB="20260301", DTEFA="20260302",
            ABFER="DC01", EZESSION="CUST99",
            BTGEW=1500.0, GEWEI="KG",
            VOLUM=20.0, VOLEH="M3",
            EXTI1="PRO123", EXTI2="BOL456",
            TNDR_STS="A", TNDR_TRKID="TRK1",
            ERDAT="20260228", ERZET="120000",
        )),
    ])
    records = adapter._map_freight_orders(df)
    assert len(records) == 1
    r = records[0]
    assert r["external_id"] == "4711"
    assert r["status"] == "IN_TRANSIT"
    assert r["transport_mode"] == "FTL"
    assert r["planned_pickup_date"] == datetime(2026, 3, 1, 8, 0, 0)
    assert r["planned_delivery_date"] == datetime(2026, 3, 2, 17, 0, 0)
    assert r["origin_facility"] == "DC01"
    assert r["destination_facility"] == "CUST99"
    assert r["reference_numbers"]["pro"] == "PRO123"
    assert r["reference_numbers"]["bol"] == "BOL456"


def test_map_carriers_odata_maps_business_partner(adapter):
    raw = [{
        "BusinessPartner": "BP100",
        "BusinessPartnerFullName": "Acme Freight",
        "Country": "US",
        "StandardCarrierAlphaCode": "ACME",
        "PhoneNumber1": "555-0100",
        "BusinessPartnerIsBlocked": False,
        "IsMarkedForArchiving": False,
        "BusinessPartnerGrouping": "FLFR",
    }]
    records = adapter._map_carriers_odata(raw)
    assert records == [{
        "vendor_number": "BP100",
        "name": "Acme Freight",
        "country": "US",
        "scac": "ACME",
        "phone": "555-0100",
        "is_blocked": False,
        "is_deleted": False,
        "account_group": "FLFR",
        "source": "SAP_TM",
    }]


# ── Appointment derivation ─────────────────────────────────────────────

def test_derive_appointments_produces_pickup_and_delivery(adapter):
    row = _row(
        TKNUM="4711", ABFER="DC01", EZESSION="CUST99", TDLNR="V100",
        DTABF="20260301", UZABF="080000",
        DTANK="20260302", UZANK="170000",
        DTEFB="20260301", DTEFA="20260302",
    )
    appts = adapter._derive_appointments(row)
    assert len(appts) == 2
    pu, dl = appts
    assert pu["appointment_type"] == "PICKUP"
    assert pu["facility"] == "DC01"
    assert pu["external_id"] == "4711-PU"
    assert dl["appointment_type"] == "DELIVERY"
    assert dl["facility"] == "CUST99"
    assert dl["planned_start"] == datetime(2026, 3, 2, 17, 0, 0)


def test_derive_appointments_skips_missing_dates(adapter):
    row = _row(
        TKNUM="4712", ABFER="DC01", EZESSION="CUST99", TDLNR="V100",
        DTABF="00000000", UZABF="000000",
        DTANK="20260302", UZANK="170000",
        DTEFB=None, DTEFA=None,
    )
    appts = adapter._derive_appointments(row)
    assert len(appts) == 1
    assert appts[0]["appointment_type"] == "DELIVERY"


# ── Injection (BAPI orchestration) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_inject_load_plan_without_connector_returns_error(adapter):
    result = await adapter.inject_load_plan(
        load_external_id="4711", shipment_ids=["80001"]
    )
    assert result.success is False
    assert "RFC connection" in result.error


@pytest.mark.asyncio
async def test_inject_load_plan_commits_on_success(adapter):
    connector = MagicMock()
    connector.execute_bapi.side_effect = [
        {"RETURN": [{"TYPE": "S", "MESSAGE": "OK"}]},  # SHIPMENT_CHANGE
        {"RETURN": [{"TYPE": "S"}]},                    # COMMIT
    ]
    adapter._connector = connector

    result = await adapter.inject_load_plan(
        load_external_id="4711",
        shipment_ids=["80001", "80002"],
        equipment_type="01",
        metadata={"id": 99},
    )

    assert result.success is True
    assert result.decision_id == 99
    # Two BAPIs called: SHIPMENT_CHANGE + COMMIT
    assert connector.execute_bapi.call_count == 2
    change_call = connector.execute_bapi.call_args_list[0]
    assert change_call[0][0] == "BAPI_SHIPMENT_CHANGE"
    deliveries = change_call[1]["DELIVERIES"]
    assert [d["VBELN"] for d in deliveries] == ["80001", "80002"]
    assert all(d["MAFLAG"] == "I" for d in deliveries)
    # Commit called
    commit_call = connector.execute_bapi.call_args_list[1]
    assert commit_call[0][0] == "BAPI_TRANSACTION_COMMIT"


@pytest.mark.asyncio
async def test_inject_load_plan_aborts_on_bapi_error(adapter):
    connector = MagicMock()
    connector.execute_bapi.return_value = {
        "RETURN": [{"TYPE": "E", "MESSAGE": "Delivery locked by another user"}]
    }
    adapter._connector = connector

    result = await adapter.inject_load_plan(
        load_external_id="4711", shipment_ids=["80001"]
    )

    assert result.success is False
    assert "locked" in result.error
    # Only the CHANGE was called — no commit after failure
    assert connector.execute_bapi.call_count == 1


@pytest.mark.asyncio
async def test_inject_carrier_assignment_error_path(adapter):
    result = await adapter.inject_carrier_assignment(
        shipment_external_id="4711", carrier_id="V100"
    )
    assert result.success is False
    assert "RFC" in (result.error or "")
