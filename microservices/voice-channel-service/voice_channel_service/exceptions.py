"""
Voice Channel Service Exceptions Module

Defines custom exceptions for the Voice Channel Service,
including domain-specific errors related to voice channel management.
"""

from datetime import datetime
from typing import Any

from shared.models.voice_channel import VoiceChannelErrorCode


class DomainException(Exception):
    """Base for all domain errors carrying HTTP status and error-code.

    Attributes
    ----------
    status_code : int
        The HTTP status code for the error.
    error_code : VoiceChannelErrorCode | str
        The specific error code for the voice channel operation.
    message : str | None
        An optional human-readable message describing the error.
    """

    status_code: int
    error_code: VoiceChannelErrorCode | str
    message: str | None

    def __init__(
        self,
        *,
        status_code: int,
        error_code: VoiceChannelErrorCode | str,
        message: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        for k, v in kwargs.items():
            setattr(self, k, v)


class ChannelNotManaged(DomainException):
    """Exception raised when a channel is not managed by the voice channel service.

    Attributes
    ----------
    status_code : int
        HTTP status code 404 Not Found.
    error_code : VoiceChannelErrorCode
        VoiceChannelErrorCode.CHANNEL_NOT_MANAGED.
    """

    def __init__(self):
        super().__init__(
            status_code=404,
            error_code=VoiceChannelErrorCode.CHANNEL_NOT_MANAGED,
        )


class RenameLimitExceeded(DomainException):
    """Exception raised when the rename limit for a voice channel is exceeded.

    Attributes
    ----------
    status_code : int
        HTTP status code 429 Too Many Requests.
    error_code : VoiceChannelErrorCode
        VoiceChannelErrorCode.RENAME_LIMIT_EXCEEDED.
    """

    def __init__(self, reset_at: datetime):
        super().__init__(
            status_code=429,
            error_code=VoiceChannelErrorCode.RENAME_LIMIT_EXCEEDED,
            cooldown_reset_at=reset_at,
        )
