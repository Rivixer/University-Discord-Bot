# SPDX-License-Identifier: MIT
"""A module to define exceptions related to role assignment."""

__all__ = (
    "RoleAssignmentError",
    "ConfigurationUpdateError",
    "ResourceFetchFailed",
    "RoleAssignmentFailed",
    "ViewNotLoaded",
    "ConfigurationSaveFailed",
    "InvalidConfiguration",
)


class RoleAssignmentError(Exception):
    """Base exception for role assignment errors."""


class ConfigurationUpdateError(RoleAssignmentError):
    """An exception raised when updating the configuration fails.

    Subclass of :exc:`RoleAssignmentError`.
    """


class ResourceFetchFailed(RoleAssignmentError):
    """An exception raised when fetching a resource fails.

    Subclass of :exc:`RoleAssignmentError`.

    Attributes
    ----------
    resource: :class:`str`
        The resource that failed to fetch.
    """

    resource: str

    def __init__(self, resource: str, *args: object) -> None:
        self.resource = resource
        super().__init__(*args)


class RoleAssignmentFailed(RoleAssignmentError):
    """An exception raised when a role assignment fails.

    Subclass of :exc:`RoleAssignmentError`.
    """


class ViewNotLoaded(RoleAssignmentError):
    """An exception raised when a view is not loaded.

    Subclass of :exc:`RoleAssignmentError`.
    """


class ConfigurationSaveFailed(RoleAssignmentError):
    """An exception raised when saving data fails.

    Subclass of :exc:`RoleAssignmentError`.
    """


class InvalidConfiguration(RoleAssignmentError):
    """An exception raised when the configuration is invalid.

    Subclass of :exc:`RoleAssignmentError`.
    """
