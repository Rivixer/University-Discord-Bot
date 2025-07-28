"""
Voice Channel API Client

Provides VoiceChannelApiClient, an HTTPX-based client for communicating
with the voice-channel microservice.
"""

import logging

from httpx import AsyncClient

from bot_gateway.core.error_handlers import handle_api_errors
from bot_gateway.settings import settings
from shared.models.voice_channel import (
    RenameChannelRequest,
    RenameChannelResponse,
    RenameStatusResponse,
    ServiceConfigResponse,
    ServiceConfigUpdateRequest,
)

logger = logging.getLogger(__name__)


class VoiceChannelApiClient:
    """API client for interacting with the voice channel service.

    This client handles all API requests to the voice channel service.
    """

    _client: AsyncClient

    def __init__(self, *, timeout: float | None = None):
        self._client = AsyncClient(
            timeout=timeout,
            base_url=settings.voice_channel_service_url.rstrip("/"),
        )

    async def close(self) -> None:
        """|coro|

        Closes the HTTP client connection.
        """
        logger.info("Closing VoiceChannelApiClient")

        if self._client.is_closed:
            logger.warning("VoiceChannelApiClient is already closed")
            return

        await self._client.aclose()

    @handle_api_errors()
    async def is_managed_channel(self, channel_id: int) -> bool:
        """|coro|

        Checks if a voice channel is managed by the voice channel service.

        Parameters
        ----------
        channel_id : int
            The ID of the voice channel to check.

        Returns
        -------
        bool
            True if the channel is managed by the service, False otherwise.

        Raises
        ------
        ApiClientError
            If there is a network error or if the service returns non-200 status code.
        """
        url = "/api/v1/voice-channel/is-managed"
        resp = await self._client.get(url, params={"channel_id": channel_id})
        resp.raise_for_status()
        return resp.json().get("is_managed", False)

    @handle_api_errors()
    async def get_rename_status(
        self, guild_id: int, channel_id: int
    ) -> RenameStatusResponse:
        """|coro|

        Retrieves the rename status of a voice channel.

        Parameters
        ----------
        guild_id : int
            The ID of the guild where the channel is located.
        channel_id : int
            The ID of the voice channel to check.

        Returns
        -------
        RenameStatusResponse
            The rename status of the voice channel.

        Raises
        ------
        ApiClientError
            If there is a network error or if the service returns non-200 status code.
        """
        url = "/api/v1/voice-channel/rename-status"
        resp = await self._client.get(
            url,
            params={
                "guild_id": guild_id,
                "channel_id": channel_id,
            },
        )
        resp.raise_for_status()
        return RenameStatusResponse(**resp.json())

    @handle_api_errors()
    async def rename(
        self, guild_id: int, channel_id: int, new_name: str
    ) -> RenameChannelResponse:
        """|coro|

        Renames a voice channel.

        Parameters
        ----------
        guild_id : int
            The ID of the guild where the channel is located.
        channel_id : int
            The ID of the voice channel to rename.
        new_name : str
            The new name for the voice channel.

        Returns
        -------
        RenameChannelResponse
            The response from the voice channel service.

        Raises
        ------
        ApiClientError
            If there is a network error or if the service returns non-200 status code.
        """
        url = "/api/v1/voice-channel/rename"
        req = RenameChannelRequest(
            guild_id=guild_id,
            channel_id=channel_id,
            new_name=new_name,
        )
        resp = await self._client.post(
            url,
            json=req.model_dump(mode="json"),
        )
        resp.raise_for_status()
        return RenameChannelResponse(**resp.json())

    @handle_api_errors()
    async def get_service_config(self, guild_id: int) -> ServiceConfigResponse:
        """|coro|

        Retrieves the service configuration for a specific guild.

        Parameters
        ----------
        guild_id : int
            The ID of the guild to retrieve the configuration for.

        Returns
        -------
        ServiceConfigResponse
            The service configuration for the specified guild.

        Raises
        ------
        ApiClientError
            If there is a network error or if the service returns non-200 status code.
        """
        url = f"/api/v1/config/{guild_id}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        return ServiceConfigResponse(**resp.json())

    @handle_api_errors()
    async def update_service_config(
        self,
        guild_id: int,
        category_id: int | None,
        default_name_template: str,
        available_names: list[str],
    ) -> ServiceConfigResponse:
        """|coro|

        Updates the service configuration for a specific guild.

        Parameters
        ----------
        guild_id : int
            The ID of the guild to update the configuration for.
        category_id : int | None
            The ID of the category where voice channels are created.
        default_name_template : str
            The default name template for voice channels.
        available_names : list[str]
            List of available names for voice channels.

        Returns
        -------
        ServiceConfigResponse
            The updated service configuration for the specified guild.

        Raises
        ------
        ApiClientError
            If there is a network error or if the service returns non-200 status code.
        """
        url = f"/api/v1/config/{guild_id}"
        req = ServiceConfigUpdateRequest(
            category_id=category_id,
            default_name_template=default_name_template,
            available_names=available_names,
        )
        resp = await self._client.put(
            url,
            json=req.model_dump(mode="json"),
        )
        resp.raise_for_status()
        return ServiceConfigResponse(**resp.json())
