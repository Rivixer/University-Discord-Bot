# SPDX-License-Identifier: MIT
"""A module providing utilities for the calendar."""

from __future__ import annotations

from collections import defaultdict
from functools import cmp_to_key
from typing import TYPE_CHECKING

from .models import Event

if TYPE_CHECKING:
    import datetime

__all__ = (
    "group_events_by_date",
    "sorted_events",
)


def group_events_by_date(
    events: list[Event],
) -> dict[datetime.date, list[Event]]:
    """Groups events by their date.

    Parameters
    ----------
    events: Sequence[:class:`.Event`]
        The list of events to be grouped.

    Returns
    -------
    dict[datetime.date, list[:class:`Event`]]
        A dictionary where keys are event dates,
        and values are lists of events on those dates.
    """
    grouped_events: dict[datetime.date, list[Event]] = defaultdict(list)
    for event in events:
        grouped_events[event.date].append(event)
    return grouped_events


def sorted_events(events: list[Event]) -> list[Event]:
    """Returns a sorted list of events by date and time in ascending order.

    Parameters
    ----------
    events: list[:class:`.Event`]
        The list of events to be sorted.

    Returns
    -------
    list[:class:`.Event`]
        The sorted list of events.

    Note
    ----
    Events are sorted by :meth:`.Event.compare_datetime_method`.
    """
    return sorted(events, key=cmp_to_key(Event.compare_datetime_method))
