# SPDX-License-Identifier: MIT
"""A module for utility functions related to interactions."""

from functools import wraps
from typing import Any, Callable

from nextcord import HTTPException

from .exceptions import format_exception_chain
from .logger import get_logger
from .types import Interaction

__all__ = ("catch_interaction_exceptions",)


def catch_interaction_exceptions(
    exception_types: list[type[Exception]],
    *,
    separator: str = "\n",
    prefix: str = "```ex\n",
    suffix: str = "```",
    delete_after: int | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    r"""Decorator to catch specified exceptions and respond with a formatted message.

    Parameters
    ----------
    exception_types: list[type[:class:`Exception`]]
        A list of exception types to catch.
    separator: :class:`str` | None
        Separator for formatting exception messages.
    prefix: :class:`str` | None
        Prefix for the exception message formatting.
    suffix: :class:`str` | None
        Suffix for the exception message formatting.
    delete_after: :class:`int` | None
        Time in seconds after which the response message is deleted, by default None.

    Returns
    -------
    Callable[[Callable[..., Any]], Callable[..., Any]]
        The decorated function.

    Raises
    ------
    :exc:`TypeError`
        If the exception types are not specified.

    Example
    -------
    ```python
    class ExampleCog(Cog):
        @nextcord.slash_command()
        @catch_exceptions([ZeroDivisionError])
        async def divide_by_zero(self, interaction) -> None:
            return 1 / 0
    ```
    """

    if not exception_types:
        raise TypeError("No exception types specified.")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        logger = get_logger(func.__module__)

        async def handle_exception_response(
            interaction: Interaction, exception: Exception
        ) -> None:
            formatted_exception = format_exception_chain(exception, sep=separator)
            content = f"{prefix}{formatted_exception}{suffix}"

            send_message = (
                interaction.followup.send
                if interaction.response.is_done()
                else interaction.response.send_message
            )

            try:
                await send_message(content, ephemeral=True, delete_after=delete_after)
            except HTTPException as e:
                logger.error(
                    "Failed to send exception response: %s | Original exception: %s",
                    e,
                    exception,
                )

        @wraps(func)
        async def wrapper(
            self: Any, interaction: Interaction, *args: Any, **kwargs: Any
        ) -> Any:
            try:
                return await func(self, interaction, *args, **kwargs)
            except Exception as e:
                for exception_type in exception_types:
                    if isinstance(e, exception_type):
                        await handle_exception_response(interaction, e)
                        return
                raise

        return wrapper

    return decorator
