# SPDX-License-Identifier: MIT
"""A module to define the configuration models for the calendar."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, override
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from babel.core import Locale, UnknownLocaleError
from babel.dates import (
    format_date,
    format_datetime,
    format_time,
    parse_date,
    parse_time,
)
from nextcord import Color, Embed
from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from university_bot import ConfigUtils, get_logger
from university_bot.mixins.static_message import StaticMessageDataConfig

if TYPE_CHECKING:
    from university_bot import EmbedDict

__all__ = (
    "CalendarConfig",
    "CalendarDataConfig",
    "EventFieldLimits",
    "EventReprFormat",
)

_logger = get_logger(__name__)


class EventFieldLimits:  # pylint: disable=too-few-public-methods
    """Constants for character limits in event fields."""

    DESCRIPTION: Final[int] = 384
    PREFIX: Final[int] = 64
    LOCATION: Final[int] = 512


class CalendarConfig(BaseModel):
    """The calendar configuration."""

    enabled: bool = True
    data_filepath: Path

    @field_validator("data_filepath", mode="before")
    @classmethod
    def _validate_data_filepath(cls, value: str | Path) -> Path:
        path = Path(value) if not isinstance(value, Path) else value
        ConfigUtils.validate_data_filepath(path, ".json")
        return path


class EventReprFormat(BaseModel):
    """The format of the event representation."""

    indent: str = "- "
    prefix: str = "[{prefix}] "
    description: str = "**{description}**"
    time: str = " ({time})"
    location: str = " [{location}]"


@ConfigUtils.auto_model_dump
class CalendarDataConfig(StaticMessageDataConfig):
    """The data configuration of the calendar."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    version: str = "1.0"
    message_id: int | None
    channel_id: int | None
    content: str | None = None
    locale: str = "en"
    timezone_key: str = "UTC"
    modified: datetime.datetime | None = None
    modified_format: str = "dd.MM.yyyy HH:mm"
    date_input_format: str = "dd.MM.yyyy"
    date_repr_format: str = "dd.MM.yyyy (EEEE)"
    time_input_format: str = "HH.mm"
    time_repr_format: str = "HH:mm"
    event_repr_format: EventReprFormat = EventReprFormat()
    embed: Embed

    def __init__(self, **data: Any):
        super().__init__(**data)
        if self.version != "1.0":
            raise ValueError(f"Unsupported configuration version: {self.version}")

    @override
    @staticmethod
    def load(path: Path | str) -> CalendarDataConfig:
        with open(path, "r", encoding="utf-8") as f:
            return CalendarDataConfig(**json.load(f))

    @field_validator("locale", mode="before")
    @classmethod
    def _validate_locale(cls, value: str) -> str:
        try:
            Locale.parse(value)
        except UnknownLocaleError as e:
            raise ValueError(f"Invalid locale: {value}") from e
        return value

    @field_validator("timezone_key", mode="before")
    @classmethod
    def _validate_timezone_key(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"Invalid timezone: {value}") from e
        return value

    @field_validator("modified", mode="before")
    @classmethod
    def _validate_modified(cls, value: str | None) -> datetime.datetime | None:
        if value is None:
            return None
        try:
            return datetime.datetime.fromisoformat(value)
        except ValueError as e:
            _logger.warning(
                "Invalid modified datetime: %s. Setting current datetime.", e
            )
            return datetime.datetime.now()

    @field_validator("modified_format", mode="after")
    @staticmethod
    def _validate_modified_format(value: str, info: ValidationInfo) -> str:
        locale = info.data.get("locale", "en")
        sample_date = datetime.date.today()
        format_datetime(sample_date, format=value, locale=locale)
        return value

    @field_validator("date_input_format", mode="after")
    @staticmethod
    def _validate_date_input_format(value: str, info: ValidationInfo) -> str:
        locale = info.data.get("locale", "en")
        sample_date = datetime.date.today()
        format_date(sample_date, format=value, locale=locale)
        return value

    @field_validator("date_repr_format", mode="after")
    @staticmethod
    def _validate_date_repr_format(value: str, info: ValidationInfo) -> str:
        locale = info.data.get("locale", "en")
        sample_date = datetime.date.today()
        format_date(sample_date, format=value, locale=locale)
        return value

    @field_validator("time_input_format", mode="after")
    @staticmethod
    def _validate_time_input_format(value: str, info: ValidationInfo) -> str:
        locale = info.data.get("locale", "en")
        sample_time = datetime.datetime.now().time()
        format_time(sample_time, format=value, locale=locale)
        return value

    @field_validator("time_repr_format", mode="after")
    @staticmethod
    def _validate_time_repr_format(value: str, info: ValidationInfo) -> str:
        locale = info.data.get("locale", "en")
        sample_time = datetime.datetime.now().time()
        format_time(sample_time, format=value, locale=locale)
        return value

    @field_validator("embed", mode="before")
    @classmethod
    def _validate_embed(cls, value: Embed | EmbedDict) -> Embed | None:
        embed = Embed.from_dict(value) if isinstance(value, dict) else value

        if embed.fields:
            raise ValueError(
                "Fields are reserved for events. Do not use them in the embed."
            )

        return embed

    @override
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(*args, **kwargs)
        if data.get("embed"):
            data["embed"] = data["embed"].to_dict()

        try:
            del data["embed"]["fields"]
        except KeyError:
            pass

        data["modified"] = data["modified"].isoformat() if data["modified"] else None

        return data

    @property
    def timezone(self) -> ZoneInfo:
        """The timezone of the calendar."""
        return ZoneInfo(self.timezone_key)

    def format_modified(self, dt: datetime.datetime) -> str:
        """Formats the modified date and time.

        Parameters
        ----------
        dt: :class:`datetime.datetime`
            The date and time to format.

        Returns
        -------
        :class:`str`
            The formatted date and time.
        """
        return format_datetime(
            dt, format=self.modified_format, locale=self.locale, tzinfo=self.timezone
        )

    def format_input_date(self, date: datetime.date) -> str:
        """Formats the input date.

        Parameters
        ----------
        date: :class:`datetime.date`
            The date to format.

        Returns
        -------
        :class:`str`
            The formatted date.
        """
        return format_date(date, format=self.date_input_format, locale=self.locale)

    def format_repr_date(self, date: datetime.date) -> str:
        """Formats the representation date.

        Parameters
        ----------
        date: :class:`datetime.date`
            The date to format.

        Returns
        -------
        :class:`str`
            The formatted date.
        """
        return format_date(date, format=self.date_repr_format, locale=self.locale)

    def parse_input_date(self, date: str) -> datetime.date:
        """Parses the input date.

        Parameters
        ----------
        date: :class:`str`
            The date to parse.

        Returns
        -------
        :class:`datetime.date`
            The parsed date.

        Raises
        ------
        ValueError | IndexError
            If the date could not be parsed.
        """
        return parse_date(date, format=self.date_input_format, locale=self.locale)

    def format_input_time(self, time: datetime.time) -> str:
        """Formats the input time.

        Parameters
        ----------
        time: :class:`datetime.time`
            The time to format.

        Returns
        -------
        :class:`str`
            The formatted time.
        """
        return format_time(time, format=self.time_input_format, locale=self.locale)

    def format_repr_time(self, time: datetime.time) -> str:
        """Formats the representation time.

        Parameters
        ----------
        time: :class:`datetime.time`
            The time to format.

        Returns
        -------
        :class:`str`
            The formatted time.
        """
        return format_time(time, format=self.time_repr_format, locale=self.locale)

    def parse_input_time(self, time: str) -> datetime.time:
        """Parses the input time.

        Parameters
        ----------
        time: :class:`str`
            The time to parse.

        Returns
        -------
        :class:`datetime.time`
            The parsed time.

        Raises
        ------
        ValueError | IndexError
            If the time could not be parsed.
        """
        return parse_time(time, format=self.time_input_format, locale=self.locale)

    @staticmethod
    def get_example() -> CalendarDataConfig:
        """Returns an example of the data configuration."""
        return CalendarDataConfig(
            message_id=None,
            channel_id=None,
            content=None,
            embed=Embed(
                title="Calendar",
                description="Last modified: {modified}",
                color=Color.blurple(),
            ),
        )
