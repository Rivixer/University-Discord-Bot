"""
gRPC Server Initialization

This module initializes the gRPC server for the bot gateway service.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import grpc

if TYPE_CHECKING:
    from nextcord.ext import commands

from ..settings import settings

logger = logging.getLogger(__name__)


async def serve(bot: commands.Bot) -> None:
    """|coro|

    Starts the gRPC server for the bot gateway service.

    Parameters
    ----------
    bot : nextcord.ext.commands.Bot
        The bot instance whose state will be used.
    """
    server = grpc.aio.server()
    server.add_insecure_port(f"[::]:{settings.grpc_port}")

    from bot_gateway.features.guild.services.grpc import register_guild_services
    from bot_gateway.features.voice_channel.services.grpc import (
        register_voice_channel_services,
    )

    register_guild_services(server, bot)
    register_voice_channel_services(server, bot)

    logger.info("gRPC server starting on port %s", settings.grpc_port)
    await server.start()

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("gRPC server termination requested")
        await server.stop(grace=5)
        logger.info("gRPC server stopped gracefully")
