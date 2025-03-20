# SPDX-License-Identifier: MIT
"""A module to define the calendar service.

This module provides the CalendarService class which manages calendar operations,
such as adding, updating, and deleting events from the calendar database.

It integrates configuration management and static message updates to ensure that
the calendar view is always up-to-date. The service also provides methods to
validate configuration data and set up the necessary database structures.
"""

from __future__ import annotations

import asyncio
import datetime
import json
from typing import TYPE_CHECKING, NoReturn, override

from nextcord import Embed
from nextcord.ui import View
from nextcord.utils import MISSING
from sqlalchemy.exc import SQLAlchemyError

from university_bot import MessageData, ResourceFetchFailed, get_logger
from university_bot.database.utils import create_tables_if_not_exist
from university_bot.mixins.configuration import (
    ConfigurationServiceMixin,
    InvalidConfigurationError,
)
from university_bot.mixins.static_message import StaticMessageMixin

from .config import CalendarDataConfig
from .dto import CalendarBase
from .enums import EventVisibility
from .handler import CalendarHandler
from .models import Event, RawEvent
from .repository import CalendarRepository
from .ui.embeds import CalendarEmbed
from .utils import group_events_by_date, sorted_events

if TYPE_CHECKING:
    from university_bot import UniversityBot

    from .config import CalendarConfig

__all__ = ("CalendarService",)

_logger = get_logger(__name__)


