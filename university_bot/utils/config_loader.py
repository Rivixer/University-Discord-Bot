# SPDX-License-Identifier: MIT
"""A module for loading bot configuration."""

from __future__ import annotations

from pathlib import Path

import toml
from pydantic import ValidationError

from ..exceptions.configuration import ConfigurationLoadError, ConfigurationNotLoaded
from ..models.configs import BotConfig

__all__ = ("ConfigLoader",)


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
