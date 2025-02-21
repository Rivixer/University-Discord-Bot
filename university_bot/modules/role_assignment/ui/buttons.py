# SPDX-License-Identifier: MIT
"""A module to define buttons for role assignment UI."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from nextcord.ui import Button

from university_bot import catch_interaction_exceptions

from ..exceptions import RoleAssignmentError

if TYPE_CHECKING:
    from university_bot import Interaction

    from ..config import RoleAssignmentNodeConfig
    from ..handler import RoleAssignmentHandler

__all__ = ("RoleAssignmentButton",)


class RoleAssignmentButton(Button):  # type: ignore
    """Represents a UI button for selecting a role.

    Parameters
    ----------
    node: :class:`.RoleAssignmentNodeConfig`
        The role assignment node.
    handler: :class:`.RoleAssignmentHandler`
        The role assignment handler.
    """

    node: RoleAssignmentNodeConfig
    handler: RoleAssignmentHandler

    def __init__(
        self, node: RoleAssignmentNodeConfig, handler: RoleAssignmentHandler
    ) -> None:
        self.node = node
        self.handler = handler
        super().__init__(label=node.button.label, style=node.button.style)

    @override
    @catch_interaction_exceptions([RoleAssignmentError], delete_after=15)
    async def callback(self, interaction: Interaction) -> None:
        await self.handler.handle_node_selection(interaction, self.node)
