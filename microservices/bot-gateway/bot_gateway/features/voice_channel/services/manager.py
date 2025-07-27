"""
Discord Voice Channel Manager

Provides DiscordVoiceChannelManager, a manager for handling voice channel operations
in Discord, including creating, deleting, and editing voice channels.
"""

import logging
from typing import Any, overload

import nextcord
from nextcord import VoiceChannel
from nextcord.ext import commands

from bot_gateway.core.error_handlers import handle_discord_errors

from .exceptions import DiscordVoiceChannelManagerError

logger = logging.getLogger(__name__)


class DiscordVoiceChannelManager:
    """Manager for handling voice channel operations in Discord."""

    bot: commands.Bot

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @handle_discord_errors(DiscordVoiceChannelManagerError)
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
        VoiceChannelManagerError
            If the guild or category is not found, or if there are permission issues.
        """
        if not (guild := self.bot.get_guild(guild_id)):
            logger.error("Guild not found: %s", guild_id)
            raise DiscordVoiceChannelManagerError("Guild not found")

        if not (category := nextcord.utils.get(guild.categories, id=category_id)):
            logger.error("Category not found: %s", category_id)
            raise DiscordVoiceChannelManagerError("Category not found")

        logger.info(
            "Creating voice channel '%s' in category '%s' for guild '%s'",
            name,
            category.name,
            guild.name,
        )

        channel = await category.create_voice_channel(name=name, **options)
        return channel

    @handle_discord_errors(DiscordVoiceChannelManagerError)
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
        VoiceChannelManagerError
            If the channel is not found, or if it is not a voice channel,
            or if there are permission issues.
        """
        if not (channel := self.bot.get_channel(channel_id)):
            logger.error("Channel not found: %s", channel_id)
            raise DiscordVoiceChannelManagerError("Channel not found")

        if not isinstance(channel, VoiceChannel):
            logger.error("Channel is not a voice channel: %s", channel_id)
            raise DiscordVoiceChannelManagerError("Channel is not a voice channel")

        logger.info(
            "Deleting voice channel '%s' in category '%s' for guild '%s'",
            channel.name,
            channel.category.name if channel.category else "No Category",
            channel.guild.name,
        )

        await channel.delete(reason=reason)

    @overload
    async def edit_channel(self, channel: VoiceChannel, **options: Any) -> None:
        """Edits a voice channel with the given options.

        Parameters
        ----------
        channel : VoiceChannel
            The voice channel to edit.
        options : Any
            The options to edit the voice channel, such as name, bitrate, user limit, etc.

        Returns
        -------
        nextcord.VoiceChannel
            The edited voice channel.

        Raises
        ------
        VoiceChannelManagerError
            If the channel is not found or if it is not a voice channel.
        """

    @overload
    async def edit_channel(self, channel: int, **options: Any) -> None:
        """Edits a voice channel with the given options.

        Parameters
        ----------
        channel : int
            The ID of the voice channel to edit.
        options : Any
            The options to edit the voice channel, such as name, bitrate, user limit, etc.

        Returns
        -------
        nextcord.VoiceChannel
            The edited voice channel.

        Raises
        ------
        VoiceChannelManagerError
            If the channel is not found or if it is not a voice channel.
        """

    @handle_discord_errors(DiscordVoiceChannelManagerError)
    async def edit_channel(self, _channel: int | VoiceChannel, **options: Any) -> None:
        if isinstance(_channel, int):
            if not (channel := self.bot.get_channel(_channel)):
                logger.error("Channel not found: %s", _channel)
                raise DiscordVoiceChannelManagerError("Channel not found")

            if not isinstance(channel, VoiceChannel):
                logger.error("Channel is not a voice channel: %s", _channel)
                raise DiscordVoiceChannelManagerError("Channel is not a voice channel")
        else:
            channel = _channel

        logger.info(
            "Editing voice channel '%s' in guild '%s'",
            channel.name,
            channel.guild.name,
        )

        await channel.edit(**options)
