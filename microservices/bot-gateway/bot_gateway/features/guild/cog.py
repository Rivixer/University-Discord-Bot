"""
Cog for handling guild events.

This cog listens for guild join and leave events, publishing them to a Redis channel.
"""

from __future__ import annotations

import logging

from nextcord import Guild
from nextcord.ext import commands

from bot_gateway.settings import settings
from shared.gen.guild.v1.envelope_pb2 import GuildEventEnvelope
from shared.gen.guild.v1.events_pb2 import GuildJoinedEvent, GuildLeftEvent
from shared.redis_client import RedisPublisher

logger = logging.getLogger(__name__)


class GuildCog(commands.Cog):
    """Cog for handling guild events."""

    bot: commands.Bot
    redis_event_publisher: RedisPublisher

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.redis_event_publisher = RedisPublisher(
            f"{settings.redis_guild_base}:gateway"
        )
        logger.info("GuildCog initialized")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: Guild):
        logger.info("Joined guild: %s (ID: %s)", guild.name, guild.id)
        event = GuildJoinedEvent(guild_id=guild.id)
        envelope = GuildEventEnvelope(joined_event=event)
        await self.redis_event_publisher.publish(envelope)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: Guild):
        logger.info("Left guild: %s (ID: %s)", guild.name, guild.id)
        event = GuildLeftEvent(guild_id=guild.id)
        envelope = GuildEventEnvelope(left_event=event)
        await self.redis_event_publisher.publish(envelope)


def setup(bot: commands.Bot):
    bot.add_cog(GuildCog(bot))
