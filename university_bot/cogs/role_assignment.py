# SPDX-License-Identifier: MIT
"""A module to define the cog for role assignment."""

from __future__ import annotations

from typing import TYPE_CHECKING

import nextcord
from nextcord import Attachment, SlashOption
from nextcord.ext.commands import Cog
from pydantic import ValidationError

from .. import Interaction, catch_interaction_exceptions
from ..exceptions.configuration_view import ContentTooLongError
from ..exceptions.role_assignment import InvalidConfiguration, RoleAssignmentError
from ..handlers.role_assignment import RoleAssignmentHandler
from ..models.configs.role_assignment import RoleAssignmentConfig
from ..services.role_assignment import RoleAssignmentService
from . import LoadCogError

if TYPE_CHECKING:
    from .. import UniversityBot


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
        self.__cog_name__ = "Role Assignment"
        self.bot = bot

        try:
            self.config = RoleAssignmentConfig(**bot.config["role_assignment"])
        except ValidationError as e:
            raise LoadCogError(self, "Error while loading configuration.") from e

        try:
            self.service = RoleAssignmentService(bot, self.config)
        except InvalidConfiguration as e:
            raise LoadCogError(self, "Error while loading service.") from e

        self.handler = RoleAssignmentHandler(self.service)
        self.bot.loop.create_task(self.service.load_view(self.handler))

    @nextcord.slash_command(name="role_assignment")
    async def _role_assignment(self, *_) -> None:
        """Placeholder for the role_assignment command group."""

    @_role_assignment.subcommand(
        name="send",
        description="Send a new role_assignment message.",
    )
    @catch_interaction_exceptions([RoleAssignmentError])
    async def _send(self, interaction: Interaction, preview: bool = False) -> None:
        await self.handler.send_message(interaction, preview)

    @_role_assignment.subcommand(
        name="get_configuration",
        description="Get the configuration of the role assignment.",
    )
    @catch_interaction_exceptions([RoleAssignmentError])
    async def _get_configuration(self, interaction: Interaction) -> None:
        await self.handler.get_configuration(interaction)

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
