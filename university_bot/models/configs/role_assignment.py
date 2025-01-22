# SPDX-License-Identifier: MIT
"""A module to define the configuration models for the role assignment."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from nextcord import ButtonStyle, Color, Embed
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ... import ConfigUtils

if TYPE_CHECKING:
    from nextcord import Guild, Role

    from ... import EmbedDict

__all__ = (
    "RoleAssignmentConfig",
    "RoleAssignmentDataConfig",
    "RoleAssignmentNodeConfig",
    "RoleAssignmentButtonConfig",
    "RoleAssignmentSuccessConfig",
    "RoleConfig",
)


class RoleAssignmentConfig(BaseModel):
    """The Role Assignment configuration."""

    data_filepath: Path

    @field_validator("data_filepath", mode="before")
    @classmethod
    def _validate_data_filepath(cls, value: str | Path) -> Path:
        path = Path(value) if not isinstance(value, Path) else value
        ConfigUtils.validate_data_filepath(path, ".json")
        return path


@ConfigUtils.auto_model_dump
class RoleAssignmentDataConfig(BaseModel):
    """The data configuration of the role assignment."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    version: str = "1.0"
    message_id: int | None
    channel_id: int | None
    content: str | None = None
    embed: Embed | None = None
    nodes: dict[str, RoleAssignmentNodeConfig]

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

    @staticmethod
    def get_example() -> RoleAssignmentDataConfig:
        """Returns an example of the data configuration."""
        return RoleAssignmentDataConfig(
            message_id=None,
            channel_id=None,
            content=None,
            embed=Embed(
                title="Click the button below to assign roles.",
                description="Use */role_assignment edit_configuration* to edit this message.",
                color=Color.red(),
            ),
            nodes={"example": RoleAssignmentNodeConfig.get_example()},
        )


class RoleAssignmentNodeConfig(BaseModel):
    """The configuration of the role assignment node."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    enabled: bool = True
    content: str | None
    embed: Embed | None
    button: RoleAssignmentButtonConfig
    placeholder: str | None
    delete_after: float | None
    success: RoleAssignmentSuccessConfig
    min_selections: int | None
    max_selections: int | None
    roles: list[RoleConfig]

    @model_validator(mode="after")
    def _validate_selections(self) -> RoleAssignmentNodeConfig:
        if self.min_selections is not None and self.max_selections is not None:
            if self.min_selections < 0:
                raise ValueError("min_selections must be greater than or equal to 0")
            if self.max_selections <= 0:
                raise ValueError("max_selections must be greater than 0")
            if self.max_selections > 25:
                raise ValueError("max_selections must be less than or equal to 25")
            if self.min_selections > self.max_selections:
                raise ValueError(
                    "min_selections must be less than or equal to max_selections"
                )
        return self

    @field_validator("embed", mode="before")
    @classmethod
    def _validate_embed(cls, value: Embed | EmbedDict | None) -> Embed | None:
        if value is None or isinstance(value, Embed):
            return value
        return Embed.from_dict(value)

    def get_roles(self, guild: Guild) -> list[Role]:
        """Returns the roles of the role assignment node.

        Parameters
        ----------
        guild: :class:`Guild`
            The guild where the roles are located.

        Returns
        -------
        List[:class:`Role`]
            The roles of the role assignment node.
        """
        return [r for r in (guild.get_role(r.id_) for r in self.roles) if r is not None]

    @staticmethod
    def get_example() -> RoleAssignmentNodeConfig:
        """Returns an example of the role assignment node configuration."""
        return RoleAssignmentNodeConfig(
            content="**EXAMPLE**",
            embed=Embed(
                title="Choose your role",
                description="Use */role_assignment edit_configuration* to modify "
                + "this message or roles.",
                color=Color.orange(),
            ),
            button=RoleAssignmentButtonConfig.get_example(),
            placeholder="Select a role",
            delete_after=30,
            success=RoleAssignmentSuccessConfig.get_example(),
            min_selections=1,
            max_selections=1,
            roles=[
                RoleConfig(
                    label="Role 1",
                    id_=1,
                    description="Description of Role 1",
                    emoji="🔴",
                ),
                RoleConfig(
                    label="Role 2",
                    id_=2,
                    description="Description of Role 2",
                    emoji="🟢",
                ),
                RoleConfig(
                    label="Role 3",
                    id_=3,
                    description="Description of Role 3",
                    emoji="🔵",
                ),
            ],
        )


class RoleAssignmentButtonConfig(BaseModel):
    """The configuration of the role assignment node button."""

    label: str
    style: ButtonStyle

    @staticmethod
    def get_example() -> RoleAssignmentButtonConfig:
        """Returns an example of the role assignment node button."""
        return RoleAssignmentButtonConfig(
            label="Select a role", style=ButtonStyle.primary
        )


class RoleAssignmentSuccessConfig(BaseModel):
    """The configuration of the role assignment success message."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    content: str | None
    embed: Embed | None
    delete_after: float | None

    @model_validator(mode="after")
    def _validate_content_and_embed(self) -> RoleAssignmentSuccessConfig:
        if self.content is None and self.embed is None:
            raise ValueError("At least one of 'content' or 'embed' must be provided.")
        return self

    @field_validator("embed", mode="before")
    @classmethod
    def _validate_embed(cls, value: Embed | EmbedDict | None) -> Embed | None:
        if value is None or isinstance(value, Embed):
            return value
        return Embed.from_dict(value)

    @staticmethod
    def get_example() -> RoleAssignmentSuccessConfig:
        """Returns an example of the role assignment success configuration."""
        return RoleAssignmentSuccessConfig(
            content="**CONGRATULATIONS**",
            embed=Embed(
                title="Success",
                description="You have successfully assigned the role.",
                color=Color.green(),
            ),
            delete_after=5,
        )


class RoleConfig(BaseModel):
    """The configuration of the role."""

    label: str
    id_: int
    description: str | None = None
    emoji: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _handle_alternative_id(cls, values: dict[str, Any]) -> dict[str, Any]:
        if "id" in values:
            values["id_"] = values.pop("id")
        return values
