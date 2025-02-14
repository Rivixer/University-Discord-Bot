# SPDX-License-Identifier: MIT
"""A module providing utilities for the database."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    conn: :class:`Connection
        The database connection to use for the query.
    table_name : str
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
