# SPDX-License-Identifier: MIT
"""A module providing data transfer objects for the calendar."""

from __future__ import annotations

import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, String, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import EventFieldLimits

if TYPE_CHECKING:
    from ..reminder.dto import ReminderDTO

__all__ = ("EventDTO", "CalendarBase")

CalendarBase = declarative_base()


class EventDTO(CalendarBase):  # pylint: disable=too-few-public-methods
    """Represents an event stored in the SQL database.

    Attributes
    ----------
    id: :class:`str`
        The unique identifier of the event.
    description: :class:`str`
        The description of the event.
    date: :class:`datetime.date`
        The date of the event.
    time: :class:`datetime.time`
        The time of the event.
    prefix: :class:`str`
        The prefix of the event.
    location: :class:`str`
        The location of the event.
    is_hidden: :class:`bool`
        Whether the event is hidden.
    reminders: list[:class:`ReminderDTO`]
        The reminders associated with the event.
    """

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    description: Mapped[str] = mapped_column(
        String(EventFieldLimits.DESCRIPTION),
        nullable=False,
    )
    date: Mapped[datetime.date] = mapped_column(
        Date,
        nullable=False,
    )
    time: Mapped[datetime.time | None] = mapped_column(
        Time,
        nullable=True,
    )
    prefix: Mapped[str] = mapped_column(
        String(EventFieldLimits.PREFIX),
        nullable=True,
    )
    location: Mapped[str] = mapped_column(
        String(EventFieldLimits.LOCATION),
        nullable=True,
    )
    is_hidden: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    reminders: Mapped[list[ReminderDTO]] = relationship(
        "ReminderDTO",
        back_populates="event",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Returns a string representation of the event."""
        return (
            f"<Event(id={self.id}, "
            f"date={self.date}, "
            f"time={self.time}, "
            f"description={self.description})>"
        )
