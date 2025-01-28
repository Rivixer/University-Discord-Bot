# SPDX-License-Identifier: MIT
"""A module to define the configuration models for the voice channel manager."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from nextcord import CategoryChannel
from pydantic import BaseModel, model_validator

from .exceptions import MissingPermissions

if TYPE_CHECKING:
    from nextcord import Guild


class VoiceChannelManagerConfig(BaseModel):
    """The voice channel manager config."""

    enabled: bool
    managed_category_id: int
    ignore_bots: bool
    channel_order_strategy: Literal["random", "first available"]
    ensure_unique_names: bool
    overflow_channel_name: str
    available_channel_names: list[str]
    logging: VoiceChannelManagerLoggingConfig
    _category: CategoryChannel | None = None

    @property
    def category(self) -> CategoryChannel:
        """The managed category channel."""
        assert self._category is not None, "Category is not set."
        return self._category

    def set_category(self, guild: Guild):
        """Sets the `category` field.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild where the category is located.

        Raises
        ------
        ValueError
            If the category is invalid.
        """
        self._category = self._validate_category_id(guild)

    def _validate_category_id(self, guild: Guild) -> CategoryChannel:
        """Validates and retrieves the category channel."""
        category = guild.get_channel(self.managed_category_id)
        if not category or not isinstance(category, CategoryChannel):
            raise ValueError(
                f"Invalid `category_id`: {self.managed_category_id}. It must reference a category."
            )
        return category

    def validate_category_permissions(self, category: CategoryChannel):
        """Validates permissions for the bot in the category.

        Parameters
        ----------
        category: :class:`nextcord.CategoryChannel`
            The category channel.

        Raises
        ------
        MissingPermissions
            If the bot lacks `manage_channels` permissions in the category.
        """
        if not category.permissions_for(category.guild.me).manage_channels:
            raise MissingPermissions(
                "The bot lacks `manage_channels` permissions in the specified category."
            )

    @model_validator(mode="before")
    @classmethod
    def _normalize_channel_order_strategy(
        cls, values: dict[str, Any]
    ) -> dict[str, Any]:
        if (order := values.get("channel_order_strategy")) and isinstance(order, str):
            values["channel_order_strategy"] = order.lower()
        return values

    @model_validator(mode="after")
    def _validate_overflow_channel_name(self):
        if self.ensure_unique_names and "{number}" not in self.overflow_channel_name:
            raise ValueError(
                "`overflow_channel_name` must contain '{number}' "
                "if `ensure_unique_names` is True."
            )
        return self


class VoiceChannelManagerLoggingConfig(BaseModel):
    """The voice channel manager logging config."""

    channel_events: bool
    member_events: bool
    rate_limit: bool
