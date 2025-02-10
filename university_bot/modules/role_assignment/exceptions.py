# SPDX-License-Identifier: MIT
"""A module to define exceptions related to role assignment."""

__all__ = (
    "RoleAssignmentError",
    "ConfigurationUpdateError",
    "RoleAssignmentFailed",
    "ViewNotLoaded",
)


class RoleAssignmentError(Exception):
    """Base exception for role assignment errors."""


class ConfigurationUpdateError(RoleAssignmentError):
    """An exception raised when updating the configuration fails.

    Subclass of :exc:`RoleAssignmentError`.
    """


class RoleAssignmentFailed(RoleAssignmentError):
    """An exception raised when a role assignment fails.

    Subclass of :exc:`RoleAssignmentError`.
    """


class ViewNotLoaded(RoleAssignmentError):
    """An exception raised when a view is not loaded.

    Subclass of :exc:`RoleAssignmentError`.
    """
