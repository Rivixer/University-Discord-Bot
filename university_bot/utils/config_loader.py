# SPDX-License-Identifier: MIT
"""A module for loading configurations."""

from __future__ import annotations

import logging
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import toml

from university_bot.exceptions.configuration import (
    ConfigurationLoadError,
    MigrationError,
)

if TYPE_CHECKING:
    _Config = dict[str, Any]
    ImmutableConfig = MappingProxyType[str, Any]

__all__ = ("ConfigLoader",)


class ConfigLoader:
    """A class to load configurations from a file.

    Attributes
    ----------
    REQUIRED_VERSION: :class:`str`
        The required configuration version.
    config_path: :class:`Path`
        The path to the configuration file.

    Properties
    ----------
    config: MappingProxyType[:class:`str`, :class:`Any`]
        The configuration.

    Methods
    -------
    load_config()
        Load the configuration from the file.
    """

    REQUIRED_VERSION = "1.0.0"

    config_path: Path
    _config: _Config

    def __init__(self, config_path: Path | str) -> None:
        self.config_path = (
            Path(config_path) if isinstance(config_path, str) else config_path
        )
        self._config = {}

    @property
    def config(self) -> ImmutableConfig:
        """The configuration."""
        return MappingProxyType(self._config)

    def load_config(self) -> ImmutableConfig:
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
                config = toml.load(f)
        except (FileNotFoundError, toml.TomlDecodeError) as e:
            raise ConfigurationLoadError("Failed to load configuration.") from e

        config_version = config.get("version")

        if config_version is None:
            raise ConfigurationLoadError(
                "Configuration file is missing a 'version' field."
            )

        if config_version < self.REQUIRED_VERSION:
            logging.warning(
                "Configuration version (%s) is outdated. "
                "Attempting to migrate to version %s.",
                config_version,
                self.REQUIRED_VERSION,
            )
            try:
                config = self._migrate_config(config)
            except MigrationError as e:
                logging.critical(
                    "Failed to migrate configuration from version %s to version %s.",
                    e.current_version,
                    e.target_version,
                )
                raise ConfigurationLoadError("Failed to migrate configuration.") from e

        self._config = config
        return self.config

    @staticmethod
    def _migrate_config(config: dict[str, Any]) -> dict[str, Any]:
        """Migrates the configuration to the required version.

        Parameters
        ----------
        config: dict[str, Any]
            The configuration to migrate.

        Returns
        -------
        dict[str, Any]
            The migrated configuration.

        Raises
        ------
        MigrationError
            If an error occurs while migrating the configuration.
        """

        raise MigrationError(
            config["version"],
            ConfigLoader.REQUIRED_VERSION,
            "Not implemented",
        )
