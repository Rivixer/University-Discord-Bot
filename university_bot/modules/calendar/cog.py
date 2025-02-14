# SPDX-License-Identifier: MIT
"""A module to define the calendar cog."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

import nextcord
from nextcord import Attachment, SlashOption
from nextcord.ext.commands import Cog

from university_bot import (
    Interaction,
    Localization,
    catch_interaction_exceptions,
    get_logger,
)
from university_bot.exceptions.cog import LoadCogError
from university_bot.mixins.cog import SetupMixin
from university_bot.mixins.configuration import ConfigurationError

from .config import CalendarConfig
from .exceptions import CalendarError
from .handler import CalendarHandler
from .service import CalendarService

if TYPE_CHECKING:
    from university_bot import UniversityBot

__all__ = ("CalendarCog",)

_logger = get_logger(__name__)


class CalendarCog(SetupMixin, Cog):
    """A cog for the calendar.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot client.
    config: :class:`.CalendarConfig`
        The calendar configuration.
    service: :class:`.CalendarService`
        The calendar service.
    handler: :class:`.CalendarHandler`
        The calendar handler.
    """

    bot: UniversityBot
    config: CalendarConfig
    service: CalendarService
    handler: CalendarHandler

    def __init__(self, bot: UniversityBot) -> None:
        self.bot = bot

        try:
            self.config = CalendarConfig(**bot.config["calendar"])
        except KeyError as e:
            raise LoadCogError(self, "Calendar configuration not found.") from e
        except ValueError as e:
            raise LoadCogError(self, "Invalid calendar configuration.") from e

        self.service = CalendarService(bot, self.config)
        self.handler = CalendarHandler(self.service)

    @override
    async def setup(self, bot: UniversityBot) -> None:
        _logger.debug("Setting up the calendar cog.")
        await self.service.setup_database()
        await self.service.load_calendar(self.handler)
        _logger.debug("Set up the calendar cog.")

    @Localization.apply_localizations
    @nextcord.slash_command(name="calendar")
    async def _calendar(self, *_) -> None:
        """Placeholder for the calendar command group."""

    @Localization.apply_localizations
    @_calendar.subcommand(name="send", description="Send a new calendar message.")
    @catch_interaction_exceptions([CalendarError])
    async def _send(self, interaction: Interaction, preview: bool = False) -> None:
        await self.handler.send_message(interaction, preview)

    @Localization.apply_localizations
    @_calendar.subcommand(name="menu", description="Send the calendar menu.")
    @catch_interaction_exceptions([CalendarError])
    async def _menu(self, interaction: Interaction) -> None:
        await self.handler.send_menu(interaction)

    @Localization.apply_localizations
    @_calendar.subcommand(
        name="get_configuration",
        description="Get the configuration of the calendar.",
    )
    @catch_interaction_exceptions([CalendarError, ConfigurationError])
    async def _get_configuration(self, interaction: Interaction) -> None:
        await self.handler.get_configuration(interaction)

    @Localization.apply_localizations
    @_calendar.subcommand(
        name="set_configuration",
        description="Set the configuration of the calendar.",
    )
    @catch_interaction_exceptions([CalendarError, ConfigurationError])
    async def _set_configuration(
        self,
        interaction: Interaction,
        attachment: Attachment = SlashOption(
            description="JSON configuration file.",
        ),
    ) -> None:
        await self.handler.set_configuration(interaction, attachment)

    @Localization.apply_localizations
    @_calendar.subcommand(
        name="edit_configuration",
        description="Edit the configuration of the calendar.",
    )
    @catch_interaction_exceptions([CalendarError, ConfigurationError])
    async def _edit_configuration(
        self,
        interaction: Interaction,
        indent: int = SlashOption(
            description="JSON identation level (default 2)",
            min_value=0,
            max_value=8,
            default=2,
        ),
    ) -> None:
        await self.handler.edit_configuration(interaction, indent)
