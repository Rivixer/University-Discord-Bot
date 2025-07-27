"""
Voice Channel Service Handlers Module

This module subscribes to Redis Pub/Sub envelopes, dispatches them
to the appropriate handler, and applies all business logic for:
- tracking channel state (create/delete, join/leave)
- maintaining exactly one empty channel per guild
- cleaning up guild configurations on bot removal
"""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.gen.guild.v1.envelope_pb2 import GuildEventEnvelope
from shared.gen.voice_channel.v1.envelope_pb2 import (
    GatewayEnvelope,
    ServiceEnvelope,
)
from shared.gen.voice_channel.v1.requests_pb2 import (
    CreateVoiceChannelRequest,
    DeleteVoiceChannelRequest,
)
from shared.redis_client import RedisPublisher, RedisSubscriber

from .database import get_session
from .models import ChannelState, ServiceConfig
from .rename_scheduler import cancel_cooldown
from .settings import settings

logger = logging.getLogger(__name__)

_guild_locks: dict[int, asyncio.Lock] = {}
_redis_request_publisher = RedisPublisher(f"{settings.redis_channel_base}:service")


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


async def _handle_voice_channel_create(guild_id: int, channel_id: int) -> None:
    async with get_session() as session:
        if await _get_channel_state(session, channel_id):
            logger.debug(
                "Channel %d already tracked", channel_id, extra={"guild_id": guild_id}
            )
            return

        session.add(ChannelState(channel_id=channel_id, guild_id=guild_id))
        await session.commit()
        logger.info("Registered new voice channel %d in guild %d", channel_id, guild_id)


async def _handle_voice_channel_delete(channel_id: int) -> None:
    async with get_session() as session:
        if not (state := await _get_channel_state(session, channel_id)):
            logger.debug("Deleted channel %d not tracked", channel_id)
            return

        await session.delete(state)
        await session.commit()
        logger.info("Removed deleted voice channel %d", channel_id)

    cancel_cooldown(state.guild_id, channel_id)


async def _handle_user_joined(guild_id: int, channel_id: int) -> None:
    async with get_session() as session:
        if not (config := await _get_guild_config(session, guild_id)):
            logger.debug("No voice config for guild=%d; skipping user join", guild_id)
            return

        if not (state := await _get_channel_state(session, channel_id)):
            state = ChannelState(guild_id=guild_id, channel_id=channel_id)
            session.add(state)

        state.active_users += 1
        await session.commit()

        logger.debug(
            "User joined: guild=%d channel=%d active_users=%d",
            guild_id,
            channel_id,
            state.active_users,
        )

        empty_channels = (
            await session.scalars(
                select(ChannelState).where(
                    ChannelState.guild_id == guild_id,
                    ChannelState.active_users == 0,
                    ~ChannelState.pending_deletion,
                )
            )
        ).all()

        if not empty_channels:
            new_name = await _generate_channel_name(session, config)
            create_req = CreateVoiceChannelRequest(
                guild_id=guild_id,
                category_id=config.category_id,
                name=new_name,
            )
            envelope = ServiceEnvelope(create_channel_request=create_req)
            await _redis_request_publisher.publish(envelope)


async def _handle_user_left(guild_id: int, channel_id: int) -> None:
    async with get_session() as session:
        if not await _get_guild_config(session, guild_id):
            logger.debug("No voice config for guild=%d; skipping user left", guild_id)
            return

        if not (state := await _get_channel_state(session, channel_id)):
            logger.debug(
                "User left unknown channel %d in guild %d", channel_id, guild_id
            )
            return

        state.active_users = max(0, state.active_users - 1)
        await session.commit()

        logger.debug(
            "User left: guild=%d channel=%d active_users=%d",
            guild_id,
            channel_id,
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

                cancel_cooldown(state.guild_id, channel_id)
                delete_req = DeleteVoiceChannelRequest(channel_id=channel_id)
                envelope = ServiceEnvelope(delete_channel_request=delete_req)
                await _redis_request_publisher.publish(envelope)


async def _generate_channel_name(session: AsyncSession, config: ServiceConfig) -> str:
    # TODO: Implement proper name generation logic
    return config.default_name_template.replace("{n}", "X")


_EVENT_HANDLERS: dict[str, Callable[..., Awaitable[None]]] = {
    "created_event": _handle_voice_channel_create,
    "deleted_event": _handle_voice_channel_delete,
    "user_joined_event": _handle_user_joined,
    "user_left_event": _handle_user_left,
}

_HANDLER_PARAMS: dict[str, set[str]] = {}
for evt_name, fn in _EVENT_HANDLERS.items():
    sig = inspect.signature(fn)
    _HANDLER_PARAMS[evt_name] = set(sig.parameters.keys())


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

    handler = _EVENT_HANDLERS.get(event_type)
    if not handler:
        logger.warning("Unhandled voice event type: %s", event_type)
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
        allowed = _HANDLER_PARAMS[event_type]
        kwargs: dict[str, Any] = {}
        if "guild_id" in allowed and hasattr(payload, "guild_id"):
            kwargs["guild_id"] = payload.guild_id
        if "channel_id" in allowed and hasattr(payload, "channel_id"):
            kwargs["channel_id"] = payload.channel_id

        await handler(**kwargs)


async def _handle_guild_left(guild_id: int) -> None:
    _guild_locks.pop(guild_id, None)
    async with get_session() as session:
        if not (config := await _get_guild_config(session, guild_id)):
            logger.debug("No voice config for guild=%d; skipping guild left", guild_id)
            return

        await session.delete(config)
        await session.commit()


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
            await _handle_guild_left(guild_id)
