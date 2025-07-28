"""
Voice Channel gRPC Service

Provides VoiceChannelSyncServicer, a gRPC service for synchronizing voice channel states
with the bot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.gen.voice_channel.v1.sync_pb2 import (
    BatchGetVoiceChannelStatesRequest,
    BatchGetVoiceChannelStatesResponse,
)
from shared.gen.voice_channel.v1.sync_pb2_grpc import (
    VoiceChannelStateServiceServicer,
    add_VoiceChannelStateServiceServicer_to_server,
)

if TYPE_CHECKING:
    import grpc
    from nextcord.ext import commands


class VoiceChannelSyncServicer(VoiceChannelStateServiceServicer):
    """gRPC service for synchronizing voice channel states with the bot."""

    bot: commands.Bot

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def BatchGetVoiceChannelStates(
        self,
        request: BatchGetVoiceChannelStatesRequest,
        context: grpc.ServicerContext,
    ) -> BatchGetVoiceChannelStatesResponse:
        """Fetches the current state of voice channels for multiple guilds.

        Parameters
        ----------
        request : BatchGetVoiceChannelStatesRequest
            The request object containing guild and category IDs.
        context : grpc.ServicerContext
            The gRPC context for the request.

        Returns
        -------
        BatchGetVoiceChannelStatesResponse
            A response containing the current state of voice channels for each guild.
        """
        response = BatchGetVoiceChannelStatesResponse()
        for raw_guild in request.guilds:
            if not (guild := self.bot.get_guild(raw_guild.guild_id)):
                continue

            channels = [
                i
                for i in guild.voice_channels
                if i.category and i.category.id == raw_guild.category_id
            ]
            state_msg = response.states.add(guild_id=raw_guild.guild_id)
            for channel in channels:
                state_msg.channel_states.add(
                    channel_id=channel.id,
                    active_users=len(channel.members),
                    name=channel.name,
                )
        return response


def register_voice_channel_services(server: grpc.aio.Server, bot: commands.Bot) -> None:
    """Registers the voice channel synchronization services with the gRPC server.

    Parameters
    ----------
    server : grpc.aio.Server
        The gRPC server to register the services with.
    bot : nextcord.ext.commands.Bot
        The bot instance to access the current voice channels.
    """

    add_VoiceChannelStateServiceServicer_to_server(
        VoiceChannelSyncServicer(bot), server
    )
