# SPDX-License-Identifier: MIT
"""A module to control the bot's presence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import nextcord
from nextcord import ActivityType, SlashOption, Status
from nextcord.ext import commands

from university_bot import Interaction, catch_interaction_exceptions
from university_bot.exceptions.cog import LoadCogError

from .config import PresenceConfig
from .exceptions import InvalidPresenceData, PresenceException
from .handler import PresenceHandler
from .service import PresenceService

if TYPE_CHECKING:
    from university_bot import UniversityBot


class PresenceCog(commands.Cog):
    """A cog to control the bot's presence.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot instance.
    config: :class:`.PresenceConfig`
        The presence configuration.
    service: :class:`.PresenceService`
        The presence service.
    handler: :class:`.PresenceHandler`
        The presence handler.
    """

    bot: UniversityBot
    config: PresenceConfig
    service: PresenceService
    handler: PresenceHandler

    _STATUS_TYPES = [s.name for s in Status if s != Status.offline]
    _ACTIVITY_TYPES = [at.name for at in ActivityType if at != ActivityType.unknown]

    def __init__(self, bot: UniversityBot) -> None:
        self.bot = bot

        try:
            self.config = PresenceConfig(**self.bot.config["presence"])
        except KeyError as e:
            raise LoadCogError(self, "Presence configuration not found.") from e
        except ValueError as e:
            raise LoadCogError(self, "Invalid presence configuration.") from e

        try:
            self.service = PresenceService(self.bot, self.config)
        except InvalidPresenceData as e:
            raise LoadCogError(self, "Error while loading service.") from e

        self.handler = PresenceHandler(self.service)
        self.bot.loop.create_task(self.service.load_presence())

    @nextcord.slash_command(name="presence")
    async def _presence(self, *_) -> None:
        """Placeholder command for the presence command group."""

    @_presence.subcommand(name="set_status", description="Set the bot's status.")
    @catch_interaction_exceptions([PresenceException])
    async def _set_status(
        self,
        interaction: Interaction,
        status: str = SlashOption(
            description="The status to set.",
            choices=_STATUS_TYPES,
            required=True,
        ),
    ) -> None:
        await self.handler.set_status(interaction, status)

    @_presence.subcommand(name="set_activity", description="Set the bot's activity.")
    @catch_interaction_exceptions([PresenceException])
    async def _set_activity(
        self,
        interaction: Interaction,
        type_: str = SlashOption(
            name="type",
            choices=_ACTIVITY_TYPES,
            description="The type of the activity.",
            required=True,
        ),
        activity: str = SlashOption(
            description="The text to display in the activity.",
            required=True,
        ),
    ) -> None:
        await self.handler.set_activity(interaction, type_, activity)

    @_presence.subcommand(
        name="clear_activity",
        description="Clear the bot's activity.",
    )
    @catch_interaction_exceptions([PresenceException])
    async def _clear_activity(self, interaction: Interaction) -> None:
        await self.handler.clear_activity(interaction)


def setup(bot: UniversityBot):
    """Loads the Presence cog."""
    bot.add_cog(PresenceCog(bot))
