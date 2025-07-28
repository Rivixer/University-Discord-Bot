"""
Voice Channel Panel View
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any, Callable

from nextcord import ButtonStyle, Guild, Member, VoiceChannel
from nextcord.ui import Button as NextcordButton
from nextcord.ui import View, button
from nextcord.utils import MISSING

from bot_gateway.core.exceptions import ApiClientError
from shared.models.voice_channel import RenameStatusResponse

from .embeds import VoiceChannelConfigEmbed, VoiceChannelPanelEmbed
from .modals import (
    ChangeAvailableNamesModal,
    ChangeDefaultNameTemplateModal,
    ChangeUserLimitModal,
    RenameModal,
)
from .selects import CategorySelect

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

        Raises
        -------
        ApiClientError
            If there is an error retrieving the rename status.
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
        try:
            view, embed = await self.get()
        except ApiClientError as e:
            await interaction.response.edit_message(
                content=f"Error retrieving panel view ({e.status_code}): {e.error_response.error_code}",
            )
            return

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


class VoiceChannelConfigView(View):
    """View for the voice channel configuration."""

    guild: Guild
    api_client: VoiceChannelApiClient
    category_select: CategorySelect

    category_id_temp: int | None
    default_name_template_temp: str
    available_names_temp: list[str]

    def __init__(self, guild: Guild, api_client: VoiceChannelApiClient):
        super().__init__(timeout=None)
        self.guild = guild
        self.api_client = api_client

        self.category_select = CategorySelect(
            view=self,
            categories=guild.categories,
            row=0,
        )

        self.add_item(self.category_select)

    @classmethod
    async def create(
        cls, guild: Guild, api_client: VoiceChannelApiClient
    ) -> tuple[VoiceChannelConfigView, VoiceChannelConfigEmbed]:
        """|coro|

        Creates a new instance of the voice channel configuration view.

        Parameters
        ----------
        guild : Guild
            The guild for which the configuration is being created.
        api_client : VoiceChannelApiClient
            The API client to interact with the voice channel service.

        Returns
        -------
        tuple[VoiceChannelConfigView, VoiceChannelConfigEmbed]
            The view and embed for the voice channel configuration.
        """
        self = cls(guild, api_client)

        try:
            config = await api_client.get_service_config(guild.id)
        except ApiClientError as e:
            if (
                e.status_code == 404
                and e.error_response.error_code == "config_not_found"
            ):
                self.category_id_temp = None
                self.default_name_template_temp = "Room {n}"
                self.available_names_temp = []
            else:
                raise
        else:
            self.category_id_temp = config.category_id
            self.default_name_template_temp = config.default_name_template
            self.available_names_temp = config.available_names

        self.category_select.set_default(self.category_id_temp)
        return self.get()

    def get(self) -> tuple[VoiceChannelConfigView, VoiceChannelConfigEmbed]:
        """Retrieves the current view and embed for the voice channel configuration.

        Returns
        -------
        tuple[VoiceChannelConfigView, VoiceChannelConfigEmbed]
            The current view and embed for the voice channel configuration.

        Raises
        -------
        ApiClientError
            If there is an error retrieving the service configuration.
        """
        self.category_select.set_default(self.category_id_temp)

        embed = VoiceChannelConfigEmbed(
            self.default_name_template_temp,
            self.available_names_temp,
        )

        return self, embed

    async def edit_message(
        self,
        interaction: Interaction,
        show_view: bool = True,
        show_embed: bool = True,
        content: str | None = MISSING,
        delete_after: float | None = None,
    ) -> None:
        """|coro|

        Edits the message with the current embed and view.

        Parameters
        ----------
        interaction : Interaction
            The interaction that triggered the edit.
        show_view : bool
            Whether to show the view.
        show_embed : bool
            Whether to show the embed.
        content : str | None
            The content to display in the message.
            If not provided, the content will not be changed.
        """
        view, embed = None, None
        if show_view or show_embed:
            view, embed = self.get()

        await interaction.response.edit_message(
            embed=embed if show_embed else None,
            view=view if show_view else None,
            content=content,
            delete_after=delete_after,
        )

    @button(
        label="Change available names",
        style=ButtonStyle.blurple,
        custom_id="available_names",
        row=1,
    )
    async def available_names(self, button: Button, interaction: Interaction):
        modal = ChangeAvailableNamesModal(
            self.api_client,
            self,
            self.available_names_temp,
        )
        await interaction.response.send_modal(modal)

    @button(
        label="Change default name template",
        style=ButtonStyle.gray,
        custom_id="default_name_template",
        row=1,
    )
    async def default_name_template(self, button: Button, interaction: Interaction):
        modal = ChangeDefaultNameTemplateModal(
            self.api_client,
            self,
            self.default_name_template_temp,
        )
        await interaction.response.send_modal(modal)

    @button(
        label="Save configuration",
        style=ButtonStyle.green,
        custom_id="save_configuration",
        row=2,
    )
    async def save_configuration(self, button: Button, interaction: Interaction):
        try:
            _ = await self.api_client.update_service_config(
                self.guild.id,
                self.category_id_temp,
                self.default_name_template_temp,
                self.available_names_temp,
            )
        except ApiClientError as e:
            return await self.edit_message(
                interaction,
                content=f"Error saving configuration ({e.status_code}): {e.error_response.error_code}",
            )

        await self.edit_message(
            interaction,
            show_embed=False,
            show_view=False,
            content="Configuration saved successfully.",
            delete_after=5.0,
        )

    @button(
        label="Cancel configuration",
        style=ButtonStyle.red,
        custom_id="cancel_configuration",
        row=2,
    )
    async def cancel_configuration(self, button: Button, interaction: Interaction):
        await self.edit_message(
            interaction,
            show_embed=False,
            show_view=False,
            content="Configuration cancelled.",
            delete_after=5.0,
        )
