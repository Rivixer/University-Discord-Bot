# SPDX-License-Identifier: MIT
"""A module containing the basic configuration models of the bot."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ... import ConfigUtils

__all__ = ("BasicConfig", "TemporaryFilesConfig", "LoggerConfig")


class BasicConfig(BaseModel):
    """A class for the basic configuration of the bot."""

    model_config = ConfigDict(populate_by_name=True)

    guild_id: int
    admin_role_id: int
    bot_channel_id: int
    temporary_files: TemporaryFilesConfig
    logger: LoggerConfig


class TemporaryFilesConfig(BaseModel):
    """A class for the configuration of the temporary files."""

    directory: Path
    clear_on_startup: bool
    clear_on_shutdown: bool

    @field_validator("directory", mode="before")
    @classmethod
    def _validate_directory(cls, value: Path | str) -> Path:
        path = Path(value) if not isinstance(value, Path) else value
        path.mkdir(parents=True, exist_ok=True)
        ConfigUtils.validate_data_directory(path)
        return path

    def clear(self) -> None:
        """Clears the temporary files."""
        for file in self.directory.iterdir():
            file.unlink()


class LoggerConfig(BaseModel):
    """A class for the basic configuration of the logger."""

    level: str = Field(
        pattern=r"(?i)^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        default="INFO",
    )
    directory: Path = Field(default=Path("logs"))
    filename_format: str = Field(default="%Y-%m-%d_%H-%M-%S.log")
    traceback_in_console: bool = Field(default=True)
