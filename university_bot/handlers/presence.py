# SPDX-License-Identifier: MIT
"""A module that contains the presence handler."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from nextcord import ActivityType, HTTPException, Status

from university_bot.exceptions.presence import InvalidEnumConversion

from .. import get_logger

if TYPE_CHECKING:
    from .. import Interaction
    from ..services.presence import PresenceService


_logger = get_logger(__name__)


class PresenceHandler:
    """A class to handle the presence commands.

    Attributes
    ----------
    service: :class:`.PresenceService`
        The presence service.
    """

    service: PresenceService

    def __init__(self, service: PresenceService) -> None:
        self.service = service

    async def set_status(self, interaction: Interaction, status: str) -> None:
        """|coro|

        Handles setting the bot's status.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        status: :class:`str`
            The status to set.

        Raises
        ------
        InvalidEnumConversion
            If the provided status is invalid.
        PresenceDataSaveFailed
            If saving the presence data to the file failed.
        """
        status_ = self._convert_to_enum(Status, status)
        await self.service.set_status(status_)
        await self._attempt_send_success_message(
            interaction, f"Status set to {status}."
        )

    async def set_activity(
        self,
        interaction: Interaction,
        activity_type: str,
        text: str,
    ) -> None:
        """|coro|

        Handles setting the bot's activity.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        activity_type: :class:`str`
            The type of the activity.
        text: :class:`str`
            The text of the activity.

        Raises
        ------
        InvalidEnumConversion
            If the provided activity type is invalid.
        PresenceDataSaveFailed
            If saving the presence data to the file failed.
        """
        activity_type_ = self._convert_to_enum(ActivityType, activity_type)
        await self.service.set_activity(activity_type_, text)
        await self._attempt_send_success_message(
            interaction, f"Activity set to {activity_type} {text}."
        )

    async def clear_activity(self, interaction: Interaction) -> None:
        """|coro|

        Handles clearing the bot's activity.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.

        Raises
        ------
        PresenceDataSaveFailed
            If saving the presence data to the file failed.
        """
        await self.service.clear_activity()
        await self._attempt_send_success_message(interaction, "Activity cleared.")

    async def _attempt_send_success_message(
        self,
        interaction: Interaction,
        content: str,
        delete_after: float | None = 5.0,
    ) -> None:
        send_message = (
            interaction.followup.send
            if interaction.response.is_done()
            else interaction.response.send_message
        )

        try:
            await send_message(content, ephemeral=True, delete_after=delete_after)
        except HTTPException as e:
            _logger.error(
                "Failed to send success message to %s. %s",
                interaction.user.id if interaction.user else "Unknown",
                e,
                exc_info=True,
            )

    @staticmethod
    def _convert_to_enum[T: Enum](enum_class: type[T], value: str) -> T:
        try:
            return enum_class[value.lower()]
        except KeyError as e:
            raise InvalidEnumConversion(enum_class.__name__, value) from e
