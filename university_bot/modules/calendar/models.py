# SPDX-License-Identifier: MIT
"""A module providing models for the calendar."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from babel.dates import format_date

from .dto import EventDTO

if TYPE_CHECKING:
    from nextcord import Locale

    from .config import CalendarDataConfig
    from ..reminder import RawReminder, Reminder, ReminderService

__all__ = (
    "Event",
    "RawEvent",
)


@dataclass(slots=True, frozen=True)
class Event:  # pylint: disable=too-many-instance-attributes
    """Represents an event in the calendar."""

    id: str
    description: str
    date: datetime.date
    time: datetime.time | None
    prefix: str | None
    location: str | None
    is_hidden: bool
    reminders: list[Reminder] = field(default_factory=list)

    @staticmethod
    def compare_datetime_method(event1: Event, event2: Event) -> int:
        """Compares events by date and time."""
        if event1.datetime < event2.datetime:
            return -1
        if event1.datetime > event2.datetime:
            return 1
        return 0

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Event):
            return NotImplemented
        return self.id == value.id

    @property
    def datetime(self) -> datetime.datetime:
        """:class:`datetime.datetime`: The date and time of the event.

        If the time is not provided, the time is set to midnight.
        """
        return (
            datetime.datetime.combine(self.date, self.time)
            if self.time
            else datetime.datetime.combine(self.date, datetime.time.min)
        )

    @property
    def is_all_day(self) -> bool:
        """:class:`bool`: Whether the event is an all-day event.

        An event is considered an all-day event if the time is not provided.
        """
        return self.time is None

    def to_dto(self) -> EventDTO:
        """Converts the event to a data transfer object."""
        return EventDTO(
            id=self.id,
            description=self.description,
            date=self.date,
            time=self.time,
            prefix=self.prefix,
            location=self.location,
            is_hidden=self.is_hidden,
        )

    @classmethod
    def from_dto(cls, dto: EventDTO) -> Event:
        """Converts the data transfer object to an event."""
        return cls(
            id=dto.id,
            description=dto.description,
            date=dto.date,
            time=dto.time,
            prefix=dto.prefix,
            location=dto.location,
            is_hidden=dto.is_hidden,
        )

    def to_raw(self, config: CalendarDataConfig) -> RawEvent:
        """Converts the event to a raw event.

        Parameters
        ----------
        config: :class:`.CalendarDataConfig`
            The calendar configuration.

        Returns
        -------
        :class:`.RawEvent`
            The raw event.
        """
        return RawEvent(
            config,
            self.description,
            config.format_input_date(self.date),
            config.format_input_time(self.time) if self.time else None,
            self.prefix,
            self.location,
            self.is_hidden,
            [r.to_raw(config) for r in self.reminders],
        )

    def to_calendar_repr(
        self,
        config: CalendarDataConfig,
        *,
        with_indent: bool = False,
    ) -> str:
        """Returns a string representation of the event for the calendar view.

        Parameters
        ----------
        config: :class:`.CalendarDataConfig`
            The calendar configuration.

        Returns
        -------
        :class:`str`
            The string representation of the event.
        """

        repr_format = config.event_repr_format
        parts: list[str] = [repr_format.indent] if with_indent else []

        if self.prefix:
            parts.append(repr_format.prefix.format(prefix=self.prefix))

        parts.append(repr_format.description.format(description=self.description))

        if self.time:
            formatted_time = config.format_repr_time(self.time)
            parts.append(repr_format.time.format(time=formatted_time))

        if self.location:
            parts.append(repr_format.location.format(location=self.location))

        return "".join(parts)

    async def fetch_reminders(self, service: ReminderService) -> None:
        """Fetches the reminders associated with the event.

        Parameters
        ----------
        service: :class:`.ReminderService`
            The reminder service.
        """
        object.__setattr__(self, "reminders", await service.get_reminders(self.id))


@dataclass(slots=True)
class RawEvent:  # pylint: disable=too-many-instance-attributes
    """Represents a raw event."""

    config: CalendarDataConfig
    description: str | None
    date: str | None
    time: str | None
    prefix: str | None
    location: str | None
    is_hidden: bool
    reminders: list[RawReminder] = field(default_factory=list)

    @classmethod
    def default(cls, config: CalendarDataConfig) -> RawEvent:
        """Creates a default raw event."""
        return cls(
            config=config,
            description=None,
            date=None,
            time=None,
            prefix=None,
            location=None,
            is_hidden=False,
        )

    def is_valid(self) -> bool:
        """Checks if the raw event is valid
        and can be converted to an event.

        Returns
        -------
        :class:`bool`
            ``True`` if the raw event is valid, ``False`` otherwise.
        """
        try:
            return (
                bool(self.description)
                and self.is_date_valid()
                and (not self.time or self.is_time_valid())
            )
        except ValueError:
            return False

    def is_date_valid(self) -> bool:
        """Checks if the date is valid.

        Returns
        -------
        :class:`bool`
            ``True`` if the date is valid, ``False`` otherwise.
        """
        try:
            _ = self.parsed_date
            return True
        except (ValueError, IndexError):
            return False

    def is_time_valid(self) -> bool:
        """Checks if the time is valid.

        Returns
        -------
        :class:`bool`
            ``True`` if the time is valid, ``False`` otherwise.
        """
        try:
            _ = self.parsed_time
            return True
        except (ValueError, IndexError):
            return False

    @property
    def parsed_date(self) -> datetime.date | None:
        """:class:`datetime.date` | `None`:
        The parsed date of the event or `None` if not provided.

        Raises
        ------
        ValueError
            If the date is invalid.
        """
        if not self.date:
            return None
        return self.config.parse_input_date(self.date)

    @property
    def parsed_time(self) -> datetime.time | None:
        """:class:`datetime.time` | `None`:
        The parsed time of the event or `None` if not provided.

        Raises
        ------
        ValueError
            If the time is invalid.
        """
        if not self.time:
            return None
        return self.config.parse_input_time(self.time)

    @property
    def parsed_datetime(self) -> datetime.datetime | None:
        """:class:`datetime.datetime` | `None`:
        The parsed date and time of the event.

        If the time is not provided, the time is set to midnight.

        If the date or time is invalid, ``None`` is returned.

        Raises
        ------
        ValueError
            If the date or time is invalid.
        """
        if not self.parsed_date:
            return None

        if not self.parsed_time:
            return datetime.datetime.combine(self.parsed_date, datetime.time.min)

        return datetime.datetime.combine(self.parsed_date, self.parsed_time)

    @property
    def is_all_day(self) -> bool:
        """:class:`bool`: Whether the event is an all-day event.

        An event is considered an all-day event if the time is not provided.
        """
        return self.time is None

    def get_weekday(self, locale: Locale) -> str | None:
        """Returns the weekday of the event.

        Parameters
        ----------
        locale: :class:`nextcord.Locale`
            The locale of the user.

        Returns
        -------
        :class:`str` | `None`
            The weekday of the event or `None` if the date is not provided or invalid.
        """
        if not self.is_date_valid() or not self.parsed_date:
            return None
        return format_date(self.parsed_date, "EEEE", locale=locale)

    def to_event(self, id_: str | None) -> Event:
        """Converts the raw event to an event.

        Parameters
        ----------
        id_: :class:`str`
            The ID of the event. If ``None``, a new ID is generated.

        Returns
        -------
        :class:`.Event`
            The event.

        Raises
        ------
        ValueError
            If the ``description`` or ``date`` is not provided,
            or if the raw event is invalid.
        """
        if not self.description:
            raise ValueError("Description is required.")

        if not self.parsed_date:
            raise ValueError("Date is required.")

        if not self.is_valid():
            raise ValueError("Invalid raw event.")

        return Event(
            id=id_ or str(uuid.uuid4()),
            description=self.description,
            date=self.parsed_date,
            time=self.parsed_time,
            prefix=self.prefix,
            location=self.location,
            is_hidden=self.is_hidden,
        )
