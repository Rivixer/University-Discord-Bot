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
```
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

import dotenv
import nextcord
from nextcord import TextChannel
from nextcord.ext.commands import Bot, Cog, ExtensionError
from nextcord.flags import Intents
from nextcord.guild import Guild
from pydantic_core import ValidationError

from university_bot.exceptions.cog import LoadCogError
from university_bot.mixins.cog import SetupMixin
from university_bot.utils.cogs import ENTRY_COG_ATTR, LOAD_AFTER_ATTR
from university_bot.utils.exceptions import format_exception_chain
from university_bot.utils.localization import Localization

from .config import BasicConfig, ConfigLoader
from .database import DatabaseConfig, DatabaseController
from .utils.logger import configure_logger

if TYPE_CHECKING:
    from .config import BotConfig, TemporaryFilesConfig


__all__ = ("UniversityBot",)


class UniversityBot(Bot):
    """:class:`commands.Bot` but with custom attributes added.

    Can be used as an alias in the cog class,
    because Discord API sends the :class:`commands.Bot`
    parameter in :func:`setup` in the cog's file.
    """

    _config: BotConfig
    _database_config: DatabaseConfig
    _logger: logging.Logger
    _bot_channel: TextChannel
    _guild: Guild
    _cogs_loaded: bool
    _database: DatabaseController

    def __init__(self) -> None:
        self._cogs_loaded = False

        try:
            config_loader = ConfigLoader("config.toml")
            self._config = config_loader.load_config()
        except (TypeError, IOError):
            logging.critical("Config file is missing or invalid!", exc_info=True)
            sys.exit(1)

        try:
            self._logger = configure_logger(self._basic_config.logger)
        except ValidationError:
            logging.critical("Logger config is invalid!", exc_info=True)
            raise

        if self.temporary_files_config.clear_on_startup:
            self.temporary_files_config.clear()

        Localization.load(self._basic_config.localization)

        self._database = DatabaseController(self._config.database)

        super().__init__(
            intents=Intents.all(),
            case_insensitive=True,
            default_guild_ids=[self._basic_config.guild_id],
        )

    async def on_connect(self) -> None:
        try:
            await self._database.connect()
        except RuntimeError:
            self._logger.critical("Database connection failed!", exc_info=True)
            sys.exit(1)

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
    def _basic_config(self) -> BasicConfig:
        """Returns the basic configuration."""
        return self.config.basic

    @property
    def temporary_files_config(self) -> TemporaryFilesConfig:
        """Returns the temporary files configuration."""
        return self._basic_config.temporary_files

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

    @property
    def database(self) -> DatabaseController:
        """The database controller instance."""
        return self._database

    async def _set_bot_channel(self) -> None:
        channel_id = self._basic_config.bot_channel_id
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
        guild_id = self._basic_config.guild_id
        if (guild := self.get_guild(guild_id)) is None:
            self._logger.critical("Guild %s not found!", guild_id)
            sys.exit(1)

        self._guild = guild
        setattr(self, "guild", guild)

        self._logger.debug("Set guild to bot instance")

    async def _load_cogs(self) -> None:
        if self._cogs_loaded:
            self._logger.warning("Cogs have already been loaded.")
            return

        self._logger.info("Loading cogs...")

        modules_path = Path("university_bot/modules")
        if not modules_path.exists():
            self._logger.error("Modules path does not exist: %s", modules_path)
            return

        # TODO: Refactor
        cogs_to_load: dict[type[Cog], list[type[Cog]]] = {}
        for module_name in os.listdir(modules_path):
            module_path = modules_path / module_name

            if module_name.startswith("_") or not module_path.is_dir():
                continue

            cog_file = module_path / "cog.py"

            if not cog_file.is_file():
                self._logger.warning(
                    "Cog file for module '%s' is missing, skipping.", module_name
                )
                continue

            cog_config = self.config.get(module_name)
            if not cog_config:
                self._logger.warning(
                    "Config for cog '%s' is missing, skipping.", module_name
                )
                continue

            enabled = cog_config.get("enabled", True)
            if not enabled:
                self._logger.info(
                    "Cog '%s' is disabled in configuration, skipping.", module_name
                )
                continue

            cog_import_path = f"university_bot.modules.{module_name}.cog"

            module = importlib.import_module(cog_import_path)
            cog_classes = [
                cls
                for cls in vars(module).values()
                if inspect.isclass(cls) and issubclass(cls, Cog) and cls is not Cog
            ]

            cog_class = (
                [cls for cls in cog_classes if getattr(cls, ENTRY_COG_ATTR, False)]
                or cog_classes
                or [None]
            )[0]

            if cog_class is None:
                self._logger.error(
                    "Cog '%s' couldn't be loaded! Cog class not found.",
                    module_name,
                )
                continue

            cogs_to_load[cog_class] = getattr(cog_class, LOAD_AFTER_ATTR, [])

        if not cogs_to_load:
            self._logger.info("No cogs to load.")
            self._cogs_loaded = True
            return

        sorted_cogs = self._sort_cogs_by_dependencies(cogs_to_load)

        for cog_cls in sorted_cogs:
            await self.load_cog(cog_cls)

        # TODO: Remove after refactoring
        path = Path("university_bot/cogs")
        if not path.exists():
            self._logger.error("Old cogs path does not exist: %s", path)
            return

        self._logger.info("Loading old cogs...")
        for file in os.listdir(path):
            if file.endswith(".py") and not file.startswith("_"):
                try:
                    self.load_extension(f"university_bot.cogs.{file[:-3]}")
                except Exception as e:
                    self._logger.error(f"Failed to load cog {file}: {e}")
                else:
                    self._logger.info(f"Cog {file} loaded.")

        self._logger.info("Cogs loaded.")
        self._cogs_loaded = True

    async def load_cog(self, cog_cls: type[Cog]) -> bool:
        """Loads the cog.

        Parameters
        ----------
        display_name: :class:`str`
            The name of the cog to display.
            If not provided, the name will be used.

        Returns
        -------
        :class:`bool`
            Whether the cog has been loaded successfully.
        """
        start_time = time.time()

        try:
            cog = cog_cls(self)

            if isinstance(cog, SetupMixin):
                await cog.setup(self)

            self.add_cog(cog)

            load_time = (time.time() - start_time) * 1000
            self._logger.info(
                "Cog '%s' has been loaded! (%.2fms)", cog.__cog_name__, load_time
            )
            return True
        except (
            ImportError,
            TypeError,
            AttributeError,
            RuntimeError,
            LoadCogError,
            nextcord.DiscordException,
        ) as e:
            self._logger.error(
                "Cog '%s' couldn't be loaded! %s",
                cog_cls.__cog_name__,
                format_exception_chain(e, sep="\n"),
                exc_info=True,
            )
            return False

    def _sort_cogs_by_dependencies(
        self, cogs: dict[type[Cog], list[type[Cog]]]
    ) -> list[type[Cog]]:
        sorted_list: list[type[Cog]] = []

        in_degree = {cog: 0 for cog in cogs}
        dependents: dict[type[Cog], set[type[Cog]]] = {cog: set() for cog in cogs}

        for cog, deps in cogs.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[cog] += 1
                    dependents[dep].add(cog)

        queue = deque([cog for cog, degree in in_degree.items() if degree == 0])

        while queue:
            current = queue.popleft()
            sorted_list.append(current)

            for dependent in dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(sorted_list) != len(cogs):
            raise RuntimeError("Cyclic dependencies detected!")

        return sorted_list

    def unload_cog(self, name: str, display_name: str | None = None) -> bool:
        """Unloads the cog.

        Parameters
        ----------
        name: :class:`str`
            The name of the cog to unload.
        display_name: :class:`str`
            The name of the cog to display.
            If not provided, the name will be used.

        Returns
        -------
        :class:`bool`
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
        cog_name: :class:`str`
            The name of the cog to reload.

        Returns
        -------
        :class:`bool`
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
