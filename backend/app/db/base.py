# Import from session.py to maintain a single source of truth for database configuration
from .session import Base, engine, async_session_factory, get_db

# This file is kept for backward compatibility
# All database configuration should be in session.py

# Export the async session factory as the default session factory
SessionLocal = async_session_factory
