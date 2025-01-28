# SPDX-License-Identifier: MIT
"""A module that contains the role assignment handler."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from nextcord import (
    File,
    Forbidden,
    HTTPException,
    InteractionResponded,
    InvalidArgument,
    NotFound,
)
from nextcord.utils import MISSING

from university_bot import InteractionUtils, catch_interaction_exceptions, get_logger
from university_bot.views.configuration import EditConfigurationModal

from .exceptions import (
    ConfigurationSaveFailed,
    ConfigurationUpdateError,
    InvalidConfiguration,
    RoleAssignmentError,
    RoleAssignmentFailed,
)
from .views import RoleSelectView

if TYPE_CHECKING:
    from nextcord import Attachment, Guild, Member, Message, Role

    from university_bot import Interaction

    from .config import RoleAssignmentNodeConfig
    from .service import RoleAssignmentService


_logger = get_logger(__name__)


class RoleAssignmentHandler:
    """A class to handle the role assignment commands.

    Attributes
    ----------
    service: :class:`.RoleAssignmentService`
        The role assignment service.
    """

    service: RoleAssignmentService

    def __init__(self, service: RoleAssignmentService) -> None:
        self.service = service

    async def send_message(self, interaction: Interaction, preview: bool) -> None:
        """|coro|

        Handles sending a new role assignment message.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        preview: :class:`bool`
            Whether to send a preview of the message.

        Raises
        ------
        RoleAssignmentError
            - If the command must be used on a messageable channel.
            - If the message data is invalid.
            - If the message sending fails.
            - If the save data fails.
        """
        try:
            channel = InteractionUtils.ensure_messageable_channel(interaction)
            channel_id: int = getattr(channel, "id")
        except TypeError as e:
            raise RoleAssignmentError(
                "Command must be used on messageable channel."
            ) from e

        try:
            message_data = self.service.prepare_message_data(
                self, missing=preview
            ).to_dict()

            if preview:
                await interaction.followup.send(**message_data, ephemeral=True)
                return

            message = await channel.send(**message_data)

            try:
                self.service.update_message_data(message)
            except ConfigurationSaveFailed as e:
                _logger.error(
                    "Failed to save message data for message %s on channel %s. "
                    "Trying to delete message.",
                    message.id,
                    channel_id,
                    exc_info=True,
                )
                await self._attempt_message_delete_after_save_failure(message, e)
        except Forbidden as e:
            _logger.error("Failed to send message on channel %s. %s", channel_id, e)
            raise RoleAssignmentError("Failed to send message") from e
        except HTTPException as e:
            _logger.error(
                "Failed to send message on channel %s. %s", channel_id, e, exc_info=True
            )
            raise RoleAssignmentError("Failed to send message") from e
        except (InvalidArgument, ValueError) as e:
            _logger.error("Invalid message data. %s", e, exc_info=True)
            raise RoleAssignmentError("Failed to send message") from e

        _logger.info(
            "Message with view sent on channel %s (message_id=%s).",
            channel_id,
            message.id,
        )

    async def get_configuration(self, interaction: Interaction) -> None:
        """|coro|

        Handles sending the current configuration file.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.

        Raises
        ------
        RoleAssignmentError
            - If getting the configuration file fails.
            - If sending the message with the configuration file fails.
        """
        try:
            file = File(self.service.config.data_filepath)
        except FileNotFoundError as e:
            _logger.error("Failed to get configuration file. %s", e)
            raise RoleAssignmentError("Failed to get configuration file.") from e

        try:
            await interaction.response.send_message(file=file, ephemeral=True)
        except HTTPException as e:
            _logger.error("Failed to send configuration file. %s", e, exc_info=True)
            raise RoleAssignmentError("Failed to send configuration file.") from e

    async def set_configuration(
        self,
        interaction: Interaction,
        attachment: Attachment,
    ) -> None:
        """|coro|

        Handles setting a new configuration from an attachment.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        attachment: :class:`nextcord.Attachment`
            The attachment containing the new configuration.

        Raises
        ------
        ConfigurationUpdateError
            - If reading the attachment fails.
            - If applying the configuration updates fails.
        """
        try:
            content = await attachment.read()
            content = content.decode("utf-8")
        except HTTPException as e:
            _logger.error(
                "Failed to read attachment %s. %s", attachment.id, e, exc_info=True
            )
            raise ConfigurationUpdateError("Failed to read attachment.") from e

        await self._apply_configuration_updates(content)
        await self._attempt_send_set_configuration_success_message(interaction)

    async def edit_configuration(self, interaction: Interaction, indent: int) -> None:
        """|coro|

        Handles the interaction for editing configuration.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        indent: :class:`int`
            The indentation level for the JSON content.

        Raises
        ------
        ContentTooLongError
            If the content is too long to be displayed in a TextInput.

        RoleAssignmentError
            - If getting the config content fails.
            - If sending the modal fails.
            - If validating the configuration fails.
            - If saving the configuration updates fails.
        """
        try:
            content = self.service.get_config_content(indent)
        except (FileNotFoundError, ValueError) as e:
            _logger.error("Failed to get config content. %s", e)
            raise ConfigurationUpdateError("Failed to get config content.") from e

        @catch_interaction_exceptions([RoleAssignmentError])
        async def callback(
            _: EditConfigurationModal,
            interaction: Interaction,
            content: str,
        ) -> None:
            await self._apply_configuration_updates(content)
            await self._attempt_send_set_configuration_success_message(interaction)

        modal = EditConfigurationModal(content=content, callback_fn=callback)

        try:
            await interaction.response.send_modal(modal)
        except (HTTPException, InteractionResponded) as e:
            raise RoleAssignmentError("Failed to send modal.") from e

    async def handle_node_selection(
        self,
        interaction: Interaction,
        node: RoleAssignmentNodeConfig,
    ) -> None:
        """|coro|

        Handles the role selection process for a node.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction object from the user.
        node: :class:`.RoleAssignmentNodeConfig`
            The role assignment node containing role configuration.

        Raises
        ------
        RoleAssignmentError
            If sending the role selection view fails.
        """
        member: Member = interaction.user  # type: ignore

        try:
            await interaction.response.send_message(
                embed=node.embed if node.embed else MISSING,
                view=RoleSelectView(member, node, self),
                ephemeral=True,
                delete_after=node.delete_after,
            )
        except HTTPException as e:
            _logger.error(
                "Failed to role selection view (node=%s) for member %s. %s",
                node.button.label,
                member.id,
                e,
                exc_info=True,
            )
            raise RoleAssignmentError("Failed to send role selection view.") from e

    async def handle_role_selection(
        self,
        interaction: Interaction,
        node: RoleAssignmentNodeConfig,
        selected_values: list[str],
    ) -> None:
        """|coro|

        Handles the role selection process.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction object from the user.
        node: :class:`.RoleAssignmentNodeConfig`
            The role assignment node containing role configuration.
        selected_values: list[:class:`str`]
            The selected role values.

        Raises
        ------
        RoleAssignmentFailed
            - If selected role is not found.
            - If adding or removing roles fails.
        """
        guild: Guild = interaction.guild  # type: ignore
        member: Member = interaction.user  # type: ignore

        selectable_roles = node.get_roles(guild)

        selected_roles: list[Role] = []
        for role_id in selected_values:
            if (role := guild.get_role(int(role_id))) is None:
                _logger.error(
                    "Failed to find role for %s with ID %s",
                    member.id,
                    role_id,
                )
                raise RoleAssignmentFailed(f"Failed to find role {role_id}.")
            selected_roles.append(role)

        roles_to_delete = [r for r in selectable_roles if r not in selected_roles]
        roles_to_add = [r for r in selected_roles if r and r not in member.roles]

        results = await asyncio.gather(
            member.add_roles(*roles_to_add),
            member.remove_roles(*roles_to_delete),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                _logger.error(
                    "Failed to update roles for user %s. %s",
                    member.id,
                    result,
                    exc_info=True,
                )
                raise RoleAssignmentFailed("Failed to update roles.") from result

        await self._attempt_response_assignment_success(interaction, node)

    async def _attempt_response_assignment_success(
        self,
        interaction: Interaction,
        node: RoleAssignmentNodeConfig,
    ) -> None:
        try:
            await interaction.response.edit_message(
                content=node.success.content,
                embed=node.success.embed,
                view=None,
                delete_after=node.success.delete_after,
            )
        except HTTPException as e:
            _logger.warning(
                "Failed to send success message for role assignment to %s. %s",
                interaction.user.id if interaction.user else "Unknown",
                e,
            )

    async def _attempt_message_delete_after_save_failure(
        self,
        message: Message,
        original_error: Exception,
    ) -> None:
        try:
            await message.delete()
            _logger.info(
                "Message %s successfully deleted after save failure.", message.id
            )
        except NotFound:
            _logger.warning(
                "Message %s not found during deletion. It may have already been removed.",
                message.id,
            )
        except HTTPException as e:
            _logger.error(
                "Failed to delete message %s on channel %s after save failure.",
                message.id,
                message.channel.id,
                exc_info=True,
            )
            raise RoleAssignmentError(
                "Failed to delete message after save failure. "
                f"Original error: {original_error}, Delete error: {e}"
            ) from e

    async def _attempt_send_set_configuration_success_message(
        self, interaction: Interaction
    ) -> None:
        send_message = (
            interaction.followup.send
            if interaction.response.is_done()
            else interaction.response.send_message
        )

        try:
            await send_message("Configuration updated successfully.", ephemeral=True)
        except HTTPException as e:
            _logger.error(
                "Failed to send success message for configuration update to %s. %s",
                interaction.user.id if interaction.user else "Unknown",
                e,
                exc_info=True,
            )

    async def _apply_configuration_updates(self, content: str) -> None:
        try:
            await self.service.validate_and_save_data(content)
        except (InvalidConfiguration, ConfigurationSaveFailed) as e:
            _logger.error(
                "Failed to save configuration updates. %s",
                e,
                exc_info=True,
            )
            raise ConfigurationUpdateError(
                "Failed to save configuration updates."
            ) from e

        await self.service.reload_view(self)
