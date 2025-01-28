# SPDX-License-Identifier: MIT
"""A module for loading bot configuration."""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import toml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from university_bot.utils2 import ConfigUtils

from .exceptions.configuration import ConfigurationLoadError, ConfigurationNotLoaded

__all__ = (
    "BotConfig",
    "BasicConfig",
    "TemporaryFilesConfig",
    "LoggerConfig",
    "ConfigLoader",
)


class BotConfig(BaseModel):
    """The bot configuration model.

    Attributes
    ----------
    version: tuple[:class:`int`, :class:`int`, :class:`int`]
        The version of the configuration.
    basic: :class:`.BasicConfig`
        The basic configuration.
    """

    version: tuple[int, int, int] = (1, 0, 0)
    basic: BasicConfig
    _data: dict[str, Any]

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._data = {k: v for k, v in data.items() if getattr(self, k, None) is None}

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key, None) or self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get the value of a configuration key.

        Parameters
        ----------
        key: :class:`str`
            The key of the configuration.
        default: :class:`Any`
            The default value to return if the key is not found.
        """
        try:
            return self[key]
        except KeyError:
            return default


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


class ConfigLoader:
    """A class to load configurations from a file.

    Attributes
    ----------
    config_path: :class:`Path`
        The path to the configuration file.

    Properties
    ----------
    config: :class:`BotConfig`
        The bot configuration.

    Methods
    -------
    load_config()
        Load the bot configuration from the file.
    """

    config_path: Path
    _config: BotConfig | None

    def __init__(self, config_path: Path | str) -> None:
        self.config_path = (
            Path(config_path) if isinstance(config_path, str) else config_path
        )

    @property
    def config(self) -> BotConfig:
        """The bot configuration.

        Returns
        -------
        BotConfig
            The bot configuration.

        Raises
        ------
        ConfigurationNotLoaded
            If the configuration has not been loaded yet.
        """
        if self._config is None:
            raise ConfigurationNotLoaded("Configuration has not been loaded yet.")

        return self._config

    def load_config(self) -> BotConfig:
        """Loads the configuration from the file.

        Returns
        -------
        dict[:class:`str`, :class:`Any`]
            The loaded configuration.

        Raises
        ------
        ConfigurationLoadError
            If an error occurs while loading the configuration.
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config_data = toml.load(f)
        except (FileNotFoundError, toml.TomlDecodeError) as e:
            raise ConfigurationLoadError("Failed to load configuration.") from e

        try:
            self._config = BotConfig(**config_data)
        except ValidationError as e:
            raise ConfigurationLoadError("Failed to validate configuration.") from e

        return self.config
