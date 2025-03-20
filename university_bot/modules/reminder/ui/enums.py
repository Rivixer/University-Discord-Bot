# SPDX-License-Identifier: MIT
"""A module provides enums for the reminder UI."""

from enum import Enum, auto


class ReminderSummaryNavigation(Enum):
    """An enumeration for the summary navigation."""

    FIRST = auto()
    PREVIOUS = auto()
    NEXT = auto()
    LAST = auto()
