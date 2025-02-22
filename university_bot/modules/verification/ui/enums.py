# SPDX-License-Identifier: MIT
"""A module to define enums for the verification cog."""

from enum import Enum, auto

__all__ = ("CodeStatus",)


class CodeStatus(Enum):
    """Enum for the status of a verification code."""

    UNKNOWN = auto()
    VALID = auto()
    INVALID = auto()
    UNNECESSARY = auto()
