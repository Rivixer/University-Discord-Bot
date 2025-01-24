# SPDX-License-Identifier: MIT
"""A module containing the basic configuration models of the bot."""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from pydantic import BaseModel, ConfigDict, Field, field_validator

from university_bot.utils2 import ConfigUtils

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

    @contextmanager
    def context(
        self, suffix: str = "", prefix: str = "tmp"
    ) -> Generator[Path, None, None]:
        """A context manager to create and manage a temporary file.

        Parameters
        ----------
        suffix: :class:`str`
            A suffix for the temporary file (e.g., `.json`).
        prefix: :class:`str`
            A prefix for the temporary file name.

        Yields
        ------
        Path
            The path to the temporary file.

        Example
        -------
        ```python
        with temp_config.context(suffix=".json") as temp_file:
            with temp_file.open("w", encoding="utf-8") as f:
                json.dump({"key": "value"}, f)
        ```
        """
        temp_file = None
        try:
            temp_file = Path(
                tempfile.NamedTemporaryFile(
                    dir=self.directory,
                    delete=False,
                    suffix=suffix,
                    prefix=prefix,
                ).name
            )
            yield temp_file
        except Exception as e:
            raise RuntimeError(
                "An error occurred while managing a temporary file."
            ) from e
        finally:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink(missing_ok=True)
                except OSError:
                    logging.warning(
                        "Failed to delete temporary file: %s",
                        temp_file,
                        exc_info=True,
                    )


class LoggerConfig(BaseModel):
    """A class for the basic configuration of the logger."""

    level: str = Field(
        pattern=r"(?i)^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        default="INFO",
    )
    directory: Path = Field(default=Path("logs"))
    filename_format: str = Field(default="%Y-%m-%d_%H-%M-%S.log")
    traceback_in_console: bool = Field(default=True)
