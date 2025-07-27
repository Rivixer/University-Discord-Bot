"""
Voice Channel Panel Service

This service manages the voice channel panel views in Discord, including loading existing panels
and updating or sending new panels for managed voice channels.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nextcord import NotFound, VoiceChannel

from shared.redis_client import Redis, RedisManager

from ..ui.views import VoiceChannelPanelView

if TYPE_CHECKING:
    from nextcord.ext import commands

    from .api_client import VoiceChannelApiClient
    from .manager import DiscordVoiceChannelManager

logger = logging.getLogger(__name__)

_REDIS_KEY = "gateway:vc_panel_messages"


class VoiceChannelPanelService:
    """Service for managing voice channel panel views in Discord.

    This service handles loading existing panels from Redis and updating or sending new panels
    for managed voice channels.

    Attributes
    ----------
    bot : commands.Bot
        The Discord bot instance.
    redis : Redis
        The Redis client instance.
    manager : DiscordVoiceChannelManager
        The manager for Discord voice channels.
    api_client : VoiceChannelApiClient
        The API client for voice channel management.
    """

    bot: commands.Bot
    manager: DiscordVoiceChannelManager
    api_client: VoiceChannelApiClient
    _redis: Redis

    def __init__(
        self,
        bot: commands.Bot,
        manager: DiscordVoiceChannelManager,
        api_client: VoiceChannelApiClient,
    ):
        self.bot = bot
        self.manager = manager
        self.api_client = api_client
        self._redis = RedisManager.get_redis()

    async def remove_panel_view(self, channel_id: int | str) -> None:
        """|coro|

        Removes a panel view from Redis.

        Parameters
        ----------
        channel_id: int | str
            The ID of the channel to remove the panel view for.
        """

        await self._redis.hdel(_REDIS_KEY, str(channel_id))
        logger.debug("Removed panel view for channel ID: %s", channel_id)

    async def load_panel_views(self) -> None:
        """|coro|

        Loads existing panel views from Redis and updates or sends them for managed voice channels.

        This method retrieves all panel views stored in Redis and checks if the channels still exist.
        If a channel is managed, it updates or sends the panel view accordingly.

        If a channel is not found or is not a voice channel, it removes the entry from Redis.
        """
        kv = await self._redis.hgetall(_REDIS_KEY)
        logger.debug("Loaded panel views from Redis: %s", kv)
        for raw_channel_id in kv.keys():
            channel_id = int(raw_channel_id)
            logger.debug("Loading panel view for channel ID: %s", channel_id)

            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, VoiceChannel):
                logger.warning(
                    "Channel %s not found or not a voice channel, removing from Redis",
                    channel_id,
                )
                await self._redis.hdel(_REDIS_KEY, raw_channel_id)
                continue

            await self.update_or_send_panel_view_if_managed(channel)

    async def update_or_send_panel_view_if_managed(self, channel: VoiceChannel) -> None:
        """|coro|

        Updates or sends a panel view for a managed voice channel.

        This method checks if the channel is managed by the API client.
        If it is managed, it updates the panel view in the channel or sends a new one if it doesn't exist.

        If the channel is not managed, it does nothing.

        If a new panel view is sent, it stores the message ID in Redis for future updates.

        Parameters
        ----------
        channel : VoiceChannel
            The voice channel to update or send the panel view for.
        """
        if not await self.api_client.is_managed_channel(channel.id):
            return

        logger.debug(
            "Updating panel for managed channel '%s' in guild '%s'",
            channel.name,
            channel.guild.name,
        )

        panel_view = VoiceChannelPanelView(
            self.api_client,
            self.manager,
            channel,
        )

        view, embed = await panel_view.get()

        if msg_id := await self._redis.hget(_REDIS_KEY, str(channel.id)):
            try:
                msg = await channel.fetch_message(int(msg_id))
                await msg.edit(embed=embed, view=view)
                logger.debug(
                    "Updated panel message in channel %s with ID %s", channel.id, msg.id
                )
            except NotFound:
                logger.debug(
                    "Message %s not found in channel %s, sending new message",
                    msg_id,
                    channel.id,
                )
            else:
                return
        else:
            logger.debug("Panel message not found in Redis, sending new message")

        try:
            msg = await channel.send(embed=embed, view=panel_view)
        except NotFound:
            logger.debug("Channel %s not found, message not sent", channel.id)
            return

        logger.debug(
            "Sent panel message in channel %s with ID %s",
            channel.name,
            msg.id,
        )

        await self._redis.hset(
            _REDIS_KEY,
            str(channel.id),
            str(msg.id),
        )
