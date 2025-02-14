# SPDX-License-Identifier: MIT
"""A module to define exceptions related to role assignment."""

__all__ = (
    "RoleAssignmentError",
    "RoleAssignmentFailedError",
)


class RoleAssignmentError(Exception):
    """Base exception for role assignment errors."""


class RoleAssignmentFailedError(RoleAssignmentError):
    """An exception raised when a role assignment fails.

    Subclass of :exc:`RoleAssignmentError`.
    """
