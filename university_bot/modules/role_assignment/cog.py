# SPDX-License-Identifier: MIT
"""A module to define the cog for role assignment."""

from __future__ import annotations

from typing import TYPE_CHECKING

import nextcord
from nextcord import Attachment, SlashOption
from nextcord.ext.commands import Cog
from pydantic import ValidationError

from university_bot import Interaction, Localization, catch_interaction_exceptions
from university_bot.exceptions.cog import LoadCogError
from university_bot.exceptions.configuration_view import ContentTooLongError

from .config import RoleAssignmentConfig
from .exceptions import InvalidConfiguration, RoleAssignmentError
from .handler import RoleAssignmentHandler
from .service import RoleAssignmentService

if TYPE_CHECKING:
    from university_bot import UniversityBot


class RoleAssignmentCog(Cog):
    """A cog for role assignment.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot client.
    config: :class:`.RoleAssignmentConfig`
        The role assignment configuration.
    service: :class:`.RoleAssignmentService`
        The role assignment service.
    handler: :class:`.RoleAssignmentHandler`
        The role assignment handler.
    """

    bot: UniversityBot
    config: RoleAssignmentConfig
    service: RoleAssignmentService
    handler: RoleAssignmentHandler

    def __init__(self, bot: UniversityBot) -> None:
        self.bot = bot

        try:
            self.config = RoleAssignmentConfig(**bot.config["role_assignment"])
        except KeyError as e:
            raise LoadCogError(self, "Role assignment configuration not found.") from e
        except ValidationError as e:
            raise LoadCogError(self, "Invalid role assignment configuration.") from e

        try:
            self.service = RoleAssignmentService(bot, self.config)
        except InvalidConfiguration as e:
            raise LoadCogError(self, "Error while loading service.") from e

        self.handler = RoleAssignmentHandler(self.service)
        self.bot.loop.create_task(self.service.load_view(self.handler))

    @Localization.apply_localizations
    @nextcord.slash_command(name="role_assignment")
    async def _role_assignment(self, *_) -> None:
        """Placeholder for the role_assignment command group."""

    @Localization.apply_localizations
    @_role_assignment.subcommand(
        name="send",
        description="Send a new role_assignment message.",
    )
    @catch_interaction_exceptions([RoleAssignmentError])
    async def _send(self, interaction: Interaction, preview: bool = False) -> None:
        await self.handler.send_message(interaction, preview)

    @Localization.apply_localizations
    @_role_assignment.subcommand(
        name="get_configuration",
        description="Get the configuration of the role assignment.",
    )
    @catch_interaction_exceptions([RoleAssignmentError])
    async def _get_configuration(self, interaction: Interaction) -> None:
        await self.handler.get_configuration(interaction)

    @Localization.apply_localizations
    @_role_assignment.subcommand(
        name="set_configuration",
        description="Set the configuration of the role assignment.",
    )
    @catch_interaction_exceptions([RoleAssignmentError])
    async def _set_configuration(
        self,
        interaction: Interaction,
        attachment: Attachment = SlashOption(
            description="JSON configuration file.",
        ),
    ) -> None:
        await self.handler.set_configuration(interaction, attachment)

    @Localization.apply_localizations
    @_role_assignment.subcommand(
        name="edit_configuration",
        description="Edit the configuration of the role assignment.",
    )
    @catch_interaction_exceptions([RoleAssignmentError, ContentTooLongError])
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


def setup(bot: UniversityBot):
    """Loads the RoleAssignment cog."""
    bot.add_cog(RoleAssignmentCog(bot))
