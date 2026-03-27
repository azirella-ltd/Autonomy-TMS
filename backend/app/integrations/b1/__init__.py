"""
SAP Business One (B1) Integration

Provides connectivity and data extraction from SAP Business One 10.0
via the Service Layer REST API (OData v4).

Components:
    connector.py       — Service Layer API client (login, query, pagination)
    field_mapping.py   — 3-tier mapping to AWS SC data model
    config_builder.py  — Staged data → SupplyChainConfig (reverse ETL)

Connection methods:
    1. Service Layer (primary) — OData v4, requires B1 10.0 SP0+
    2. CSV export (offline)   — Manual export from B1 queries

Demo company: OEC Computers (pre-loaded in B1 demo databases)
"""
