# SPDX-License-Identifier: MIT
"""A module to define exceptions related to configuration."""

__all__ = (
    "ConfigurationError",
    "ConfigurationNotLoaded",
    "MigrationError",
)


class ConfigurationError(Exception):
    """Base exception for configuration errors."""


class ConfigurationLoadError(ConfigurationError):
    """Raised when loading the configuration fails.

    Subclass of :exc:`ConfigurationError`.
    """


class ConfigurationNotLoaded(ConfigurationError):
    """Raised when the configuration is not loaded.

    Subclass of :exc:`ConfigurationError`.
    """


class MigrationError(ConfigurationError):
    """Raised when a migration fails.

    Subclass of :exc:`ConfigurationError`.

    Attributes
    ----------
    current_version: :class:`str`
        The current version of the configuration.
    target_version: :class:`str`
        The target version of the configuration.
    """

    current_version: str
    target_version: str

    def __init__(
        self, current_version: str, target_version: str, *args: object
    ) -> None:
        self.current_version = current_version
        self.target_version = target_version
        super().__init__(*args)
