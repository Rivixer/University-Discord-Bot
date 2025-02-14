# SPDX-License-Identifier: MIT
"""A module providing enums for the calendar."""

from enum import Flag

__all__ = ("EventVisibility",)


class EventVisibility(Flag):
    """Represents the visibility options for events."""

    VISIBLE = 1
    HIDDEN = 2
    ALL = VISIBLE | HIDDEN
