# SPDX-License-Identifier: MIT
"""A module to define exceptions related to the presence module."""

__all__ = (
    "PresenceException",
    "PresenceRuntimeError",
    "InvalidPresenceData",
    "PresenceDataSaveFailed",
    "InvalidEnumConversion",
)


class PresenceException(Exception):
    """Base class for exceptions related to the presence module."""


class PresenceRuntimeError(PresenceException):
    """Base class for runtime errors in the presence module.

    These are errors that occur during the runtime of the application,
    such as invalid user input or unexpected states.

    Subclass of :exc:`PresenceException`.
    """


class InvalidPresenceData(PresenceException):
    """Raised when the presence data is invalid.

    Subclass of :exc:`PresenceException`.
    """


class PresenceDataSaveFailed(PresenceRuntimeError):
    """Raised when saving the presence data fails.

    Subclass of :exc:`PresenceRuntimeError`.
    """


class InvalidEnumConversion(PresenceRuntimeError):
    """Raised when a string cannot be converted to a specific enum type.

    Subclass of :exc:`PresenceRuntimeError`.

    Attributes
    ----------
    enum_type: :class:`str`
        The enum type that was expected.
    value: :class:`str`
        The value that could not be converted.
    """

    def __init__(self, enum_type: str, value: str, *args: object) -> None:
        self.enum_type = enum_type
        self.value = value
        message = f"Invalid conversion: expected {enum_type}, got '{value}'"
        super().__init__(message, *args)
