"""
Error Response Models

This module defines error response models used in responses for various API endpoints.
It includes error codes and messages for common scenarios.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Base model for error responses.

    Attributes
    ----------
    error_code : str
        The error code indicating the type of error.
    message : str | None
        An optional human-readable message describing the error.
    """

    error_code: str = "unknown_error"
    message: str | None = None

    _registry: ClassVar[dict[str, type[ErrorResponse]]] = {}

    def __init_subclass__(cls, *, code: str, **kwargs: Any):
        super().__init_subclass__(**kwargs)
        cls.error_code = code
        ErrorResponse._registry[code] = cls

    @classmethod
    def for_error_code(cls, error_code: str) -> type[ErrorResponse]:
        """Retrieves the ErrorResponse subclass associated with the given error code.

        Parameters
        ----------
        error_code : str
            The error code to look up.

        Returns
        -------
        type[ErrorResponse]
            The subclass of ErrorResponse associated with the error code, if found;
            otherwise, the base ErrorResponse class.
        """
        return cls._registry.get(error_code, cls)
