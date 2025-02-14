# SPDX-License-Identifier: MIT
"""A module providing data transfer objects for the calendar."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, Date, String, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column

from .config import EventFieldLimits

__all__ = ("EventDTO",)

Base = declarative_base()


class EventDTO(Base):  # pylint: disable=too-few-public-methods
    """Represents an event stored in the SQL database."""

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

    def __repr__(self) -> str:
        """Returns a string representation of the event."""
        return (
            f"<Event(id={self.id}, "
            f"date={self.date}, "
            f"time={self.time}, "
            f"description={self.description})>"
        )
