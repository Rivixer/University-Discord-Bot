# SPDX-License-Identifier: MIT
"""A module to provide email verification services."""

from __future__ import annotations

from email.message import EmailMessage, Message
from typing import TYPE_CHECKING

from aiosmtplib import SMTP, SMTPException

from ..exceptions import SMTPLoginError, SMTPSendError

if TYPE_CHECKING:
    from ..config import SMTPConfig

__all__ = ("MailService",)


class MailService:
    """A class to provide email verification services.

    Attributes
    ----------
    config: :class:`.SMTPConfig`
        The SMTP configuration.
    email: :class:`str`
        The email address to send the verification email to.
    """

    __slots__ = (
        "config",
        "email",
    )

    config: SMTPConfig
    email: str

    def __init__(self, config: SMTPConfig, email: str) -> None:
        self.config = config
        self.email = email

    async def send_message(self, message: EmailMessage | Message[str, str]) -> None:
        """|coro|

        Sends an email message using the SMTP server.

        Parameters
        ----------
        message: :class:`email.message.EmailMessage` | :class:`email.message.Message`
            The email message to send.

        Raises
        ------
        SMTPLoginError
            An error occurred while logging into the SMTP server.
        SMTPSendError
            An error occurred while sending the email.
        """
        async with SMTP(
            hostname=self.config.hostname,
            port=self.config.port,
            use_tls=self.config.use_tls,
        ) as smtp:
            try:
                await smtp.login(self.config.username, self.config.password)
            except SMTPException as e:
                raise SMTPLoginError("Failed to login to the SMTP server.") from e

            try:
                await smtp.send_message(message)
            except (SMTPException, ValueError) as e:
                raise SMTPSendError("Failed to send the email.") from e
