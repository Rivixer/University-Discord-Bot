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
import sys
import time
from typing import Any

import dotenv
import nextcord
import toml
from nextcord.channel import TextChannel
from nextcord.ext import commands
from nextcord.flags import Intents
from nextcord.guild import Guild
from pydantic import BaseModel, ValidationError

from university_bot.logger import BasicLoggerConfig, configure_logger


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
        "_logger",
        "_bot_channel",
        "_guild",
    )

    _basic_config: _BasicConfig
    _config: dict[str, Any]
    _logger: logging.Logger
    _bot_channel: TextChannel
    _guild: Guild

    def __init__(self) -> None:
        self._cogs_loaded = False

        try:
            self._config = toml.load("config.toml")
        except (TypeError, IOError):
            print("Config file is missing or invalid!")
            raise

        try:
            basic_logger_config = BasicLoggerConfig(**self._config["logger"])
        except ValidationError:
            print("Basic logger config is invalid!")
            raise

        self._logger = configure_logger(basic_logger_config)

        try:
            self._basic_config = _BasicConfig(**self._config["basic"])
        except ValidationError as e:
            self._logger.critical("Basic config is invalid!", exc_info=e)
            raise

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
            self._logger.critical("Bot channel not found!")
            sys.exit(1)
        self._bot_channel = channel
        setattr(self, "bot_channel", channel)
        self._logger.debug("Set bot channel to bot instance")

    async def _set_guild(self) -> None:
        if (guild := self.get_guild(self._basic_config.guild_id)) is None:
            self._logger.critical("Guild not found!")
            sys.exit(1)
        self._guild = guild
        setattr(self, "guild", guild)
        self._logger.debug("Set guild to bot instance")

    async def _load_cogs(self) -> None:
        if self._cogs_loaded:
            return

        self._logger.info("Loading cogs...")

        for cog_filename in os.listdir("university_bot/cogs"):
            if not cog_filename.endswith(".py"):
                continue

            cog_name = cog_filename[:-3]
            cog_config = self.config.get(cog_name)

            if cog_config is None:
                self._logger.warning(
                    "Config for '%s' cog is missing, skipping...", cog_name
                )
                continue

            if (is_enabled := cog_config.get("is_enabled")) is None:
                self._logger.warning(
                    "`is_enabled` key for `%s` cog is missing, loading anyway...",
                    cog_name,
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
            self._logger.info(
                "Cog '%s' has been loaded! (%.2fms)", display_name or name, load_time
            )
            return True
        except (
            commands.ExtensionError,
            ModuleNotFoundError,
            nextcord.errors.HTTPException,
        ) as e:
            if isinstance(e, commands.ExtensionError):
                if isinstance(e.__cause__, ValidationError):
                    e = e.__cause__

            self._logger.error(
                "Cog '%s' couldn't be loaded!", display_name or name, exc_info=e
            )

            return False

    def unload_cog(self, name: str, display_name: str | None = None) -> bool:
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
            self._logger.info(
                "Cog '%s' has been unloaded! (%.2fms)", display_name or name, load_time
            )
            return True
        except (
            commands.ExtensionError,
            ModuleNotFoundError,
            nextcord.errors.HTTPException,
        ) as e:
            self._logger.error(
                "Cog '%s' couldn't be unloaded!", display_name or name, exc_info=e
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
            self._logger.info(
                "Cog '%s' has been reloaded! (%.2fms)", cog_name, load_time
            )
            return True
        except (
            commands.ExtensionError,
            ModuleNotFoundError,
            nextcord.errors.HTTPException,
        ) as e:
            self._logger.error("Cog '%s' couldn't be reloaded!", cog_name, exc_info=e)
            return False

    def main(self) -> None:
        """Runs the bot using `BOT_TOKEN` received from `.env` file."""
        dotenv.load_dotenv()
        token = os.environ.get("BOT_TOKEN")
        self.run(token)
