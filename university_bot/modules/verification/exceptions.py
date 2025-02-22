# SPDX-License-Identifier: MIT
"""A module to define exceptions for the verification cog."""

__all__ = (
    "VerificationError",
    "MissingPermissionsError",
    "DisabledFeatureError",
    "VerificationFailedError",
    "MailSystemError",
    "SMTPError",
    "SMTPLoginError",
    "SMTPSendError",
    "MailGeneratorError",
)


class VerificationError(Exception):
    """A base class for verification errors."""


class MissingPermissionsError(VerificationError):
    """An error raised when the bot is missing permissions.

    Subclass of :exc:`VerificationError`.
    """


class DisabledFeatureError(VerificationError):
    """An error raised when a feature is disabled.

    Subclass of :exc:`VerificationError`.
    """


class VerificationFailedError(VerificationError):
    """An error raised when a verification fails.

    Subclass of :exc:`VerificationError`.
    """


class MailSystemError(VerificationError):
    """An error raised when a mail system error occurs.

    Subclass of :exc:`VerificationError`.
    """


class SMTPError(MailSystemError):
    """An error raised when an SMTP error occurs.

    Subclass of :exc:`MailSystemError`.
    """


class SMTPLoginError(SMTPError):
    """An error raised when an SMTP login error occurs.

    Subclass of :exc:`SMTPError`.
    """


class SMTPSendError(SMTPError):
    """An error raised when an SMTP send error occurs.

    Subclass of :exc:`SMTPError`.
    """


class MailGeneratorError(MailSystemError):
    """An error raised when a mail generator error occurs.

    Subclass of :exc:`MailSystemError`.
    """
