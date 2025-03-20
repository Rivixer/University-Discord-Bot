# SPDX-License-Identifier: MIT
"""A module to define handler for calendar interactions."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from nextcord import Forbidden, HTTPException, InvalidArgument

from university_bot import InteractionUtils, get_logger
from university_bot.mixins.configuration import (
    ConfigurationHandlerMixin,
    SaveConfigurationFailedError,
)
from university_bot.utils import (
    Localization,
    MessageDeletionError,
    attempt_message_delete_after_save_failure,
)

from .exceptions import CalendarError
from .ui import CalendarManager

if TYPE_CHECKING:
    from university_bot import Interaction

    from .service import CalendarService
    from ..reminder import ReminderCog

__all__ = ("CalendarHandler",)

_logger = get_logger(__name__)


class CalendarHandler(ConfigurationHandlerMixin):
    """A class to handle calendar interactions.

    Attributes
    ----------
    service: :class:`.CalendarService`
        The calendar service.
    """

    service: CalendarService

    def __init__(self, service: CalendarService) -> None:
        self.service = service
        super().__init__(service, _logger)

    @override
    async def _apply_configuration_updates(self, content: str) -> None:
        await super()._apply_configuration_updates(content)
        await self.service.refresh_message(self)

    @property
    def _reminder_cog(self) -> ReminderCog | None:
        """:class:`.ReminderCog`: The reminder cog if available; otherwise, ``None``."""
        return self.service.bot.get_cog("ReminderCog")  # type: ignore

    async def send_message(self, interaction: Interaction, preview: bool) -> None:
        """|coro|

        Handles sending a new calendar message.

        Parameters
        ----------
        interaction: :class:`.Interaction`
            The interaction that triggered the command.
        preview: :class:`bool`
            Whether to send a preview of the message.

        Raises
        ------
        CalendarError
            - If the command is not used on a messageable channel.
            - If the message sending fails.
            - If the message data is invalid.
            - If saving the message data fails.
        """

        try:
            channel = InteractionUtils.ensure_messageable_channel(interaction)
        except TypeError as e:
            raise CalendarError("Command must be used on a messageable channel.") from e

        channel_id: int = getattr(channel, "id", -1)
        channel_name: str = getattr(channel, "name", "Unknown")
        channel_log = f'"{channel_name}" ({channel_id})'

        try:
            message_data = await self.service.prepare_message_data(
                self, missing=preview
            )
        except ValueError as e:
            _logger.error(
                "Failed to prepare message data for channel %s.",
                channel_log,
                exc_info=True,
            )
            raise CalendarError("Failed to prepare message data.") from e

        if preview:
            await interaction.response.send_message(**message_data, ephemeral=True)
            return

        try:
            message = await channel.send(**message_data)
        except (Forbidden, HTTPException, InvalidArgument) as e:
            _logger.error(
                "Failed to send message on channel %s: %s",
                channel_id,
                e,
                exc_info=True,
            )
            raise CalendarError("Failed to send message.") from e

        try:
            self.service.update_message_data(message)
        except SaveConfigurationFailedError as e:
            _logger.error(
                "Failed to save message data for message %s on channel %s. "
                "Trying to delete message.",
                message.id,
                channel_log,
                exc_info=True,
            )
            try:
                await attempt_message_delete_after_save_failure(message, e, _logger)
            except MessageDeletionError as del_err:
                raise CalendarError(
                    "Failed to save message data and delete message."
                ) from del_err
            raise CalendarError("Failed to save message data.") from e

        _logger.info(
            "Sent calendar message (%s) in channel %s.",
            message.id,
            channel_log,
        )

        self.service.start_remove_deprecated_events_loop_if_not_running(self)

        try:
            await interaction.response.send_message(
                Localization.get_command_response(
                    interaction, "message_sent", "Verification message sent."
                ),
                ephemeral=True,
                delete_after=30,
            )
        except HTTPException as e:
            pass

    async def send_menu(self, interaction: Interaction) -> None:
        """|coro|

        Handles sending a new calendar menu.

        Parameters
        ----------
        interaction: :class:`.Interaction`
            The interaction that triggered the command.

        Raises
        ------
        CalendarError
            If sending the menu view fails.
        """
        try:
            await CalendarManager.create_and_send(self, interaction, self._reminder_cog)
        except HTTPException as e:
            _logger.error("Failed to send menu view.", exc_info=True)
            raise CalendarError("Failed to send menu view.") from e
