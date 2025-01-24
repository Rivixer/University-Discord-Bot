# SPDX-License-Identifier: MIT
"""A module to define the configuration models for the presence module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nextcord import Activity, ActivityType, CustomActivity, Status
from pydantic import BaseModel, field_validator, model_validator

from university_bot.utils2 import ConfigUtils


class PresenceConfig(BaseModel):
    """A class for the configuration of the bot's presence."""

    enabled: bool = True
    data_filepath: Path

    @field_validator("data_filepath", mode="before")
    @classmethod
    def _validate_data_filepath(cls, value: str | Path) -> Path:
        path = Path(value) if not isinstance(value, Path) else value
        ConfigUtils.validate_data_filepath(path, ".json")
        return path


class PresenceDataConfig(BaseModel):
    """A class for the data configuration of the presence module."""

    version: str = "1.0"
    status: Status | None = None
    activity_text: str | None = None
    activity_type: ActivityType | None = None

    def __init__(self, **data: Any):
        super().__init__(**data)
        if self.version != "1.0":
            raise ValueError(f"Unsupported configuration version: {self.version}")

    @property
    def activity(self) -> Activity | CustomActivity | None:
        """:class:`nextcord.Activity` | `None`: The activity to set."""
        if self.activity_text is None or self.activity_type is None:
            return None

        if self.activity_type == ActivityType.custom:
            return CustomActivity(
                name=self.activity_text,
            )

        return Activity(
            type=self.activity_type,
            name=self.activity_text,
        )

    @activity.setter
    def activity(self, value: Activity | CustomActivity | None) -> None:
        if isinstance(value, Activity):
            self.activity_text = value.name
            self.activity_type = value.type
        elif isinstance(value, CustomActivity):
            self.activity_text = value.name
            self.activity_type = ActivityType.custom
        else:
            self.activity_text = None
            self.activity_type = None

    @model_validator(mode="after")
    def _validate_activity(self) -> PresenceDataConfig:
        if (self.activity_text is None) ^ (self.activity_type is None):
            raise ValueError(
                "Both 'activity_text' and 'activity_type' "
                "must be set together or not at all."
            )

        return self
