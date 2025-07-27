"""
Voice Channel Service API Router

Defines the API endpoints for managing voice channels.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy.future import select

from shared.gen.voice_channel.v1.envelope_pb2 import ServiceEnvelope
from shared.gen.voice_channel.v1.requests_pb2 import RenameVoiceChannelRequest
from shared.models import ErrorResponse
from shared.models.voice_channel import (
    IsManagedResponse,
    RenameChannelRequest,
    RenameChannelResponse,
    RenameStatusResponse,
)
from shared.redis_client import RedisPublisher

from ..database import get_session
from ..exceptions import ChannelNotManaged, RenameLimitExceeded
from ..models import ChannelState, ServiceConfig
from ..rename_scheduler import schedule_cooldown
from ..settings import settings

router = APIRouter(
    prefix="/api/v1/voice-channel",
    tags=["Voice Channel"],
)

MAX_RENAMES = 2
WINDOW = timedelta(minutes=10)


@router.get("/is-managed", response_model=IsManagedResponse)
async def is_managed_channel(channel_id: int) -> IsManagedResponse:
    """Checks if a voice channel is managed by the service.

    Parameters
    ----------
    channel_id : int
        The ID of the channel to check.

    Returns
    -------
    IsManagedResponse
        Response indicating whether the channel is managed.
    """
    async with get_session() as session:
        result = await session.execute(
            select(ChannelState).where(ChannelState.channel_id == channel_id)
        )

        channel = result.scalar_one_or_none()
        return IsManagedResponse(is_managed=channel is not None)


@router.get("/is-managed", response_model=IsManagedResponse)
async def is_managed_category(category_id: int) -> IsManagedResponse:
    """Checks if a voice channel category is managed by the service.

    Parameters
    ----------
    category_id : int
        The ID of the category to check.

    Returns
    -------
    IsManagedResponse
        Response indicating whether the category is managed.
    """
    async with get_session() as session:
        result = await session.execute(
            select(ServiceConfig).where(ServiceConfig.category_id == category_id)
        )

        config = result.scalar_one_or_none()
        return IsManagedResponse(is_managed=config is not None)


@router.get(
    "/rename-status",
    response_model=RenameStatusResponse,
    responses={
        404: {"model": ErrorResponse, "description": "ChannelState not found"},
    },
)
async def get_rename_status(guild_id: int, channel_id: int) -> RenameStatusResponse:
    """Retrieves the rename status for a voice channel.

    Parameters
    ----------
    guild_id : int
        The ID of the guild where the channel is located.
    channel_id : int
        The ID of the channel to check.

    Returns
    -------
    RenameStatusResponse
        Response containing the remaining renames and cooldown information.

    Raises
    ------
    HTTPException
        404: Channel not managed or not found.
    """
    async with get_session() as session:
        result = await session.execute(
            select(ChannelState).where(
                ChannelState.guild_id == guild_id,
                ChannelState.channel_id == channel_id,
            )
        )

        if not (state := result.scalar_one_or_none()):
            raise ChannelNotManaged()

        now = datetime.now(timezone.utc)
        if (
            state.rename_window_start is None
            or (now - state.rename_window_start) > WINDOW
        ):
            return RenameStatusResponse(
                remaining_renames=MAX_RENAMES,
                max_remaining_renames=MAX_RENAMES,
                cooldown_reset_at=None,
            )

        remaining = max(0, MAX_RENAMES - state.rename_count)
        cooldown_reset_at = (
            state.rename_window_start + WINDOW if remaining < MAX_RENAMES else None
        )
        return RenameStatusResponse(
            remaining_renames=remaining,
            max_remaining_renames=MAX_RENAMES,
            cooldown_reset_at=cooldown_reset_at,
        )


@router.post(
    "/rename",
    response_model=RenameChannelResponse,
    responses={
        404: {"model": ErrorResponse, "description": "ChannelState not found"},
        429: {"model": ErrorResponse, "description": "Too many renames"},
    },
)
async def rename_channel(req: RenameChannelRequest) -> RenameChannelResponse:
    """Renames a voice channel.

    Parameters
    ----------
    req : RenameChannelRequest
        The request containing the guild ID, channel ID, and new name.

    Returns
    -------
    RenameChannelResponse
        Response containing the status of the rename operation.

    Raises
    ------
    HTTPException
        404: Channel not managed or not found.
        429: Rename limit reached (with details: :class:`RenameLimitExceededErrorResponse`).
    """
    now = datetime.now(timezone.utc)

    async with get_session() as session:
        result = await session.execute(
            select(ChannelState)
            .where(
                ChannelState.guild_id == req.guild_id,
                ChannelState.channel_id == req.channel_id,
            )
            .with_for_update()
        )

        if not (state := result.scalar_one_or_none()):
            raise ChannelNotManaged()

        if (
            state.rename_window_start is None
            or (now - state.rename_window_start) > WINDOW
        ):
            state.rename_window_start = now
            state.rename_count = 0

        if state.rename_count >= MAX_RENAMES:
            cooldown_reset_at = state.rename_window_start + WINDOW
            raise RenameLimitExceeded(cooldown_reset_at)

        state.rename_count += 1
        state.last_rename_at = now
        session.add(state)
        await session.commit()

    schedule_cooldown(req.guild_id, req.channel_id, state.rename_window_start + WINDOW)

    request = RenameVoiceChannelRequest(
        guild_id=req.guild_id,
        channel_id=req.channel_id,
        new_name=req.new_name,
    )
    envelope = ServiceEnvelope(rename_channel_request=request)
    await RedisPublisher.publish_to_channel(
        f"{settings.redis_channel_base}:service", envelope
    )

    remaining = MAX_RENAMES - state.rename_count
    cooldown_reset_at = (
        state.rename_window_start + WINDOW if remaining < MAX_RENAMES else None
    )
    return RenameChannelResponse(
        success=True,
        remaining_renames=remaining,
        max_remaining_renames=MAX_RENAMES,
        cooldown_reset_at=cooldown_reset_at,
    )
