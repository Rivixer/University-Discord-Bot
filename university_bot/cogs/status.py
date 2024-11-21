# SPDX-License-Identifier: MIT
"""A module to control the bot's status.

This module contains a cog to control the bot's status. The bot's status can be
changed using the `/status` command. The status is saved to a JSON file so that
it can be restored when the bot restarts. The status can be set to one of the
following types: playing, listening, watching, streaming, competing, custom or unknown.

Setting the status to "custom" will display the text as the status. The status
can be reset by setting the type to "unknown".
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import (
    CustomActivity,
    ActivityType,
    Activity,
    SlashOption,
    DiscordException,
    Interaction,
)
from discord.ext import commands
from pydantic import BaseModel, field_validator

from university_bot.console import Console
from university_bot.utils import InteractionUtils

if TYPE_CHECKING:
    from discord import BaseActivity
    from university_bot import UniversityBot


class Config(BaseModel):
    """A class for the configuration of the bot's status."""

    data_filepath: Path

    @field_validator("data_filepath", mode="before")
    @classmethod
    def _validate_data_filepath(cls, value: str | Path) -> Path:
        path = Path(value) if not isinstance(value, Path) else value

        if path.name == ".json":
            raise ValueError(
                "The path cannot point to a directory "
                "or a file ambiguously named '.json'."
            )
        if (suffix := path.suffix) != ".json":
            raise ValueError(f"The file must have a .json extension. Found: {suffix}")
        if not path.parent.exists():
            raise ValueError(f"The parent directory {path.parent} does not exist.")
        if not os.access(path.parent, os.W_OK):
            raise ValueError(f"The parent directory {path.parent} is not writable.")

        return path


class StatusCog(commands.Cog):
    """A cog to control the bot's status."""

    __slots__ = (
        "bot",
        "config",
    )

    bot: UniversityBot
    config: Config

    def __init__(self, bot: UniversityBot) -> None:
        self.bot = bot
        self.config = Config(data_filepath=bot.config["status"]["data_filepath"])
        self.bot.loop.create_task(self._initialize_status())

    @discord.slash_command(
        name="status",
        description="Change the bot's status.",
        dm_permission=False,
    )
    @InteractionUtils.with_info(
        before="Setting status: {activity_type} **{text}**...",
        after="Status has been set to: {activity_type} **{text}**",
        catch_exceptions=[DiscordException],
    )
    @InteractionUtils.with_log()
    async def change_status(
        self,
        interaction: Interaction,  # pylint: disable=unused-argument
        text: str,
        activity_type: str = SlashOption(
            choices=[at.name.title() for at in ActivityType]
        ),
    ) -> None:
        """Changes the bot's status.

        Parameters
        ----------
        interaction : :class:`Interaction`
            The interaction that triggered the command.
        text : :class:`str`
            The text to display in the status.
        activity_type : :class:`str`
            The type of activity (e.g., playing, listening, watching, streaming).
        """
        await self._set_activity(activity_type, text)

    async def _initialize_status(self) -> None:
        activity_type, text = self._load_status_from_file()
        if activity_type and text:
            await self._set_activity(activity_type, text)

    def _get_activity(self, activity_type: str, text: str) -> BaseActivity:
        if activity_type.lower() == "custom":
            return CustomActivity(name=text)
        return Activity(type=ActivityType[activity_type.lower()], name=text)

    async def _set_activity(self, activity_type: str, text: str) -> None:
        try:
            activity = self._get_activity(activity_type, text)
            await self.bot.change_presence(activity=activity)
            self._save_status_to_file(activity_type, text)
        except (DiscordException, TypeError) as e:
            Console.error(f"Failed to set bot's status: {e}")

    def _load_status_from_file(self) -> tuple[str | None, str | None]:
        try:
            with self.config.data_filepath.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return data["activity_type"], data["text"]
        except (OSError, ValueError) as e:
            Console.warn(f"Failed to load the status configuration: {e}")
        return None, None

    def _save_status_to_file(self, activity_type: str, text: str) -> None:
        """Writes the bot's status to the configuration file."""
        try:
            with self.config.data_filepath.open("w", encoding="utf-8") as file:
                json.dump(
                    {"activity_type": activity_type, "text": text},
                    file,
                    indent=4,
                    ensure_ascii=False,
                )
        except OSError as e:
            Console.error(f"Failed to write configuration file: {e}")


def setup(bot: UniversityBot):
    """Loads the StatusCog cog."""
    bot.add_cog(StatusCog(bot))
