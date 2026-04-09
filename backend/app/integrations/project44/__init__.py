"""
project44 Integration — Real-time Transportation Visibility

Provides connectivity to the project44 Movement platform (API v4) for:
- Shipment tracking (create, track, update, cancel)
- ETA prediction with confidence intervals
- Exception/event detection
- Carrier connectivity and onboarding status
- Webhook ingestion for real-time tracking events
- Port intelligence (ocean)

Authentication: OAuth 2.0 Client Credentials (Bearer token)
API Base: https://na12.api.project44.com (production)
Sandbox: https://na12.api.sandbox.p-44.com

Components:
- connector.py: OAuth client, HTTP methods, rate limiting
- tracking_service.py: Shipment lifecycle (create/track/update/cancel)
- webhook_handler.py: Inbound event processing and persistence
- data_mapper.py: p44 schema ↔ TMS entity mapping
- config_service.py: Tenant-level integration settings management
"""

from .connector import P44Connector, P44ConnectionConfig
from .tracking_service import P44TrackingService
from .webhook_handler import P44WebhookHandler
from .data_mapper import P44DataMapper
from .config_service import P44ConfigService

__all__ = [
    'P44Connector',
    'P44ConnectionConfig',
    'P44TrackingService',
    'P44WebhookHandler',
    'P44DataMapper',
    'P44ConfigService',
]
