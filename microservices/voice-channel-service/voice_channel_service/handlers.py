"""
Voice Channel Service Handlers Module

This module subscribes to Redis Pub/Sub envelopes, dispatches them
to the appropriate handler, and applies all business logic for:
- tracking channel state (create/delete, join/leave)
- maintaining exactly one empty channel per guild
- cleaning up guild configurations on bot removal
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.gen.guild.v1.envelope_pb2 import GuildEventEnvelope
from shared.gen.voice_channel.v1.envelope_pb2 import GatewayEnvelope
from shared.gen.voice_channel.v1.events_pb2 import (
    BotVoiceChannelRenameEvent,
    VoiceChannelCreatedEvent,
    VoiceChannelDeletedEvent,
    VoiceChannelUserJoinedEvent,
    VoiceChannelUserLeftEvent,
)
from shared.redis_client import RedisSubscriber

from .actions import request_channel_creation, request_channel_deletion
from .database import get_session
from .models import ChannelState, ServiceConfig
from .rename_scheduler import cancel_cooldown
from .settings import settings

logger = logging.getLogger(__name__)

_guild_locks: dict[int, asyncio.Lock] = {}


def _lock_for_guild(guild_id: int) -> asyncio.Lock:
    if guild_id not in _guild_locks:
        _guild_locks[guild_id] = asyncio.Lock()
    return _guild_locks[guild_id]


async def _get_channel_state(
    session: AsyncSession, channel_id: int
) -> ChannelState | None:
    return await session.scalar(
        select(ChannelState).where(ChannelState.channel_id == channel_id)
    )


async def _get_guild_config(
    session: AsyncSession, guild_id: int
) -> ServiceConfig | None:
    return await session.scalar(
        select(ServiceConfig).where(ServiceConfig.guild_id == guild_id)
    )


async def _handle_voice_channel_create(event: VoiceChannelCreatedEvent) -> None:
    async with get_session() as session:
        if await _get_channel_state(session, event.channel_id):
            logger.debug(
                "Channel %d already tracked",
                event.channel_id,
                extra={"guild_id": event.guild_id},
            )
            return

        session.add(
            ChannelState(
                channel_id=event.channel_id,
                guild_id=event.guild_id,
                name=event.name,
            )
        )
        await session.commit()

        logger.info(
            "Registered new voice channel %d in guild %d",
            event.channel_id,
            event.guild_id,
        )


async def _handle_voice_channel_delete(event: VoiceChannelDeletedEvent) -> None:
    async with get_session() as session:
        if not (state := await _get_channel_state(session, event.channel_id)):
            logger.debug("Deleted channel %d not tracked", event.channel_id)
            return

        await session.delete(state)
        await session.commit()
        logger.info("Removed deleted voice channel %d", event.channel_id)

    cancel_cooldown(state.guild_id, event.channel_id)


async def _handle_user_joined(event: VoiceChannelUserJoinedEvent) -> None:
    async with get_session() as session:
        if not (config := await _get_guild_config(session, event.guild_id)):
            logger.debug(
                "No voice config for guild=%d; skipping user join", event.guild_id
            )
            return

        if not (state := await _get_channel_state(session, event.channel_id)):
            state = ChannelState(guild_id=event.guild_id, channel_id=event.channel_id)
            session.add(state)

        state.active_users += 1
        await session.commit()

        logger.info(
            "User joined: guild=%d channel=%d active_users=%d",
            event.guild_id,
            event.channel_id,
            state.active_users,
        )

        empty_channels = (
            await session.scalars(
                select(ChannelState).where(
                    ChannelState.guild_id == event.guild_id,
                    ChannelState.active_users == 0,
                    ~ChannelState.pending_deletion,
                )
            )
        ).all()

        if not empty_channels:
            await request_channel_creation(config)


async def _handle_user_left(event: VoiceChannelUserLeftEvent) -> None:
    guild_id = event.guild_id
    async with get_session() as session:
        if not await _get_guild_config(session, guild_id):
            logger.debug("No voice config for guild=%d; skipping user left", guild_id)
            return

        if not (state := await _get_channel_state(session, event.channel_id)):
            logger.debug(
                "User left unknown channel %d in guild %d", event.channel_id, guild_id
            )
            return

        state.active_users = max(0, state.active_users - 1)
        await session.commit()

        logger.info(
            "User left: guild=%d channel=%d active_users=%d",
            guild_id,
            event.channel_id,
            state.active_users,
        )

        if state.active_users == 0:
            empty_channels = (
                await session.scalars(
                    select(ChannelState).where(
                        ChannelState.guild_id == guild_id,
                        ChannelState.active_users == 0,
                        ~ChannelState.pending_deletion,
                    )
                )
            ).all()

            if len(empty_channels) > 1:
                state.pending_deletion = True
                await session.commit()

                cancel_cooldown(state.guild_id, event.channel_id)
                await request_channel_deletion(event.channel_id)


async def _handle_voice_channel_rename(event: BotVoiceChannelRenameEvent) -> None:
    async with get_session() as session:
        if not (state := await _get_channel_state(session, event.channel_id)):
            logger.debug(
                "Unknown channel %d in guild %d", event.channel_id, event.guild_id
            )
            return

        state.name = event.new_name
        await session.commit()

        logger.info(
            "Renamed voice channel %d in guild %d to '%s'",
            event.channel_id,
            event.guild_id,
            event.new_name,
        )


@RedisSubscriber.subscribe(f"{settings.redis_channel_base}:gateway")
async def handle_voice_channel_event(event: GatewayEnvelope) -> None:
    """|coro|

    Handles incoming voice channel events.

    This function dispatches the event to the appropriate handler based on its type.
    It extracts the necessary parameters from the event payload and calls the handler
    with those parameters.

    Parameters
    ----------
    event : VoiceChannelEventEnvelope
        The voice channel event envelope containing the event data.
    """
    event_type = event.WhichOneof("payload")
    if not event_type:
        logger.warning("Received empty voice event envelope")
        return

    payload = getattr(event, event_type)
    guild_id = getattr(payload, "guild_id", None)

    if guild_id is None:
        logger.warning(
            "Event %s missing guild_id; cannot use guild lock; possible race condition",
            event_type,
        )
        lock = asyncio.Lock()
    else:
        lock = _lock_for_guild(guild_id)

    async with lock:
        if event_type == "created_event":
            await _handle_voice_channel_create(event.created_event)
        elif event_type == "deleted_event":
            await _handle_voice_channel_delete(event.deleted_event)
        elif event_type == "user_joined_event":
            await _handle_user_joined(event.user_joined_event)
        elif event_type == "user_left_event":
            await _handle_user_left(event.user_left_event)
        elif event_type == "rename_event":
            await _handle_voice_channel_rename(event.rename_event)


@RedisSubscriber.subscribe(f"{settings.redis_guild_base}:gateway")
async def handle_guild_event(event: GuildEventEnvelope) -> None:
    """|coro|

    Handles incoming guild events.

    This function dispatches the event to the appropriate handler based on its type.
    It extracts the necessary parameters from the event payload and calls the handler
    with those parameters.

    Parameters
    ----------
    event : GuildEventEnvelope
        The guild event envelope containing the event data.
    """
    payload = event.WhichOneof("payload")
    if not payload:
        logger.warning("Received empty guild event envelope")
        return

    if payload == "left_event":
        data = event.left_event
        guild_id = data.guild_id
        lock = _lock_for_guild(guild_id)
        async with lock:
            _guild_locks.pop(guild_id, None)
            async with get_session() as session:
                if not (config := await _get_guild_config(session, guild_id)):
                    logger.debug(
                        "No voice config for guild=%d; skipping guild left", guild_id
                    )
                    return

                await session.delete(config)
                await session.commit()
