# SPDX-License-Identifier: MIT
"""A module to define enums for the verification cog."""

from enum import StrEnum

__all__ = ("VerificationType",)


class VerificationType(StrEnum):
    """Represents a verification type."""

    TARGET = "target"
    INTERNAL = "internal"
    EXTERNAL = "external"
