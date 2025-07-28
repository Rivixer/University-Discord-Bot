"""
Error Handlers Decorators

Provides decorators for handling errors in Discord and API client methods.
"""

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import nextcord
from httpx import HTTPStatusError, RequestError
from pydantic import ValidationError

from shared.models import ErrorResponse

from .exceptions import ApiClientError, DiscordManagerError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def handle_discord_errors(
    error_cls: type[DiscordManagerError] = DiscordManagerError,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator to handle Discord-related errors in discord manager methods.

    This decorator wraps methods in Discord managers to catch common Discord-related
    errors, logging them appropriately and raising a custom error if specified, or the
    default :exc:`DiscordManagerError`.

    Parameters
    ----------
    error_cls : type[DiscordManagerError]
        The custom error class to raise in case of a Discord-related error.

    Returns
    -------
    Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]
        A decorator that wraps the original function to handle Discord errors.

    Raises
    ------
    DiscordManagerError
        If there is a Discord-related error, such as missing permissions or HTTP errors.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await func(*args, **kwargs)
            except nextcord.Forbidden as e:
                logger.error("Missing permissions: %s", e)
                raise error_cls("Missing permissions") from e
            except nextcord.HTTPException as e:
                logger.exception("HTTP error while processing voice channel: %s", e)
                raise error_cls("HTTP error") from e

        return wrapper

    return decorator


def handle_api_errors(
    http_error_cls: type[ApiClientError] = ApiClientError,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator to handle HTTP errors in API client methods.

    This decorator wraps API client methods to catch network and HTTP errors,
    logging them appropriately and raising a custom error if specified, or the default
    :exc:`ApiClientError`.

    Parameters
    ----------
    http_error_cls : type[ApiClientError]
        The custom error class to raise in case of an HTTP-related error.
        Defaults to :exc:`ApiClientError`.

    Returns
    -------
    Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]
        A decorator that wraps the original function to handle HTTP errors.

    Raises
    ------
    ApiClientError
        If there is a network error or if the service returns a non-200 status code.

    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await func(*args, **kwargs)
            except RequestError as e:
                logger.warning("Request Error: %s", e)
                raise
            except HTTPStatusError as e:
                try:
                    payload: dict[str, Any] = e.response.json()
                    detail = payload.get("detail", payload)
                    resp_cls = ErrorResponse.for_error_code(detail["error_code"])
                    err = resp_cls.model_validate(detail)
                except (TypeError, KeyError, ValidationError):
                    err = ErrorResponse(message=e.response.text)
                logger.warning(
                    "HTTP Status Error (%s) [%s]: %s ",
                    e.response.status_code,
                    e.request.url,
                    err,
                )
                raise http_error_cls(e.response.status_code, err) from e

        return wrapper

    return decorator
