"""
Synchronization module for the voice channel service.

This module provides functionality to periodically synchronize voice channel states
and guild configurations with the bot gateway service.

Defines:
- VoiceChannelSyncClient: gRPC client to fetch and persist voice channel states.
- periodic_full_voice_channel_sync: background task to sync voice states periodically.
- GuildSyncService: gRPC client to fetch and persist guild IDs.
- periodic_full_guild_sync: background task to sync guild list periodically.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Sequence

import grpc
from sqlalchemy import delete, select

from shared.gen.guild.v1.sync_pb2 import GetGuildIdsRequest, GetGuildIdsResponse
from shared.gen.guild.v1.sync_pb2_grpc import GuildServiceStub
from shared.gen.voice_channel.v1.sync_pb2 import (
    BatchGetVoiceChannelStatesRequest,
    BatchGetVoiceChannelStatesResponse,
    GuildCategory,
)
from shared.gen.voice_channel.v1.sync_pb2_grpc import VoiceChannelStateServiceStub

from .database import get_session
from .models import ChannelState, ServiceConfig
from .settings import settings

logger = logging.getLogger(__name__)


class VoiceChannelSyncClient:
    """gRPC client to fetch and persist voice channel states.

    Parameters
    ----------
    target : str
        gRPC server address (host:port) for the voice channel state service.

    Attributes
    ----------
    stub : VoiceChannelStateServiceStub
        The generated gRPC stub for the voice channel state service.

    Methods
    -------
    fetch_and_persist_many(configs: Sequence[ServiceConfig]) -> None
        Fetches state for each guild/category and writes to the database.
    """

    __slots__ = (
        "stub",
        "_batch_get_vc_states",
    )

    stub: VoiceChannelStateServiceStub
    _batch_get_vc_states: Callable[
        [BatchGetVoiceChannelStatesRequest],
        Awaitable[BatchGetVoiceChannelStatesResponse],
    ]

    def __init__(self, target: str = "bot-gateway:50051") -> None:
        channel: grpc.aio.Channel = grpc.aio.insecure_channel(target)
        self.stub = VoiceChannelStateServiceStub(channel)
        self._batch_get_vc_states = self.stub.BatchGetVoiceChannelStates  # type: ignore

    async def fetch_and_persist_many(self, configs: Sequence[ServiceConfig]) -> None:
        """|coro|

        Fetches voice channel states for multiple guilds and persists them.

        This method constructs a request for each guild/category configuration,
        fetches the current state of voice channels, and writes the results to the database.

        Parameters
        ----------
        configs : Sequence[ServiceConfig]
            List of service configurations containing guild and category IDs.
        """
        request = self._build_request(configs)
        response = await self._batch_get_vc_states(request)
        await self._persist_states(response)

    def _build_request(
        self, configs: Sequence[ServiceConfig]
    ) -> BatchGetVoiceChannelStatesRequest:
        guild_categories = [self._to_guild_category(cfg) for cfg in configs]
        return BatchGetVoiceChannelStatesRequest(guilds=guild_categories)

    @staticmethod
    def _to_guild_category(cfg: ServiceConfig) -> GuildCategory:
        return GuildCategory(guild_id=cfg.guild_id, category_id=cfg.category_id)

    async def _persist_states(
        self, response: BatchGetVoiceChannelStatesResponse
    ) -> None:
        async with get_session() as session:
            guild_ids = [state.guild_id for state in response.states]
            await session.execute(
                delete(ChannelState).where(ChannelState.guild_id.in_(guild_ids))
            )

            new_states = [
                ChannelState(
                    guild_id=state.guild_id,
                    channel_id=ch.channel_id,
                    active_users=ch.active_users,
                )
                for state in response.states
                for ch in state.channel_states
            ]
            session.add_all(new_states)

            await session.commit()


async def periodic_full_voice_channel_sync() -> None:
    """|coro|

    Periodically fetches and persists voice channel states.

    The task runs indefinitely until cancelled. It applies a jitter to the
    sleep interval to avoid thundering herd problems.

    This coroutine writes the current state of all voice channels for
    configured guilds/categories to the database.

    The interval and jitter are configured via :class:`Settings`.

    Raises
    ------
    asyncio.CancelledError
        When the task is cancelled during application shutdown.
    """
    logger.info(
        "Starting periodic voice sync: interval=%ss jitter=%.2f%%",
        settings.voice_sync_interval,
        settings.voice_sync_jitter * 100,
    )

    client = VoiceChannelSyncClient()
    while True:
        logger.info("Fetching and persisting voice channel states")
        async with get_session() as session:
            cfgs = (
                await session.scalars(
                    select(ServiceConfig).where(ServiceConfig.category_id.is_not(None))
                )
            ).all()

        try:
            await client.fetch_and_persist_many(cfgs)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error fetching and persisting voice channel states")

        delta = settings.voice_sync_interval * settings.voice_sync_jitter
        sleep_time = max(
            0, settings.voice_sync_interval + random.uniform(-delta, delta)
        )
        await asyncio.sleep(sleep_time)


class GuildSyncService:
    """gRPC client to fetch and persist guild IDs.

    Parameters
    ----------
    target : str
        gRPC server address (host:port) for the guild service.

    Attributes
    ----------
    stub : GuildServiceStub
        The generated gRPC stub for the guild service.

    Methods
    -------
    fetch_and_persist_many() -> None
        Fetches all guild IDs and persists them in the database.
    """

    __slots__ = (
        "stub",
        "_get_guild_ids",
    )

    stub: GuildServiceStub
    _get_guild_ids: Callable[[GetGuildIdsRequest], Awaitable[GetGuildIdsResponse]]

    def __init__(self, target: str = "bot-gateway:50051") -> None:
        channel: grpc.aio.Channel = grpc.aio.insecure_channel(target)
        self.stub = GuildServiceStub(channel)
        self._get_guild_ids = self.stub.GetGuildIds  # type: ignore

    async def fetch_and_persist_many(self) -> None:
        """|coro|

        Fetches all guild IDs and persists them in the database.

        This method retrieves the list of guild IDs from the bot gateway service
        and removes any configurations for guilds that no longer exist.
        """
        request = GetGuildIdsRequest()
        response = await self._get_guild_ids(request)

        async with get_session() as session:
            await session.execute(
                delete(ServiceConfig).where(
                    ServiceConfig.guild_id.not_in(response.guild_ids)
                )
            )
            await session.commit()


async def periodic_full_guild_sync():
    """|coro|

    Periodically fetches and persists guild IDs.

    This task runs indefinitely until cancelled.
    It applies a jitter to the sleep interval to avoid thundering herd problems.

    The interval and jitter are configured via :class:`Settings`.

    Raises
    ------
    asyncio.CancelledError
        When the task is cancelled during application shutdown.
    """
    logger.info(
        "Starting periodic guild sync: interval=%ss jitter=%.2f%%",
        settings.guild_sync_interval,
        settings.guild_sync_jitter * 100,
    )

    client = GuildSyncService()
    while True:
        logger.info("Fetching and persisting guild IDs")

        try:
            await client.fetch_and_persist_many()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error fetching and persisting guild IDs")

        delta = settings.guild_sync_interval * settings.guild_sync_jitter
        sleep_time = max(
            0, settings.guild_sync_interval + random.uniform(-delta, delta)
        )
        await asyncio.sleep(sleep_time)
