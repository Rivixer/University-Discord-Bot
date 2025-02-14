# SPDX-License-Identifier: MIT
"""A module providing enums for the calendar UI."""

from enum import Enum, auto

__all__ = ("EventSummaryNavigation",)


class EventSummaryNavigation(Enum):
    """Represents the navigation options for the event summary."""

    FIRST = auto()
    PREVIOUS = auto()
    NEXT = auto()
    LAST = auto()
