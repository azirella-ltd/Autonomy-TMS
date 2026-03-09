"""
SAP Connection Model

Persists SAP system connection configurations to the database.
Each connection is tenant-scoped and supports multiple connection methods
(OData, RFC, CSV, IDoc) for SAP S/4HANA, APO, ECC, and BW systems.
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func

from .base import Base


class SAPConnection(Base):
    """Persistent SAP connection configuration.

    Extension: Platform-specific model for managing SAP system connections.
    Not part of the AWS SC data model but required for SAP data ingestion.
    """

    __tablename__ = "sap_connections"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # SAP System Identity
    system_type = Column(String(20), nullable=False, default="s4hana")
    sid = Column(String(10), nullable=True)

    # Connection Method
    connection_method = Column(String(20), nullable=False, default="odata")

    # Network / Host
    hostname = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True)
    use_ssl = Column(Boolean, nullable=False, default=True)
    ssl_verify = Column(Boolean, nullable=False, default=False)

    # RFC-specific fields
    ashost = Column(String(255), nullable=True)
    sysnr = Column(String(5), nullable=True)

    # SAP Login
    client = Column(String(5), nullable=True)
    sap_user = Column(String(50), nullable=True)
    sap_password_encrypted = Column(Text, nullable=True)
    language = Column(String(5), nullable=True, default="EN")

    # OData-specific
    odata_base_path = Column(String(500), nullable=True)

    # CSV-specific
    csv_directory = Column(String(500), nullable=True)
    csv_pattern = Column(String(100), nullable=True)

    # SAP Router
    sap_router_string = Column(String(500), nullable=True)

    # Cloud Connector
    cloud_connector_location_id = Column(String(100), nullable=True)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    is_validated = Column(Boolean, nullable=False, default=False)
    last_validated_at = Column(DateTime, nullable=True)
    validation_message = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
