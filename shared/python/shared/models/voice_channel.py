"""
Voice Channel Models

Defines the data models used in the voice channel service.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from .error_response import ErrorResponse


class VoiceChannelErrorCode(str, Enum):
    """Enumeration of error codes used in error responses.

    Attributes
    ----------
    UNKNOWN_ERROR : str
        An unknown error.
    CHANNEL_NOT_MANAGED : str
        The channel is not managed.
    RENAME_LIMIT_EXCEEDED : str
        The rename limit has been exceeded.
    """

    UNKNOWN_ERROR = "unknown_error"
    CHANNEL_NOT_MANAGED = "channel_not_managed"
    RENAME_LIMIT_EXCEEDED = "rename_limit_exceeded"


class RenameLimitExceededErrorResponse(ErrorResponse):
    """Error response for when the rename limit has been exceeded.

    Attributes
    ----------
    error_code : str
        The error code indicating the type of error.
        Should be "max_renames_reached".
    message : str
        An optional human-readable message describing the error.
    cooldown_reset_at : datetime | None
        The time when the rename cooldown resets,
        or None if no cooldown is active.

    """

    error_code: str = VoiceChannelErrorCode.RENAME_LIMIT_EXCEEDED
    cooldown_reset_at: datetime | None = None


class IsManagedResponse(BaseModel):
    """Response model for checking if a channel or category is managed.

    Attributes
    ----------
    is_managed : bool
        Indicates whether the channel or category is managed.
    """

    is_managed: bool


class RenameChannelRequest(BaseModel):
    """Request model for renaming a voice channel.

    Attributes
    ----------
    guild_id : int
        The ID of the guild where the channel is located.
    channel_id : int
        The ID of the channel to rename.
    new_name : str
        The new name for the channel.
    """

    guild_id: int
    channel_id: int
    new_name: str


class RenameStatusResponse(BaseModel):
    """Response model for the rename status of a voice channel.

    Attributes
    ----------
    remaining_renames : int
        The number of renames left in the current window.
    max_remaining_renames : int
        The maximum number of renames allowed in the current window.
    cooldown_reset_at : datetime | None
        The time when the rename cooldown resets,
        or None if no cooldown is active.
    """

    remaining_renames: int
    max_remaining_renames: int
    cooldown_reset_at: datetime | None = None


class RenameChannelResponse(BaseModel):
    """Response model for renaming a voice channel.

    Attributes
    ----------
    success : bool
        Indicates whether the rename operation was successful.
    remaining_renames : int
        The number of renames left in the current 10-minute window.
    cooldown_reset_at : datetime | None
        The time when the rename cooldown resets,
        or None if no cooldown is active.
    """

    success: bool
    remaining_renames: int
    max_remaining_renames: int
    cooldown_reset_at: datetime | None = None
