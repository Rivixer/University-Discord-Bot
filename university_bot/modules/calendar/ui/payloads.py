# SPDX-License-Identifier: MIT
"""A module providing payloads for the calendar UI."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nextcord import Locale

    from university_bot import Interaction

    from ..config import CalendarDataConfig
    from ..models import Event, RawEvent

__all__ = (
    "AddEventPayload",
    "CopyEventPayload",
    "EditEventPayload",
    "EventInformationModalPayload",
    "SummaryEventPayload",
)


@dataclass(slots=True, frozen=True)
class AddEventPayload:
    """A payload for adding a new event.

    Attributes
    ----------
    raw_event: :class:`.RawEvent`
        The raw event to add.
    locale: :class:`nextcord.Locale`
        The locale of the user.
    config: :class:`.CalendarDataConfig`
        The calendar data configuration.
    """

    raw_event: RawEvent
    locale: Locale
    config: CalendarDataConfig


@dataclass(slots=True, frozen=True)
class EditEventPayload:
    """A payload for editing an event.

    Attributes
    ----------
    event_id: :class:`str`
        The ID of the event to edit.
    raw_event: :class:`.RawEvent`
        The raw event to edit.
    locale: :class:`nextcord.Locale`
        The locale of the user.
    config: :class:`.CalendarDataConfig`
        The calendar data configuration.
    """

    event_id: str
    raw_event: RawEvent
    locale: Locale
    config: CalendarDataConfig


@dataclass(slots=True, frozen=True)
class CopyEventPayload:
    """A payload for copying an event.

    Attributes
    ----------
    raw_event: :class:`.RawEvent`
        The raw event to copy.
    locale: :class:`nextcord.Locale`
        The locale of the user.
    config: :class:`.CalendarDataConfig`
        The calendar data configuration."""

    raw_event: RawEvent
    locale: Locale
    config: CalendarDataConfig


@dataclass(slots=True, frozen=True)
class SummaryEventPayload:
    """A payload for displaying a summary of an event.

    Attributes
    ----------
    event: :class:`.Event`
        The event to display.
    index: :class:`int`
        The index of the event.
    total: :class:`int`
        The total number of events.
    locale: :class:`nextcord.Locale`
        The locale of the user.
    config: :class:`.CalendarDataConfig`
        The calendar data configuration.
    """

    event: Event
    index: int
    total: int
    locale: Locale
    config: CalendarDataConfig
    raw_event: RawEvent = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_event", self.event.to_raw(self.config))


@dataclass(slots=True, frozen=True)
class EventInformationModalPayload:
    """A payload for the event information modal.

    Attributes
    ----------
    raw_event: :class:`.RawEvent`
        The raw event to fill the modal with.
    locale: :class:`nextcord.Locale`
        The locale of the user.
    config: :class:`.CalendarDataConfig`
        The calendar data configuration.
    refresh_method: Callable[[:class:`Interaction`], Awaitable[`None`]]
    """

    raw_event: RawEvent
    locale: Locale
    config: CalendarDataConfig
    refresh_method: Callable[[Interaction], Awaitable[None]]
