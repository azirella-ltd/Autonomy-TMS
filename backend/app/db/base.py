# Central re-exports for backward compatibility.
# Database configuration lives in session.py; Base lives in models.base.
from app.models.base import Base
from .session import engine, async_session_factory, get_db

# Export the async session factory as the default session factory
SessionLocal = async_session_factory
