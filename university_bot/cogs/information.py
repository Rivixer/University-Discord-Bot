# SPDX-License-Identifier: MIT
"""A module to control the information embed.

The information embed is used to display important information.

The information embed is sent to the channel
where the command `/information send` was used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import nextcord
from nextcord.application_command import SlashOption
from nextcord.channel import TextChannel
from nextcord.errors import DiscordException
from nextcord.ext import commands
from nextcord.interactions import Interaction
from nextcord.message import Attachment

from university_bot.errors import UpdateEmbedError
from university_bot.models import ControllerWithEmbed, EmbedModel, Model
from university_bot.utils import InteractionUtils

if TYPE_CHECKING:
    from university_bot import UniversityBot


class InformationCog(commands.Cog):
    """A cog to control the information embed."""

    __slots__ = (
        "_bot",
        "_ctrl",
    )

    _bot: UniversityBot
    _ctrl: InformationController

    def __init__(self, bot: UniversityBot) -> None:
        """Initialize the cog."""
        self._bot = bot
        model = InformationModel()
        embed_model = InformationEmbedModel(model, bot)
        self._ctrl = InformationController(model, embed_model)

    @nextcord.slash_command(
        name="information",
        description="The information embed.",
    )
    async def _information(self, *_) -> None:
        """The information embed.

        This command is a placeholder for the subcommands.
        """

    @_information.subcommand(
        name="send",
        description="Send a new information embed.",
    )
    @InteractionUtils.with_info(
        before="Sending information embed...",
        after="The information embed has been sent.",
        catch_exceptions=[DiscordException],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _send(self, interaction: Interaction) -> None:
        """Sends a new information embed.

        The information embed is sent to the channel where the command was used.
        """

        channel = interaction.channel
        if isinstance(channel, TextChannel):
            await self._ctrl.send_embed(channel)

    @_information.subcommand(
        name="update",
        description="Update the information embed.",
    )
    @InteractionUtils.with_info(
        before="Updating information embed...",
        after="The information embed has been updated.",
        catch_exceptions=[UpdateEmbedError],
    )
    @InteractionUtils.with_log()
    async def _update(
        self, interaction: Interaction  # pylint: disable=unused-argument
    ) -> None:
        """Updates the information embed.

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

    @_information.subcommand(
        name="get_json",
        description="Get the information embed json.",
    )
    @InteractionUtils.with_info(
        before="Getting information embed json...",
        catch_exceptions=[DiscordException],
    )
    @InteractionUtils.with_log()
    async def _get_json(self, interaction: Interaction) -> None:
        """Gets the json file representing the information embed.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        """
        msg = await interaction.original_message()
        await msg.edit(content=None, file=self._ctrl.embed_json)

    @_information.subcommand(
        name="set_json",
        description="Set the information embed json and update the embed.",
    )
    @InteractionUtils.with_info(
        before="Setting information embed json and updating the embed...",
        after="The information embed and json file have been updated.",
        catch_exceptions=[TypeError, DiscordException, UpdateEmbedError],
    )
    @InteractionUtils.with_log()
    async def _set_json(
        self,
        interaction: Interaction,  # pylint: disable=unused-argument
        file: Attachment = SlashOption(
            description="JSON file "
            "downloaded from `/information get_json` and updated"
        ),
    ) -> None:
        """Sets the json file representing the information embed.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        file: :class:`Attachment`
            The json file downloaded from `/information get_json` and updated.

        Raises
        ------
        UpdateEmbedError
            The embed could not be updated.
        """
        await self._ctrl.set_embed_json(file)
        await self._ctrl.update_embed()


class InformationModel(Model):
    """Represents the information model.

    Notes
    -----
    The information model is a singleton.
    """


class InformationEmbedModel(EmbedModel):
    """Represents the information embed model.

    Notes
    -----
    The information model is a singleton.
    """


class InformationController(ControllerWithEmbed):
    """Represents the information controller.

    Notes
    -----
    The information model is a singleton.
    """


def setup(bot: UniversityBot):
    """Loads the InformationCog cog."""
    bot.add_cog(InformationCog(bot))
