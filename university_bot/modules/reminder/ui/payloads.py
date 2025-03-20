# SPDX-License-Identifier: MIT
"""A module providing payloads for the reminder UI."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nextcord import Locale

    from university_bot import EmbedDict, Interaction

    from ..models import RawReminder, Reminder
    from ..service import ReminderService
    from ...calendar import CalendarDataConfig, Event, RawEvent


@dataclass(slots=True, frozen=True)
class ReminderPayload:
    """A payload for adding a reminder.

    Attributes
    ----------
    reminder: :class:`.Reminder` | :class:`.RawReminder`
        The reminder to display.
    event: :class:`.Event` | :class:`.RawEvent`
        The event associated with the reminder.
    service: :class:`.ReminderService`
        The reminder service.
    """

    reminder: Reminder | RawReminder
    event: Event | RawEvent
    service: ReminderService

    @property
    def embed_dict(self) -> EmbedDict:
        """The embed dictionary for the payload."""
        return self.service.data.embed.to_dict()  # type: ignore


@dataclass(slots=True, frozen=True)
class ConfigReminderPayload(ReminderPayload):
    """A payload for configuring a reminder.

    Attributes
    ----------
    reminder: :class:`.RawReminder`
        The reminder to display.
    event: :class:`.RawEvent` | :class:`.Event`
        The event associated with the reminder.
    index: :class:`int`
        The index of the event.
    total: :class:`int`
        The total number of events.
    locale: :class:`nextcord.Locale`
        The locale to use for localization.
    guild_id: :class:`int`
        The ID of the guild.
    """

    reminder: RawReminder
    locale: Locale
    guild_id: int


@dataclass(slots=True, frozen=True)
class SummaryReminderPayload(ConfigReminderPayload):
    """A payload for displaying a summary of a reminder.

    Attributes
    ----------
    reminder: :class:`.RawReminder`
        The reminder to display.
    locale: :class:`nextcord.Locale`
        The locale to use for localization.
    guild_id: :class:`int`
        The ID of the guild.
    event: :class:`.RawEvent`
        The event associated with the reminder.
    index: :class:`int`
        The index of the event.
    total: :class:`int`
        The total number of events.
    """

    event: RawEvent
    index: int
    total: int


@dataclass(slots=True, frozen=True)
class ReminderInformationModalPayload:
    """A payload for the reminder information modal.

    Attributes
    ----------
    reminder: :class:`.RawReminder`
        The raw reminder to fill the modal with.
    locale: :class:`nextcord.Locale`
        The locale of the user.
    calendar_data: :class:`.CalendarDataConfig`
        The calendar data configuration.
    refresh_method: Callable[[:class:`Interaction`], Awaitable[`None`]]
        The method to refresh the view.
    """

    reminder: RawReminder
    locale: Locale
    calendar_data: CalendarDataConfig
    refresh_method: Callable[[Interaction], Awaitable[None]]
