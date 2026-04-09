"""
project44 Integration Configuration Service

Manages tenant-level p44 connection settings:
- Client credentials (encrypted at rest)
- Environment (production/sandbox)
- Webhook configuration
- Connection health checks
- Feature flags (which p44 capabilities are enabled)

Stored in tenant_preferences or a dedicated integration_config table.
For MVP, uses the existing tenant_preferences JSON column.
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Preference Keys ────────────────────────────────────────────────────────

P44_CONFIG_KEY = "p44_integration"

# Default configuration template
P44_DEFAULT_CONFIG = {
    "enabled": False,
    "environment": "sandbox",  # "sandbox" or "production"
    "client_id": "",
    "client_secret_encrypted": "",  # Column-level encrypted per SOC II
    "webhook_secret": "",
    "webhook_url": "",  # Populated after registration
    "features": {
        "truckload_tracking": True,
        "ltl_tracking": True,
        "ocean_tracking": False,
        "port_intelligence": False,
        "carrier_accounts": False,
    },
    "rate_limit_per_sec": 10,
    "timeout_seconds": 30,
    "max_retries": 3,
    "last_connection_test": None,
    "connection_status": "unconfigured",  # unconfigured, connected, failed
    "error_message": None,
}

P44_ENVIRONMENTS = {
    "sandbox": "https://sandbox.api.project44.com",
    "production": "https://api.project44.com",
}


class P44ConfigService:
    """
    Manages p44 integration configuration per tenant.

    Configuration is stored in the tenant_preferences table as a JSON
    blob under the key 'p44_integration'. Credentials are encrypted
    at the column level per SOC II requirements.
    """

    @classmethod
    async def get_config(
        cls,
        tenant_id: int,
        db_session: Any,
    ) -> Dict[str, Any]:
        """
        Get p44 configuration for a tenant.

        Returns merged config (defaults + tenant overrides).
        """
        raw = await cls._get_raw_config(tenant_id, db_session)
        if not raw:
            return dict(P44_DEFAULT_CONFIG)

        # Merge with defaults so new keys are always present
        config = dict(P44_DEFAULT_CONFIG)
        config.update(raw)
        if isinstance(raw.get("features"), dict):
            features = dict(P44_DEFAULT_CONFIG["features"])
            features.update(raw["features"])
            config["features"] = features

        return config

    @classmethod
    async def update_config(
        cls,
        tenant_id: int,
        updates: Dict[str, Any],
        db_session: Any,
    ) -> Dict[str, Any]:
        """
        Update p44 configuration for a tenant.

        Only updates provided keys; preserves existing values.
        Sensitive fields (client_secret) must be encrypted by caller.
        """
        current = await cls.get_config(tenant_id, db_session)

        # Apply updates
        for key, value in updates.items():
            if key == "features" and isinstance(value, dict):
                current.setdefault("features", {}).update(value)
            else:
                current[key] = value

        current["updated_at"] = datetime.utcnow().isoformat()

        await cls._set_raw_config(tenant_id, current, db_session)
        return current

    @classmethod
    async def test_connection(
        cls,
        tenant_id: int,
        db_session: Any,
    ) -> Dict[str, Any]:
        """
        Test p44 connection for a tenant.

        Attempts OAuth token acquisition and a simple API call.
        Updates connection_status in config.
        """
        from .connector import P44Connector, P44ConnectionConfig, P44APIError

        config = await cls.get_config(tenant_id, db_session)

        if not config.get("client_id") or not config.get("client_secret_encrypted"):
            return {
                "status": "failed",
                "error": "Missing client credentials",
            }

        env = config.get("environment", "sandbox")
        base_url = P44_ENVIRONMENTS.get(env, P44_ENVIRONMENTS["sandbox"])

        conn_config = P44ConnectionConfig(
            client_id=config["client_id"],
            client_secret=config["client_secret_encrypted"],  # Decrypted by caller
            base_url=base_url,
            timeout=config.get("timeout_seconds", 30),
            max_retries=config.get("max_retries", 3),
            rate_limit_per_sec=config.get("rate_limit_per_sec", 10),
            webhook_secret=config.get("webhook_secret", ""),
        )

        connector = P44Connector(conn_config)
        try:
            result = await connector.test_connection()
            status = "connected" if result else "failed"
            error = None if result else "Connection test returned False"
        except P44APIError as e:
            status = "failed"
            error = str(e)
        except Exception as e:
            status = "failed"
            error = f"Unexpected error: {e}"
        finally:
            await connector.close()

        # Update config with test result
        await cls.update_config(tenant_id, {
            "connection_status": status,
            "last_connection_test": datetime.utcnow().isoformat(),
            "error_message": error,
        }, db_session)

        return {"status": status, "error": error}

    @classmethod
    def build_connector(cls, config: Dict[str, Any]) -> "P44Connector":
        """
        Build a P44Connector from config dict.

        Caller must ensure client_secret is decrypted.
        """
        from .connector import P44Connector, P44ConnectionConfig

        env = config.get("environment", "sandbox")
        base_url = P44_ENVIRONMENTS.get(env, P44_ENVIRONMENTS["sandbox"])

        conn_config = P44ConnectionConfig(
            client_id=config["client_id"],
            client_secret=config["client_secret_encrypted"],
            base_url=base_url,
            timeout=config.get("timeout_seconds", 30),
            max_retries=config.get("max_retries", 3),
            rate_limit_per_sec=config.get("rate_limit_per_sec", 10),
            webhook_secret=config.get("webhook_secret", ""),
        )

        return P44Connector(conn_config)

    @classmethod
    def build_webhook_handler(cls, config: Dict[str, Any]) -> "P44WebhookHandler":
        """Build a P44WebhookHandler from config dict."""
        from .webhook_handler import P44WebhookHandler
        return P44WebhookHandler(webhook_secret=config.get("webhook_secret", ""))

    # ── Internal Storage ────────────────────────────────────────────────

    @classmethod
    async def _get_raw_config(
        cls,
        tenant_id: int,
        db_session: Any,
    ) -> Optional[Dict]:
        """Read raw p44 config from tenant_preferences."""
        from sqlalchemy import select, text

        # Try tenant_preferences table first
        try:
            result = await db_session.execute(
                text("""
                    SELECT preference_value
                    FROM tenant_preferences
                    WHERE tenant_id = :tid AND preference_key = :key
                """),
                {"tid": tenant_id, "key": P44_CONFIG_KEY},
            )
            row = result.first()
            if row and row[0]:
                import json
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception as e:
            logger.debug(f"tenant_preferences lookup failed: {e}")

        return None

    @classmethod
    async def _set_raw_config(
        cls,
        tenant_id: int,
        config: Dict,
        db_session: Any,
    ) -> None:
        """Write p44 config to tenant_preferences (upsert)."""
        from sqlalchemy import text
        import json

        config_json = json.dumps(config)

        try:
            await db_session.execute(
                text("""
                    INSERT INTO tenant_preferences (tenant_id, preference_key, preference_value, updated_at)
                    VALUES (:tid, :key, :val, :now)
                    ON CONFLICT (tenant_id, preference_key)
                    DO UPDATE SET preference_value = :val, updated_at = :now
                """),
                {
                    "tid": tenant_id,
                    "key": P44_CONFIG_KEY,
                    "val": config_json,
                    "now": datetime.utcnow(),
                },
            )
            await db_session.flush()
        except Exception as e:
            logger.error(f"Failed to save p44 config for tenant {tenant_id}: {e}")
            raise
