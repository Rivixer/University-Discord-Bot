"""
Voice Channel Service Configuration API Router

Defines the API endpoints for managing voice channels configurations.
"""

from fastapi import APIRouter, Response, status
from sqlalchemy import delete, func
from sqlalchemy.future import select

from shared.models.voice_channel import (
    IsManagedResponse,
    ServiceConfigResponse,
    ServiceConfigUpdateRequest,
)
from voice_channel_service.sync import VoiceChannelSyncClient

from ..actions import request_channel_creation
from ..database import get_session
from ..exceptions import ConfigNotFound
from ..models import ChannelState, ServiceConfig

router = APIRouter(
    prefix="/api/v1/config",
    tags=["Voice Channel Config"],
)


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


@router.get("/{guild_id}", response_model=ServiceConfigResponse)
async def get_service_config(guild_id: int) -> ServiceConfigResponse:
    """Retrieves the service configuration.

    Returns
    -------
    ServiceConfigResponse
        The current service configuration.
    """
    async with get_session() as session:
        result = await session.execute(
            select(ServiceConfig).where(ServiceConfig.guild_id == guild_id)
        )
        config = result.scalar_one_or_none()

    if not config:
        raise ConfigNotFound

    return ServiceConfigResponse.model_validate(config)


@router.put(
    "/{guild_id}",
    response_model=ServiceConfigResponse,
    responses={
        200: {"description": "Existing config updated"},
        201: {"description": "New config created"},
    },
)
async def put_service_config(
    guild_id: int,
    req: ServiceConfigUpdateRequest,
    response: Response,
) -> ServiceConfigResponse:
    """Creates or replaces the service configuration.

    Parameters
    ----------
    guild_id : int
        The ID of the guild for which to update the configuration.
    req : ServiceConfigUpdateRequest
        The request containing the updated configuration.

    Returns
    -------
    ServiceConfig
        The updated or newly created service configuration.
    """
    async with get_session() as session:
        config = await session.execute(
            select(ServiceConfig).where(ServiceConfig.guild_id == guild_id)
        )
        config = config.scalar_one_or_none()

        if not config:
            config = ServiceConfig(
                guild_id=guild_id,
                category_id=req.category_id,
                default_name_template=req.default_name_template,
                available_names=req.available_names,
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)

            response.status_code = status.HTTP_201_CREATED
            return ServiceConfigResponse.model_validate(config)

        old_category = config.category_id
        config.category_id = req.category_id
        config.default_name_template = req.default_name_template

        config.available_names = sorted(set(n[:100] for n in req.available_names))

        await session.commit()
        await session.refresh(config)

        if old_category != req.category_id:
            await session.execute(
                delete(ChannelState).where(ChannelState.guild_id == guild_id)
            )
            await session.commit()

            client = VoiceChannelSyncClient()
            await client.fetch_and_persist_many([config])

            vc_count = await session.scalar(
                select(func.count())
                .select_from(ChannelState)
                .where(ChannelState.guild_id == guild_id)
            )
            if vc_count == 0:
                await request_channel_creation(config)

    return ServiceConfigResponse.model_validate(config)
