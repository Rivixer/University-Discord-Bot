# SPDX-License-Identifier: MIT
"""A module providing utilities for the database."""

from __future__ import annotations

from logging import Logger
from typing import TYPE_CHECKING, Any

from sqlalchemy import inspect

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


async def table_exists(
    conn: AsyncConnection,
    table_name: str,
) -> bool:
    """Checks if a given table exists in the database.

    Parameters
    ----------
    conn: :class:`sqlalchemy.ext.asyncio.Connection`
        The database connection to use for the query.
    table_name: :class:`str`
        The name of the table to check.

    Returns
    -------
    bool
        True if the table exists, False otherwise.
    """
    table_names = await conn.run_sync(
        lambda connection: inspect(connection).get_table_names()
    )
    return table_name in table_names


async def create_tables_if_not_exist(
    conn: AsyncConnection,
    logger: Logger,
    base: Any,
) -> None:
    """|coro|

    Creates missing tables from the provided metadata.

    This function checks each table defined in base.metadata and creates only those
    that do not already exist in the database. It prevents errors caused by attempting
    to create tables that are already present.

    Parameters
    ----------
    conn: :class:`sqlalchemy.ext.asyncio.AsyncConnection`
        The database connection to use for the queries.
    logger: :class:`Logger`
        The logger to use for logging messages.
    base: Any
        The base class (typically a declarative base) that contains the table metadata.

    Raises
    ------
    SQLAlchemyError
        An error occurred while creating the tables.
    """
    existing_tables: list[str] = await conn.run_sync(
        lambda connection: inspect(connection).get_table_names()
    )

    missing_tables = [
        table
        for table in base.metadata.sorted_tables
        if table.name not in existing_tables
    ]

    if not missing_tables:
        logger.debug("All tables exist. Skipping creation.")
    else:
        missing_names = ", ".join(table.name for table in missing_tables)
        logger.debug("Creating missing tables: %s", missing_names)
        await conn.run_sync(
            lambda connection: base.metadata.create_all(
                connection, tables=missing_tables
            )
        )
        logger.info("Created missing tables: %s", missing_names)
