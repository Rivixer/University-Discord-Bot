"""
Database module for the voice channel service.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .settings import settings

engine = create_async_engine(settings.database_url)
Session = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """|coro|

    Provides an async context manager for database sessions.

    Yields
    ------
    AsyncSession
        An active database session.

    Notes
    -----
    All changes made within the session should be committed or rolled back
    before the session is closed. This context manager ensures that the session
    is properly closed after use, even if an error occurs.

    Examples
    --------
    .. code-block:: python
        async with get_session() as session:
            result = await session.execute(select(User).where(User.id == 1))
            user = result.scalar_one()
            user.name = "New Name"
            await session.commit()
    """
    async with Session() as session:
        yield session
