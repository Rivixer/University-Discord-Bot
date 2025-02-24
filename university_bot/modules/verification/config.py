# SPDX-License-Identifier: MIT
"""A module to define the verification configurations."""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, override
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from babel.dates import format_datetime
from nextcord import ButtonStyle, Color, Embed, Locale
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

from university_bot.mixins.static_message import StaticMessageDataConfig
from university_bot.modules.verification.enums import VerificationType
from university_bot.utils2 import ConfigUtils

from .exceptions import MissingPermissionsError

if TYPE_CHECKING:
    from nextcord import Guild, Role

    from university_bot import EmbedDict

__all__ = (
    "InputLimits",
    "VerificationConfig",
    "EmailMessageConfig",
    "LocalizedEmailMessageConfig",
    "AdditionalSummaryFieldConfig",
    "LocalizedAdditionalSummaryFieldConfig",
    "PrivacyPolicyConfig",
    "LocalizedPrivacyPolicyConfig",
    "RetentionPeriodConfig",
    "SMTPConfig",
    "AssignedRolesConfig",
    "VerificationDataConfig",
    "VerificationButtonConfig",
    "WhoisConfig",
)


class InputLimits:  # pylint: disable=too-few-public-methods
    """Constants for character limits in input fields."""

    FIRST_NAME: Final[int] = 64
    LAST_NAME: Final[int] = 64
    STUDY_INFO: Final[int] = 512


