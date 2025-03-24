# SPDX-License-Identifier: MIT
"""A module to define the reminder service."""

from __future__ import annotations

import asyncio
import datetime
import json
import re
from typing import TYPE_CHECKING, NoReturn, overload, override

from nextcord import Embed
from nextcord.abc import Messageable

from university_bot import MessageData, ResourceFetchFailed, get_logger
from university_bot.mixins.configuration import (
    ConfigurationServiceMixin,
    InvalidConfigurationError,
)
from university_bot.modules.reminder.ui.payloads import ReminderPayload
from university_bot.utils.embeds import format_embed_values

from .config import ReminderDataConfig
from .exceptions import MissingPermissions
from .models import Reminder
from .repository import ReminderRepository
from .ui.embeds import ReminderEmbed
from ..calendar import Event, RawEvent

if TYPE_CHECKING:
    from university_bot import EmbedDict, UniversityBot

    from .config import ReminderConfig
    from .models import RawReminder
    from ..calendar import CalendarService


__all__ = ("ReminderService",)

_logger = get_logger(__name__)


class ReminderService(ConfigurationServiceMixin[ReminderDataConfig]):
    """A service to manage reminders.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot client.
    config: :class:`.ReminderConfig`
        The reminder configuration.
    data: :class:`.ReminderDataConfig`
        The reminder data configuration.
    repository: :class:`.ReminderRepository`
        The reminder repository.
    calendar_service: :class:`.CalendarService`
        The calendar service.
    """

    bot: UniversityBot
    config: ReminderConfig
    data: ReminderDataConfig
    repository: ReminderRepository
    calendar_service: CalendarService

    def __init__(
        self,
        bot: UniversityBot,
        config: ReminderConfig,
        calendar_service: CalendarService,
    ) -> None:
        self.bot = bot
        self.config = config

        try:
            self.data = ReminderDataConfig.load(self.config.data_filepath)
            self.data.validate_roles(bot.guild)
            self.data.validate_channels(bot.guild)
        except FileNotFoundError:
            _logger.warning("Data file is missing, creating a new one.")
            self.data = ReminderDataConfig.get_example()
            self.data.save(self.config.data_filepath, bot, _logger)
        except (ValueError, TypeError, MissingPermissions, json.JSONDecodeError) as e:
            _logger.error("Data file is invalid. %s", e)
            raise InvalidConfigurationError("Data file is invalid.") from e

        self.repository = ReminderRepository(bot.database.async_session_factory)
        self.calendar_service = calendar_service

        ConfigurationServiceMixin.__init__(  # type: ignore
            self,
            bot,
            self.data,
            self.config.data_filepath,
            _logger,
        )

        self.bot.loop.create_task(self.send_reminders_loop())

    @override
    def get_data_from_string(self, content: str) -> ReminderDataConfig:
        return ReminderDataConfig(**json.loads(content))

    async def send_reminders_loop(self) -> NoReturn:
        """|coro|

        A loop to send reminders.
        """
        while True:
            await self.send_reminders()
            await asyncio.sleep(60 - datetime.datetime.now().second)

    async def send_reminders(self) -> None:
        """|coro|

        Sends reminders that are due.
        """
        reminders = await self.get_reminders()
        for reminder in reminders:
            if (
                reminder.message_id is None
                and reminder.datetime <= datetime.datetime.now()
            ):
                await self.send_reminder(reminder)

    async def send_reminder(self, reminder: Reminder) -> None:
        """|coro|

        Sends a reminder.

        Parameters
        ----------
        reminder: :class:`.Reminder`
            The reminder to send.
        """
        event = await self.calendar_service.get_event_by_id(reminder.event_id)
        if event is None:
            _logger.warning("Event not found for reminder %s", reminder.id)
            return

        if (channel := self.bot.get_channel(reminder.channel_id)) is None:
            _logger.warning("Channel not found for reminder %s", reminder.id)
            return

        if not isinstance(channel, Messageable):
            _logger.warning("Channel is not a messageable for reminder %s", reminder.id)
            return

        try:
            mobile_content = self.generate_mobile_content_message(event, reminder)
            message_data = self.generate_reminder_message(event, reminder)
            message = await channel.send(content=mobile_content)
            await message.edit(**message_data)
        except ResourceFetchFailed as e:
            _logger.error("Failed to send reminder %s: %s", reminder.id, e)
            return

        dto = reminder.to_dto()
        dto.message_id = message.id

        await self.repository.update_reminder(reminder.id, dto)
        _logger.info("Sent reminder %s", reminder.id)

    async def update_event_reminders(
        self, event_id: str, reminders: list[Reminder]
    ) -> None:
        """|coro|

        Updates the reminders associated with an event.

        Parameters
        ----------
        event_id: :class:`str`
            The unique identifier of the event.
        reminders: list[:class:`.Reminder`]
            The reminders to associate with the event.
        """
        reminder_dtos = [r.to_dto() for r in reminders]
        await self.repository.update_event_reminders(event_id, reminder_dtos)
        _logger.debug("Updated event reminders in database: %s", reminders)

    async def get_reminders(self, event_id: str | None = None) -> list[Reminder]:
        """|coro|

        Retrieves reminders from the reminder database.

        Parameters
        ----------
        event_id: :class:`str` | `None`
            If provided, only reminders associated with the given event ID will be retrieved.
            Defaults to retrieving all reminders.

        Returns
        -------
        list[:class:`.Reminder`]
            The list of reminders.
        """
        dtos = await self.repository.get_reminders(event_id)
        return [Reminder.from_dto(dto) for dto in dtos]

    async def get_sorted_reminders(self, event_id: str | None = None) -> list[Reminder]:
        """|coro|

        Retrieves reminders from the reminder database and sorts them.

        Parameters
        ----------
        event_id: :class:`str` | `None`
            If provided, only reminders associated with the given event ID will be retrieved.
            Defaults to retrieving all reminders.

        Returns
        -------
        list[:class:`.Reminder`]
            The list of reminders.
        """
        reminders = await self.get_reminders(event_id)
        return sorted(reminders, key=lambda reminder: reminder.datetime)

    def get_formatting_dict(
        self,
        event: Event | RawEvent,
        reminder: Reminder | RawReminder,
    ) -> dict[str, str]:
        """Gets the formatting dictionary for the reminder.

        Parameters
        ----------
        event: :class:`.Event`
            The event associated with the reminder.
        reminder: :class:`.Reminder`
            The reminder.

        Returns
        -------
        dict[:class:`str`, :class:`str`]
            The formatting dictionary.
        """
        dt = event.datetime if isinstance(event, Event) else event.parsed_datetime

        if dt and event.is_all_day:
            dt_repr = self.data.format_repr_date(dt)
        elif dt:
            dt_repr = self.data.format_repr_datetime(dt)
        else:
            dt_repr = None

        keywords: dict[str, str] = {
            "datetime": dt_repr or "N/A",
            "description": reminder.description or "",
            "location": event.location or "",
            "additional_info": reminder.additional_info or "",
            "roles": ", ".join(map(lambda i: f"<@&{i}>", reminder.role_ids)),
        }

        fmt = (
            self.data.date_ts_format
            if event.is_all_day
            else self.data.datetime_ts_format
        )

        if isinstance(event, Event):
            timestamp = int(event.datetime.timestamp())
        elif event.parsed_datetime:
            timestamp = int(event.parsed_datetime.timestamp())
        else:
            timestamp = "**(!)**"

        keywords["formatted_timestamp"] = fmt.replace("{timestamp}", str(timestamp))

        return keywords

    @overload
    def format_content(
        self,
        content: str,
        event: Event | RawEvent,
        reminder: Reminder | RawReminder,
    ) -> str:
        pass

    @overload
    def format_content(
        self,
        content: Embed,
        event: Event | RawEvent,
        reminder: Reminder | RawReminder,
    ) -> Embed:
        pass

    @overload
    def format_content(
        self,
        content: EmbedDict,
        event: Event | RawEvent,
        reminder: Reminder | RawReminder,
    ) -> EmbedDict:
        pass

    def format_content(
        self,
        content: str | Embed | EmbedDict,
        event: Event | RawEvent,
        reminder: Reminder | RawReminder,
    ) -> str | Embed | EmbedDict:
        """Formats the content of the reminder.

        Parameters
        ----------
        content: :class:`str` | :class:`nextcord.Embed` | dict[:class:`str`, :class:`str`]
            The content to format.
        event: :class:`.Event` | :class:`.RawEvent`
            The event associated with the reminder.
        reminder: :class:`.Reminder`
            The reminder.

        Returns
        -------
        :class:`str` | :class:`nextcord.Embed` | dict[:class:`str`, :class:`str`]
            The formatted content.
        """
        fmt_dict = self.get_formatting_dict(event, reminder)
        if isinstance(content, (dict, Embed)):
            return format_embed_values(content, **fmt_dict)  # type: ignore

        for key, value in fmt_dict.items():
            content = content.replace(f"{{{key}}}", value)

        keyword_re = re.compile(r"{(.*?)\??([A-Za-z\_]+)\??(.*?)}", re.DOTALL)
        for match in keyword_re.finditer(content):
            keyword_value = fmt_dict.get(match.group(2), "INVALID_KEY")
            content = content.replace(
                match.group(0),
                (
                    ""
                    if not keyword_value
                    else f"{match.group(1)}{keyword_value}{match.group(3)}"
                ),
            )

        return content

    def generate_mobile_content_message(self, event: Event, reminder: Reminder) -> str:
        """Generates a mobile content message.

        Parameters
        ----------
        event: :class:`.Event`
            The event associated with the reminder.
        reminder: :class:`.Reminder`
            The reminder.

        Returns
        -------
        :class:`str`
            The mobile content message.
        """
        return self.format_content(self.data.mobile_content, event, reminder)

    def generate_reminder_message(
        self, event: Event, reminder: Reminder
    ) -> MessageData[ReminderEmbed, None]:
        """Generates a reminder message.

        Parameters
        ----------
        event: :class:`.Event`
            The event associated with the reminder.
        reminder: :class:`.Reminder`
            The reminder.

        Returns
        -------
        :class:`.MessageData`
            The reminder message data.
        """
        content = self.format_content(self.data.content, event, reminder)
        payload = ReminderPayload(reminder, event, self)
        embed = ReminderEmbed.create(payload)
        return MessageData(content=content, embed=embed, view=None)
