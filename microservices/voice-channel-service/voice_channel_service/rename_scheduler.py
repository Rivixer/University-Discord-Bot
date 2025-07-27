"""
Voice Channel Service Rename Scheduler

Manages scheduling of rename-cooldown tasks for voice channels:
- schedule new cooldown (and replace existing)
- cancel a scheduled cooldown
- initialize pending cooldowns from the database
- publish cooldown-expired events via Redis
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from shared.gen.voice_channel.v1.envelope_pb2 import ServiceEnvelope
from shared.gen.voice_channel.v1.events_pb2 import (
    BotVoiceChannelRenameCooldownExpiredEvent,
)
from shared.redis_client import RedisPublisher

from .database import get_session
from .models import ChannelState
from .settings import settings

logger = logging.getLogger(__name__)

_scheduler: dict[tuple[int, int], asyncio.Task[None]] = {}


async def _cooldown_task(guild_id: int, channel_id: int, fire_at: datetime) -> None:
    try:
        while datetime.now(timezone.utc) < fire_at:
            remaining = (fire_at - datetime.now(timezone.utc)).total_seconds()
            await asyncio.sleep(min(remaining, 1.0))

        logger.info(
            "Cooldown expired for guild=%s, channel=%s",
            guild_id,
            channel_id,
        )

        event = BotVoiceChannelRenameCooldownExpiredEvent(
            guild_id=guild_id,
            channel_id=channel_id,
        )
        envelope = ServiceEnvelope(rename_cooldown_expired_event=event)
        await RedisPublisher.publish_to_channel(
            f"{settings.redis_channel_base}:service", envelope
        )
    except asyncio.CancelledError:
        logger.info(
            "Cooldown task cancelled: guild=%s, channel=%s",
            guild_id,
            channel_id,
        )
    finally:
        _scheduler.pop((guild_id, channel_id), None)


def schedule_cooldown(guild_id: int, channel_id: int, fire_at: datetime) -> None:
    """Schedules a cooldown task for a voice channel rename operation.

    This function checks if a cooldown task is already scheduled for the given guild and channel ID.
    If no task exists, a new cooldown task is created and scheduled to run at the specified time;
    otherwise, the existing task is cancelled and replaced with the new one.

    Parameters
    ----------
    guild_id : int
        The ID of the guild where the voice channel is located.
    channel_id : int
        The ID of the voice channel to schedule the cooldown for.
    fire_at : datetime
        The time at which the cooldown should expire.
    """
    key = (guild_id, channel_id)
    if existing := _scheduler.get(key):
        logger.debug(
            "Cancelling existing cooldown task for guild=%s, channel=%s",
            guild_id,
            channel_id,
        )
        existing.cancel()

    logger.debug(
        "Scheduling cooldown task for guild=%s, channel=%s at %s",
        guild_id,
        channel_id,
        fire_at,
    )
    task = asyncio.create_task(_cooldown_task(guild_id, channel_id, fire_at))
    _scheduler[key] = task


def cancel_cooldown(guild_id: int, channel_id: int) -> None:
    """Cancels the scheduled cooldown task for a voice channel rename operation.

    This function checks if a cooldown task is scheduled for the given guild and channel ID,
    and cancels it if it exists; otherwise, it does nothing.

    Parameters
    ----------
    guild_id : int
        The ID of the guild where the voice channel is located.
    channel_id : int
        The ID of the voice channel to cancel the cooldown for.
    """
    key = (guild_id, channel_id)
    if task := _scheduler.pop(key, None):
        task.cancel()


async def initialize_cooldowns():
    """|coro|

    Initializes existing cooldowns from the database.

    This function retrieves all voice channels with an active rename cooldown from the database
    and schedules their cooldown tasks."""
    from .routers.voice_channel import WINDOW

    async with get_session() as session:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(ChannelState).where(ChannelState.rename_window_start.is_not(None))
        )

        for state in result.scalars():
            if state.rename_window_start is None:
                continue

            fire_at = state.rename_window_start + WINDOW
            if fire_at > now:
                schedule_cooldown(state.guild_id, state.channel_id, fire_at)
