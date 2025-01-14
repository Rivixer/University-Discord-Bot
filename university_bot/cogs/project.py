# SPDX-License-Identifier: MIT
"""A module to control the project embed.

The project embed is used to display information about the project.

The project embed is sent to the channel
where the command `/project send` was used.

The project embed is updated when the bot is started.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import nextcord
from nextcord.application_command import SlashOption
from nextcord.channel import TextChannel
from nextcord.errors import DiscordException
from nextcord.ext import commands, tasks
from nextcord.interactions import Interaction
from nextcord.message import Attachment

import university_bot
from university_bot.console import Console
from university_bot.errors import UpdateEmbedError
from university_bot.models import ControllerWithEmbed, EmbedModel, Model
from university_bot.utils import InteractionUtils, ProjectUtils

if TYPE_CHECKING:
    from nextcord.embeds import Embed

    from university_bot import UniversityBot


class ProjectCog(commands.Cog):
    """A cog to control the project embed."""

    __slots__ = (
        "_bot",
        "_ctrl",
    )

    _bot: UniversityBot
    _ctrl: ProjectController

    def __init__(self, bot: UniversityBot) -> None:
        """Initialize the cog."""
        self._bot = bot
        model = ProjectModel()
        embed_model = ProjectEmbedModel(model, bot)
        self._ctrl = ProjectController(model, embed_model)
        self._update_embed.start()  # pylint: disable=no-member

    @nextcord.slash_command(
        name="project",
        description="The project embed.",
    )
    async def _project(self, *_) -> None:
        """The project embed.

        This command is a placeholder for the subcommands.
        """

    @_project.subcommand(
        name="send",
        description="Send a new project embed.",
    )
    @InteractionUtils.with_info(
        before="Sending project embed...",
        after="The project embed has been sent.",
        catch_exceptions=[DiscordException],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _send(self, interaction: Interaction) -> None:
        """Sends a new project embed.

        The project embed is sent to the channel where the command was used.


        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        """
        channel = interaction.channel
        if isinstance(channel, TextChannel):
            await self._ctrl.send_embed(channel)

    @_project.subcommand(
        name="update",
        description="Update the project embed.",
    )
    @InteractionUtils.with_info(
        before="Updating project embed...",
        after="The project embed has been updated.",
        catch_exceptions=[UpdateEmbedError],
    )
    @InteractionUtils.with_log()
    async def _update(
        self, interaction: Interaction  # pylint: disable=unused-argument
    ) -> None:
        """Updates the project embed.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.

        Raises
        ------
        UpdateEmbedError
            The embed could not be updated.
        """
        await self._ctrl.update_embed()

    @_project.subcommand(
        name="get_json",
        description="Get the project embed json.",
    )
    @InteractionUtils.with_info(
        before="Getting project embed json...",
        catch_exceptions=[DiscordException],
    )
    @InteractionUtils.with_log()
    async def _get_json(self, interaction: Interaction) -> None:
        """Gets the json file representing the project embed.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        """
        msg = await interaction.original_message()
        await msg.edit(file=self._ctrl.embed_json)

    @_project.subcommand(
        name="set_json",
        description="Set the project embed json and update the embed.",
    )
    @InteractionUtils.with_info(
        before="Setting project embed json and updating the embed...",
        after="The project embed and json file have been updated.",
        catch_exceptions=[TypeError, DiscordException, UpdateEmbedError],
    )
    @InteractionUtils.with_log()
    async def _set_json(
        self,
        interaction: Interaction,  # pylint: disable=unused-argument
        file: Attachment = SlashOption(
            description="JSON file " "downloaded from `/project get_json` and updated"
        ),
    ) -> None:
        """Sets the json file representing the project embed.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        file: :class:`Attachment`
            The json file downloaded from `/project get_json` and updated.
        """
        await self._ctrl.set_embed_json(file)
        await self._ctrl.update_embed()

    @tasks.loop(count=1)
    async def _update_embed(self) -> None:
        """Updates the project embed.

        This task is run once when the bot is started.

        If the embed cannot be updated, a warning is logged.
        """
        await self._bot.wait_until_ready()
        try:
            await self._ctrl.update_embed()
        except UpdateEmbedError as e:
            Console.warn("Updating the project embed failed.", exception=e)


class ProjectModel(Model):
    """Represents the project model."""


class ProjectEmbedModel(EmbedModel):
    """Represents the project embed model."""

    def generate_embed(self, **_) -> Embed:
        lines_of_code = ProjectUtils.lines_of_code()

        if 2 <= lines_of_code % 10 <= 4 and not 12 <= lines_of_code % 100 <= 14:
            lines_of_code_text = "linijki kodu"
        else:
            lines_of_code_text = "linijek kodu"

        return super().generate_embed(
            LINES_OF_CODE=f"{lines_of_code} {lines_of_code_text}",
            VERSION=university_bot.__version__,
        )


class ProjectController(ControllerWithEmbed):
    """Represents the project controller."""


def setup(bot: UniversityBot):
    """Loads the ProjectCog cog."""
    bot.add_cog(ProjectCog(bot))
