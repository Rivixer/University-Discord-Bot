# SPDX-License-Identifier: MIT
"""A module providing models for the reminder."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .dto import ReminderDTO

if TYPE_CHECKING:
    from ..calendar import CalendarDataConfig


@dataclass(slots=True, frozen=True)
class Reminder:  # pylint: disable=too-many-instance-attributes
    """Represents a reminder model.

    Attributes
    ----------
    id: :class:`str`
        The unique identifier of the reminder.
    event_id: :class:`str`
        The unique identifier of the event associated with the reminder.
    datetime: :class:`datetime.datetime`
        The date and time of the reminder.
    description: :class:`str`
        The description of the reminder.
    additional_info: :class:`str`
        Additional information about the reminder.
    event: :class:`Event`
        The event associated with the reminder.
    channel_id: :class:`int`
        The ID of the channel to send the reminder.
    role_ids: list[:class:`int`]
        The IDs of the roles to mention when sending the reminder.
    message_id: :class:`int` | `None`
        The ID of the message sent for the reminder.
    """

    id: str
    event_id: str
    datetime: datetime.datetime
    description: str
    additional_info: str | None
    channel_id: int
    role_ids: list[int] = field(default_factory=list)
    message_id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "datetime", self.datetime.replace(microsecond=0))

    def to_dto(self) -> ReminderDTO:
        """Converts the reminder to a data transfer object."""
        return ReminderDTO(
            id=self.id,
            event_id=self.event_id,
            datetime=self.datetime,
            description=self.description,
            additional_info=self.additional_info,
            channel_id=self.channel_id,
            role_ids=self.role_ids,
            message_id=self.message_id,
        )

    @classmethod
    def from_dto(cls, dto: ReminderDTO) -> Reminder:
        """Converts the data transfer object to a reminder.

        Parameters
        ----------
        dto: :class:`.ReminderDTO`
            The data transfer object.
        """
        return cls(
            id=dto.id,
            event_id=dto.event_id,
            datetime=dto.datetime,
            description=dto.description,
            additional_info=dto.additional_info,
            channel_id=dto.channel_id,
            role_ids=dto.role_ids,
            message_id=dto.message_id,
        )

    def to_raw(self, config: CalendarDataConfig) -> RawReminder:
        """Converts the reminder to a raw reminder.

        Parameters
        ----------
        config: :class:`.CalendarDataConfig`
            The calendar configuration.

        Returns
        -------
        :class:`.RawReminder`
            The raw reminder.
        """
        return RawReminder(
            config,
            date=config.format_input_date(self.datetime.date()),
            time=config.format_input_time(self.datetime.time()),
            description=self.description,
            additional_info=self.additional_info,
            channel_id=self.channel_id,
            role_ids=self.role_ids,
            message_id=self.message_id,
        )


@dataclass(slots=True)
class RawReminder:  # pylint: disable=too-many-instance-attributes
    """Represents a raw reminder model."""

    config: CalendarDataConfig
    date: str | None
    time: str | None
    description: str | None
    additional_info: str | None
    channel_id: int | None
    role_ids: list[int]
    message_id: int | None

    @classmethod
    def default(cls, config: CalendarDataConfig) -> RawReminder:
        """Creates a default raw reminder.

        Parameters
        ----------
        config: :class:`.CalendarDataConfig`
            The calendar configuration.
        """
        return cls(
            config=config,
            date=None,
            time=None,
            description=None,
            additional_info=None,
            channel_id=None,
            role_ids=[],
            message_id=None,
        )

    def is_valid(self) -> bool:
        """Checks if the raw reminder is valid."""
        return (
            bool(self.description)
            and self.is_date_valid()
            and self.is_time_valid()
            and self.channel_id is not None
        )

    @property
    def sent(self) -> bool:
        """:class:`bool`: Whether the reminder has been sent."""
        return self.message_id is not None

    def is_datetime_in_past(self) -> bool | None:
        """Checks if the datetime is in the past.

        Returns
        -------
        :class:`bool` | `None`
            ``True`` if the datetime is in the past,
            ``False`` if in the future,
            or ``None`` if not provided.
        """
        if not self.parsed_datetime:
            return None
        return self.parsed_datetime < datetime.datetime.now()

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
        The parsed date of the reminder or `None` if not provided.

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
        The parsed time of the reminder or `None` if not provided.

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
        The parsed datetime of the reminder or `None` if not provided.

        Raises
        ------
        ValueError
            If the date or time is invalid.
        """
        if not self.parsed_date or not self.parsed_time:
            return None
        return datetime.datetime.combine(self.parsed_date, self.parsed_time)

    def to_reminder(
        self,
        event_id: str,
        id_: str | None,
    ) -> Reminder:
        """Converts the raw reminder to a reminder model.

        Parameters
        ----------
        event_id: :class:`str`
            The unique identifier of the event associated with the reminder.
        id_: :class:`str`
            The unique identifier of the reminder.
            If ``None``, a new one will be generated.

        Returns
        -------
        :class:`.Reminder`
            The created reminder model.

        Raises
        ------
        ValueError
            If the raw reminder is invalid.
        """
        if not self.description:
            raise ValueError("Description is required.")

        if not self.parsed_date or not self.parsed_time:
            raise ValueError("Date and time are required.")

        if not self.channel_id:
            raise ValueError("Channel ID is required.")

        if not self.is_valid():
            raise ValueError("Invalid raw reminder.")

        return Reminder(
            id=id_ or str(uuid.uuid4()),
            event_id=event_id,
            description=self.description,
            additional_info=self.additional_info,
            channel_id=self.channel_id,
            role_ids=self.role_ids,
            datetime=datetime.datetime.combine(self.parsed_date, self.parsed_time),
            message_id=self.message_id,
        )