class VerificationConfig(BaseModel):
    """The verification configuration."""

    enabled: bool = True
    data_filepath: Path
    index_placeholder: str | None = "123456"
    index_min_length: int | None = None
    index_max_length: int | None = None
    code_length: int = 8
    view_timeout: int = 600
    max_attempts: int = 3
    email_message: EmailMessageConfig
    smtp: SMTPConfig
    assigned_roles: AssignedRolesConfig
    additional_summary_field: AdditionalSummaryFieldConfig | None
    privacy_policy: PrivacyPolicyConfig | None
    retention_period: RetentionPeriodConfig
    whois: WhoisConfig

    @field_validator("data_filepath", mode="before")
    @classmethod
    def _validate_data_filepath(cls, value: str | Path) -> Path:
        path = Path(value) if not isinstance(value, Path) else value
        ConfigUtils.validate_data_filepath(path, ".json")
        return path

    @model_validator(mode="after")
    def _validate_index_length(self) -> VerificationConfig:
        if self.index_min_length is not None:
            if self.index_min_length <= 0:
                raise ValueError("index_min_length must be greater than 0")

        if self.index_max_length is not None:
            if self.index_max_length <= 0:
                raise ValueError("index_min_length must be greater than 0")
            if self.index_max_length > 256:
                raise ValueError("index_max_length must be less than or equal to 256")

            if self.index_min_length is not None:
                if self.index_min_length > self.index_max_length:
                    raise ValueError(
                        "index_min_length must be less than or equal to index_max_length"
                    )
        return self

    @field_validator("code_length", mode="before")
    @classmethod
    def _validate_code_length(cls, value: int) -> int:
        if value < 1:
            raise ValueError("code_length must be greater than 0")
        if value > 16:
            raise ValueError("code_length must be less than or equal to 16")
        return value

    @field_validator("view_timeout", mode="before")
    @classmethod
    def _validate_view_timeout(cls, value: int) -> int:
        if value < 1:
            raise ValueError("view_timeout must be greater than 0")
        return value

    @field_validator("max_attempts", mode="before")
    @classmethod
    def _validate_max_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_attempts must be greater than 0")
        return value

    @field_validator("additional_summary_field", mode="before")
    @classmethod
    def _check_additional_summary_field_enabled(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if value is None or not value.get("enabled"):
            return None
        return value

    @field_validator("privacy_policy", mode="before")
    @classmethod
    def _check_privacy_policy_enabled(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if value is None or not value.get("enabled"):
            return None
        return value


class EmailMessageConfig(BaseModel):
    """The email message configuration."""

    address_template: str
    subject: str
    body_filepath: Path
    localized: dict[Locale, LocalizedEmailMessageConfig]

    @field_validator("body_filepath", mode="before")
    @classmethod
    def _validate_body_filepath(cls, value: str | Path) -> Path:
        path = Path(value) if not isinstance(value, Path) else value
        ConfigUtils.validate_data_filepath(path, ".html")
        return path

    @model_validator(mode="before")
    @classmethod
    def _validate_localized_keys(cls, values: dict[str, Any]) -> dict[str, Any]:
        localized = {}

        for key, item in list(values.items()):
            if isinstance(item, dict):
                localized[key] = LocalizedEmailMessageConfig(**item)  # type: ignore
                del values[key]

        values["localized"] = localized
        return values

    def get_localized(self, locale: Locale) -> LocalizedEmailMessageConfig:
        """Returns the localized configuration for the locale.

        If the localized configuration is not found, the default configuration is returned.

        Parameters
        ----------
        locale: :class:`nextcord.Locale`
            The locale to get the localized configuration for.

        Returns
        -------
        :class:`.LocalizedEmailMessageConfig`
            The localized configuration for the locale.
        """
        localized = self.localized.get(locale) if self.localized else None
        if localized:
            return localized
        return LocalizedEmailMessageConfig(
            subject=self.subject,
            body_filepath=self.body_filepath,
        )


class LocalizedEmailMessageConfig(BaseModel):
    """The localized email message configuration."""

    subject: str
    body_filepath: Path

    @field_validator("body_filepath", mode="before")
    @classmethod
    def _validate_body_filepath(cls, value: str | Path) -> Path:
        path = Path(value) if not isinstance(value, Path) else value
        ConfigUtils.validate_data_filepath(path, ".html")
        return path


class AdditionalSummaryFieldConfig(BaseModel):
    """The configuration of the additional summary field."""

    enabled: bool
    name: str
    value: str
    localized: dict[Locale, LocalizedAdditionalSummaryFieldConfig]

    @model_validator(mode="before")
    @classmethod
    def _validate_localized_keys(cls, values: dict[str, Any]) -> dict[str, Any]:
        localized = {}

        for key, item in list(values.items()):
            if isinstance(item, dict):
                try:
                    locale = Locale(key)
                except Exception as e:
                    raise ValueError(f"Invalid locale key: {key}") from e
                localized[locale] = LocalizedAdditionalSummaryFieldConfig(**item)  # type: ignore
                del values[key]

        values["localized"] = localized
        return values

    def get_localized(self, locale: Locale) -> LocalizedAdditionalSummaryFieldConfig:
        """Returns the localized configuration for the locale.

        If the localized configuration is not found, the default configuration is returned.

        Parameters
        ----------
        locale: :class:`nextcord.Locale`
            The locale to get the localized configuration for.

        Returns
        -------
        :class:`.LocalizedAdditionalSummaryFieldConfig`
            The localized configuration for the locale.
        """
        localized = self.localized.get(locale) if self.localized else None
        if localized:
            return localized
        return LocalizedAdditionalSummaryFieldConfig(
            name=self.name,
            value=self.value,
        )


class LocalizedAdditionalSummaryFieldConfig(BaseModel):
    """The localized additional summary field configuration."""

    name: str
    value: str


class PrivacyPolicyConfig(BaseModel):
    """The privacy policy configuration."""

    enabled: bool
    filepath: Path
    button_label: str
    localized: dict[Locale, LocalizedPrivacyPolicyConfig]

    @field_validator("filepath", mode="before")
    @classmethod
    def _validate_body_filepath(cls, value: str | Path) -> Path:
        path = Path(value) if not isinstance(value, Path) else value
        ConfigUtils.validate_data_filepath(path, extension=None)

        file_size = path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        if file_size_mb > 8:
            raise ValueError("The file size cannot exceed 8 MB.")

        return path

    @model_validator(mode="before")
    @classmethod
    def _validate_localized_keys(cls, values: dict[str, Any]) -> dict[str, Any]:
        localized = {}

        for key, item in list(values.items()):
            if isinstance(item, dict):
                try:
                    locale = Locale(key)
                except Exception as e:
                    raise ValueError(f"Invalid locale key: {key}") from e
                localized[locale] = LocalizedPrivacyPolicyConfig(**item)  # type: ignore
                del values[key]

        values["localized"] = localized
        return values

    def get_localized(self, locale: Locale) -> LocalizedPrivacyPolicyConfig:
        """Returns the localized configuration for the locale.

        If the localized configuration is not found, the default configuration is returned.

        Parameters
        ----------
        locale: :class:`nextcord.Locale`
            The locale to get the localized configuration for.

        Returns
        -------
        :class:`.LocalizedPrivacyPolicyConfig`
            The localized configuration for the locale.
        """
        localized = self.localized.get(locale) if self.localized else None
        if localized:
            return localized
        return LocalizedPrivacyPolicyConfig(
            filepath=self.filepath,
            button_name=self.button_label,
        )


class LocalizedPrivacyPolicyConfig(BaseModel):
    """The localized privacy policy configuration."""

    filepath: Path
    button_name: str

    @field_validator("filepath", mode="before")
    @classmethod
    def _validate_body_filepath(cls, value: str | Path) -> Path:
        path = Path(value) if not isinstance(value, Path) else value
        ConfigUtils.validate_data_filepath(path, extension=None)

        file_size = path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        if file_size_mb > 8:
            raise ValueError("The file size cannot exceed 8 MB.")

        return path


class RetentionPeriodConfig(BaseModel):
    """The retention period configuration."""

    target: int = 0
    internal: int = 0
    external: int = 0
    external_request: int = 31

    def get(self, type_: VerificationType) -> int:
        """Returns the retention period for the type.

        Parameters
        ----------
        type_: :class:`.VerificationType`
            The verification type.

        Returns
        -------
        :class:`int`
            The retention period.
        """
        return getattr(self, type_.value)


class SMTPConfig(BaseModel):
    """The SMTP configuration."""

    username: EmailStr
    password: str
    hostname: str
    port: int
    use_tls: bool = True

    @field_validator("port", mode="before")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if 1 <= value <= 65535:
            return value
        raise ValueError("port must be between 1 and 65535")

    @field_validator("password", mode="before")
    @classmethod
    def _validate_password(cls, value: str | None) -> str:
        if not value:
            env_variable = "VERIFICATION_SMTP_PASSWORD"
            if not (value := os.getenv(env_variable)):
                raise ValueError(
                    "password must be provided or set "
                    f"as an environment variable ({env_variable})"
                )
        return value


class AssignedRolesConfig(BaseModel):
    """The configuration of the assigned roles."""

    target: set[int] = set()
    internal: set[int] = set()
    external_request: set[int] = set()
    external: set[int] = set()
    _target_roles: set[Role] | None = None
    _internal_roles: set[Role] | None = None
    _external_request_roles: set[Role] | None = None
    _external_roles: set[Role] | None = None

    @property
    def target_roles(self) -> set[Role]:
        """Roles for a verified user who is a student for whom the server is intended."""
        if self._target_roles is None:
            raise ValueError("Roles are not set.")
        return self._target_roles

    @property
    def internal_roles(self) -> set[Role]:
        """Roles for a verified user who is a student from the same university."""
        if self._internal_roles is None:
            raise ValueError("Roles are not set.")
        return self._internal_roles

    @property
    def external_request_roles(self) -> set[Role]:
        """Roles for a verified user who is a student
        from another university and requested access.
        """
        if self._external_request_roles is None:
            raise ValueError("Roles are not set.")
        return self._external_request_roles

    @property
    def external_roles(self) -> set[Role]:
        """Roles for a verified user who is a student from another university."""
        if self._external_roles is None:
            raise ValueError("Roles are not set.")
        return self._external_roles

    @property
    def all_roles(self) -> set[Role]:
        """All roles."""
        return (
            self.target_roles
            | self.internal_roles
            | self.external_roles
            | self.external_request_roles
        )

    @property
    def is_any_role_provided(self) -> bool:
        """Whether any role is provided."""
        return len(self.all_roles) > 0

    def get(self, type_: VerificationType) -> set[Role]:
        """Returns the roles for the type.

        Parameters
        ----------
        type_: :class:`.VerificationType`
            The verification type.

        Returns
        -------
        List[:class:`nextcord.Role`]
            The roles for the type.
        """
        return set(getattr(self, f"{type_.value}_roles"))

    def set_roles(self, guild: Guild) -> None:
        """Sets the roles.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild where the roles are located.
        """
        self._target_roles = self._validate_roles(guild, self.target)
        self._internal_roles = self._validate_roles(guild, self.internal)
        self._external_roles = self._validate_roles(guild, self.external)
        self._external_request_roles = self._validate_roles(
            guild, self.external_request
        )

    def _validate_roles(self, guild: Guild, role_ids: set[int]) -> set[Role]:
        if invalid_role_ids := [r for r in role_ids if guild.get_role(r) is None]:
            raise ValueError(
                f"Invalid role IDs: {invalid_role_ids}. "
                "Each must reference an existing role."
            )

        return {guild.get_role(role_id) for role_id in role_ids}  # type: ignore

    def validate_all_roles_permissions(self) -> None:
        """Validates permissions for the bot in the roles.

        Must be called after `set_roles`.

        Raises
        ------
        MissingPermissionsError
            If the bot lacks `manage_roles` permissions in any of the roles.
        """
        missing_permissions = [
            r for r in self.all_roles if not r.guild.me.guild_permissions.manage_roles
        ]

        if missing_permissions:
            raise MissingPermissionsError(
                "The bot lacks `manage_roles` permissions in the following roles: "
                f"{', '.join(r.name for r in missing_permissions)}."
            )


@ConfigUtils.auto_model_dump
class VerificationDataConfig(StaticMessageDataConfig):
    """The data configuration of the verification."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    version: str = "1.0"
    message_id: int | None
    channel_id: int | None
    content: str | None = None
    embed: Embed
    target_button: VerificationButtonConfig
    internal_button: VerificationButtonConfig
    external_button: VerificationButtonConfig

    def __init__(self, **data: Any):
        super().__init__(**data)
        if self.version != "1.0":
            raise ValueError(f"Unsupported configuration version: {self.version}")

    @field_validator("embed", mode="before")
    @classmethod
    def _validate_embed(cls, value: Embed | EmbedDict | None) -> Embed | None:
        if value is None or isinstance(value, Embed):
            return value
        return Embed.from_dict(value)

    @override
    @staticmethod
    def load(path: Path | str) -> VerificationDataConfig:
        with open(path, "r", encoding="utf-8") as f:
            return VerificationDataConfig(**json.load(f))

    @staticmethod
    def get_example() -> VerificationDataConfig:
        """Returns an example configuration."""
        return VerificationDataConfig(
            message_id=None,
            channel_id=None,
            content=None,
            embed=Embed(
                title="Verification",
                description="Use `/verification get_configuration` to edit the message.",
                color=Color.magenta(),
            ),
            target_button=VerificationButtonConfig(
                enabled=True,
                label="Student for whom the server is intended",
                style=ButtonStyle.green,
            ),
            internal_button=VerificationButtonConfig(
                enabled=True,
                label="Student from the same university",
                style=ButtonStyle.blurple,
            ),
            external_button=VerificationButtonConfig(
                enabled=True,
                label="Other",
                style=ButtonStyle.gray,
            ),
        )


class VerificationButtonConfig(BaseModel):
    """The configuration of the verification button."""

    enabled: bool
    label: str
    style: ButtonStyle


class WhoisConfig(BaseModel):
    """The configuration of the whois command."""

    verified_at_format: str = "yyyy-MM-dd HH:mm:ss"
    verified_at_timezone_key: str = "UTC"

    @field_validator("verified_at_timezone_key", mode="before")
    @classmethod
    def _validate_verified_at_timezone_key(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"Invalid timezone: {value}") from e
        return value

    @property
    def verified_at_timezone(self) -> ZoneInfo:
        """The timezone of the calendar."""
        return ZoneInfo(self.verified_at_timezone_key)

    def format_verified_at(self, dt: datetime.datetime, locale: Locale) -> str:
        """Formats the verified at datetime.

        Parameters
        ----------
        dt: :class:`datetime.datetime`
            The datetime to format.
        locale: :class:`nextcord.Locale`
            The locale to format the datetime with.

        Returns
        -------
        :class:`str`
            The formatted datetime.
        """
        return format_datetime(
            dt,
            format=self.verified_at_format,
            locale=locale.split("-")[0],
            tzinfo=self.verified_at_timezone,
        )
