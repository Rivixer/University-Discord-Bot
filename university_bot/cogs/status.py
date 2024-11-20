# SPDX-License-Identifier: MIT
"""A module to control the bot's status."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import nextcord
from nextcord.activity import Activity
from nextcord.application_command import SlashOption
from nextcord.enums import ActivityType
from nextcord.errors import DiscordException
from nextcord.ext import commands
from nextcord.interactions import Interaction

from university_bot.console import Console
from university_bot.utils import InteractionUtils

if TYPE_CHECKING:
    from university_bot import UniversityBot


class StatusCog(commands.Cog):
    """A cog to control the bot's status."""

    __slots__ = ("_bot",)

    _STATUS_PATH = Path("data/status.txt")
    _bot: UniversityBot

    def __init__(self, bot: UniversityBot) -> None:
        self._bot = bot

    @commands.Cog.listener(name="on_ready")
    async def _on_ready(self) -> None:
        """Sets the status when the bot is ready."""
        activity_type, text = self._get_data_from_file()
        await self._set_status(activity_type, text)

    @nextcord.slash_command(
        name="status", description="Change bot status", dm_permission=False
    )
    @InteractionUtils.with_info(
        before="Changing status...",
        after="Status has been changed to: **{activity_type} *{text}***",
        catch_exceptions=[DiscordException],
    )
    @InteractionUtils.with_log()
    async def _status(
        self,
        interaction: Interaction,  # pylint: disable=unused-argument
        text: str,
        activity_type: str = SlashOption(
            choices=[
                ActivityType.playing.name,
                ActivityType.listening.name,
                ActivityType.watching.name,
                ActivityType.streaming.name,
            ],
        ),
    ) -> None:
        """Changes the bot's status.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        text: :class:`str`
            The text to display in the status.
        activity_type: :class:`str`
            The type of the activity. Can be one of the following:
            - playing
            - listening
            - watching
            - streaming
        """
        await self._set_status(ActivityType[activity_type], text)

    def _get_data_from_file(self) -> tuple[ActivityType, str]:
        try:
            with open(self._STATUS_PATH, "r", encoding="utf-8") as f:
                lines = list(map(str.strip, f.readlines()))
            return (ActivityType[lines[0]], lines[1].strip())
        except (OSError, nextcord.DiscordException, KeyError) as e:
            Console.warn(
                "Status could not be loaded. The default status has been set.",
                exception=e,
            )
            return (ActivityType.playing, "zarządzenie serwerem")

    def _save_data_to_file(self, activity_type: ActivityType, text: str) -> None:
        try:
            with open(self._STATUS_PATH, "w", encoding="utf-8") as f:
                f.write(f"{activity_type.name}\n{text}")
        except OSError as e:
            Console.error("Error while saving the status.", exception=e)

    async def _set_status(self, activity_type: ActivityType, text: str) -> None:
        activity = Activity(name=text, type=activity_type)
        await self._bot.change_presence(activity=activity)
        self._save_data_to_file(activity_type, text)


def setup(bot: UniversityBot):
    """Loads the StatusCog cog."""
    bot.add_cog(StatusCog(bot))
