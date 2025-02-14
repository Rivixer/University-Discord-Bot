# SPDX-License-Identifier: MIT
"""A module providing the database controller for the bot."""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .enums import DatabaseType

if TYPE_CHECKING:
    from .config import DatabaseConfig

_logger = logging.getLogger(__name__)


class DatabaseController:
    """Handles relational databases using SQLAlchemy (async)."""

    __slots__ = (
        "config",
        "_engine",
        "_async_session_factory",
    )

    config: DatabaseConfig
    _engine: AsyncEngine | None
    _async_session_factory: sessionmaker[AsyncSession] | None  # type: ignore

    REQUIRED_LIBRARIES: dict[DatabaseType, list[str]] = {
        DatabaseType.SQLITE: ["aiosqlite"],
        DatabaseType.MYSQL: ["aiomysql"],
        DatabaseType.POSTGRESQL: ["asyncpg"],
    }

    def __init__(self, config: DatabaseConfig) -> None:
        """Initializes the SQLAlchemy database controller."""
        self.config = config
        self._engine = None
        self._async_session_factory = None
        self._ensure_dependencies()

    @property
    def type(self) -> DatabaseType:
        """The type of the database."""
        return self.config.db_type

    @property
    def engine(self) -> AsyncEngine:
        """The async engine used for database operations."""
        if self._engine is None:
            raise RuntimeError("Database is not initialized.")
        return self._engine

    @property
    def async_session_factory(self) -> sessionmaker[AsyncSession]:  # type: ignore
        """The async session factory used for database operations."""
        if self._async_session_factory is None:
            raise RuntimeError("Database is not initialized.")
        return self._async_session_factory

    async def connect(self) -> None:
        """|coro|

        Establishes a connection to an SQL database and verifies it.

        Raises
        ------
        RuntimeError
            If the connection to the database fails.
        """

        try:
            url = self.config.get_connection_uri()
            self._engine = create_async_engine(url, echo=False)

            async with self.engine.connect() as connection:
                for query in self.config.connection_setup_queries:
                    _logger.debug("Executing setup query: %s", query)
                    result = await connection.execute(text(query))

                    if result.returns_rows:
                        rows = result.fetchall()
                        _logger.info('Query "%s" returned %d rows.', query, len(rows))
                    else:
                        _logger.info('Query "%s" executed successfully.', query)

            self._async_session_factory = sessionmaker(  # type: ignore
                bind=self.engine,  # type: ignore
                class_=AsyncSession,
                expire_on_commit=False,
            )

            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                _logger.info("Connected to %s database.", self.config.db_type.name)

        except SQLAlchemyError as e:
            _logger.error("Failed to connect to the database: %s", str(e))
            raise RuntimeError("Database connection failed") from e

    async def close(self) -> None:
        """|coro|

        Closes the SQL database connection.
        """
        if self.engine:
            await self.engine.dispose()
            _logger.info("SQL database connection closed.")

    def _ensure_dependencies(self) -> None:
        """Checks and installs required dependencies dynamically."""
        required_packages: list[str] = self.REQUIRED_LIBRARIES.get(
            self.config.db_type, []
        )

        for package in required_packages:
            if not self._is_package_installed(package):
                _logger.warning("Installing missing package: %s", package)
                self._install_package(package)

    @staticmethod
    def _is_package_installed(package: str) -> bool:
        """Checks if a package is installed."""
        try:
            __import__(package)
            return True
        except ImportError:
            return False

    @staticmethod
    def _install_package(package: str) -> None:
        """Installs a package dynamically using pip."""
        subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
