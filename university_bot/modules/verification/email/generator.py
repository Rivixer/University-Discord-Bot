# SPDX-License-Identifier: MIT
"""A module to generate email messages for verification."""

from __future__ import annotations

from email import policy
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from nextcord import Locale

from university_bot.utils.localization import Localization

from ..exceptions import MailGeneratorError

if TYPE_CHECKING:
    from nextcord import Member

    from ..config import VerificationConfig

__all__ = ("MailGenerator",)


class MailGenerator:
    """A class to generate email messages for verification.

    Attributes
    ----------
    config: :class:`.VerificationConfig`
        The verification configuration.
    """

    __slots__ = ("config",)

    config: VerificationConfig

    def __init__(self, config: VerificationConfig) -> None:
        self.config = config

    def generate_verification_message(
        self,
        member: Member,
        address: str,
        code: str,
        locale: Locale | None = None,
    ) -> MIMEMultipart:
        if locale is None:
            preferred_locale = member.guild.preferred_locale
            locale = (
                Locale(preferred_locale)
                if preferred_locale
                else Localization.default_locale()
            )

        localized_config = self.config.email_message.get_localized(locale)

        try:
            path = localized_config.body_filepath
            with open(path, "r", encoding="utf-8") as file:
                body = file.read()
        except OSError as e:
            raise MailGeneratorError("Failed to read the email body file.") from e

        subject = self._format_subject(localized_config.subject, member)
        body = self._format_body(body, member, code)

        message = MIMEMultipart()
        message.policy = policy.default
        message["From"] = self.config.smtp.username
        message["To"] = address
        message["Subject"] = subject
        message.attach(MIMEText(body, "html", "utf-8"))

        return message

    def _format_subject(self, subject: str, member: Member) -> str:
        return subject.replace("{guild_name}", member.guild.name)

    def _format_body(self, body: str, member: Member, code: str) -> str:
        body = (
            body.replace("{{MEMBER_DISPLAY_NAME}}", member.display_name)
            .replace("{{REGISTRATION_CODE}}", code)
            .replace("{{GUILD_NAME}}", member.guild.name)
        )

        if member.guild.icon:
            body = body.replace("{{GUILD_ICON}}", member.guild.icon.url)

        if member.avatar:
            body = body.replace("{{MEMBER_AVATAR}}", member.avatar.url)

        return body
