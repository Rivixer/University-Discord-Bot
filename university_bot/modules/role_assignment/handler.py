# SPDX-License-Identifier: MIT
"""A module that contains the role assignment handler."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, override

from nextcord import Forbidden, HTTPException, InvalidArgument
from nextcord.utils import MISSING

from university_bot import InteractionUtils, Localization, get_logger
from university_bot.mixins.configuration import (
    ConfigurationHandlerMixin,
    SaveConfigurationFailedError,
)
from university_bot.utils import MessageDeletionError, attempt_message_delete

from .exceptions import RoleAssignmentError, RoleAssignmentFailedError
from .ui.views import RoleSelectView

if TYPE_CHECKING:
    from nextcord import Guild, Member, Role

    from university_bot import Interaction

    from .config import RoleAssignmentNodeConfig
    from .service import RoleAssignmentService


_logger = get_logger(__name__)


class RoleAssignmentHandler(ConfigurationHandlerMixin):
    """A class to handle the role assignment commands.

    Attributes
    ----------
    service: :class:`.RoleAssignmentService`
        The role assignment service.
    """

    service: RoleAssignmentService

    def __init__(self, service: RoleAssignmentService) -> None:
        self.service = service
        super().__init__(service, _logger)

    @override
    async def _apply_configuration_updates(self, content: str) -> None:
        await super()._apply_configuration_updates(content)
        await self.service.reload_view(self)

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
            - If the command is not used on a messageable channel.
            - If preparing the message data fails.
            - If sending the message fails.
            - If saving the message data fails.
        """
        try:
            channel = InteractionUtils.ensure_messageable_channel(interaction)
        except TypeError as e:
            raise RoleAssignmentError(
                "Command must be used on a messageable channel."
            ) from e

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
            raise RoleAssignmentError("Failed to prepare message data.") from e

        try:
            message = await channel.send(**message_data)
        except (Forbidden, HTTPException, InvalidArgument) as e:
            _logger.error(
                "Failed to send message on channel %s: %s",
                channel_id,
                e,
                exc_info=True,
            )
            raise RoleAssignmentError("Failed to send message.") from e

        if preview:
            await interaction.followup.send(**message_data, ephemeral=True)
            return

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
                await attempt_message_delete(message, e, _logger)
            except MessageDeletionError as del_err:
                raise RoleAssignmentError(
                    "Failed to save message data and delete message."
                ) from del_err
            raise RoleAssignmentError("Failed to save message data.") from e

        _logger.info(
            "Sent role assignment message (%s) in channel %s.",
            message.id,
            channel_log,
        )

        try:
            await interaction.response.send_message(
                Localization.get_command_response(
                    interaction, "message_sent", "Role assignment message sent."
                ),
                ephemeral=True,
                delete_after=30,
            )
        except HTTPException as e:
            pass

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

        if forbidden_role := node.get_forbidden_member_role(member):
            content = node.forbidden.content
            embed = node.forbidden.embed or MISSING
            if embed.description:
                embed.description = embed.description.format(
                    role=forbidden_role.mention
                )
            view = MISSING
            delete_after = node.forbidden.delete_after
        else:
            content = node.content
            embed = node.embed or MISSING
            view = RoleSelectView(member, node, self)
            delete_after = node.delete_after

        try:
            await interaction.response.send_message(
                content=content,
                embed=embed,
                view=view,
                delete_after=delete_after,
                ephemeral=True,
            )
        except HTTPException as e:
            _logger.error(
                "Failed to send role selection view (node=%s) for member %s. %s",
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
                raise RoleAssignmentFailedError(f"Failed to find role {role_id}.")
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
                raise RoleAssignmentFailedError("Failed to update roles.") from result

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
