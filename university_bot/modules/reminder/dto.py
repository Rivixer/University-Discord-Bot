# SPDX-License-Identifier: MIT
"""A module providing data transfer objects for the calendar."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import ReminderFieldLimits
from ..calendar.dto import CalendarBase, EventDTO

__all__ = ("ReminderDTO",)


class ReminderDTO(CalendarBase):  # pylint: disable=too-few-public-methods
    """Represents a reminder stored in the SQL database.

    Attributes
    ----------
    id: :class:`str`
        The unique identifier of the reminder.
    event_id: :class:`str`
        The unique identifier of the event associated with the reminder.
    description: :class:`str`
        The description of the reminder.
    additional_info: :class:`str`
        Additional information about the reminder.
    datetime: :class:`datetime.datetime`
        The date and time of the reminder.
    channel_id: :class:`int`
        The ID of the channel to send the reminder.
    event: :class:`.EventDTO`
        The event associated with the reminder.
    sent: :class:`bool`
        Whether the reminder has been sent.
    role_ids: list[:class:`int`]
        The IDs of the roles to mention when sending the reminder.
    """

    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(ReminderFieldLimits.DESCRIPTION),
        nullable=False,
    )
    additional_info: Mapped[str | None] = mapped_column(
        String(ReminderFieldLimits.ADDITIONAL_INFO),
        nullable=True,
    )
    datetime: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    channel_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    _role_ids: Mapped[list[int] | None] = mapped_column(
        "role_ids",
        JSON,
        nullable=False,
        default=list,
        server_default=text("[]"),
    )
    message_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )

    event: Mapped[EventDTO] = relationship("EventDTO", back_populates="reminders")

    @property
    def role_ids(self):
        """list[:class:`int`]: The IDs of the roles to mention when sending the reminder."""
        return self._role_ids if self._role_ids is not None else []

    @role_ids.setter
    def role_ids(self, value: list[int]):
        self._role_ids = value

    def __repr__(self) -> str:
        return (
            f"<ReminderDTO id={self.id!r} event_id={self.event_id!r} "
            f"description={self.description!r} datetime={self.datetime!r} "
            f"message_id={self.message_id!r}>"
        )
