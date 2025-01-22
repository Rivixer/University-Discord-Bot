# SPDX-License-Identifier: MIT
"""A module to define exceptions related to configuration views."""

__all__ = (
    "ConfigurationViewError",
    "ContentTooLongError",
)


class ConfigurationViewError(Exception):
    """Base class for configuration view errors."""


class ContentTooLongError(ConfigurationViewError):
    """Raised when the content is too long to be displayed in a TextInput.

    Subclass of :exc:`ConfigurationViewError`.
    """
