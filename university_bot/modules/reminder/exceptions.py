# SPDX-License-Identifier: MIT
"""A module to define exceptions for the reminder cog."""


class ReminderError(Exception):
    """A base class for reminder exceptions."""


class MissingPermissions(ReminderError):
    """An exception raised when the bot is missing permissions.

    Subclass of :class:`.ReminderError`.
    """


class RepositoryError(ReminderError):
    """An exception raised when a repository error occurs.

    Subclass of :class:`.ReminderError`.
    """
