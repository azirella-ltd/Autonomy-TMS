from sqlalchemy import text
from app.db.session import sync_engine
import json

with sync_engine.begin() as conn:
    rows = conn.execute(text("SELECT id, attributes FROM nodes WHERE type = 'MARKET_SUPPLY'"))
    updated = 0
    for row in rows:
        attrs = row.attributes if row.attributes is not None else {}
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except Exception:
                attrs = {}
        if attrs.get("max_supply") != 0:
            attrs = dict(attrs)
            attrs["max_supply"] = 0
            conn.execute(
                text("UPDATE nodes SET attributes = :attrs WHERE id = :id"),
                {"attrs": json.dumps(attrs), "id": row.id},
            )
            updated += 1
    print(f"market_supply nodes updated: {updated}")
