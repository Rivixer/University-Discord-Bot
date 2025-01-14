# SPDX-License-Identifier: MIT
"""A module to control the calendar embed.

The calendar embed is an embed that shows the events.
The events are stored in the data/settings/calendar_settings.json file.

Each event can have a reminder set.
To set a reminder, use the `/calendar reminder` command.
"""

# pylint: disable=too-many-lines

from __future__ import annotations

import asyncio
import datetime
import functools
import re
import sys
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, Flag, auto
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Coroutine, Generator

import nextcord
from nextcord.application_command import SlashOption
from nextcord.channel import TextChannel
from nextcord.embeds import Embed
from nextcord.enums import TextInputStyle
from nextcord.errors import DiscordException
from nextcord.ext import commands, tasks
from nextcord.interactions import Interaction
from nextcord.member import Member
from nextcord.message import Attachment
from nextcord.role import Role
from nextcord.ui import Modal, TextInput
from nextcord.utils import format_dt

from university_bot.console import Console, FontColour
from university_bot.errors import (
    ExceptionData,
    InvalidSettingsFile,
    MissingPermission,
    UpdateEmbedError,
)
from university_bot.models import ControllerWithEmbed, EmbedModel, Model
from university_bot.utils import (
    InteractionUtils,
    Matcher,
    SmartDict,
    wait_until_midnight,
)

if TYPE_CHECKING:
    from nextcord.guild import Guild
    from nextcord.message import PartialMessage

    from university_bot import UniversityBot


class SummaryEventTypes(Flag):
    """Types of events to show in the summary."""

    VISIBLE = auto()
    HIDDEN = auto()
    ALL = VISIBLE | HIDDEN


