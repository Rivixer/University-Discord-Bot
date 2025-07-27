"""
Gateway Microservice Exceptions
"""

from dataclasses import dataclass

from shared.models import ErrorResponse


class DiscordManagerError(Exception):
    """Base exception for all Discord manager errors."""


@dataclass(slots=True, frozen=True)
class ApiClientError(Exception):
    """Base exception for all HTTP-related client errors.

    Attributes
    ----------
    status_code : int
        The HTTP status code returned by the API.
    error_response : ErrorResponse
        The error response containing error code and message.
    """

    status_code: int
    error_response: ErrorResponse
