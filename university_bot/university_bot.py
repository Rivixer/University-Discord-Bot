# SPDX-License-Identifier: MIT
"""A module containing the main class of the bot.

The :class:`UniversityBot` class is used to initialize the bot.

Examples
-------- ::

    from university_bot import UniversityBot

    class Cog(commands.Cog):
        def __init__(self, bot: UniversityBot) -> None:
            self.bot = bot

    def setup(bot: UniversityBot) -> None:
        bot.add_cog(Cog(bot))
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import dotenv
import nextcord
from pydantic import BaseModel, ValidationError
import toml
from nextcord.channel import TextChannel
from nextcord.ext import commands
from nextcord.flags import Intents
from nextcord.guild import Guild

from university_bot.console import Console


class _BasicConfig(BaseModel):
    """A class for the basic configuration of the bot."""

    guild_id: int
    admin_role_id: int
    bot_channel_id: int


class UniversityBot(commands.Bot):
    """:class:`commands.Bot` but with custom commands added.

    Can be used as an alias in the cog class,
    because Discord API sends the :class:`commands.Bot`
    parameter in :func:`setup` in the cog's file.
    """

    __slots__ = (
        "_basic_config",
        "_config",
        "_bot_channel",
        "_guild",
    )

    _basic_config: _BasicConfig
    _config: dict
    _bot_channel: TextChannel
    _guild: Guild

    def __init__(self) -> None:
        self._cogs_loaded = False

        try:
            self._config = toml.load("config.toml")
        except (TypeError, IOError) as e:
            Console.critical_error("Config file is missing or invalid!", exception=e)

        try:
            self._basic_config = _BasicConfig(**self._config["basic"])
        except ValidationError as e:
            Console.critical_error("Basic config is invalid!", exception=e)

        super().__init__(
            intents=Intents.all(),
            case_insensitive=True,
        )

    async def on_connect(self) -> None:
        await self._set_guild()
        await self.wait_until_ready()
        await self._set_bot_channel()
        await self._load_cogs()
        await self.sync_all_application_commands()

    @property
    def config(self) -> dict[str, Any]:
        """Returns the bot configuration from the `config.toml` file."""
        return self._config

    @property
    def guild(self) -> Guild:
        """Returns the guild the bot is in."""
        return self._guild

    @guild.setter
    def guild(self, guild: Guild) -> None:
        self._guild = guild

    @property
    def bot_channel(self) -> TextChannel:
        """Returns the bot channel."""
        return self._bot_channel

    @bot_channel.setter
    def bot_channel(self, channel: TextChannel) -> None:
        self._bot_channel = channel

    async def _set_bot_channel(self) -> None:
        channel = self._guild.get_channel(self._basic_config.bot_channel_id)
        if not isinstance(channel, TextChannel):
            Console.critical_error("Bot channel not found!")
        self._bot_channel = channel
        setattr(self, "bot_channel", channel)
        logging.debug("Set bot channel to bot instance")

    async def _set_guild(self) -> None:
        if (guild := self.get_guild(self._basic_config.guild_id)) is None:
            Console.critical_error("Guild not found!")
        self._guild = guild
        setattr(self, "guild", guild)
        logging.debug("Set guild to bot instance")

    async def _load_cogs(self) -> None:
        if self._cogs_loaded:
            return

        logging.info("Loading cogs...")

        for cog_filename in os.listdir("university_bot/cogs"):
            if not cog_filename.endswith(".py"):
                continue

            cog_name = cog_filename[:-3]
            cog_config = self.config.get(cog_name)

            if cog_config is None:
                Console.warn(f"Config for `{cog_name}` cog is missing, skipping...")
                continue

            if (is_enabled := cog_config.get("is_enabled")) is None:
                Console.warn(
                    f"`is_enabled` key for `{cog_name}` cog is missing, "
                    "loading anyway..."
                )

            if is_enabled:
                self.load_cog(f"university_bot.cogs.{cog_name}", cog_name)

        logging.info("Cogs loaded")
        self._cogs_loaded = True

    def load_cog(self, name: str, display_name: str | None = None) -> bool:
        """Loads the cog.

        Parameters
        ----------
        display_name : str
            The name of the cog to display.
            If not provided, the name will be used.

        Returns
        -------
        bool
            Whether the cog has been loaded successfully.
        """
        start_time = time.time()

        try:
            self.load_extension(name)
            load_time = (time.time() - start_time) * 1000
            Console.info(
                f"Cog '{display_name or name}' has been loaded! ({load_time:.2f}ms)"
            )
            return True
        except (
            commands.ExtensionError,
            ModuleNotFoundError,
            nextcord.errors.HTTPException,
        ) as e:
            Console.important_error(
                f"Cog '{display_name or name}' couldn't be loaded!", exception=e
            )
            return False

    def unload_cog(self, name: str, display_name: str | None) -> bool:
        """Unloads the cog.

        Parameters
        ----------
        name : str
            The name of the cog to unload.
        display_name : str
            The name of the cog to display.
            If not provided, the name will be used.

        Returns
        -------
        bool
            Whether the cog has been unloaded successfully.
        """
        start_time = time.time()

        try:
            self.unload_extension(name)
            load_time = (time.time() - start_time) * 1000
            Console.info(
                f"Cog '{display_name or name}' has been unloaded! ({load_time:.2f}ms)"
            )
            return True
        except (
            commands.ExtensionError,
            ModuleNotFoundError,
            nextcord.errors.HTTPException,
        ) as e:
            Console.important_error(
                f"Cog '{display_name or name}' couldn't be unloaded!", exception=e
            )
            return False

    def reload_cog(self, cog_name: str) -> bool:
        """Reloads the cog.

        Parameters
        ----------
        cog_name : str
            The name of the cog to reload.

        Returns
        -------
        bool
            Whether the cog has been reloaded successfully.
        """
        start_time = time.time()

        try:
            self.reload_extension(cog_name)
            load_time = (time.time() - start_time) * 1000
            Console.info(f"Cog '{cog_name}' has been reloaded! ({load_time:.2f}ms)")
            return True
        except (
            commands.ExtensionError,
            ModuleNotFoundError,
            nextcord.errors.HTTPException,
        ) as e:
            Console.important_error(
                f"Cog '{cog_name}' couldn't be reloaded!", exception=e
            )
            return False

    def main(self) -> None:
        """Runs the bot using `BOT_TOKEN` received from `.env` file."""
        dotenv.load_dotenv()
        token = os.environ.get("BOT_TOKEN")
        self.run(token)