class CalendarCog(commands.Cog):
    """Cog to control the calendar embed."""

    __slots__ = ("_bot", "_ctrl", "_model", "_reminder_ctrl")

    _bot: UniversityBot
    _ctrl: CalendarController
    _model: CalendarModel
    _reminder_ctrl: ReminderController

    def __init__(self, bot: UniversityBot) -> None:
        """Initializes the Calendar cog."""
        self._bot = bot
        self._model = CalendarModel()
        embed_model = CalendarEmbedModel(self._model, bot)
        self._ctrl = CalendarController(self._model, embed_model)
        ReminderGenerator.settings = self._model.reminder_embed_data
        self._reminder_ctrl = ReminderController(self._bot, self._model)
        self._reminder_ctrl.load_reminders()
        self._send_reminders_task.start()  # pylint: disable=no-member
        self._remove_expired_events_task.start()  # pylint: disable=no-member

    @nextcord.slash_command(
        name="calendar",
        description="The calendar embed.",
    )
    async def _calendar(self, *_) -> None:
        """The calendar embed.

        This command is a placeholder for the subcommands.
        """

    @_calendar.subcommand(
        name="send",
        description="Send a new calendar embed.",
    )
    @InteractionUtils.with_info(
        before="Sending calendar embed...",
        after="The calendar embed has been sent.",
        catch_exceptions=[DiscordException, InvalidSettingsFile],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _send(self, interaction: Interaction) -> None:
        """Sends a new calendar embed.

        The calendar embed is sent to the channel where the command was used.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        """

        channel = interaction.channel
        if isinstance(channel, TextChannel):
            await self._ctrl.send_embed(channel)

    @_calendar.subcommand(
        name="update",
        description="Update the calendar embed.",
    )
    @InteractionUtils.with_info(
        before="Updating calendar embed...",
        after="The calendar embed has been updated.",
        catch_exceptions=[UpdateEmbedError, InvalidSettingsFile],
    )
    @InteractionUtils.with_log()
    async def _update(self, _: Interaction) -> None:
        """Updates the calendar embed.

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

    @_calendar.subcommand(
        name="get_json",
        description="Get the calendar embed json.",
    )
    @InteractionUtils.with_info(
        before="Getting calendar embed json...",
        catch_exceptions=[DiscordException],
    )
    @InteractionUtils.with_log()
    async def _get_json(self, interaction: Interaction) -> None:
        """Gets the json file representing the calendar embed.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        """
        msg = await interaction.original_message()
        await msg.edit(file=self._ctrl.embed_json)

    @_calendar.subcommand(
        name="set_json",
        description="Set the calendar embed json and update the embed.",
    )
    @InteractionUtils.with_info(
        before="Setting calendar embed json and updating the embed...",
        after="The calendar embed and json file have been updated.",
        catch_exceptions=[
            TypeError,
            DiscordException,
            UpdateEmbedError,
            InvalidSettingsFile,
        ],
    )
    @InteractionUtils.with_log()
    async def _set_json(
        self,
        _: Interaction,
        file: Attachment = SlashOption(
            description="JSON file " "downloaded from `/calendar get_json` and updated"
        ),
    ) -> None:
        """Sets the json file representing the calendar embed and updates this embed.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        file: :class:`Attachment`
            The json file downloaded from `/calendar get_json` and updated.

        Raises
        ------
        UpdateEmbedError
            The embed could not be updated.
        """
        await self._ctrl.set_embed_json(file)
        await self._ctrl.update_embed()

    @_calendar.subcommand(
        name="add",
        description="Add a new event.",
    )
    @InteractionUtils.with_info(
        catch_exceptions=[UpdateEmbedError, InvalidSettingsFile, ValueError]
    )
    @InteractionUtils.with_log()
    async def _add(self, interaction: Interaction) -> None:
        modal = EventModal(EventModalType.ADD, self._ctrl)
        await interaction.response.send_modal(modal)

    @_calendar.subcommand(
        name="add_hidden",
        description="Add a new hidden event.",
    )
    @InteractionUtils.with_info(
        catch_exceptions=[UpdateEmbedError, InvalidSettingsFile, ValueError]
    )
    @InteractionUtils.with_log()
    async def _add_hidden(self, interaction: Interaction) -> None:
        modal = EventModal(EventModalType.ADD_HIDDEN, self._ctrl)
        await interaction.response.send_modal(modal)

    @_calendar.subcommand(
        name="edit",
        description="Edit an event.",
    )
    @InteractionUtils.with_info(
        catch_exceptions=[
            UpdateEmbedError,
            ValueError,
            ExceptionData(
                IndexError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ],
    )
    @InteractionUtils.with_log()
    async def _edit(
        self,
        interaction: Interaction,
        index: str = SlashOption(
            description="The index of the event to edit started from 1.",
        ),
    ) -> None:
        event = self._model.get_event_with_index(index)
        modal = EventModal(
            EventModalType.EDIT,
            self._ctrl,
            event=event,
        )
        await interaction.response.send_modal(modal)

    @_calendar.subcommand(
        name="copy",
        description="Copy an event.",
    )
    @InteractionUtils.with_info(
        catch_exceptions=[
            UpdateEmbedError,
            ValueError,
            ExceptionData(
                IndexError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ],
    )
    @InteractionUtils.with_log()
    async def _copy(
        self,
        interaction: Interaction,
        index: str = SlashOption(
            description="The index of the event to copy started from 1.",
        ),
    ) -> None:
        event = self._model.get_event_with_index(index)
        modal = EventModal(
            EventModalType.COPY,
            self._ctrl,
            event=event,
        )
        await interaction.response.send_modal(modal)

    @_calendar.subcommand(
        name="hide",
        description="Hide an event.",
    )
    @InteractionUtils.with_info(
        before="Hiding event with index **{index}**...",
        after="The event has been hidden.",
        catch_exceptions=[
            UpdateEmbedError,
            ValueError,
            ExceptionData(
                IndexError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ],
    )
    @InteractionUtils.with_log()
    async def _hide(
        self,
        _: Interaction,
        index: str = SlashOption(
            description="The index of the event to hide started from 1.",
        ),
    ) -> None:
        event = self._model.get_event_with_index(index)
        if event.is_hidden:
            raise ValueError("The event is already hidden.")
        event.is_hidden = True
        await self._ctrl.update_embed()

    @_calendar.subcommand(
        name="show",
        description="Show an event.",
    )
    @InteractionUtils.with_info(
        before="Showing event with index **{index}**...",
        after="The event has been showed.",
        catch_exceptions=[
            UpdateEmbedError,
            ValueError,
            ExceptionData(
                IndexError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ],
    )
    @InteractionUtils.with_log()
    async def _show(
        self,
        _: Interaction,
        index: str = SlashOption(
            description="The index of the event to show started from 1.",
        ),
    ) -> None:
        event = self._model.get_event_with_index(index)
        if not event.is_hidden:
            raise ValueError("The event is already visible.")
        event.is_hidden = False
        await self._ctrl.update_embed()

    @_calendar.subcommand(
        name="summary",
        description="Show summary of events.",
    )
    @InteractionUtils.with_info(
        catch_exceptions=[
            DiscordException,
            InvalidSettingsFile,
            ExceptionData(
                ValueError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ]
    )
    @InteractionUtils.with_log()
    async def _summary(
        self,
        interaction: Interaction,
        page: int = SlashOption(
            description="The page number of the events summary.",
            default=1,
            min_value=1,
        ),
        _type: str = SlashOption(
            name="type",
            description="The type of the events to show.",
            choices={i.name.title(): i.name for i in SummaryEventTypes},
            default=SummaryEventTypes.ALL.name,
        ),
    ) -> None:
        """Shows summary of events.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        page: :class:`int`
            The page number of the events summary.
        _type: :class:`str`
            The type of the events to show.
        """
        event_type = SummaryEventTypes[_type]
        embed = CalendarSummaryEmbed(self._model).generate(page, event_type)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @_calendar.subcommand(
        name="remove",
        description="Remove an event with the given index.",
    )
    @InteractionUtils.with_info(
        before="Removing event with index **{index}**...",
        catch_exceptions=[
            DiscordException,
            UpdateEmbedError,
            InvalidSettingsFile,
            ExceptionData(
                IndexError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ],
    )
    @InteractionUtils.with_log()
    async def _remove(
        self,
        interaction: Interaction,
        index: str = SlashOption(
            description="The index of the event to remove started from 1.",
        ),
    ) -> None:
        """Removes an event from the calendar with the given index.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        index: :class:`int`
            The index of the event to remove.

        Raises
        ------
        UpdateEmbedError
            The embed could not be updated.
        """

        event = self._model.get_event_with_index(index)
        self._model.remove_event_from_json(event)

        if not event.is_hidden:
            await self._ctrl.update_embed()

        # We edit the original message here
        # instead of in the `with_info` decorator,
        # because we don't have access to the event description there.
        msg = await interaction.original_message()
        await msg.edit(f"The event '{event.full_info}' has been removed.")

    @_calendar.subcommand(
        name="remove_expired_events",
        description="Remove expired events.",
    )
    @InteractionUtils.with_info(
        before="Removing expired events...",
        after="Expired events have been removed.",
        catch_exceptions=[DiscordException, UpdateEmbedError, InvalidSettingsFile],
    )
    @InteractionUtils.with_log()
    async def _remove_expired_events(self, _: Interaction) -> None:
        """Removes expired events from the calendar.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.

        Raises
        ------
        UpdateEmbedError
            The embed could not be updated.
        """

        removed_events = self._model.remove_expired_events()
        if any(map(lambda i: not i.is_hidden, removed_events)):
            await self._ctrl.update_embed()

    @tasks.loop(count=1)
    async def _remove_expired_events_task(self) -> None:
        """Removes expired events from the calendar.

        Expired events are events that have already taken place.

        The events are removed at midnight.

        Raises
        ------
        UpdateEmbedError
            The embed could not be updated.
        """
        await self._bot.wait_until_ready()
        while True:
            removed_events = self._model.remove_expired_events()
            if any(map(lambda i: not i.is_hidden, removed_events)):
                await self._ctrl.update_embed()
            await wait_until_midnight()

    @_calendar.subcommand(
        name="reminder",
        description="Set or edit an event reminder.",
    )
    @InteractionUtils.with_info(
        catch_exceptions=[
            DiscordException,
            InvalidSettingsFile,
            ExceptionData(
                IndexError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ],
    )
    @InteractionUtils.with_log()
    async def _reminder(
        self,
        interaction: Interaction,
        index: str = SlashOption(
            description="The index of the event to edit started from 1.",
        ),
    ) -> None:
        """Sets or edits an event reminder.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        index: :class:`int`
            The index of the event to edit.

        Raises
        ------
        UpdateEmbedError
            The embed could not be updated.
        """
        event = self._model.get_event_with_index(index)
        guild: Guild = interaction.guild  # type: ignore
        modal = ReminderModal(event, guild)
        await interaction.response.send_modal(modal)

    @_calendar.subcommand(
        name="remove_reminder",
        description="Remove an event reminder.",
    )
    @InteractionUtils.with_info(
        before="Removing the reminder for the event with index **{index}**...",
        after="The reminder for the event has been removed.",
        catch_exceptions=[
            DiscordException,
            InvalidSettingsFile,
            ExceptionData(
                IndexError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ],
    )
    @InteractionUtils.with_log()
    async def _remove_reminder(
        self,
        _: Interaction,
        index: str = SlashOption(
            description="The index of the event to edit started from 1.",
        ),
    ) -> None:
        """Removes the reminder for the event with the given index.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        index: :class:`int`
            The index of the event to edit.

        Raises
        ------
        ValueError
            The event has no reminder set.
        """
        event = self._model.get_event_with_index(index)
        if event.reminder is None:
            raise ValueError("The event has no reminder set.")
        event.reminder = None

    @_calendar.subcommand(
        name="reminder_preview",
        description="Preview the reminder embed.",
    )
    @InteractionUtils.with_info(
        catch_exceptions=[
            DiscordException,
            InvalidSettingsFile,
            ExceptionData(
                ValueError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
            ExceptionData(
                IndexError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ]
    )
    @InteractionUtils.with_log()
    async def _reminder_preview(
        self,
        interaction: Interaction,
        index: str = SlashOption(
            description="The index of the event to edit started from 1.",
        ),
    ) -> None:
        """Previews the reminder embed for the event with the given index.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        index: :class:`int`
            The index of the event to preview.

        Raises
        ------
        ValueError
            The event has no reminder set.
        """
        event = self._model.get_event_with_index(index)
        if event.reminder is None:
            raise ValueError("The event has no reminder set.")

        assert interaction.guild is not None
        generator = ReminderGenerator(event, interaction.guild)

        await interaction.response.send_message(
            content=generator.preview_message, embed=generator.embed, ephemeral=True
        )

    @tasks.loop(count=1)
    async def _send_reminders_task(self) -> None:
        await self._bot.wait_until_ready()
        while True:
            await self._reminder_ctrl.send_reminders()  # type: ignore
            await asyncio.sleep(60 - datetime.datetime.now().second)


@dataclass(slots=True)
class Event:  # pylint: disable=too-many-instance-attributes
    r"""Represents an event in the calendar.

    If event is an all-day event, :attr:`time` will be '00:00'.

    Attributes
    ----------
    description: :class:`str`
        The event description.
    date: :class:`datetime.date`
        The date when the event is to take place.
    time: :class:`datetime.date`
        The time when the event is to take place.
        If is None, the event is an all-day one.
    prefix: :class:`str`
        The prefix of the event.
    location: :class:`str`
        The location of the event.
    reminder: :class:`Reminder` | `None`
        The reminder for the event.

    Events
    ------
    on_update: list[:class:`Callable`]
        A list of functions that are called when the event's attributes are updated.

    Methods
    -------
    compare_method(event1: :class:`Event`, event2: :class:`Event`) -> :class:`int`
        Compares events with their date and time.
    """

    _uuid: str = field(init=False, default_factory=lambda: str(uuid.uuid4()))
    _description: str
    _date: datetime.date
    _time: datetime.time | None
    _prefix: str
    _location: str
    _is_hidden: bool = field(default=False)
    _reminder: Reminder | None = field(default=None)

    on_update: list[Callable[[Event], None]] = field(
        init=False, default_factory=list, compare=False, repr=False
    )

    @classmethod
    def from_dict(cls, _uuid: str, data: dict[str, Any]) -> Event:
        """Creates an event from a dictionary.

        Parameters
        ----------
        uuid: :class:`str`
            The unique identifier of the event.
        data: :class:`dict`
            The event data.

        Returns
        -------
        :class:`Event`
            The created event.

        Raises
        ------
        InvalidSettingsFile
            The event data is invalid.
        """
        try:
            self = cls(
                data["description"],
                datetime.datetime.strptime(data["date"], "%d.%m.%Y").date(),
                (
                    datetime.datetime.strptime(data["time"], "%H.%M").time()
                    if data["time"]
                    else None
                ),
                data["prefix"],
                data["location"],
                data.get("is_hidden", False),
                Reminder.from_dict(d) if (d := data["reminder"]) else None,
            )
        except KeyError as e:
            raise InvalidSettingsFile(
                f"Invalid event data for event with uuid '{_uuid}'"
            ) from e

        self._uuid = _uuid

        if self.reminder:
            self.reminder.on_update.append(
                lambda _: self._on_update_invoke()  # pylint: disable=protected-access
            )

        return self

    @property
    def uuid(self) -> str:
        """The unique identifier of the event."""
        return self._uuid

    @property
    def description(self) -> str:
        """The event description."""
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        self._description = value
        self._on_update_invoke()

    @property
    def date(self) -> datetime.date:
        """The date when the event is to take place."""
        return self._date

    @date.setter
    def date(self, value: datetime.date) -> None:
        self._date = value
        self._on_update_invoke()

    @property
    def time(self) -> datetime.time | None:
        """The time when the event is to take place.

        If is None, the event is an all-day one.
        """
        return self._time

    @time.setter
    def time(self, value: datetime.time | None) -> None:
        self._time = value
        self._on_update_invoke()

    @property
    def prefix(self) -> str:
        """The prefix of the event."""
        return self._prefix

    @prefix.setter
    def prefix(self, value: str) -> None:
        self._prefix = value
        self._on_update_invoke()

    @property
    def location(self) -> str:
        """The location of the event."""
        return self._location

    @location.setter
    def location(self, value: str) -> None:
        self._location = value
        self._on_update_invoke()

    @property
    def is_hidden(self) -> bool:
        """Whether the event is hidden in the calendar embed."""
        return self._is_hidden

    @is_hidden.setter
    def is_hidden(self, value: bool) -> None:
        self._is_hidden = value
        self._on_update_invoke()

    @property
    def reminder(self) -> Reminder | None:
        """The reminder for the event."""
        return self._reminder

    @reminder.setter
    def reminder(self, value: Reminder | None) -> None:
        self._reminder = value
        if self._reminder is not None:
            self._reminder.on_update.append(lambda _: self._on_update_invoke())
        self._on_update_invoke()

    @property
    def datetime(self) -> datetime.datetime:
        """The datetime representation of the event.

        If the event is an all-day one, the time is set to 00:00:00.
        """
        time = self.time if self.time is not None else datetime.time()
        return datetime.datetime.combine(self.date, time)

    @property
    def is_all_day(self) -> bool:
        """Whether the event is an all-day one.

        Notes
        -----
        An event is an all-day one if its time is None.
        """
        return self.time is None

    @property
    def is_expired(self) -> bool:
        """Whether the event has already started.

        Notes
        -----
        If the event is an all-day one,
        the start time is taken as 11:59 PM.
        """

        now = datetime.datetime.now()
        if self.time is None:
            return self.date < now.date()
        return self.datetime < now

    @property
    def full_name(self) -> str:
        r"""The full name of the event in format:

        `[prefix*] **description** [location*] (time**)`

        \* - if exists;
        \** - if not an all-day event;
        """

        result = f"**{self.description}**"

        if self.prefix:
            result = f"[{self.prefix}] {result}"

        if self.location:
            result = f"{result} [{self.location}]"

        if self.time is not None:
            if sys.platform == "win32":
                result += f' ({self.time.strftime("%#H:%M")})'  # pragma: no cover
            else:
                result += f' ({self.time.strftime("%-H:%M")})'  # pragma: no cover

        return result

    @property
    def full_info(self) -> str:
        """The full information of the event in format:

        `(date) [prefix if exists] **description**
        [location if exists] (time if not an all-day event) (hidden if hidden)`

        Similar to :attr:`.Event.full_name` but with the date at the beginning
        and the hidden status at the end.
        """
        return (
            f"({self.date.strftime('%d.%m.%Y')}) "
            f"{self.full_name}"
            f"{' (hidden)' if self.is_hidden else ''}"
        )

    @property
    def weekday(self) -> str:
        """The weekday of the event."""

        weekdays = {
            0: "poniedziałek",
            1: "wtorek",
            2: "środa",
            3: "czwartek",
            4: "piątek",
            5: "sobota",
            6: "niedziela",
        }
        return weekdays.get(self.date.weekday(), "")

    @staticmethod
    def compare_method(event1: Event, event2: Event) -> int:
        """Compares events with their date and time."""
        return int((event1.datetime - event2.datetime).total_seconds())

    def _on_update_invoke(self) -> None:
        for func in self.on_update:
            func(self)

    def to_dict(self) -> dict[str, Any]:
        """Converts the event to a dictionary."""
        return {
            "description": self.description,
            "date": self.date.strftime("%d.%m.%Y"),
            "time": self.time.strftime("%H.%M") if self.time else None,
            "prefix": self.prefix,
            "location": self.location,
            "is_hidden": self.is_hidden,
            "reminder": self.reminder.to_dict() if self.reminder else None,
        }


@dataclass(slots=True)
class CalendarSummaryEmbed:
    """Generates an embed with events summary."""

    _model: CalendarModel

    def _get_event_summary(self, event: Event, index: int) -> str:
        return f"{index}.{' 🔔' if event.reminder else ''} {event.full_info}"

    def _adding_event_exceeds_max_length(self, result: str, event_summary: str) -> bool:
        max_description_length = 4096
        return len(f"{result}\n{event_summary}") >= max_description_length

    def _generate_description_parts(
        self, _type: SummaryEventTypes
    ) -> Generator[str, None, None]:
        visible_events = self._model.visible_events
        hidden_events = self._model.hidden_events
        result = ""

        if visible_events and SummaryEventTypes.VISIBLE in _type:
            result += "**Visible events:**"
            index = 1

            for event in visible_events:
                event_summary = f"\n{self._get_event_summary(event, index)}"
                if self._adding_event_exceeds_max_length(result, event_summary):
                    yield result
                    result = "**Visible events:**"
                result += event_summary
                index += 1

        hidden_info = (
            "**Hidden events:**\nTo interact with them, precede the index with `_`"
        )

        if (
            hidden_events
            and SummaryEventTypes.HIDDEN in _type
            and not self._adding_event_exceeds_max_length(
                result,
                f"\n{hidden_info}\n{self._get_event_summary(hidden_events[0], 1)}",
            )
        ):
            if result:
                result += "\n\n"

            result += hidden_info
            index = 1

            for event in hidden_events:
                event_summary = f"\n{self._get_event_summary(event, index)}"
                if self._adding_event_exceeds_max_length(result, event_summary):
                    yield result
                    result = hidden_info
                result += event_summary
                index += 1

        yield result

    def generate(self, page: int, _type: SummaryEventTypes) -> Embed:
        """Generates an embed with events summary.

        Parameters
        ----------
        page: :class:`int`
            The page number.
        _type: :class:`SummaryEventTypes`
            The type of the events to show.
        """
        description_parts = list(self._generate_description_parts(_type))

        pages = len(description_parts)
        if not 1 <= page <= pages:
            raise ValueError(f"Page must be between 1 and {pages}")

        return Embed(
            title="Calendar events summary",
            description=description_parts[page - 1] or "No events.",
            color=nextcord.Colour.dark_green(),
        ).set_footer(text=f"Page {page}/{pages}.")


class CalendarModel(Model):
    """Represents the calendar model."""

    @property
    def events_data(self) -> dict[str, dict[str, Any]]:
        """A dictionary of events data."""
        return self.data.get("events", {})

    @staticmethod
    def convert_datetime_input(
        date_input: str, time_input: str | None
    ) -> datetime.datetime:
        """Converts date and time inputs to the datetime format."""
        date_input = re.sub("[-:/]", ".", date_input)
        time_input = re.sub("[-:/]", ".", time_input) if time_input else "00.00"
        _input = f"{date_input} {time_input}"
        return datetime.datetime.strptime(_input, "%d.%m.%Y %H.%M")

    @property
    def calendar_data(self) -> list[Event]:
        """A list of events formatted to the :class:`.Event` class.
        Sorted by date."""
        result: list[Event] = []
        for _uuid, event_data in self.events_data.items():
            event = Event.from_dict(_uuid, event_data)
            event.on_update.append(self.update_event_in_json)
            result.append(event)
        result.sort(key=functools.cmp_to_key(Event.compare_method))
        return result

    @property
    def visible_events(self) -> list[Event]:
        """A list of visible events formatted to the :class:`.Event` class.
        Sorted by date."""
        return [e for e in self.calendar_data if not e.is_hidden]

    @property
    def hidden_events(self) -> list[Event]:
        """A list of hidden events formatted to the :class:`.Event` class.
        Sorted by date."""
        return [e for e in self.calendar_data if e.is_hidden]

    def get_event_with_index(self, index: str) -> Event:
        """Returns the event with the specified index.

        If the index starts with `_`, the event is hidden.

        Parameters
        ----------
        index: :class:`str`
            The index of the event to get.

        Returns
        -------
        :class:`.Event`
            The found event.

        Raises
        ------
        IndexError
            - If the index is out of bounds (less than 1 or greater than the number of events).
            - If there are no events.
        """
        is_hidden = index.startswith("_")
        idx = int(index[1:] if is_hidden else index)
        return self.get_event_at_index(idx, is_hidden=is_hidden)

    def get_event_at_index(self, index: int, *, is_hidden: bool = False) -> Event:
        """Returns the event at the specified index.

        Parameters
        ----------
        index: :class:`int`
            The index of the event to get.
        is_hidden: :class:`bool`
            Whether the event is hidden in the calendar embed.

        Returns
        -------
        :class:`.Event`
            The found event.

        Raises
        ------
        IndexError
            - If the index is out of bounds (less than 1 or greater than the number of events).
            - If there are no events.
        """

        events = [e for e in self.calendar_data if e.is_hidden == is_hidden]
        number_of_events = len(events)

        if number_of_events == 0:
            raise IndexError("There are no events")

        if not 1 <= index <= number_of_events:
            raise IndexError(f"Index must be between 1 and {number_of_events}")

        return events[index - 1]

    def remove_event_from_json(self, event: Event) -> None:
        """Removes event from the `settings.json` file.

        Parameters
        ----------
        event: :class:`.Event`
            The event to remove.
        """
        events_data = self.events_data
        del events_data[event.uuid]
        self._save_events_data(events_data)

    def remove_expired_events(self) -> list[Event]:
        """Removes all events that have already started.

        Returns
        -------
        list[:class:`.Event`]
            A list of removed events.
        """

        removed_events = []
        for event in self.calendar_data:
            if event.is_expired:
                self.remove_event_from_json(event)
                removed_events.append(event)

                Console.specific(
                    f"Event '{event.full_info}' has been removed due to expiration.",
                    "Calendar",
                    FontColour.GREEN,
                    bold_type=True,
                )

        return removed_events

    def add_event_to_json(self, event: Event) -> None:
        """Adds the event to the `settings.json` file.

        Parameters
        ----------
        event: :class:`.Event`
            An event to be added.
        """
        events_data = self.events_data
        events_data[event.uuid] = event.to_dict()
        self._save_events_data(events_data)

    def get_grouped_events(
        self,
    ) -> Generator[tuple[datetime.date, list[Event]], None, None]:
        """An iterator that reads all visible events from settings and sorts them.

        Yields
        ------
        tuple[:class:`datetime.date`, list[:class:`.Event`]]
            A tuple of events, grouped by date and sorted.
        """
        calendar: dict[datetime.date, list[Event]] = {}

        for event in self.calendar_data:
            if event.is_hidden:
                continue

            try:
                calendar[event.date].append(event)
            except KeyError:
                calendar[event.date] = [event]

        for date, event in calendar.items():
            yield (date, event)

    def update_event_in_json(self, event: Event) -> None:
        """Updates the event in the `settings.json` file.

        Parameters
        ----------
        event: :class:`.Event`
            The event to update.
        """
        events_data = self.events_data
        events_data[event.uuid] = event.to_dict()
        self._save_events_data(events_data)

    @property
    def reminder_embed_data(self) -> _ReminderSettings:
        """The reminder embed data used to generate the reminder embed."""
        data = self.data.get("reminder")
        if data is None:
            data = self._get_default_reminder_embed_data()
            self.update_settings("reminder", data, force=True)
        return _ReminderSettings.load(data)

    def _save_events_data(self, events_data: dict[str, dict[str, Any]]) -> None:
        self.update_settings("events", events_data, force=True)

    def _get_default_reminder_embed_data(self) -> dict[str, Any]:
        return {
            "_keywords": {
                "{{DATETIME}}": "the event date and time",
                "{{DATETIME:X}}": "the event date and time where X is one of (f, F, d, D, t, T, R) "
                "(see https://discord-date.shyked.fr/)",
                "{{DESCRIPTION}}": "the event description",
                "{{CONTENT}}": "the reminder content "
                "(if not set, it will be the event description)",
                "{{ROLES}}": "the mentioned roles",
                "{{LOCATION}}": "the event location",
                "{{MORE_INFO}}": "more information about the event",
                "_": "Each keyword can be preceded or followed by any text "
                "separated by question mark to display it only if the keyword is not empty. "
                "For example: {{More info:\n?{{MORE_INFO}}}}. In this case, the text "
                "'More info:\n' will be displayed only if the keyword 'MORE_INFO' is not empty.",
            },
            "text": "{{DATETIME}}: {{DESCRIPTION}}\n{{ROLES}}",
            "embed": {
                "title": "REMINDER",
                "description": "{{CONTENT}}",
                "thumbnail": {
                    "url": "",
                    "width": 512,
                    "height": 512,
                },
                "color": {
                    "default": 16763432,
                    "use_role_color_if_single_was_pinged": True,
                },
                "fields": {
                    "datetime": {
                        "name": "When?",
                        "value": "{{DATETIME:f}}",
                        "inline": True,
                    },
                    "datetime_all_day": {
                        "name": "When?",
                        "value": "{{DATETIME:D}}",
                        "inline": True,
                    },
                    "location": {
                        "name": "Where?",
                        "value": "{{LOCATION}}",
                        "inline": True,
                    },
                    "more_info": {
                        "name": "More information:",
                        "value": "{{MORE_INFO}}",
                        "inline": False,
                    },
                },
            },
        }


# pylint: disable=no-member


class CalendarEmbedModel(EmbedModel):
    """Represents the calendar embed model.

    Attributes
    ----------
    model: :class:`.CalendarModel`
        The calendar model.

    Methods
    -------
    generate_embed(**_) -> :class:`nextcord.Embed`
        Generates an embed with all events.
    """

    model: CalendarModel

    def _get_field_value(self, events: list[Event]) -> str:
        truncated_text = "\n*... and more.*"
        max_length = 1024 - len(truncated_text)
        result = f"- {events[0].full_name}"
        for event in events[1:]:
            event_summary = f"- {event.full_name}"
            if len(result) + len(event_summary) > max_length:
                result += truncated_text
                break
            result += f"\n{event_summary}"
        return result

    def generate_embed(self, **_) -> Embed:
        """Generates an embed with all events."""
        embed = super().generate_embed()

        grouped_events = list(self.model.get_grouped_events())

        for day, events in grouped_events[:25]:
            weekday = events[0].weekday
            date = day.strftime("%d.%m.%Y")
            embed.add_field(
                name=f"{date} ({weekday}):",
                value=self._get_field_value(events),
                inline=False,
            )

        if len(grouped_events) > 25:
            embed.set_footer(text="Showing only the first 25 days.")

        return embed


class CalendarController(ControllerWithEmbed):
    """Represents the calendar controller.

    Attributes
    ----------
    embed_model: :class:`.CalendarEmbedModel`
        The calendar embed model.
    model: :class:`.CalendarModel`
        The calendar model.
    """

    embed_model: CalendarEmbedModel
    model: CalendarModel

    @staticmethod
    def _convert_input_to_event(
        description: str,
        date: str,
        time: str | None,
        prefix: str,
        location: str,
    ) -> Event:
        dt = CalendarModel.convert_datetime_input(date, time)
        return Event(
            description,
            dt.date(),
            dt.time() if time else None,
            prefix,
            location,
        )

    def add_event_from_input(  # pylint: disable=too-many-arguments
        self,
        description: str,
        date: str,
        time: str | None,
        prefix: str,
        location: str,
    ) -> Event:
        """Adds event to the `settings.json` file.

        The date and time separator can be `.`, `:`, `-` or `/`.

        Parameters
        ----------
        description: :class:`str`
            The event description.
        date: :class:`str`
            The date in the format `dd.mm.yyyy`.
        time: :class:`str` | `None`
            The time in the format `hh.mm`.
            If `None`, the time will be set to `00.00`.
        prefix: :class:`str`
            The prefix of the event.
        location: :class:`str`
            The location of the event.

        Returns
        -------
        :class:`.Event`
            An event that has been added.

        Raises
        ------
        ValueError
            The date or time was invalid.
        """
        event = self._convert_input_to_event(description, date, time, prefix, location)
        event.on_update.append(self.model.update_event_in_json)
        self.model.add_event_to_json(event)
        return event


class EventModalType(Enum):
    """Represents type of event modal."""

    ADD = auto()
    ADD_HIDDEN = auto()
    EDIT = auto()
    COPY = auto()


class EventModal(Modal):  # pylint: disable=too-many-instance-attributes
    """A modal to add or edit an event.

    Parameters
    ----------
    title: :class:`str`
        The title of the modal.
    controller: :class:`.CalendarController`
        The calendar controller.
    event: :class:`.Event` | `None`
        The event to edit. If `None`, a new event will be added.

    Attributes
    ----------
    description: :class:`TextInput`
        The description of the event.
    date: :class:`TextInput`
        The date of the event.
    time: :class:`TextInput`
        The time of the event.
    prefix: :class:`TextInput`
        The prefix of the event.
    location: :class:`TextInput`
        The location of the event.
    modal_type: :class:`EventModalType`
        The type of the modal.
    """

    __slots__ = (
        "description",
        "date",
        "time",
        "prefix",
        "location",
        "modal_type",
        "_controller",
        "_event",
    )

    description: TextInput
    date: TextInput
    time: TextInput
    prefix: TextInput
    location: TextInput
    modal_type: EventModalType
    _controller: CalendarController
    _event: Event | None

    def __init__(
        self,
        modal_type: EventModalType,
        /,
        controller: CalendarController,
        event: Event | None = None,
    ):
        """Initializes the modal.

        Parameters
        ----------
        modal_type: :class:`EventModal
            The type of the modal.
        controller: :class:`.CalendarController`
            The calendar controller.
        event: :class:`.Event` | `None`
            The event to fill the modal with.
        """

        match modal_type:
            case EventModalType.ADD:
                title = "Add a new event"
            case EventModalType.ADD_HIDDEN:
                title = "Add a new hidden event"
            case EventModalType.EDIT:
                title = "Edit the event"
            case EventModalType.COPY:
                title = "Copy the event"
            case _:
                raise NotImplementedError

        super().__init__(title=title, timeout=None)

        self.modal_type = modal_type
        self._controller = controller
        self._event = event

        self.description = TextInput(
            label="Description:",
            placeholder="The description of the event",
            default_value=event.description if event else "",
            max_length=100,
            required=True,
        )
        self.add_item(self.description)

        self.date = TextInput(
            label="Date:",
            placeholder="The date in the format `dd.mm.yyyy`",
            default_value=event.date.strftime("%d.%m.%Y") if event else "",
            max_length=10,
            required=True,
        )
        self.add_item(self.date)

        self.time = TextInput(
            label="Time:",
            placeholder="The time (`hh.mm`), not specified = all day event",
            max_length=5,
            required=False,
        )

        if event is None or event.time is None:
            self.time.default_value = None
        else:
            self.time.default_value = event.time.strftime("%H.%M")

        self.add_item(self.time)

        self.prefix = TextInput(
            label="Prefix:",
            placeholder="The prefix of the event",
            default_value=event.prefix if event else "",
            max_length=10,
            required=False,
        )
        self.add_item(self.prefix)

        self.location = TextInput(
            label="Location:",
            placeholder="The location of the event",
            default_value=event.location if event else "",
            max_length=256,
            required=False,
        )
        self.add_item(self.location)

    @InteractionUtils.with_info(catch_exceptions=[ValueError, UpdateEmbedError])
    async def callback(self, interaction: Interaction) -> None:
        """The callback for the modal.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the modal.
        """
        member = interaction.user
        assert isinstance(member, Member)
        await interaction.response.defer()
        old_event = self._event
        event = self._create_new_event()

        if old_event is not None:
            event.is_hidden = old_event.is_hidden
            if old_reminder := old_event.reminder:
                event.reminder = self._copy_reminder(old_reminder)
        update_date_result = self._update_reminder_date(old_event, event)

        self._send_info_to_console(old_event, event, member)

        response_content = self._generate_response_content(
            old_event, event, update_date_result
        )

        if old_event is not None and self.modal_type is not EventModalType.COPY:
            self._controller.model.remove_event_from_json(old_event)

        embed = nextcord.utils.MISSING
        if event.reminder:
            guild: Guild = interaction.guild  # type: ignore
            generator = ReminderGenerator(event, guild)
            response_content += "\n\n**Reminder preview:**\n"
            response_content += generator.preview_message
            embed = generator.embed

        async def update_embed_if_event_is_visible() -> None:
            if not event.is_hidden:
                await self._controller.update_embed()

        await asyncio.gather(
            *(
                update_embed_if_event_is_visible(),
                interaction.followup.send(
                    response_content, embed=embed, ephemeral=True
                ),
            )
        )

    def _create_new_event(self) -> Event:
        description = self.description.value or ""
        date = self.date.value or ""
        time = self.time.value or None
        prefix = self.prefix.value or ""
        location = self.location.value or ""

        self._validate_datetime(date, time)

        event = self._controller.add_event_from_input(
            description, date, time, prefix, location
        )

        if self.modal_type is EventModalType.ADD_HIDDEN:
            event.is_hidden = True

        return event

    def _validate_datetime(self, date: str, time: str | None) -> None:
        dt = CalendarModel.convert_datetime_input(date, time)
        is_all_day = time is None

        is_in_past = (
            dt.date() < datetime.datetime.now().date()
            if is_all_day
            else dt < datetime.datetime.now()
        )

        if is_in_past:
            raise ValueError("The event date and time must be in the future.")

        if dt > datetime.datetime.now() + datetime.timedelta(days=365 * 5):
            raise ValueError("The event date and time must be in the next 5 years.")

    def _copy_reminder(self, reminder: Reminder) -> Reminder | None:
        copied_reminder = deepcopy(reminder)
        if self.modal_type is EventModalType.COPY:
            copied_reminder.reset_sent_data()
        return copied_reminder

    class _UpdateReminderDateResult(Enum):
        UNCHANGED = auto()
        UPDATED = auto()
        SET_TO_IN_HOUR = auto()
        SET_TO_EVENT = auto()

    def _update_reminder_date(
        self, old_event: Event | None, new_event: Event
    ) -> _UpdateReminderDateResult:
        if old_event is None or new_event.reminder is None:
            return self._UpdateReminderDateResult.UNCHANGED

        deltatime = new_event.datetime - old_event.datetime
        if deltatime.total_seconds() == 0:
            return self._UpdateReminderDateResult.UNCHANGED

        reminder = new_event.reminder
        reminder.datetime += deltatime
        now = datetime.datetime.now()

        if reminder.datetime < now:
            reminder.datetime = now + datetime.timedelta(hours=1)
            if reminder.datetime > new_event.datetime:
                reminder.datetime = new_event.datetime
                return self._UpdateReminderDateResult.SET_TO_EVENT
            return self._UpdateReminderDateResult.SET_TO_IN_HOUR
        return self._UpdateReminderDateResult.UPDATED

    def _send_info_to_console(
        self,
        old_event: Event | None,
        new_event: Event,
        member: Member,
    ) -> None:
        content = f"{member} "
        match self.modal_type:
            case EventModalType.ADD:
                content += "added a new event."
            case EventModalType.ADD_HIDDEN:
                content += "added a new hidden event."
            case EventModalType.EDIT:
                assert old_event is not None
                content += f"edited the event '{old_event.full_info}' -> "
            case EventModalType.COPY:
                assert old_event is not None
                content += f"copied the event '{old_event.full_info}' -> "
            case _:
                raise NotImplementedError
        content += f"'{new_event.full_info}'"
        Console.specific(content, "Calendar", FontColour.GREEN, bold_type=True)

    def _generate_response_content(
        self,
        old_event: Event | None,
        new_event: Event,
        update_data_result: _UpdateReminderDateResult,
    ) -> str:
        result = f"Event '{new_event.full_info}' has been "

        match self.modal_type:
            case EventModalType.ADD | EventModalType.ADD_HIDDEN | EventModalType.COPY:
                result += "added."
            case EventModalType.EDIT:
                result += "edited."
            case EventModalType.COPY:
                assert old_event is not None
                result += f"copied from the event '{old_event.full_info}'."
            case _:
                raise NotImplementedError

        if new_event.reminder is not None:
            match update_data_result:
                case self._UpdateReminderDateResult.UNCHANGED:
                    result += "\n\nReminder date remains unchanged."
                case self._UpdateReminderDateResult.UPDATED:
                    assert old_event is not None
                    deltatime = new_event.datetime - old_event.datetime
                    result += f"\n\nReminder date updated by {deltatime}."
                case self._UpdateReminderDateResult.SET_TO_IN_HOUR:
                    result += (
                        "\n\nReminder date set to one hour from now "
                        "due to event date/time rollback."
                    )
                case self._UpdateReminderDateResult.SET_TO_EVENT:
                    result += (
                        "\n\nReminder date set to event date/time "
                        "due to event date/time rollback."
                    )
                case _:
                    raise NotImplementedError

        return result


class ReminderController:
    """Represents the reminder controller.

    Methods
    -------
    load_reminders()
        Loads all reminders from the calendar model.
    send_reminders()
        Sends all reminders that are ready to be sent.
    """

    __slots__ = (
        "_bot",
        "_calendar_model",
        "_reminders",
    )

    _bot: UniversityBot
    _calendar_model: CalendarModel
    _reminders: list[Reminder]

    def __init__(self, bot: UniversityBot, calendar_model: CalendarModel):
        self._bot = bot
        self._calendar_model = calendar_model
        self._reminders = []

    def load_reminders(self) -> None:
        """Loads all reminders from the calendar model.

        Notes
        -----
        This method should be called once at the start of the bot."""
        for event in self._calendar_model.calendar_data:
            if event.reminder:
                self._reminders.append(event.reminder)

    async def send_reminders(self) -> None:
        """|coro|

        Sends all reminders that are ready to be sent.
        """
        await asyncio.gather(*(method for method in self._reminder_methods))

    @property
    def _reminder_methods(
        self,
    ) -> Generator[Coroutine[Any, Any, None], None, None]:
        current_time = datetime.datetime.now()
        guild: Guild = self._bot.get_default_guild()  # type: ignore

        async def send_reminder(event: Event) -> None:
            reminder = event.reminder
            assert reminder is not None
            try:
                await reminder.send(ReminderGenerator(event, guild))
            except (InvalidSettingsFile, ValueError, DiscordException) as e:
                Console.specific(
                    f"An error occurred while sending the reminder for the event "
                    f"'{event.full_info}': {e}",
                    "Calendar",
                    FontColour.RED,
                    bold_type=True,
                )

        for event in self._calendar_model.calendar_data:
            reminder = event.reminder
            if reminder and reminder.datetime <= current_time and not reminder.is_sent:
                yield send_reminder(event)


@dataclass(slots=True, frozen=True)
class _ReminderSettings:
    plain_content: str
    embed_settings: _ReminderEmbedSettings

    @classmethod
    def load(cls, data: dict[str, Any]) -> _ReminderSettings:
        """Loads the reminder settings from the dictionary."""
        text = data["text"]
        embed = _ReminderEmbedSettings.load(data["embed"])
        return cls(text, embed)


@dataclass(slots=True, frozen=True)
class _ReminderEmbedSettings:
    @dataclass(slots=True, frozen=True)
    class _Thumbnail:
        url: str
        width: int
        height: int

    @dataclass(slots=True, frozen=True)
    class _Color:
        default: int
        use_role_color_if_single_was_pinged: bool

    @dataclass(slots=True, frozen=True)
    class _Field:
        name: str
        value: str
        inline: bool

    title: str
    description: str
    thumbnail: _Thumbnail
    color: _Color
    fields: dict[str, _Field]

    @classmethod
    def load(cls, data: dict[str, Any]) -> _ReminderEmbedSettings:
        """Loads the reminder embed settings from the dictionary."""
        title = data["title"]
        description = data["description"]
        thumbnail = cls._Thumbnail(**data["thumbnail"])
        color = cls._Color(**data["color"])
        fields = {k: cls._Field(**v) for k, v in data.get("fields", {}).items()}
        return cls(title, description, thumbnail, color, fields)


@dataclass(slots=True, frozen=True)
class ReminderGenerator:
    """Represents a reminder generator.

    Attributes
    ----------
    event: :class:`.Event`
        The event to generate the reminder for.
    guild: :class:`nextcord.Guild`
        The guild to send the reminder to.

    Class Attributes
    ----------------
    settings: :class:`_ReminderSettings`
        The reminder settings.

    Properties
    ----------
    preview_message: :class:`str`
        The preview message of the reminder.
    reminder: :class:`.Reminder`
        The reminder of the event.
    channel_to_send: :class:`nextcord.TextChannel`
        The channel to send the reminder to.
    roles_to_ping: list[:class:`nextcord.Role`]
        The roles to ping.
    plain_content: :class:`str`
        The plain content of the reminder.
    content: :class:`str`
        The content of the reminder.
    embed: :class:`nextcord.Embed`
        The embed of the reminder.
    """

    event: Event
    guild: Guild
    settings: ClassVar[_ReminderSettings] = field(init=False)

    def __post_init__(self) -> None:
        if self.event.reminder is None:
            raise ValueError("The event has no reminder")

    @property
    def preview_message(self) -> str:
        """The preview message of the reminder.

        Contains the reminder date, the channel to send the reminder to
        and the content of the reminder.
        """
        short_dt = format_dt(self.reminder.datetime, style="f")
        relative_dt = format_dt(self.reminder.datetime, style="R")
        return (
            f"Reminder date: {short_dt} ({relative_dt})\n"
            f"Channel: {self.channel_to_send.mention} \n\n"
            f"{self.content}"
        )

    @property
    def reminder(self) -> Reminder:
        """The reminder of the event."""
        return self.event.reminder  # type: ignore

    @property
    def channel_to_send(self) -> TextChannel:
        """The channel to send the reminder to."""
        return self.guild.get_channel(self.reminder.channel_id)  # type: ignore

    @property
    def roles_to_ping(self) -> list[Role]:
        """The roles to ping."""
        return list(filter(None, map(self.guild.get_role, self.reminder.role_ids)))

    @property
    def _color(self) -> int:
        """The color of the embed.

        If the event has only one role to ping and the setting is enabled,
        the color will be the same as the role color.
        Otherwise, the color will be the default one.
        """
        if (
            self.settings.embed_settings.color.use_role_color_if_single_was_pinged
            and len(roles := self.roles_to_ping) == 1
        ):
            return roles[0].color.value
        return self.settings.embed_settings.color.default

    @property
    def plain_content(self) -> str:
        """The plain content of the reminder.

        The plain content is the text that will be sent first and then replaced with the embed.

        It is useful for push reminders on mobile devices.
        """
        return self._replace_keywords(self.settings.plain_content)

    @property
    def content(self) -> str:
        """The content of the reminder."""
        return ", ".join(map(lambda i: i.mention, self.roles_to_ping))

    @property
    def embed(self) -> Embed:
        """The embed of the reminder."""
        embed = Embed(
            title=self.settings.embed_settings.title,
            description=self._description,
            color=self._color,
        )

        thumbnail = self.settings.embed_settings.thumbnail
        embed.set_thumbnail(url=thumbnail.url)
        embed.thumbnail.width = thumbnail.width
        embed.thumbnail.height = thumbnail.height

        fields = self.settings.embed_settings.fields
        datetime_field = fields["datetime"]
        datetime_all_day_field = fields["datetime_all_day"]
        location_field = fields["location"]
        more_info_field = fields["more_info"]

        if self.event.is_all_day:
            embed.add_field(
                name=datetime_all_day_field.name,
                value=self._replace_keywords(datetime_all_day_field.value),
                inline=datetime_all_day_field.inline,
            )
        else:
            embed.add_field(
                name=datetime_field.name,
                value=self._replace_keywords(datetime_field.value),
                inline=datetime_field.inline,
            )

        if self.event.location:
            embed.add_field(
                name=location_field.name,
                value=self._replace_keywords(location_field.value),
                inline=location_field.inline,
            )

        if self.reminder.more_info:
            embed.add_field(
                name=more_info_field.name,
                value=self._replace_keywords(more_info_field.value),
                inline=more_info_field.inline,
            )

        return embed

    @property
    def _description(self) -> str:
        return self.settings.embed_settings.description.replace(
            "{{CONTENT}}", self.reminder.content
        )

    def _replace_keywords(self, text: str) -> str:
        datetime_re = re.compile(r"{{DATETIME:([fFdDtTR])}}")
        text = datetime_re.sub(
            lambda match: format_dt(self.event.datetime, style=match.group(1)),  # type: ignore
            text,
        )

        keywords = {
            "DATETIME": (
                self.event.datetime.strftime("%d.%m.%Y")
                if self.event.is_all_day
                else self.event.datetime.strftime(Reminder.DT_FORMAT)
            ),
            "DESCRIPTION": self.event.description,
            "LOCATION": self.event.location,
            "MORE_INFO": self.reminder.more_info,
            "ROLES": " ".join(
                map(
                    lambda i: i.mention,
                    filter(None, map(self.guild.get_role, self.reminder.role_ids)),
                )
            ),
        }

        keyword_re = re.compile(r"{{(.*?)\??([A-Z\_]+)\??(.*?)}}", re.DOTALL)
        for match in keyword_re.finditer(text):
            keyword_value = keywords.get(match.group(2), "INVALID_KEYWORD")
            text = text.replace(
                match.group(0),
                (
                    ""
                    if not keyword_value
                    else f"{match.group(1)}{keyword_value}{match.group(3)}"
                ),
            )

        return text


@dataclass(slots=True)
class Reminder:  # pylint: disable=too-many-instance-attributes
    """Represents a reminder.

    Attributes
    ----------
    on_update: list[Callable[[Reminder], None]]
        The event that is invoked when the reminder is updated.

    Class Attributes
    ----------------
    DT_FORMAT: :class:`str`
        The datetime format.
    DT_FORMAT_PLACEHOLDER: :class:`str`
        The datetime format placeholder.

    Properties with setters
    ----------
    datetime: :class:`datetime.datetime`
        The datetime of the reminder.
    content: :class:`str`
        The content of the reminder.
    more_info: :class:`str`
        More information about the event.
    channel_id: :class:`int`
        The ID of the channel to send the reminder.
    role_ids: list[:class:`int`]
        The IDs of the roles to ping.

    Each property above has a setter that invokes the :attr:`.on_update` event.

    Properties
    ----------
    is_sent: :class:`bool`
        Whether the reminder has been sent.
    time_to_send: :class:`datetime.timedelta`
        The time to send the reminder.

    Methods
    -------
    get_channel(guild: :class:`nextcord.Guild`) -> :class:`nextcord.TextChannel` | `None`
        Gets the channel to send the reminder to.
    get_roles(guild: :class:`nextcord.Guild`) -> list[:class:`nextcord.Role`]
        Gets the roles to ping.
    get_sent_channel(guild: :class:`nextcord.Guild`) -> :class:`nextcord.TextChannel` | `None`
        Gets the channel the reminder has been sent to.
    get_sent_message(guild: :class:`nextcord.Guild`) -> :class:`nextcord.PartialMessage` | `None`
        Gets the message the reminder has been sent to.
    try_delete_sent_message(guild: :class:`nextcord.Guild`) -> :class:`None`
        Tries to delete the message the reminder has been sent to.
    send(generator: :class:`ReminderGenerator`) -> :class:`None`
        Sends the reminder.
    to_dict() -> :class:`dict`
        Converts the reminder to a dictionary.

    Class Methods
    -------------
    from_dict(data: :class:`dict`) -> :class:`Reminder`
        Creates a reminder from the dictionary.
    """

    _datetime_iso: str
    _datetime: datetime.datetime = field(init=False)
    _content: str
    _more_info: str
    _channel_id: int
    _role_ids: list[int]
    _sent_data: dict[str, Any]

    DT_FORMAT: ClassVar[str] = "%d.%m.%Y %H:%M"
    DT_FORMAT_PLACEHOLDER: ClassVar[str] = "dd.mm.yyyy hh:mm"

    on_update: list[Callable[[Reminder], None]] = field(
        init=False, default_factory=list
    )

    def __post_init__(self) -> None:
        self.datetime = datetime.datetime.fromisoformat(self._datetime_iso)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Reminder:
        """Creates a reminder from the dictionary."""
        try:
            return cls(
                data["datetime_iso"],
                data["content"],
                data["more_info"],
                data["channel_id"],
                data["role_ids"],
                data["sent_data"],
            )
        except KeyError as e:
            raise InvalidSettingsFile(f"Invalid reminder data: {e}") from e

    @property
    def datetime(self) -> datetime.datetime:
        """The datetime of the reminder."""
        return self._datetime

    @datetime.setter
    def datetime(self, value: datetime.datetime) -> None:
        self._datetime = value
        self._on_update_invoke()

    @property
    def content(self) -> str:
        """The content of the reminder."""
        return self._content

    @content.setter
    def content(self, value: str) -> None:
        self._content = value
        self._on_update_invoke()

    @property
    def more_info(self) -> str:
        """More information about the event."""
        return self._more_info

    @more_info.setter
    def more_info(self, value: str) -> None:
        self._more_info = value
        self._on_update_invoke()

    @property
    def channel_id(self) -> int:
        """The ID of the channel to send the reminder."""
        return self._channel_id

    @channel_id.setter
    def channel_id(self, value: int) -> None:
        self._channel_id = value
        self._on_update_invoke()

    @property
    def role_ids(self) -> list[int]:
        """The IDs of the roles to ping."""
        return self._role_ids

    @role_ids.setter
    def role_ids(self, value: list[int]) -> None:
        self._role_ids = value
        self._on_update_invoke()

    @property
    def is_sent(self) -> bool:
        """Whether the reminder has been sent."""
        return bool(self._sent_data)

    @property
    def time_to_send(self) -> datetime.timedelta:
        """The time to send the reminder."""
        return self.datetime - datetime.datetime.now()

    def reset_sent_data(self) -> None:
        """Resets the sent data."""
        self._sent_data = {}
        self._on_update_invoke()

    def get_channel(self, guild: Guild) -> TextChannel | None:
        """Gets the channel to send the reminder to.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild to get the channel from.

        Returns
        -------
        :class:`nextcord.TextChannel` | `None`
            The channel to send the reminder to.

        Raises
        ------
        ValueError
            The channel with the ID is not found or is not a text channel.
        """
        channel = guild.get_channel(self.channel_id)
        if channel is None:
            raise ValueError(f"Channel with ID {self.channel_id} not found")
        if not isinstance(channel, TextChannel):
            raise ValueError(f"Channel with ID {self.channel_id} is not a text channel")
        return channel

    def get_roles(self, guild: Guild) -> list[Role]:
        """Gets the roles to ping.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild to get the roles from.

        Returns
        -------
        list[:class:`nextcord.Role`]
            The roles to ping.

        Notes
        -----
        The roles that are not found will be filtered out.
        """
        return list(filter(None, map(guild.get_role, self.role_ids)))

    def get_sent_channel(self, guild: Guild) -> TextChannel | None:
        """Gets the channel the reminder has been sent to.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild to get the channel from.

        Returns
        -------
        :class:`nextcord.TextChannel` | `None`
            The channel the reminder has been sent to.
        """
        return guild.get_channel(self._sent_data.get("channel_id", 0))  # type: ignore

    async def get_sent_message(self, guild: Guild) -> PartialMessage | None:
        """|coro|

        Gets the message the reminder has been sent to.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild the reminder was sent in.

        Returns
        -------
        :class:`nextcord.PartialMessage` | `None`
            The message the reminder has been sent to.
        """
        if (channel := self.get_sent_channel(guild)) is None:
            return None
        return channel.get_partial_message(self._sent_data.get("message_id", 0))

    async def try_delete_sent_message(self, guild: Guild) -> None:
        """|coro|

        Tries to delete the message the reminder has been sent to.

        If the message has been deleted, the sent data will be cleared.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild the reminder was sent in.
        """
        if (message := await self.get_sent_message(guild)) is not None:
            try:
                await message.delete()
            except nextcord.NotFound:
                pass
            self._sent_data = {}

    async def send(self, generator: ReminderGenerator) -> None:
        """|coro|

        Sends the reminder.

        Parameters
        ----------
        generator: :class:`ReminderGenerator`
            The reminder generator.
        """
        channel = self.get_channel(generator.guild)
        assert isinstance(channel, TextChannel)

        msg = await channel.send(generator.plain_content)
        await msg.edit(content=generator.content, embed=generator.embed)
        self._sent_data = {"channel_id": channel.id, "message_id": msg.id}
        self._on_update_invoke()

    def to_dict(self) -> dict[str, Any]:
        """Converts the reminder to a dictionary.

        Returns
        -------
        :class:`dict`
            The dictionary representation of the reminder.
        """
        return {
            "datetime_iso": self.datetime.isoformat(),
            "content": self.content,
            "more_info": self.more_info,
            "channel_id": self.channel_id,
            "role_ids": self.role_ids,
            "sent_data": self._sent_data,
        }

    def _on_update_invoke(self) -> None:
        for func in self.on_update:
            func(self)


class ReminderModal(Modal):
    """A modal to set or edit a reminder for an event."""

    __slots__ = (
        "roles_to_ping_input",
        "channel_to_send_input",
        "datetime_input",
        "content_input",
        "more_info_input",
        "event",
        "guild",
        "_calendar_model",
    )

    roles_to_ping_input: TextInput
    channel_to_send_input: TextInput
    datetime_input: TextInput
    content_input: TextInput
    more_info_input: TextInput
    event: Event
    guild: Guild

    def __init__(self, event: Event, guild: Guild):
        title = ("Set" if event.reminder is None else "Edit") + " a reminder"
        super().__init__(title=title, timeout=None)

        self.event = event
        self.guild = guild
        reminder = event.reminder

        roles = filter(
            None,
            map(self.guild.get_role, reminder.role_ids if reminder else []),
        )
        self.roles_to_ping_input = TextInput(
            label="Roles to ping:",
            placeholder="Role names or IDs separated by a comma",
            default_value=(", ".join(map(str, roles))),
            required=False,
            max_length=512,
        )
        self.add_item(self.roles_to_ping_input)

        channel = self.guild.get_channel(reminder.channel_id) if reminder else None
        self.channel_to_send_input = TextInput(
            label="Channel to send:",
            placeholder="The channel name or ID",
            default_value=channel.name if channel else "",
            required=True,
            max_length=256,
        )
        self.add_item(self.channel_to_send_input)

        self.datetime_input = TextInput(
            label="Datetime to send:",
            placeholder=Reminder.DT_FORMAT_PLACEHOLDER,
            default_value=self._get_default_datetime().strftime(Reminder.DT_FORMAT),
            max_length=16,
            required=True,
        )
        self.add_item(self.datetime_input)

        self.content_input = TextInput(
            label="Content:",
            placeholder="The content (default: event description)",
            default_value=reminder.content if reminder else event.description,
            style=TextInputStyle.paragraph,
            required=True,
            max_length=1024,
        )
        self.add_item(self.content_input)

        self.more_info_input = TextInput(
            label="More informaton:",
            placeholder="More information about the event",
            default_value=reminder.more_info if reminder else "",
            style=TextInputStyle.paragraph,
            required=False,
            max_length=1024,
        )
        self.add_item(self.more_info_input)

    @InteractionUtils.with_info(
        catch_exceptions=[
            ValueError,
            UpdateEmbedError,
            ExceptionData(
                MissingPermission,
                with_traceback_in_log=False,
                with_traceback_in_response=False,
            ),
        ]
    )
    async def callback(self, interaction: Interaction) -> None:
        """The callback for the modal.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the modal.
        """
        member = interaction.user
        assert isinstance(member, Member)
        await interaction.response.defer()

        roles = self._find_roles(self.roles_to_ping_input.value or "")
        roles.sort(key=lambda i: i.position, reverse=True)

        channel = self._find_channel(self.channel_to_send_input.value or "")
        self._check_permissions(channel)

        if (datetime_value := self.datetime_input.value) is None:
            raise ValueError("The datetime is invalid.")
        dt = datetime.datetime.strptime(datetime_value, Reminder.DT_FORMAT)
        self._validate_datetime(dt)

        content = self.content_input.value or self.event.description
        more_info = self.more_info_input.value or ""

        old_reminder = self.event.reminder
        reminder = self._create_new_reminder(dt, content, more_info, channel, roles)
        self.event.reminder = reminder

        self._send_info_to_console(member, old_reminder, reminder)

        await asyncio.gather(
            *(
                self._send_response_with_preview(interaction),
                self._remove_reminder_if_sent(old_reminder),
            )
        )

    async def _remove_reminder_if_sent(self, reminder: Reminder | None) -> None:
        if reminder and reminder.is_sent:
            await reminder.try_delete_sent_message(self.guild)

    def _validate_datetime(self, dt: datetime.datetime) -> None:
        is_in_past = (
            dt.date() < datetime.datetime.now().date()
            if self.event.is_all_day
            else dt < datetime.datetime.now()
        )

        if is_in_past:
            raise ValueError("The datetime must be in the future.")
        if dt.date() > self.event.datetime.date():
            raise ValueError("The datetime must be before the event.")

    @staticmethod
    def _check_permissions(channel: TextChannel) -> None:
        needed_permissions = [
            "view_channel",
            "send_messages",
            "embed_links",
            "read_message_history",
            "read_messages",
        ]
        for permission in needed_permissions:
            if not getattr(channel.permissions_for(channel.guild.me), permission):
                raise MissingPermission(
                    f"Missing '{permission}' permission in {channel.mention}."
                )

    def _create_new_reminder(  # pylint: disable=too-many-arguments
        self,
        dt: datetime.datetime,
        content: str,
        more_info: str,
        channel: TextChannel,
        roles: list[Role],
    ) -> Reminder:
        return Reminder(
            dt.isoformat(),
            content,
            more_info,
            channel.id,
            list(map(lambda i: i.id, roles)),
            {},
        )

    def _get_default_datetime(self) -> datetime.datetime:
        if reminder := self.event.reminder:
            return reminder.datetime
        return max(
            (
                self.event.datetime - datetime.timedelta(days=1),
                datetime.datetime.now() + datetime.timedelta(minutes=5),
            )
        )

    def _send_info_to_console(
        self,
        member: Member,
        old_reminder: Reminder | None,
        new_reminder: Reminder,
    ) -> None:
        def get_reminder_info(reminder: Reminder) -> str:
            channel = reminder.get_channel(self.guild)
            channel_name = channel.name if channel else "Unknown channel"
            roles = reminder.get_roles(self.guild)
            return (
                f"({reminder.datetime.strftime(Reminder.DT_FORMAT)} | {channel_name}) "
                f"[{', '.join(map(str, roles))}] {reminder.content}"
            )

        msg = f"{member} "
        if old_reminder is None:
            msg += f"set a reminder for the event '{self.event.full_info}': "
        else:
            msg += (
                f"edited the reminder for the event '{self.event.full_info}': "
                f"'{get_reminder_info(old_reminder)}' -> "
            )
        msg += f"'{get_reminder_info(new_reminder)}'"
        Console.specific(msg, "Calendar", FontColour.GREEN, bold_type=True)

    async def _send_response_with_preview(self, interaction: Interaction) -> None:
        guild = interaction.guild
        assert guild is not None

        generator = ReminderGenerator(self.event, guild)

        await interaction.followup.send(
            f"**The reminder has been set.**\n\n{generator.preview_message}",
            embed=generator.embed,
            ephemeral=True,
        )

    def _find_channel(self, form_input: str) -> TextChannel:
        matcher = Matcher(self.guild.text_channels, ignore_case=True)
        match = matcher.match_max(form_input, key=lambda i: i.name)
        return match.item

    def _find_roles(self, form_input: str) -> list[Role]:
        smart_dict = SmartDict[Role, float](lambda a, b: a > b)
        matcher = Matcher[Role](self.guild.roles, ignore_case=True)

        for data in filter(None, form_input.split(",")):
            match_by_id = matcher.match_max(data, key=lambda i: str(i.id))
            if match_by_id.ratio == 1.0:
                smart_dict[match_by_id.item] = match_by_id.ratio
                continue

            matches_by_name = matcher.match_all(data, key=lambda i: i.name)
            if (max_ratio := max(map(lambda i: i.ratio, matches_by_name))) <= 0.2:
                continue
            threshold = max_ratio * 0.9

            for match in matches_by_name:
                if match.ratio >= threshold:
                    smart_dict[match.item] = match.ratio

        return list(sorted(smart_dict.keys()))


def setup(bot: UniversityBot):
    """Loads the CalendarCog cog."""
    bot.add_cog(CalendarCog(bot))
