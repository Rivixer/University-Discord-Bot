"""
gRPC server initialization for the bot gateway service.

This module sets up the gRPC server for the bot gateway, registering services
for guild management and voice channel operations. It listens for incoming
gRPC requests and routes them to the appropriate service handlers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import grpc

if TYPE_CHECKING:
    from nextcord.ext import commands

from ...settings import settings

logger = logging.getLogger(__name__)


async def serve(bot: commands.Bot) -> None:
    """Starts the gRPC server for the bot gateway service.

    Parameters
    ----------
    bot : nextcord.ext.commands.Bot
        The bot instance whose state will be used.
    """
    server = grpc.aio.server()
    server.add_insecure_port(f"[::]:{settings.grpc_port}")

    from .guild import register_guild_services
    from .voice_channel import register_voice_channel_services

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
