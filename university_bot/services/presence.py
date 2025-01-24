# SPDX-License-Identifier: MIT
"""A service to manage the presence module."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from nextcord import Activity, ActivityType, CustomActivity, Status
from pydantic import ValidationError

from .. import get_logger
from ..exceptions.presence import InvalidPresenceData, PresenceDataSaveFailed
from ..models.configs.presence import PresenceDataConfig

if TYPE_CHECKING:
    from .. import UniversityBot
    from ..models.configs.presence import PresenceConfig

_logger = get_logger(__name__)


class PresenceService:
    """A class to manage the presence module.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot instance.
    config: :class:`.PresenceConfig`
        The presence configuration.
    data: :class:`.PresenceDataConfig`
        The presence data configuration.
    """

    __slots__ = (
        "bot",
        "config",
        "data",
    )

    bot: UniversityBot
    config: PresenceConfig
    data: PresenceDataConfig

    def __init__(self, bot: UniversityBot, config: PresenceConfig) -> None:
        self.bot = bot
        self.config = config

        try:
            self.data = PresenceDataConfig(**self._load_data())
        except FileNotFoundError:
            _logger.warning(
                "Presence data file '%s' not found. Using default configuration.",
                self.config.data_filepath,
            )
            self.data = PresenceDataConfig()
            self._save_data()
        except (ValidationError, json.JSONDecodeError) as e:
            _logger.warning(
                "Failed to parse presence data file '%s'. Loading skipped.",
                self.config.data_filepath,
            )
            raise InvalidPresenceData("Invalid data in the presence data file.") from e

    async def load_presence(self) -> None:
        """|coro|

        Loads the bot's presence.
        """
        activity = self.data.activity
        status = self.data.status
        await self.bot.change_presence(activity=activity, status=status)

        _logger.info(
            "Presence loaded. Status: %s. Activity: %s.",
            status if status else "online (default)",
            f"[{activity.type.name}] {activity.name}" if activity else None,
        )

    async def set_activity(self, activity_type: ActivityType, text: str) -> None:
        """|coro|

        Sets the bot's activity.

        Parameters
        ----------
        activity_type: :class:`nextcord.ActivityType`
            The type of activity.
        text: :class:`str`
            The text to display in the status.

        Raises
        ------
        PresenceDataSaveFailed
            If saving the updated presence data to the file failed.
        """
        if activity_type == ActivityType.custom:
            activity = CustomActivity(name=text)
        else:
            activity = Activity(type=activity_type, name=text)

        self.data.activity = activity
        assert self.data is not None

        await self.bot.change_presence(status=self.data.status, activity=activity)
        self._save_data()
        _logger.info("Activity set to %s %s.", activity_type.name, text)

    async def clear_activity(self) -> None:
        """|coro|

        Clears the bot's activity.

        Raises
        ------
        PresenceDataSaveFailed
            If saving the updated presence data to the file failed.
        """
        self.data.activity = None
        await self.bot.change_presence(status=self.data.status, activity=None)
        self._save_data()
        _logger.info("Activity cleared.")

    async def set_status(self, status: Status) -> None:
        """|coro|

        Sets the bot's status.

        Parameters
        ----------
        status: :class:`nextcord.Status`
            The status to set.

        Raises
        ------
        PresenceDataSaveFailed
            If saving the updated presence data to the file failed.
        """
        self.data.status = status
        await self.bot.change_presence(status=status, activity=self.data.activity)
        self._save_data()
        _logger.info("Status set to %s.", status)

    def _save_data(self) -> None:
        try:
            with self.bot.temporary_files_config.context() as temp_file:
                with temp_file.open("w", encoding="utf-8") as f:
                    json.dump(self.data.model_dump(), f, indent=4)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_file, self.config.data_filepath)
            _logger.debug("Presence data saved successfully.")
        except Exception as e:
            _logger.error("Failed to save presence data file.", exc_info=True)
            raise PresenceDataSaveFailed("Failed to save presence data file.") from e

    def _load_data(self) -> dict[str, Any]:
        if not self.config.data_filepath.exists():
            _logger.warning("Presence data file not found. Returning empty data.")
            return {}

        with open(self.config.data_filepath, "r", encoding="utf-8") as f:
            return json.load(f)
