# SPDX-License-Identifier: MIT
"""A module to define utility functions for messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nextcord.errors import HTTPException, NotFound

if TYPE_CHECKING:
    from logging import Logger

    from nextcord import Message

__all__ = (
    "MessageDeletionError",
    "attempt_message_delete_after_save_failure",
)


class MessageDeletionError(Exception):
    """Raised when an operation to delete a message fails."""


async def attempt_message_delete_after_save_failure(
    message: Message,
    original_error: Exception,
    logger: Logger,
) -> None:
    """
    Attempts to delete a message after a save failure.

    Logs the result and raises MessageDeletionError if the deletion fails.

    Parameters
    ----------
    message: :class:`nextcord.Message`
        The message to be deleted.
    original_error: :class:`Exception`
        The original error that caused the save failure.

    Raises
    ------
    MessageDeletionError
        If the message deletion fails due to an HTTPException.
    """
    channel_name = getattr(message.channel, "name", "Unknown")
    try:
        await message.delete()
        logger.info(
            'Deleted message %s on channel "%s" (%s) after save failure.',
            message.id,
            channel_name,
            message.channel.id,
        )
    except NotFound:
        logger.warning(
            'Message %s on channel "%s" (%s) not found after save failure.',
            message.id,
            channel_name,
            message.channel.id,
        )
    except HTTPException as e:
        logger.error(
            'Failed to delete message "%s" on channel %s (%s) after save failure.',
            message.id,
            channel_name,
            message.channel.id,
            exc_info=True,
        )
        raise MessageDeletionError(
            "Failed to delete message after save failure. "
            f"Original error: {original_error}; Delete error: {e}"
        ) from e
