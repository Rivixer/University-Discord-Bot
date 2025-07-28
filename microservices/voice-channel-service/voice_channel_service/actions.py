"""
Voice Channel Service Actions

Defines actions for sending requests to the bot gateway.
"""

import logging
import random

from sqlalchemy import select

from shared.gen.voice_channel.v1.envelope_pb2 import ServiceEnvelope
from shared.gen.voice_channel.v1.requests_pb2 import (
    CreateVoiceChannelRequest,
    DeleteVoiceChannelRequest,
)
from shared.redis_client import RedisPublisher

from .database import get_session
from .models import ChannelState, ServiceConfig
from .settings import settings

logger = logging.getLogger(__name__)

_redis_request_publisher = RedisPublisher(f"{settings.redis_channel_base}:service")


async def _generate_channel_name(config: ServiceConfig) -> str:
    logger.debug("Generating channel name for guild %d", config.guild_id)
    async with get_session() as session:
        stmt = select(ChannelState.name).where(ChannelState.guild_id == config.guild_id)
        used_names = set(await session.scalars(stmt))

    if remaining := [name for name in config.available_names if name not in used_names]:
        return random.choice(remaining)

    n = len(used_names) + 1
    while True:
        name = config.default_name_template.format(n=n)
        if name not in used_names:
            break
        n += 1

    logger.debug("Generated channel name: %s", name)
    return name


async def request_channel_creation(config: ServiceConfig) -> None:
    """Requests the creation of a voice channel.

    This function generates a new channel name based on the service configuration
    and sends a request to the voice channel service to create the channel.

    Parameters
    ----------
    config : ServiceConfig
        The service configuration containing the guild and category IDs.
    """
    logger.debug("Requesting channel creation for guild %d", config.guild_id)
    new_name = await _generate_channel_name(config)

    req = CreateVoiceChannelRequest(
        guild_id=config.guild_id,
        category_id=config.category_id,
        name=new_name,
    )
    envelope = ServiceEnvelope(create_channel_request=req)

    await _redis_request_publisher.publish(envelope)


async def request_channel_deletion(channel_id: int) -> None:
    """Requests the deletion of a voice channel.

    Parameters
    ----------
    channel_id : int
        The ID of the voice channel to delete.
    """
    logger.debug("Requesting channel deletion for channel %d", channel_id)
    req = DeleteVoiceChannelRequest(channel_id=channel_id)
    envelope = ServiceEnvelope(delete_channel_request=req)
    await _redis_request_publisher.publish(envelope)
