# SPDX-License-Identifier: MIT
"""A module to define exceptions related to the calendar."""

__all__ = (
    "CalendarError",
    "RepositoryError",
)


class CalendarError(Exception):
    """Base exception for calendar errors."""


class RepositoryError(CalendarError):
    """An exception raised when an error occurs in the repository.

    Subclass of :class:`.CalendarError`.
    """
