"""
ERP Connection Model — Generalized

Persists ERP system connection configurations to the database.
Supports SAP, Odoo, Microsoft Dynamics 365 F&O, and future ERP systems.
Each connection is tenant-scoped with ERP-specific credentials stored as JSON.

Extension: Platform-specific model for managing ERP integrations.
Not part of the AWS SC data model but required for data ingestion.
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func

from .base import Base


class ERPConnection(Base):
    """Persistent ERP connection configuration.

    Generalised from SAPConnection to support multiple ERP systems.
    ERP-specific fields live in ``connection_params`` (JSON) so the schema
    does not grow with every new ERP.
    """

    __tablename__ = "erp_connections"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # ── ERP Identity ─────────────────────────────────────────────────────
    # Canonical ERP system type
    erp_type = Column(String(30), nullable=False)
    # e.g. "s4hana", "odoo_community", "odoo_enterprise", "d365_fo", "netsuite", "epicor_kinetic"

    # Specific variant / version
    erp_version = Column(String(50), nullable=True)
    # e.g. "18.0" (Odoo), "10.0.40" (D365), "2024.2" (Epicor)

    # ── Connection Method ────────────────────────────────────────────────
    connection_method = Column(String(30), nullable=False, default="rest_api")
    # "rest_api", "odata", "json_rpc", "xml_rpc", "csv", "db_direct", "dmf"

    # ── Common Network ───────────────────────────────────────────────────
    base_url = Column(String(500), nullable=True)
    # e.g. "http://localhost:8069" (Odoo), "https://contoso.operations.dynamics.com" (D365)

    # ── Auth ─────────────────────────────────────────────────────────────
    auth_type = Column(String(30), nullable=True)
    # "password", "api_key", "oauth2_client_credentials", "oauth2_auth_code", "token"
    auth_credentials_encrypted = Column(Text, nullable=True)
    # JSON blob encrypted: {"username":"x","password":"y"} or {"client_id":"x","client_secret":"y","token_endpoint":"z"}

    # ── CSV / File-based ─────────────────────────────────────────────────
    csv_directory = Column(String(500), nullable=True)
    csv_pattern = Column(String(100), nullable=True)

    # ── ERP-specific parameters ──────────────────────────────────────────
    connection_params = Column(JSON, nullable=True)
    # Odoo:  {"database": "odoo_db", "load_demo_data": true}
    # D365:  {"legal_entity": "USMF", "tenant_id_azure": "abc-123", "data_area_id": "usmf"}
    # SAP:   {"sid": "S4H", "client": "100", "ashost": "10.0.0.1", "sysnr": "00"}

    # ── Discovered schema cache ──────────────────────────────────────────
    discovered_models = Column(JSON, nullable=True)
    # Cached list of available models/entities from the ERP

    file_table_mapping = Column(JSON, nullable=True)
    # For CSV connections: file → ERP model mapping

    # ── Status ───────────────────────────────────────────────────────────
    is_active = Column(Boolean, nullable=False, default=True)
    is_validated = Column(Boolean, nullable=False, default=False)
    last_validated_at = Column(DateTime, nullable=True)
    validation_message = Column(Text, nullable=True)

    # ── Metadata ─────────────────────────────────────────────────────────
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