class CalendarService(
    ConfigurationServiceMixin[CalendarDataConfig],
    StaticMessageMixin[CalendarHandler, CalendarDataConfig],
):
    """A service to manage the calendar.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot instance.
    config: :class:`.CalendarConfig`
        The calendar configuration.
    data: :class:`.CalendarDataConfig`
        The calendar data configuration.
    repository: :class:`.CalendarRepository`
        The calendar repository.
    """

    bot: UniversityBot
    config: CalendarConfig
    data: CalendarDataConfig
    repository: CalendarRepository
    _loop_running: bool = False

    def __init__(self, bot: UniversityBot, config: CalendarConfig) -> None:
        self.bot = bot
        self.config = config

        try:
            self.data = CalendarDataConfig.load(self.config.data_filepath)
        except FileNotFoundError:
            _logger.warning("Data file is missing, creating a new one.")
            self.data = CalendarDataConfig.get_example()
            self.data.save(self.config.data_filepath, bot, _logger)
        except json.JSONDecodeError as e:
            _logger.error("Data file is invalid.")
            raise InvalidConfigurationError("Data file is invalid.") from e

        self.repository = CalendarRepository(bot.database.async_session_factory)

        ConfigurationServiceMixin.__init__(  # type: ignore
            self,
            bot,
            self.data,
            self.config.data_filepath,
            _logger,
        )

        StaticMessageMixin.__init__(  # type: ignore
            self,
            bot,
            self.config.data_filepath,
            self.data,
            _logger,
        )

    async def load_calendar(self, handler: CalendarHandler) -> None:
        """|coro|

        Loads the calendar.

        This method removes deprecated events and refreshes the calendar message.

        Parameters
        ----------
        handler: :class:`.CalendarHandler`
            The calendar handler.
        """
        await self.remove_deprecated_events()
        try:
            await self.refresh_message(handler)
        except ResourceFetchFailed:
            _logger.warning(
                "Failed to load calendar. "
                "Remove deprecated events loop will not be started."
            )
        else:
            self.start_remove_deprecated_events_loop_if_not_running(handler)

    def start_remove_deprecated_events_loop_if_not_running(
        self, handler: CalendarHandler
    ) -> None:
        """Starts the remove deprecated events loop if it is not already running.

        Parameters
        ----------
        handler: :class:`.CalendarHandler`
            The calendar handler.
        """
        if not self._loop_running:
            _logger.debug("Starting remove deprecated events loop.")
            self.bot.loop.create_task(self._remove_deprecated_events_loop(handler))

    async def _remove_deprecated_events_loop(
        self, handler: CalendarHandler
    ) -> NoReturn:
        try:
            self._loop_running = True
            while True:
                now = datetime.datetime.now()
                next_midnight = datetime.datetime.combine(
                    now.date() + datetime.timedelta(days=1), datetime.time()
                )
                sleep_duration = (next_midnight - now).total_seconds()
                await asyncio.sleep(sleep_duration)
                if await self.remove_deprecated_events():
                    await self.refresh_message(handler)
        finally:
            self._loop_running = False

    async def remove_deprecated_events(self) -> list[Event]:
        """|coro|

        Removes deprecated events from the database.

        An event is considered deprecated if its date is earlier than today.
        This method retrieves all such events and deletes them using a single
        database operation, avoiding per-event delete calls.

        Returns
        -------
        list[:class:`Event`]
            A list of removed events.
        """

        today = datetime.date.today()
        deprecated_event_dtos = await self.repository.remove_deprecated_events(today)
        deprecated_events = [Event.from_dto(e) for e in deprecated_event_dtos]

        for event in deprecated_events:
            datetime_str = self.data.format_input_date(event.date)
            if event.time:
                datetime_str += " " + self.data.format_input_time(event.time)

            _logger.debug(
                "Removed deprecated event: %s, %s",
                datetime_str,
                event.description,
            )

        return deprecated_events

    @override
    def get_data_from_string(self, content: str) -> CalendarDataConfig:
        return CalendarDataConfig(**json.loads(content))

    @override
    async def validate_data(self, json_content: str) -> None:
        try:
            data = self.get_data_from_string(json_content)
            await data.ensure_valid_message(self.bot)
        except (ValueError, json.JSONDecodeError, ResourceFetchFailed) as e:
            raise InvalidConfigurationError("Invalid JSON content.") from e

    async def setup_database(self) -> None:
        """|coro|

        Sets up the calendar database.

        Raises
        ------
        RuntimeError
            If the database initialization fails.
        """
        try:
            async with self.bot.database.engine.begin() as conn:
                await create_tables_if_not_exist(conn, _logger, CalendarBase)
        except SQLAlchemyError as e:
            _logger.error("Failed to initialize the database.", exc_info=True)
            raise RuntimeError("Failed to initialize the database.") from e

    async def add_event(self, event: Event) -> None:
        """|coro|

        Adds an event to the calendar database.

        Parameters
        ----------
        event: :class:`.Event`
            The event to add.
        """
        event_dto = event.to_dto()
        await self.repository.add_event(event_dto)
        self._update_last_modified()
        _logger.debug("Added event to database: %s", event)

    async def delete_event(self, event: Event) -> None:
        """|coro|

        Deletes an event from the calendar database.

        Parameters
        ----------
        event: :class:`.Event`
            The event to delete.
        """
        success = await self.repository.delete_event(event.id)
        if not success:
            _logger.warning("Event with id %s not found in database.", event.id)
            return
        self._update_last_modified()
        _logger.debug("Deleted event from database: %s", event)

    async def update_event(self, event_id: str, raw_event: RawEvent) -> None:
        """|coro|

        Updates an event in the calendar database.

        This method replaces the existing event data
        with the new values provided in the event object.

        Parameters
        ----------
        event: :class:`.RawEvent`
            The raw event object containing the new values.
        """
        event = raw_event.to_event(event_id)
        success = await self.repository.update_event(event_id, event)
        if not success:
            _logger.warning("Update failed: Event with ID %s not found.", event_id)
            return
        self._update_last_modified()
        _logger.debug("Updated event ID %s with new values.", event_id)

    async def get_event_by_id(self, event_id: str) -> Event | None:
        """|coro|

        Retrieves an event from the calendar database by its ID.

        Parameters
        ----------
        event_id: :class:`str`
            The unique identifier of the event.

        Returns
        -------
        Optional[:class:`.Event`]
            The event with the given ID, or `None` if not found.
        """
        dto = await self.repository.get_event_by_id(event_id)
        return Event.from_dto(dto) if dto else None

    async def get_events(
        self, visibility: EventVisibility = EventVisibility.ALL
    ) -> list[Event]:
        """|coro|

        Retrieves events from the calendar database.

        This method fetches events and applies a visibility filter based on the parameter.

        Parameters
        ----------
        visibility: :class:`EventVisibility`
            The visibility filter to apply. Defaults to `EventVisibility.ALL`.

        Returns
        -------
        Sequence[:class:`Event`]
            The list of events matching the visibility filter.
        """
        dtos = await self.repository.get_events(visibility)
        return [Event.from_dto(dto) for dto in dtos]

    async def get_sorted_events(
        self, visibility: EventVisibility = EventVisibility.ALL
    ) -> list[Event]:
        """|coro|

        Retrieves and sorts events from the calendar database.

        This method fetches events and sorts them based on their
        datetime values.

        Parameters
        ----------
        with_visibility: :class:`EventVisibility`
            The visibility filter to apply (default is ALL).

        Returns
        -------
        list[:class:`Event`]
            The sorted list of events.
        """
        return sorted_events(await self.get_events(visibility))

    @override
    async def prepare_message_data(
        self, handler: CalendarHandler, missing: bool = False
    ) -> MessageData[Embed | None, View | None]:
        """|coro|

        Prepares the message data for the calendar.

        This method gathers visible events, groups them by date,
        and creates an embed using the CalendarEmbed class.
        It returns the message data needed to send/update the calendar message.

        Parameters
        ----------
        missing: :class:`bool`
            Whether to include missing values in the data,
            instead of `None`.

        Returns
        -------
        :class:`.MessageData`
            The message data for the calendar.
        """
        events = await self.get_sorted_events(EventVisibility.VISIBLE)
        grouped_events = group_events_by_date(events)

        return MessageData(
            content=self.data.content or (MISSING if missing else None),
            embed=CalendarEmbed.create(self.data, grouped_events),
            view=None,
        )

    def _update_last_modified(self) -> None:
        """Updates the last modified date and time.

        This method sets the `updated` attribute of the calendar data
        to the current date and time, and then saves the updated data
        to the configuration file.
        """
        self.data.modified = datetime.datetime.now(datetime.timezone.utc)
        self.save_data()
