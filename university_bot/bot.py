# SPDX-License-Identifier: MIT
"""A module containing the main class of the bot.

The :class:`UniversityBot` class is used to initialize the bot.

Examples
--------
```python
from university_bot import UniversityBot

class Cog(commands.Cog):
    def __init__(self, bot: UniversityBot) -> None:
        self.bot = bot

def setup(bot: UniversityBot) -> None:
    bot.add_cog(Cog(bot))
    ```
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import TYPE_CHECKING

import dotenv
import nextcord
from nextcord import TextChannel
from nextcord.ext.commands import Bot, ExtensionError
from nextcord.flags import Intents
from nextcord.guild import Guild
from pydantic_core import ValidationError

from university_bot.utils.config_loader import ConfigLoader

from .models.configs import TemporaryFilesConfig
from .utils.logger import configure_logger

if TYPE_CHECKING:
    from .models.configs import BotConfig

__all__ = ("UniversityBot",)


class UniversityBot(Bot):
    """:class:`commands.Bot` but with custom attributes added.

    Can be used as an alias in the cog class,
    because Discord API sends the :class:`commands.Bot`
    parameter in :func:`setup` in the cog's file.
    """

    _config: BotConfig
    _logger: logging.Logger
    _bot_channel: TextChannel
    _guild: Guild
    _cogs_loaded: bool

    def __init__(self) -> None:
        self._cogs_loaded = False

        try:
            config_loader = ConfigLoader("config.toml")
            self._config = config_loader.load_config()
        except (TypeError, IOError):
            logging.critical("Config file is missing or invalid!", exc_info=True)
            sys.exit(1)

        try:
            self._logger = configure_logger(self._config.basic.logger)
        except ValidationError:
            logging.critical("Basic logger config is invalid!", exc_info=True)
            raise

        if self.config.basic.temporary_files.clear_on_startup:
            self.config.basic.temporary_files.clear()

        super().__init__(
            intents=Intents.all(),
            case_insensitive=True,
            default_guild_ids=[self.config.basic.guild_id],
        )

    async def on_connect(self) -> None:
        await self._set_guild()
        await self.wait_until_ready()
        await self._set_bot_channel()
        await self._load_cogs()
        await self.sync_all_application_commands()

    @property
    def config(self) -> BotConfig:
        """Returns the bot configuration."""
        return self._config

    @property
    def temporary_files_config(self) -> TemporaryFilesConfig:
        """Returns the temporary files configuration."""
        return self.config.basic.temporary_files

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
        channel_id = self.config.basic.bot_channel_id
        channel = self._guild.get_channel(channel_id)

        if not isinstance(channel, TextChannel):
            self._logger.critical(
                "Bot channel (id=%s) not found!",
                channel_id,
                exc_info=True,
            )
            sys.exit(1)

        self._bot_channel = channel
        setattr(self, "bot_channel", channel)

        self._logger.debug("Set bot channel to bot instance")

    async def _set_guild(self) -> None:
        guild_id = self.config.basic.guild_id
        if (guild := self.get_guild(guild_id)) is None:
            self._logger.critical("Guild %s not found!", guild_id)
            sys.exit(1)

        self._guild = guild
        setattr(self, "guild", guild)

        self._logger.debug("Set guild to bot instance")

    async def _load_cogs(self) -> None:
        if self._cogs_loaded:
            return

        self._logger.info("Loading cogs.")

        for cog_filename in os.listdir("university_bot/cogs"):
            if not cog_filename.endswith(".py"):
                continue

            if cog_filename == "__init__.py":
                continue

            cog_name = cog_filename[:-3]
            cog_config = getattr(self.config, cog_name, None)

            if cog_config is None:
                self._logger.warning(
                    "Config for '%s' cog is missing, skipping.", cog_name
                )
                continue

            if (enabled := getattr(cog_config, "enabled", None)) is None:
                self._logger.warning(
                    "`enabled` key for `%s` cog is missing, loading anyway.",
                    cog_name,
                )

            if enabled:
                self.load_cog(f"university_bot.cogs.{cog_name}", cog_name)

        self._logger.info("Cogs loaded.")
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
            ExtensionError,
            ModuleNotFoundError,
            nextcord.errors.HTTPException,
        ) as e:
            if isinstance(e, ExtensionError):
                if isinstance(e.__cause__, ValidationError):
                    e = e.__cause__

            self._logger.error(
                "Cog '%s' couldn't be loaded! %s",
                display_name or name,
                e.__cause__ if isinstance(e, ExtensionError) else e,
                exc_info=True,
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
            ExtensionError,
            ModuleNotFoundError,
            nextcord.errors.HTTPException,
        ) as e:
            self._logger.error(
                "Cog '%s' couldn't be unloaded! %s",
                display_name or name,
                e.__cause__ if isinstance(e, ExtensionError) else e,
                exc_info=True,
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
            ExtensionError,
            ModuleNotFoundError,
            nextcord.errors.HTTPException,
        ) as e:
            self._logger.error(
                "Cog '%s' couldn't be reloaded! %s",
                cog_name,
                e.__cause__ if isinstance(e, ExtensionError) else e,
                exc_info=True,
            )
            return False

    def main(self) -> None:
        """Runs the bot using `BOT_TOKEN` received from `.env` file."""
        dotenv.load_dotenv()
        token = os.environ.get("BOT_TOKEN")

        if token is None:
            self._logger.critical("BOT_TOKEN in .env file is missing!")
            sys.exit(1)

        try:
            self.run(token)
        finally:
            if self.temporary_files_config.clear_on_shutdown:
                self.temporary_files_config.clear()
            self._logger.info("Bot has been stopped!")
