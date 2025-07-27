"""
Voice Channel Panel View

This module defines the view for the voice channel panel in the bot gateway.
It includes buttons for renaming the channel, changing user limits, and resetting the limit.
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any, Callable

from nextcord import ButtonStyle, Member, VoiceChannel
from nextcord.ui import Button as NextcordButton
from nextcord.ui import View, button

from shared.models.voice_channel import RenameStatusResponse

from .embeds import VoiceChannelPanelEmbed
from .modals import ChangeUserLimitModal, RenameModal

if TYPE_CHECKING:
    from bot_gateway.types import Button, Interaction

    from ..services.api_client import VoiceChannelApiClient
    from ..services.manager import (
        DiscordVoiceChannelManager,
    )

    _ItemCallback = Callable[[Any, Button, Interaction], Coroutine[Any, Any, Any]]


class VoiceChannelPanelView(View):
    """View for the voice channel panel."""

    api_client: VoiceChannelApiClient
    manager: DiscordVoiceChannelManager
    channel: VoiceChannel

    def __init__(
        self,
        api_client: VoiceChannelApiClient,
        manager: DiscordVoiceChannelManager,
        channel: VoiceChannel,
    ):
        super().__init__(timeout=None)
        self.api_client = api_client
        self.manager = manager
        self.channel = channel

    async def get(self) -> tuple[VoiceChannelPanelView, VoiceChannelPanelEmbed]:
        """|coro|

        Retrieves the current view and embed for the voice channel panel.

        Returns
        -------
        tuple[VoiceChannelPanelView, VoiceChannelPanelEmbed]
            The current view and embed for the voice channel panel.
        """
        rename_status = await self.api_client.get_rename_status(
            self.channel.guild.id, self.channel.id
        )
        self._update_buttons(rename_status)
        embed = VoiceChannelPanelEmbed(self.channel, rename_status)
        return self, embed

    async def edit_message(self, interaction: Interaction) -> None:
        """|coro|

        Edits the message with the current embed and view.

        Parameters
        ----------
        interaction : Interaction
            The interaction that triggered the edit.
        """
        view, embed = await self.get()
        await interaction.response.edit_message(embed=embed, view=view)

    def _update_buttons(self, rename_status: RenameStatusResponse) -> None:
        for child in self.children:  # type: ignore
            if not isinstance(child, NextcordButton):
                continue

            if child.custom_id == "rename":
                child.disabled = rename_status.remaining_renames <= 0
            elif child.custom_id == "limit":
                child.label = (
                    "Set limit" if self.channel.user_limit == 0 else "Change limit"
                )
            elif child.custom_id == "reset_limit":
                child.disabled = self.channel.user_limit == 0

    @staticmethod
    def _require_voice_connection(func: _ItemCallback) -> _ItemCallback:
        async def wrapper(
            self: VoiceChannelPanelView,
            button: Button,
            interaction: Interaction,
        ):
            if not isinstance(member := interaction.user, Member):
                return await interaction.response.send_message(
                    "This button can only be used by members.",
                    ephemeral=True,
                )

            if not interaction.channel or not isinstance(
                interaction.channel, VoiceChannel
            ):
                return await interaction.response.send_message(
                    "This button can only be used in a voice channel.",
                    ephemeral=True,
                )

            if (
                not member.voice
                or not member.voice.channel
                or member.voice.channel.id != interaction.channel.id
            ):
                channel_mention = interaction.channel.mention
                return await interaction.response.send_message(
                    f"You must be in {channel_mention} to use this button.",
                    ephemeral=True,
                )

            return await func(self, button, interaction)

        return wrapper

    @button(label="Rename", style=ButtonStyle.green, custom_id="rename")
    @_require_voice_connection
    async def rename(self, button: Button, interaction: Interaction):
        modal = RenameModal(self.api_client, self.channel, self)
        await interaction.response.send_modal(modal)

    @button(style=ButtonStyle.blurple, custom_id="limit")
    @_require_voice_connection
    async def change_limit(self, button: Button, interaction: Interaction):
        modal = ChangeUserLimitModal(self.manager, self)
        await interaction.response.send_modal(modal)

    @button(label="Reset limit", style=ButtonStyle.gray, custom_id="reset_limit")
    @_require_voice_connection
    async def reset_limit(self, button: Button, interaction: Interaction):
        await self.manager.edit_channel(self.channel, user_limit=0)
        await self.edit_message(interaction)
