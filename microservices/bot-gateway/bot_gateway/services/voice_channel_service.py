"""
Voice Channel Service for managing Discord voice channels.
"""

import functools
import logging
from collections.abc import Callable
from typing import Any

import nextcord
from nextcord import VoiceChannel
from nextcord.ext import commands

logger = logging.getLogger(__name__)


class VoiceChannelServiceError(Exception):
    """Custom exception for voice channel service errors."""


def _handle_discord_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    async def wrapper(self: ..., *args: Any, **kwargs: Any):
        try:
            return await func(self, *args, **kwargs)
        except nextcord.Forbidden as e:
            logger.error("Missing permissions: %s", e)
            raise VoiceChannelServiceError("Missing permissions") from e
        except nextcord.HTTPException as e:
            logger.exception("HTTP error while processing voice channel: %s", e)
            raise VoiceChannelServiceError("HTTP error") from e

    return wrapper


class VoiceChannelService:
    """Service for managing voice channels in Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @_handle_discord_errors
    async def create_channel(
        self, guild_id: int, category_id: int, name: str, **options: Any
    ) -> VoiceChannel:
        """Creates a new voice channel in the specified guild and category.

        Parameters
        ----------
        guild_id : int
            The ID of the guild where the channel will be created.
        category_id : int
            The ID of the category where the channel will be created.
        name : str
            The name of the new voice channel.
        options : dict
            Additional options for creating the voice channel, such as bitrate, user limit, etc.

        Returns
        -------
        nextcord.VoiceChannel
            The created voice channel.

        Raises
        ------
        VoiceChannelServiceError
            If the guild or category is not found, or if there are permission issues.
        """
        if not (guild := self.bot.get_guild(guild_id)):
            logger.error("Guild not found: %s", guild_id)
            raise VoiceChannelServiceError("Guild not found")

        if not (category := nextcord.utils.get(guild.categories, id=category_id)):
            logger.error("Category not found: %s", category_id)
            raise VoiceChannelServiceError("Category not found")

        logger.info(
            "Creating voice channel '%s' in category '%s' for guild '%s'",
            name,
            category.name,
            guild.name,
        )

        channel = await category.create_voice_channel(name=name, **options)
        return channel

    @_handle_discord_errors
    async def delete_channel(self, channel_id: int, reason: str | None = None) -> None:
        """Deletes a voice channel by its ID.

        Parameters
        ----------
        channel_id : int
            The ID of the voice channel to delete.
        reason : str | None
            The reason for deleting the channel, which will be logged in the audit log.

        Raises
        ------
        VoiceChannelServiceError
            If the channel is not found, or if it is not a voice channel,
            or if there are permission issues.
        """
        if not (channel := self.bot.get_channel(channel_id)):
            logger.error("Channel not found: %s", channel_id)
            raise VoiceChannelServiceError("Channel not found")

        if not isinstance(channel, VoiceChannel):
            logger.error("Channel is not a voice channel: %s", channel_id)
            raise VoiceChannelServiceError("Channel is not a voice channel")

        logger.info(
            "Deleting voice channel '%s' in category '%s' for guild '%s'",
            channel.name,
            channel.category.name if channel.category else "No Category",
            channel.guild.name,
        )

        await channel.delete(reason=reason)

    @_handle_discord_errors
    async def edit_channel(self, channel_id: int, **options: Any) -> VoiceChannel:
        """Edits a voice channel with the given options.

        Parameters
        ----------
        channel_id : int
            The ID of the voice channel to edit.
        options : Any
            The options to edit the voice channel, such as name, bitrate, user limit, etc.

        Returns
        -------
        nextcord.VoiceChannel
            The edited voice channel.

        Raises
        ------
        VoiceChannelServiceError
            If the channel is not found or if it is not a voice channel.
        """
        if not (channel := self.bot.get_channel(channel_id)):
            logger.error("Channel not found: %s", channel_id)
            raise VoiceChannelServiceError("Channel not found")

        if not isinstance(channel, VoiceChannel):
            logger.error("Channel is not a voice channel: %s", channel_id)
            raise VoiceChannelServiceError("Channel is not a voice channel")

        logger.info(
            "Editing voice channel '%s' in guild '%s'",
            channel.name,
            channel.guild.name,
        )

        await channel.edit(**options)
        return channel
