"""
Voice Channel Cog

This cog listens for voice channel creation, deletion, and user join/leave events,
publishing them to a Redis channel. It also handles voice channel requests
from other services.
"""

from __future__ import annotations

import asyncio
import logging
from typing import override

from nextcord import (
    Member,
    VoiceChannel,
    VoiceState,
)
from nextcord.abc import GuildChannel
from nextcord.ext import commands

from bot_gateway.settings import settings
from shared.gen.voice_channel.v1.envelope_pb2 import GatewayEnvelope, ServiceEnvelope
from shared.gen.voice_channel.v1.events_pb2 import (
    BotVoiceChannelRenameEvent,
    VoiceChannelCreatedEvent,
    VoiceChannelDeletedEvent,
    VoiceChannelUserJoinedEvent,
    VoiceChannelUserLeftEvent,
)
from shared.redis_client import (
    RedisPublisher,
    RedisPubSubHandlerCogMixin,
    RedisSubscriber,
)

from .services.api_client import VoiceChannelApiClient
from .services.manager import DiscordVoiceChannelManager
from .services.panel import VoiceChannelPanelService

logger = logging.getLogger(__name__)


class VoiceChannelCog(RedisPubSubHandlerCogMixin, commands.Cog):
    """Cog for handling voice channel events and redis requests."""

    bot: commands.Bot
    api_client: VoiceChannelApiClient
    manager: DiscordVoiceChannelManager
    redis_event_publisher: RedisPublisher
    panel_service: VoiceChannelPanelService

    def __init__(self, bot: commands.Bot):
        super().__init__()

        self.bot = bot
        self.api_client = VoiceChannelApiClient()
        self.manager = DiscordVoiceChannelManager(bot)
        self.redis_event_publisher = RedisPublisher(
            f"{settings.redis_voice_channel_base}:gateway"
        )
        self.panel_service = VoiceChannelPanelService(
            bot, self.manager, self.api_client
        )

        logger.info("VoiceChannelCog initialized")

    @override
    def cog_unload(self) -> None:
        """Unloads the cog and closes the API client."""
        self.bot.loop.create_task(self.api_client.close())
        super().cog_unload()

    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.sleep(5)  # Ensure voice channel service is ready
        await self.panel_service.load_panel_views()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ):
        if before.channel == after.channel:
            return

        if before.channel and isinstance(before.channel, VoiceChannel):
            logger.info(
                "User '%s' left voice channel '%s' in guild '%s'",
                member.name,
                before.channel.name,
                member.guild.name,
            )
            event = VoiceChannelUserLeftEvent(
                guild_id=member.guild.id,
                user_id=member.id,
                channel_id=before.channel.id,
                category_id=before.channel.category_id,
            )
            envelope = GatewayEnvelope(user_left_event=event)
            await asyncio.gather(
                self.redis_event_publisher.publish(envelope),
                self.panel_service.update_or_send_panel_view_if_managed(before.channel),
            )

        if after.channel and isinstance(after.channel, VoiceChannel):
            logger.info(
                "User '%s' joined voice channel '%s' in guild '%s'",
                member.name,
                after.channel.name,
                member.guild.name,
            )
            event = VoiceChannelUserJoinedEvent(
                guild_id=member.guild.id,
                user_id=member.id,
                channel_id=after.channel.id,
                category_id=after.channel.category_id,
            )
            envelope = GatewayEnvelope(user_joined_event=event)
            await asyncio.gather(
                self.redis_event_publisher.publish(envelope),
                self.panel_service.update_or_send_panel_view_if_managed(after.channel),
            )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: GuildChannel):
        if not isinstance(channel, VoiceChannel):
            return

        logger.info(
            "Voice channel created: '%s' in guild '%s'",
            channel.name,
            channel.guild.name,
        )

        event = VoiceChannelCreatedEvent(
            guild_id=channel.guild.id,
            channel_id=channel.id,
            category_id=channel.category_id,
        )

        envelope = GatewayEnvelope(created_event=event)
        await self.redis_event_publisher.publish(envelope)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: GuildChannel):
        if not isinstance(channel, VoiceChannel):
            return

        event = VoiceChannelDeletedEvent(
            guild_id=channel.guild.id,
            channel_id=channel.id,
            category_id=channel.category_id,
        )

        envelope = GatewayEnvelope(deleted_event=event)
        await self.redis_event_publisher.publish(envelope)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: GuildChannel, after: GuildChannel):
        if not isinstance(after, VoiceChannel) or before.name == after.name:
            return

        event = BotVoiceChannelRenameEvent(
            guild_id=after.guild.id,
            channel_id=after.id,
            new_name=after.name,
        )

        envelope = GatewayEnvelope(rename_event=event)
        await self.redis_event_publisher.publish(envelope)

    @RedisSubscriber.subscribe(f"{settings.redis_voice_channel_base}:service")
    async def handle_voice_event(self, event: ServiceEnvelope) -> None:
        logger.debug("Handling voice event: %s", event)

        request_type = event.WhichOneof("payload")

        if request_type == "create_channel_request":
            msg = event.create_channel_request
            await self.manager.create_channel(msg.guild_id, msg.category_id, msg.name)

        elif request_type == "delete_channel_request":
            msg = event.delete_channel_request
            await self.panel_service.remove_panel_view(msg.channel_id)
            await self.manager.delete_channel(msg.channel_id)

        elif request_type == "rename_channel_request":
            msg = event.rename_channel_request
            try:
                await asyncio.wait_for(
                    self.manager.edit_channel(msg.channel_id, name=msg.new_name),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Timeout while changing name for channel %s to %s",
                    msg.channel_id,
                    msg.new_name,
                )

        elif request_type == "rename_cooldown_expired_event":
            msg = event.rename_cooldown_expired_event
            channel = self.bot.get_channel(msg.channel_id)
            if channel and isinstance(channel, VoiceChannel):
                await self.panel_service.update_or_send_panel_view_if_managed(channel)

        else:
            logger.warning("Unhandled voice event: %s", request_type)


def setup(bot: commands.Bot):
    bot.add_cog(VoiceChannelCog(bot))
