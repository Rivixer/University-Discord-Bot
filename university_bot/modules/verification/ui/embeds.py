# SPDX-License-Identifier: MIT
"""A module to define embeds for the verification system."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from nextcord import Color, Embed

from university_bot import Localization
from university_bot.mixins import LocalizedMixin

from .enums import CodeStatus

if TYPE_CHECKING:
    from nextcord import Locale, Member

    from university_bot.utils import LocalizedGroup

    from .models import ExternalVerificationData
    from .payloads import (
        ExternalDataSummaryPayload,
        InternalDataSummaryPayload,
        TargetDataSummaryPayload,
    )
    from ..config import AdditionalSummaryFieldConfig, WhoisConfig
    from ..models import MatchingMember


__all__ = (
    "CodeSentEmbed",
    "DataSummaryEmbed",
    "TargetDataSummaryEmbed",
    "InternalDataSummaryEmbed",
    "ExternalDataSummaryEmbed",
    "VerificationSuccessEmbed",
    "VerificationRequestSentEmbed",
    "MaxAttemptsEmbed",
    "IndexTakenEmbed",
    "AlreadyVerifiedEmbed",
    "RequestAlreadySentEmbed",
    "ErrorEmbed",
    "VerificationRequestEmbed",
    "MemberInformationEmbed",
)

_loc = Localization.get_group("ui.verification.embeds")


class CodeSentEmbed(LocalizedMixin, Embed):
    """Embed for the code sent message."""

    def __init__(self, email: str, locale: Locale) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("code_sent"))

        title = self.get_loc("title", "Verification code sent")
        description = self.get_loc(
            "description",
            "A verification code has been sent to `{email}`.",
        ).replace("{email}", email)

        Embed.__init__(self, title=title, description=description, color=Color.orange())

        continue_name = self.get_loc(
            "fields.continue.name",
            "Click the button below to continue.",
        )

        self.add_field(name=continue_name, value="", inline=False)


class DataSummaryEmbed(LocalizedMixin, Embed, ABC):
    """Base class for data summary embeds."""

    _locale: Locale
    _fields_loc: LocalizedGroup

    def __init__(self, locale: Locale) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("data_summary"))

        title = self.get_loc("title", "Are your details correct?")
        description = self.get_loc(
            "description",
            "Please review the data below and confirm if it is correct.",
        )

        Embed.__init__(self, title=title, description=description, color=Color.gold())

        self._locale = locale
        self._fields_loc = self.get_loc_group("fields")

    def _add_code_field(self, code_status: CodeStatus) -> None:
        assert code_status is not CodeStatus.UNNECESSARY

        if code_status is CodeStatus.VALID:
            code_value = self._fields_loc.get("code.value.valid", "Valid")
        else:
            code_value = "**(!)** " + self._fields_loc.get(
                "code.value.invalid", "Invalid"
            )

        self.add_field(
            name=self._fields_loc.get("code.name", "Verification code:"),
            value=code_value,
            inline=False,
        )

    def _add_first_name_field(self, first_name: str) -> None:
        self.add_field(
            name=self._fields_loc.get("first_name.name", "First name:"),
            value=first_name or "**(!)**",
            inline=True,
        )

    def _add_last_name_field(self, last_name: str) -> None:
        self.add_field(
            name=self._fields_loc.get("last_name.name", "Last name:"),
            value=last_name or "**(!)**",
            inline=True,
        )

    def _add_index_field(self, index: str) -> None:
        self.add_field(
            name=self._fields_loc.get("index.name", "Index number:"),
            value=index or "**(!)**",
            inline=True,
        )

    def _all_study_field(self, study_info: str) -> None:
        self.add_field(
            name=self._fields_loc.get("study_info.name", "Study information:"),
            value=study_info or "**(!)**",
            inline=False,
        )

    def _add_reason_field(self, reason: str) -> None:
        self.add_field(
            name=self._fields_loc.get("reason.name", "Reason:"),
            value=reason or "**(!)**",
            inline=False,
        )

    def _add_additional_field(self, config: AdditionalSummaryFieldConfig) -> None:
        localized_additional_field = config.get_localized(self._locale)
        self.add_field(
            name=localized_additional_field.name,
            value=localized_additional_field.value,
            inline=False,
        )


class TargetDataSummaryEmbed(DataSummaryEmbed):
    """Embed for target data summary."""

    def __init__(self, payload: TargetDataSummaryPayload) -> None:
        super().__init__(payload.locale)

        if payload.code_status is not CodeStatus.UNNECESSARY:
            self._add_code_field(payload.code_status)

        self._add_first_name_field(payload.first_name)
        self._add_last_name_field(payload.last_name)
        self._add_index_field(payload.index)

        config = payload.config.additional_summary_field
        if config and payload.code_status is not CodeStatus.INVALID:
            self._add_additional_field(config)


class InternalDataSummaryEmbed(DataSummaryEmbed):
    """Embed for internal verification data summary."""

    def __init__(self, payload: InternalDataSummaryPayload) -> None:
        super().__init__(payload.locale)

        if payload.code_status is not CodeStatus.UNNECESSARY:
            self._add_code_field(payload.code_status)

        self._add_first_name_field(payload.first_name)
        self._add_last_name_field(payload.last_name)
        self._add_index_field(payload.index)
        self._all_study_field(payload.study_info)
        self._add_reason_field(payload.reason)

        config = payload.config.additional_summary_field
        if config and payload.code_status is not CodeStatus.INVALID:
            self._add_additional_field(config)


class ExternalDataSummaryEmbed(DataSummaryEmbed):
    """Embed for external verification data summary."""

    def __init__(self, payload: ExternalDataSummaryPayload) -> None:
        super().__init__(payload.locale)

        self._add_first_name_field(payload.first_name)
        self._add_last_name_field(payload.last_name)
        self._add_reason_field(payload.reason)

        if config := payload.config.additional_summary_field:
            self._add_additional_field(config)


class VerificationSuccessEmbed(LocalizedMixin, Embed):
    """Embed for successful verification."""

    def __init__(self, locale: Locale | str | None) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("verification_success"))

        title = self.get_loc("title", "Verification successful")
        description = self.get_loc(
            "description",
            "Your account has been successfully verified.",
        )

        Embed.__init__(
            self,
            title=title,
            description=description,
            color=Color.green(),
        )


class VerificationRequestSentEmbed(LocalizedMixin, Embed):
    """Embed for the verification request sent message."""

    def __init__(self, locale: Locale | str | None) -> None:
        LocalizedMixin.__init__(
            self, locale, _loc.get_group("verification_request_sent")
        )

        title = self.get_loc("title", "Verification request sent")
        description = self.get_loc(
            "description",
            "Your verification request has been sent.\n"
            "Please wait for the server administration to review it.",
        )

        Embed.__init__(
            self,
            title=title,
            description=description,
            color=Color.greyple(),
        )


class MaxAttemptsEmbed(LocalizedMixin, Embed):
    """Embed for reaching the maximum number of incorrect code attempts."""

    def __init__(self, locale: Locale) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("max_attempts"))

        title = self.get_loc("title", "Too many incorrect code attempts")
        description = self.get_loc(
            "description",
            "You have reached the maximum number of incorrect code attempts.",
        )

        Embed.__init__(
            self,
            title=title,
            description=description,
            color=Color.red(),
        )


class IndexTakenEmbed(LocalizedMixin, Embed):
    """Embed for the case when the provided index is already taken."""

    def __init__(self, locale: Locale, external_btn_label: str) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("index_taken"))

        title = self.get_loc("title", "Index taken")
        description = self.get_loc(
            "description",
            "The index you provided is already taken.\n"
            "If you are verifying another account, please use `{external_btn_label}` button.\n"
            "If you believe this is an error, please contact the server administration.",
        ).replace("{external_btn_label}", external_btn_label)

        Embed.__init__(
            self,
            title=title,
            description=description,
            color=Color.red(),
        )


class AlreadyVerifiedEmbed(LocalizedMixin, Embed):
    """Embed for the case when the account has already been verified."""

    def __init__(self, locale: Locale) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("already_verified"))

        title = self.get_loc("title", "Already verified")
        description = self.get_loc(
            "description",
            "Your account has already been verified.\n"
            "If you believe this is an error, please contact the server administration.",
        )

        Embed.__init__(
            self,
            title=title,
            description=description,
            color=Color.green(),
        )


class RequestAlreadySentEmbed(LocalizedMixin, Embed):
    """Embed for the case when the verification request has already been sent."""

    def __init__(self, locale: Locale) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("request_already_sent"))

        title = self.get_loc("title", "Request already sent")
        description = self.get_loc(
            "description",
            "Your verification request has already been sent.\n"
            "Please wait for the server administration to review it.",
        )

        Embed.__init__(
            self,
            title=title,
            description=description,
            color=Color.greyple(),
        )


class ErrorEmbed(LocalizedMixin, Embed):
    """Embed for error messages."""

    def __init__(self, locale: Locale, exception: Exception | str) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("error"))

        title = self.get_loc("title", "Oops! An error occurred")
        description = self.get_loc(
            "description",
            "An error occurred while processing your request.\n"
            "Please try again.\n"
            "If the issue persists, please contact the server administration.",
        )

        Embed.__init__(
            self,
            title=title,
            description=description,
            color=Color.red(),
        )

        self.set_footer(
            text=(
                (f"{exception.__class__.__name__}: {exception}")
                if isinstance(exception, Exception)
                else str(exception)
            )[:2048]
        )


class VerificationRequestEmbed(LocalizedMixin, Embed):
    """Embed for the verification request message."""

    def __init__(
        self, locale: Locale, member: Member, data: ExternalVerificationData
    ) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("verification_request"))

        Embed.__init__(
            self,
            title=self.get_loc("title", "Verification request"),
            description=member.mention,
            color=Color.teal(),
        )

        self.add_field(
            name=self.get_loc("fields.first_name", "First name:"),
            value=data.first_name,
            inline=True,
        )

        self.add_field(
            name=self.get_loc("fields.last_name", "Last name:"),
            value=data.last_name,
            inline=True,
        )

        self.add_field(
            name=self.get_loc("fields.reason", "Reason:"),
            value=data.reason,
            inline=False,
        )

        self.add_field(
            name=self.get_loc("fields.id", "ID:"),
            value=str(member.id),
            inline=False,
        )

        if member.avatar:
            self.set_thumbnail(url=member.avatar.url)


class MemberInformationEmbed(LocalizedMixin, Embed):
    """Embed for showing member information."""

    def __init__(
        self,
        locale: Locale,
        matching_member: MatchingMember,
        whois_config: WhoisConfig,
    ) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("member_information"))

        member = matching_member.member
        data = matching_member.verification_data

        Embed.__init__(
            self,
            title=self.get_loc("title", "Member information"),
            description=member.mention,
            color=member.top_role.color,
        )

        self.add_field(
            name=self.get_loc("fields.first_name", "First name:"),
            value=data.first_name,
            inline=True,
        )

        self.add_field(
            name=self.get_loc("fields.last_name", "Last name:"),
            value=data.last_name,
            inline=True,
        )

        if data.index:
            self.add_field(
                name=self.get_loc("fields.index", "Index number:"),
                value=data.index,
                inline=True,
            )

        if data.study_info:
            self.add_field(
                name=self.get_loc("fields.study_info", "Study information:"),
                value=data.study_info,
                inline=False,
            )

        if data.reason:
            self.add_field(
                name=self.get_loc("fields.reason", "Reason:"),
                value=data.reason,
                inline=False,
            )

        no_loc = self.get_loc("other.no", "No")
        na_loc = self.get_loc("other.na", "N/A")

        roles = sorted(
            [role for role in member.roles if not role.is_default()],
            key=lambda i: i.position,
        )

        if data.verified_at and roles:
            verified_at_value = whois_config.format_verified_at(
                data.verified_at, locale
            )
        elif roles:
            verified_at_value = na_loc
        else:
            verified_at_value = no_loc

        self.add_field(
            name=self.get_loc("fields.verified_at", "Verified at:"),
            value=verified_at_value,
            inline=True,
        )

        self.add_field(
            name=self.get_loc("fields.display_name", "Display name:"),
            value=member.display_name,
            inline=True,
        )

        self.add_field(
            name=self.get_loc("fields.discord_name", "Discord name:"),
            value=member.name,
            inline=True,
        )

        self.add_field(
            name=self.get_loc("fields.id", "ID:"),
            value=str(member.id),
            inline=False,
        )

        self.add_field(
            name=self.get_loc("fields.roles", "Roles:"),
            value=", ".join(role.mention for role in roles) or na_loc,
            inline=False,
        )

        if member.avatar:
            self.set_thumbnail(url=member.avatar.url)
