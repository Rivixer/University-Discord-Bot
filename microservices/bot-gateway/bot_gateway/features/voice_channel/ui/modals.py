"""
Voice Channel Modals

This module defines modals for renaming voice channels and changing user limits in Discord.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, override

from nextcord import VoiceChannel
from nextcord.ui import Modal, View
from nextcord.ui import TextInput as NextcordTextInput
from nextcord.utils import format_dt

from bot_gateway.core.exceptions import ApiClientError
from bot_gateway.settings import settings
from shared.gen.voice_channel.v1.envelope_pb2 import GatewayEnvelope
from shared.models.voice_channel import RenameLimitExceededErrorResponse
from shared.redis_client import RedisSubscriber

if TYPE_CHECKING:
    from bot_gateway.types import Interaction

    from .views import VoiceChannelPanelView
    from ..services.api_client import VoiceChannelApiClient
    from ..services.manager import DiscordVoiceChannelManager

TextInput = NextcordTextInput[View]

logger = logging.getLogger(__name__)


class RenameModal(Modal):
    """Modal for renaming a voice channel."""

    api_client: VoiceChannelApiClient
    channel: VoiceChannel
    parent_view: VoiceChannelPanelView
    user_limit_input: TextInput

    def __init__(
        self,
        api_client: VoiceChannelApiClient,
        channel: VoiceChannel,
        view: VoiceChannelPanelView,
    ) -> None:
        super().__init__(title="Rename voice channel", timeout=180)
        self.api_client = api_client
        self.channel = channel
        self.parent_view = view

        self.channel_name_input = TextInput(
            label="New channel name",
            placeholder="Enter new channel name",
            required=True,
        )

        self.add_item(self.channel_name_input)  # type: ignore

    @override
    async def callback(self, interaction: Interaction) -> None:
        new_name = self.channel_name_input.value
        assert new_name is not None, "Channel name input should not be None"

        rename_task = asyncio.create_task(
            RedisSubscriber.wait_for_event(
                f"{settings.redis_voice_channel_base}:gateway",
                GatewayEnvelope,
                lambda e: e.WhichOneof("payload") == "rename_event"
                and e.rename_event.channel_id == self.channel.id
                and e.rename_event.new_name == new_name,
                timeout=5.0,
            )
        )

        try:
            response = await self.api_client.rename(
                guild_id=self.channel.guild.id,
                channel_id=self.channel.id,
                new_name=new_name,
            )
        except ApiClientError as e:
            if isinstance(e.error_response, RenameLimitExceededErrorResponse):
                msg = "Maximum number of renames reached."
                if e.error_response.cooldown_reset_at:
                    msg += f" Try again {format_dt(e.error_response.cooldown_reset_at, 'R')}."
                else:
                    msg += " Please try again later."
            else:
                logger.exception(
                    "Failed to rename channel %s in guild %s.",
                    self.channel.name,
                    self.channel.guild.name,
                )
                msg = f"Failed to rename channel ({e.status_code}): {e.error_response.error_code}."
            await interaction.response.send_message(msg, ephemeral=True)
            return

        if not response.success:
            logger.error(
                "Failed to rename channel %s in guild %s.",
                self.channel.name,
                self.channel.guild.name,
            )
            rename_task.cancel()
            await interaction.response.send_message(
                "Failed to rename channel.", ephemeral=True
            )
            return

        await rename_task
        await self.parent_view.edit_message(interaction)


class ChangeUserLimitModal(Modal):
    """Modal for changing the user limit of a voice channel."""

    manager: DiscordVoiceChannelManager
    parent_view: VoiceChannelPanelView
    user_limit_input: TextInput

    def __init__(
        self, manager: DiscordVoiceChannelManager, view: VoiceChannelPanelView
    ) -> None:
        super().__init__(title="Change user limit", timeout=60)
        self.manager = manager
        self.parent_view = view

        self.user_limit_input = TextInput(
            label="New user limit",
            placeholder="1-99",
            required=True,
        )

        self.add_item(self.user_limit_input)  # type: ignore

    @override
    async def callback(self, interaction: Interaction) -> None:
        new_limit = self.user_limit_input.value
        assert new_limit is not None, "User limit input should not be None"

        if not new_limit.isdigit() or not (1 <= int(new_limit) <= 99):
            await interaction.response.send_message(
                "Invalid user limit.\nPlease enter a number between 1 and 99.",
                ephemeral=True,
            )
            return

        assert isinstance(interaction.channel, VoiceChannel), (
            "Interaction channel should be a VoiceChannel"
        )

        await self.manager.edit_channel(interaction.channel, user_limit=int(new_limit))
        await self.parent_view.edit_message(interaction)
