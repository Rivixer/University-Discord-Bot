"""
Cog for handling voice channel events.

This cog listens for voice channel creation, deletion, and user join/leave events,
publishing them to a Redis channel. It also handles voice channel requests
from other services.
"""

from __future__ import annotations

import logging

from nextcord import (
    Member,
    VoiceChannel,
    VoiceState,
)
from nextcord.abc import GuildChannel
from nextcord.ext import commands

from shared.gen.voice_channel.v1.envelope_pb2 import (
    VoiceChannelEventEnvelope,
    VoiceChannelRequestEnvelope,
)
from shared.gen.voice_channel.v1.events_pb2 import (
    VoiceChannelCreatedEvent,
    VoiceChannelDeletedEvent,
    VoiceChannelUserJoinedEvent,
    VoiceChannelUserLeftEvent,
)
from shared.redis_client import (
    RedisPublisher,
    RedisPubSubHandlerMixin,
    RedisSubscriber,
)

from ..services.voice_channel_service import VoiceChannelService
from ..settings import settings

logger = logging.getLogger(__name__)


class VoiceChannelCog(RedisPubSubHandlerMixin, commands.Cog):
    """Cog for handling voice channel events and redis requests."""

    bot: commands.Bot
    service: VoiceChannelService
    redis_event_publisher: RedisPublisher

    def __init__(self, bot: commands.Bot):
        super().__init__()

        self.bot = bot
        self.service = VoiceChannelService(bot)
        self.redis_event_publisher = RedisPublisher(
            f"{settings.redis_voice_channel_base}:event"
        )

        logger.info("VoiceChannelCog initialized")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ):
        if before.channel == after.channel:
            return

        if before.channel:
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
            envelope = VoiceChannelEventEnvelope(user_left_event=event)
            await self.redis_event_publisher.publish(envelope)

        if after.channel:
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
            envelope = VoiceChannelEventEnvelope(user_joined_event=event)
            await self.redis_event_publisher.publish(envelope)

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

        envelope = VoiceChannelEventEnvelope(channel_created_event=event)
        await self.redis_event_publisher.publish(envelope)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: GuildChannel):
        if not isinstance(channel, VoiceChannel):
            return

        logger.info(
            "Voice channel deleted: '%s' in guild '%s'",
            channel.name,
            channel.guild.name,
        )

        event = VoiceChannelDeletedEvent(
            guild_id=channel.guild.id,
            channel_id=channel.id,
            category_id=channel.category_id,
        )

        envelope = VoiceChannelEventEnvelope(channel_deleted_event=event)
        await self.redis_event_publisher.publish(envelope)

    @RedisSubscriber.subscribe(f"{settings.redis_voice_channel_base}:request")
    async def handle_voice_request(
        self,
        event: VoiceChannelRequestEnvelope,
    ) -> None:
        logger.debug("Handling voice event: %s", event)

        request_type = event.WhichOneof("payload")

        if request_type == "create_channel_request":
            msg = event.create_channel_request
            await self.service.create_channel(msg.guild_id, msg.category_id, msg.name)

        elif request_type == "delete_channel_request":
            msg = event.delete_channel_request
            await self.service.delete_channel(msg.channel_id)

        elif request_type == "update_channel_request":
            msg = event.update_channel_request
            logger.info("Updating voice channel with options: %s", msg.options)
            await self.service.edit_channel(msg.channel_id, **dict(msg.options))

        else:
            logger.warning("Unhandled voice event: %s", request_type)


def setup(bot: commands.Bot):
    bot.add_cog(VoiceChannelCog(bot))
