"""
Infor M3 / CloudSuite Integration

Provides connectivity and data extraction from Infor M3, LN, and CloudSuite
via the ION API Gateway (REST + OAuth 2.0).

Components:
    connector.py       — ION API Gateway client (OAuth2, REST, pagination)
    field_mapping.py   — OAGIS noun→field mapping to AWS SC data model
    config_builder.py  — Staged data → SupplyChainConfig (reverse ETL)

Connection methods:
    1. ION API Gateway (primary) — REST/JSON, OAuth 2.0, requires .ionapi credentials
    2. M3 API (MI programs)      — REST via ION Gateway, program/transaction pattern
    3. CSV/JSON export (offline) — Manual export from M3 or BOD XML extracts

Integration protocol:
    Infor ION (Intelligent Open Network) is the middleware layer.
    BODs (Business Object Documents) follow OAGIS standard: Verb + Noun
    (e.g., SyncItemMaster, ProcessPurchaseOrder, GetSalesOrder).

    Public schemas: https://schema.infor.com/InforOAGIS/Nouns/

Demo company: Midwest Industrial Supply (synthetic, generated from OAGIS schemas)
"""
