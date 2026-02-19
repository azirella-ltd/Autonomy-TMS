"""Utility script to block until the application database is reachable."""
from __future__ import annotations

import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import settings

MAX_ATTEMPTS = 60
SLEEP_SECONDS = 2

def wait_for_database(engine: Engine) -> None:
    """Block until a simple SELECT succeeds or raise after timeout."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(SLEEP_SECONDS)
        else:
            return

def main() -> None:
    database_uri = settings.SQLALCHEMY_DATABASE_URI
    engine = create_engine(database_uri, pool_pre_ping=True)
    try:
        wait_for_database(engine)
    finally:
        engine.dispose()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.exit(f"Database not ready: {exc}")
