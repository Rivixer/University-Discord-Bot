# SPDX-License-Identifier: MIT
"""A module to define the reminder cog.

This cog extends the calendar cog.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import nextcord
from nextcord import Attachment, SlashOption
from nextcord.ext.commands import Cog

from university_bot import Interaction, Localization, catch_interaction_exceptions
from university_bot.exceptions.cog import LoadCogError
from university_bot.mixins.configuration import ConfigurationError
from university_bot.utils import entry_cog, load_after

from .config import ReminderConfig
from .exceptions import ReminderError
from .handler import ReminderHandler
from .service import ReminderService
from ..calendar import CalendarCog

if TYPE_CHECKING:
    from university_bot import UniversityBot


__all__ = ("ReminderCog",)


@entry_cog
@load_after(CalendarCog)
class ReminderCog(Cog):
    """A cog for the reminder.

    This cog extends the calendar cog.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot client.
    config: :class:`.ReminderConfig`
        The reminder configuration.
    service: :class:`.ReminderService`
        The reminder service.
    handler: :class:`.ReminderHandler`
        The reminder handler.
    calendar: :class:`.CalendarCog`
        The calendar cog.
    """

    bot: UniversityBot
    config: ReminderConfig
    service: ReminderService
    handler: ReminderHandler
    calendar: CalendarCog

    def __init__(self, bot: UniversityBot) -> None:
        self.bot = bot

        calendar = bot.get_cog(CalendarCog.__cog_name__)
        if calendar is None or not isinstance(calendar, CalendarCog):
            raise LoadCogError(self, "Calendar cog not found.")
        self.calendar = calendar

        try:
            self.config = ReminderConfig(**bot.config["reminder"])
        except KeyError as e:
            raise LoadCogError(self, "Reminder configuration not found.") from e
        except ValueError as e:
            raise LoadCogError(self, "Invalid reminder configuration.") from e

        self.service = ReminderService(bot, self.config, self.calendar.service)
        self.handler = ReminderHandler(self.service)

    @Localization.apply_localizations
    @nextcord.slash_command(name="reminder")
    async def _reminder(self, *_) -> None:
        """Placeholder for the reminder command group."""

    @Localization.apply_localizations
    @_reminder.subcommand(
        name="get_configuration",
        description="Get the configuration of the reminder.",
    )
    @catch_interaction_exceptions([ReminderError, ConfigurationError])
    async def _get_configuration(self, interaction: Interaction) -> None:
        await self.handler.get_configuration(interaction)

    @Localization.apply_localizations
    @_reminder.subcommand(
        name="set_configuration",
        description="Set the configuration of the reminder.",
    )
    @catch_interaction_exceptions([ReminderError, ConfigurationError])
    async def _set_configuration(
        self,
        interaction: Interaction,
        attachment: Attachment = SlashOption(
            description="JSON configuration file.",
        ),
    ) -> None:
        await self.handler.set_configuration(interaction, attachment)

    @Localization.apply_localizations
    @_reminder.subcommand(
        name="edit_configuration",
        description="Edit the configuration of the reminder.",
    )
    @catch_interaction_exceptions([ReminderError, ConfigurationError])
    async def _edit_configuration(
        self,
        interaction: Interaction,
        indent: int = SlashOption(
            description="JSON identation level (default {default}).",
            min_value=0,
            max_value=8,
            default=2,
        ),
    ) -> None:
        await self.handler.edit_configuration(interaction, indent)
