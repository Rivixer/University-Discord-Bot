# SPDX-License-Identifier: MIT
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, override

from babel.dates import format_date, format_datetime
from nextcord import Embed, Guild, TextChannel
from pydantic import BaseModel, ConfigDict, field_validator

from university_bot import ConfigUtils
from university_bot.models import DataConfigBaseModel

from .exceptions import MissingPermissions

if TYPE_CHECKING:
    from nextcord import Role

    from university_bot import EmbedDict


class ReminderFieldLimits:  # pylint: disable=too-few-public-methods
    """Constants for character limits in event fields."""

    DESCRIPTION: Final[int] = 4000
    ADDITIONAL_INFO: Final[int] = 1024


class ReminderConfig(BaseModel):
    """A model to define the reminder configuration."""

    enabled: bool
    data_filepath: Path


@ConfigUtils.auto_model_dump
class ReminderDataConfig(DataConfigBaseModel):
    """A model to define the reminder data configuration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    version: str = "1.0"
    datetime_ts_format: str = "<t:{timestamp}:f> (<t:{timestamp}:R>)"
    date_ts_format: str = "<t:{timestamp}:D>"
    datetime_repr_format: str = "dd.MM.yyyy HH:mm"
    date_repr_format: str = "dd.MM.yyyy"
    mobile_content: str = (
        "Reminder {datetime}:\n{description}{\n\n?additional_info?\n}\n{roles}"
    )
    content: str = r"{roles}"
    embed: Embed
    channel_ids: list[int] = []
    role_ids: list[int] = []

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if self.version != "1.0":
            raise ValueError(f'Unsupported version "{self.version}"')

    @override
    @staticmethod
    def load(path: Path | str) -> ReminderDataConfig:
        with open(path, "r", encoding="utf-8") as f:
            return ReminderDataConfig(**json.load(f))

    def get_channels(self, guild: Guild) -> list[TextChannel]:
        """Returns the channels where reminders can be sent.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild where the channels are located.

        Returns
        -------
        list[:class:`nextcord.TextChannel`]
            The channels where reminders can be sent.
        """
        return [guild.get_channel(i) for i in self.channel_ids]  # type: ignore

    def get_roles(self, guild: Guild) -> list[Role]:
        """Returns the roles that can be mentioned in reminders.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild where the roles are located.

        Returns
        -------
        list[:class:`nextcord.Role`]
            The roles that can be mentioned in reminders.
        """
        return [guild.get_role(i) for i in self.role_ids]  # type: ignore

    def format_repr_datetime(self, dt: datetime.datetime) -> str:
        """Formats a datetime object for representation in reminders.

        Parameters
        ----------
        dt: :class:`datetime.datetime`
            The datetime object to format.

        Returns
        -------
        str
            The formatted datetime.
        """
        return format_datetime(dt, self.datetime_repr_format)

    def format_repr_date(self, date: datetime.date | datetime.datetime) -> str:
        """Formats a date object for representation in reminders.

        Parameters
        ----------
        date: :class:`datetime.date` | :class:`datetime.datetime`
            The date object to format.

        Returns
        -------
        str
            The formatted date.
        """
        return format_date(date, format=self.date_repr_format)

    @field_validator("embed", mode="before")
    @classmethod
    def _validate_embed(cls, value: Embed | EmbedDict) -> Embed | None:
        return Embed.from_dict(value) if isinstance(value, dict) else value

    def validate_channels(self, guild: Guild) -> None:
        """Validates the channels in the configuration.

        Checks that:
        - No channel ID is duplicated.
        - All channel IDs refer to existing channels.
        - All channels are text channels.
        - The bot has permission to send messages in these channels.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild where the channels are located.

        Raises
        ------
        ValueError
            If any channel ID is duplicated or does not refer to an existing channel.
        TypeError
            If any channel ID does not refer to a text channel.
        MissingPermissions
            If the bot lacks `send_messages` permission in any of the channels.
        """

        if duplicate_ids := {
            x for x in self.channel_ids if self.channel_ids.count(x) > 1
        }:
            raise ValueError(
                "The following channel IDs are duplicated: "
                + ", ".join(map(str, duplicate_ids))
            )

        missing_ids: list[int] = []
        non_text_ids: list[int] = []
        no_permission_channels: list[TextChannel] = []

        valid_channels: list[TextChannel] = []
        for channel_id in self.channel_ids:
            channel = guild.get_channel(channel_id)
            if channel is None:
                missing_ids.append(channel_id)
            elif not isinstance(channel, TextChannel):
                non_text_ids.append(channel_id)
            else:
                valid_channels.append(channel)

        if missing_ids:
            raise ValueError(
                "The following channel IDs are invalid (channel not found): "
                + ", ".join(map(str, missing_ids))
            )

        if non_text_ids:
            raise TypeError(
                "The following channel IDs do not reference a text channel: "
                + ", ".join(map(str, non_text_ids))
            )

        for channel in valid_channels:
            if not channel.permissions_for(guild.me).send_messages:
                no_permission_channels.append(channel)

        if no_permission_channels:
            raise MissingPermissions(
                "The bot lacks `send_messages` permission in the following channels: "
                + ", ".join(
                    f"#{channel.name} ({channel.id})"
                    for channel in no_permission_channels
                )
            )

    def validate_roles(self, guild: Guild) -> None:
        """Validates the roles in the configuration.

        Checks that:
        - No role ID is duplicated.
        - All role IDs refer to existing roles.
        - All roles are mentionable.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild where the channels are located.

        Raises
        ------
        ValueError
            If any role ID is duplicated,
            does not refer to an existing role
            or is not mentionable.
        """
        if duplicate_ids := {x for x in self.role_ids if self.role_ids.count(x) > 1}:
            raise ValueError(
                "The following role IDs are duplicated: "
                + ", ".join(map(str, duplicate_ids))
            )

        missing_ids: list[int] = []
        not_mentionable_ids: list[int] = []

        for role_id in self.role_ids:
            role = guild.get_role(role_id)
            if role is None:
                missing_ids.append(role_id)
            elif not role.mentionable:
                not_mentionable_ids.append(role_id)

        if missing_ids:
            raise ValueError(
                "The following role IDs are invalid (role not found): "
                + ", ".join(map(str, missing_ids))
            )

        if not_mentionable_ids:
            raise ValueError(
                "The following role IDs are not mentionable: "
                + ", ".join(map(str, not_mentionable_ids))
            )

    @staticmethod
    def get_example() -> ReminderDataConfig:
        """Returns an example reminder data configuration."""
        return ReminderDataConfig(
            embed=Embed(
                title="Reminder",
                description=r"{description}",
                color=0xFFFF00,
            )
            .add_field(
                name="When?",
                value=r"{formatted_timestamp}",
                inline=False,
            )
            .add_field(
                name="Where?",
                value=r"{location}",
                inline=False,
            )
            .add_field(
                name="Additional Info",
                value=r"{additional_info}",
                inline=False,
            ),
        )
