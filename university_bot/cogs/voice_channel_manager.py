# SPDX-License-Identifier: MIT
"""A module for managing voice channels."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nextcord import SlashOption, slash_command
from nextcord.ext import commands

from .. import Interaction, catch_interaction_exceptions
from ..exceptions.voice_channel_manager import (
    InvalidConfiguration,
    VoiceChannelManagerException,
)
from ..handlers.voice_channel_manager import VoiceChannelManagerHandler
from ..models.configs.voice_channel_manager import VoiceChannelManagerConfig
from ..services.voice_channel_manager import VoiceChannelManagerService
from . import LoadCogError

if TYPE_CHECKING:
    from nextcord import Member, VoiceState

    from .. import UniversityBot


class VoiceChannelManager(commands.Cog):
    """A cog to manage voice channels."""

    bot: UniversityBot
    config: VoiceChannelManagerConfig
    service: VoiceChannelManagerService
    handler: VoiceChannelManagerHandler

    def __init__(self, bot: UniversityBot) -> None:
        self.bot = bot
        self.config = self.bot.config.voice_channel_manager

        try:
            self.service = VoiceChannelManagerService(bot, self.config)
        except InvalidConfiguration as e:
            raise LoadCogError(self, "Error while loading service.") from e

        self.handler = VoiceChannelManagerHandler(self.service)
        self.bot.loop.create_task(self.service.check_voice_channels())

    @commands.Cog.listener(name="on_ready")
    async def _on_ready(self) -> None:
        await self.handler.on_ready()

    @commands.Cog.listener(name="on_voice_state_update")
    async def _on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ):
        await self.handler.on_voice_state_update(member, before, after)

    @slash_command(name="voice_channel")
    async def _voice_channel(self, *_) -> None:
        """Placeholder for the voice_channel command group."""

    @_voice_channel.subcommand(
        name="set_limit",
        description="Set the limit of the voice channel you are in.",
    )
    @catch_interaction_exceptions([VoiceChannelManagerException])
    async def _set_limit(
        self,
        interaction: Interaction,
        value: int = SlashOption(
            description="The limit to be set (1-99).",
            min_value=1,
            max_value=99,
        ),
    ) -> None:
        await self.handler.set_limit(interaction, value)

    @_voice_channel.subcommand(
        name="reset_limit",
        description="Reset the limit of the voice channel you are in.",
    )
    @catch_interaction_exceptions([VoiceChannelManagerException])
    async def _reset_limit(self, interaction: Interaction) -> None:
        await self.handler.reset_limit(interaction)

    @_voice_channel.subcommand(
        name="rename",
        description="Rename the voice channel you are in (max 2 times per 10 minutes).",
    )
    @catch_interaction_exceptions([VoiceChannelManagerException])
    async def _name(
        self,
        interaction: Interaction,
        name: str = SlashOption(description="A new name for the voice channel."),
    ) -> None:
        await self.handler.rename(interaction, name)


def setup(bot: UniversityBot) -> None:
    """Loads the voice channel manager cog."""
    bot.add_cog(VoiceChannelManager(bot))
