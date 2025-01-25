# SPDX-License-Identifier: MIT
"""A module to define the voice channel manager exceptions."""


class VoiceChannelManagerException(Exception):
    """Base exception for voice channel manager errors."""


class InvalidConfiguration(VoiceChannelManagerException):
    """An exception raised when the configuration is invalid.

    Subclass of :exc:`VoiceChannelManagerException`.
    """


class MissingPermissions(VoiceChannelManagerException):
    """An exception raised when the bot lacks required permissions.

    Subclass of :exc:`VoiceChannelManagerException`.
    """


class UnmanagedCategory(VoiceChannelManagerException):
    """An exception raised when the category is wrong.

    Subclass of :exc:`VoiceChannelManagerException`.
    """


class RateLimitExceeded(VoiceChannelManagerException):
    """An exception raised when the rate limit is exceeded.

    Subclass of :exc:`VoiceChannelManagerException`.
    """
