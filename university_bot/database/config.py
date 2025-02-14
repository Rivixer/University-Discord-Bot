# SPDX-License-Identifier: MIT
"""A module to define the database configuration."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator

from .enums import DatabaseType

__all__ = ("DatabaseConfig",)


class DatabaseConfig(BaseModel):
    """A class for parsing the database configuration."""

    db_type: DatabaseType
    host: str
    port: int
    name: str
    username: str
    password: str
    connection_setup_queries: list[str]

    @model_validator(mode="before")
    @classmethod
    def _convert_db_type(cls, values: dict[str, Any]) -> dict[str, Any]:
        if "db_type" not in values and "type" in values:
            values["db_type"] = values.pop("type")

        if isinstance(values["db_type"], str):
            try:
                values["db_type"] = DatabaseType[values["db_type"].upper()]
            except KeyError as e:
                raise ValueError(f"Invalid database type: {values['db_type']}") from e

        return values

    def get_connection_uri(self) -> str:
        """Generates an async connection URI for SQLAlchemy."""
        match self.db_type:
            case DatabaseType.SQLITE:
                return f"sqlite+aiosqlite:///{self.name}"
            case DatabaseType.MYSQL:
                return (
                    f"mysql+aiomysql://{self.username}:{self.password}"
                    f"@{self.host}:{self.port}/{self.name}"
                )
            case DatabaseType.POSTGRESQL:
                return (
                    f"postgresql+asyncpg://{self.username}:{self.password}"
                    f"@{self.host}:{self.port}/{self.name}"
                )
