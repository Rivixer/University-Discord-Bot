# SPDX-License-Identifier: MIT
"""A module to define utility functions for fetching resources."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nextcord import TextChannel, Thread
from nextcord.errors import Forbidden, HTTPException, InvalidData, NotFound

if TYPE_CHECKING:
    from nextcord import Message

    from university_bot import UniversityBot


class ResourceFetchFailed(Exception):
    """An exception raised when fetching a resource fails.

    Attributes
    ----------
    resource: :class:`str`
        The resource that failed to fetch.
    """

    resource: str

    def __init__(self, resource: str, message: str, *args: object) -> None:
        self.resource = resource
        super().__init__(message, *args)


async def fetch_channel(bot: UniversityBot, channel_id: int) -> TextChannel | Thread:
    """|coro|

    Fetches a text channel or thread from the guild.

    Parameters
    ----------
    bot: :class:`.UniversityBot`
        The bot instance.
    channel_id: :class:`int`
        The ID of the channel to fetch.

    Returns
    -------
    :class:`nextcord.TextChannel` | :class:`nextcord.Thread`
        The fetched channel.

    Raises
    ------
    ResourceFetchFailed
        - If the channel does not exist.
        - If the bot does not have permission to access the channel.
        - If an error occurred while fetching the channel.
        - If the channel is not a text channel or thread.
    """

    try:
        channel = await bot.guild.fetch_channel(channel_id)
    except NotFound as e:
        raise ResourceFetchFailed(
            "channel", f"Channel {channel_id} does not exist in guild."
        ) from e
    except Forbidden as e:
        raise ResourceFetchFailed(
            "channel", f"Permission denied for channel {channel_id}."
        ) from e
    except (HTTPException, InvalidData) as e:
        raise ResourceFetchFailed(
            "channel", f"An error occurred while fetching channel {channel_id}: {e}"
        ) from e

    if not isinstance(channel, TextChannel | Thread):
        raise ResourceFetchFailed(
            "channel", f"Channel {channel_id} is not a text channel or thread."
        )

    return channel


async def fetch_message(channel: TextChannel | Thread, message_id: int) -> Message:
    """|coro|

    Fetches a message from the channel.

    Parameters
    ----------
    channel: :class:`.nextcordTextChannel` | :class:`.nextcordThread`
        The channel to fetch the message from.
        message_id: :class:`int`
        The ID of the message to fetch.

    Returns
    -------
    :class:`nextcord.Message`
        The fetched message.

    Raises
    ------
    ResourceFetchFailed
        - If the message does not exist in the channel.
        - If the bot does not have permission to access the message.
        - If an error occurred while fetching the message.
    """

    try:
        return await channel.fetch_message(message_id)
    except Forbidden as e:
        raise ResourceFetchFailed(
            "message", f"Permission denied for message {message_id}."
        ) from e
    except NotFound as e:
        raise ResourceFetchFailed(
            "message",
            f"Message {message_id} does not exist in channel {channel.id}.",
        ) from e
    except HTTPException as e:
        raise ResourceFetchFailed(
            "message", f"An error occurred while fetching message {message_id}: {e}"
        ) from e
