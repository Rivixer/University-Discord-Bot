# SPDX-License-Identifier: MIT
"""A module providing enums for the database."""

from __future__ import annotations

from enum import Enum, auto

__all__ = ("DatabaseType",)


class DatabaseType(Enum):
    """Defines the available database types."""

    SQLITE = auto()
    MYSQL = auto()
    POSTGRESQL = auto()
