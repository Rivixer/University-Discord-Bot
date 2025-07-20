"""gRPC service for synchronizing guild IDs with the bot.

This module defines a gRPC service that allows the bot to fetch and persist
guild IDs from the bot's current state. It provides a method to retrieve
the list of guild IDs the bot is currently connected to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.gen.guild.v1.sync_pb2 import GetGuildIdsRequest, GetGuildIdsResponse
from shared.gen.guild.v1.sync_pb2_grpc import (
    GuildServiceServicer,
    add_GuildServiceServicer_to_server,
)

if TYPE_CHECKING:
    import grpc
    from nextcord.ext import commands


class GuildSyncServicer(GuildServiceServicer):
    """gRPC service for synchronizing guild IDs with the bot."""

    bot: commands.Bot

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def GetGuildIds(
        self,
        request: GetGuildIdsRequest,
        context: grpc.ServicerContext,
    ) -> GetGuildIdsResponse:
        """Fetches the list of guild IDs the bot is currently connected to.

        Parameters
        ----------
        request : GetGuildIdsRequest
            The request object, not used in this implementation.
        context : grpc.ServicerContext
            The gRPC context for the request.

        Returns
        -------
        GetGuildIdsResponse
            A response containing the list of guild IDs the bot is connected to.
        """
        return GetGuildIdsResponse(guild_ids=[guild.id for guild in self.bot.guilds])


def register_guild_services(server: grpc.aio.Server, bot: commands.Bot) -> None:
    """Registers the guild synchronization services with the gRPC server.

    Parameters
    ----------
    server : grpc.aio.Server
        The gRPC server to register the services with.
    bot : nextcord.ext.commands.Bot
        The bot instance to access the current guilds.
    """
    add_GuildServiceServicer_to_server(GuildSyncServicer(bot), server)
