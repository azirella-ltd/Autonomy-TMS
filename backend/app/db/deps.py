from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session_factory

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a DB session.
    
    Yields:
        AsyncSession: An async SQLAlchemy session
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()
