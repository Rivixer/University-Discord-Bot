# SPDX-License-Identifier: MIT
"""A module to define views for role assignment."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nextcord.ui import View

from .buttons import RoleAssignmentButton
from .selects import RoleSelect

if TYPE_CHECKING:
    from nextcord import Member

    from ..config import RoleAssignmentNodeConfig
    from ..handler import RoleAssignmentHandler

__all__ = (
    "RoleAssignmentView",
    "RoleSelectView",
)


class RoleAssignmentView(View):
    """Represents a view for selecting a role.

    Parameters
    ----------
    nodes: :class:`.RoleAssignmentNodeConfig`
        A list of role assignment nodes.
    handler: :class:`.RoleAssignmentHandler`
        The role assignment handler.
    """

    def __init__(
        self,
        nodes: list[RoleAssignmentNodeConfig],
        handler: RoleAssignmentHandler,
    ) -> None:
        super().__init__(timeout=None)

        for node in nodes:
            if node.enabled:
                self.add_item(RoleAssignmentButton(node, handler))  # type: ignore


class RoleSelectView(View):
    """A view with a dropdown to select roles.

    Parameters
    ----------
    member: :class:`nextcord.Member`
        The member who is selecting the role.
    node: :class:`.RoleAssignmentNodeConfig`
        The role assignment node.
    handler: :class:`.RoleAssignmentHandler`
        The role assignment handler.
    """

    def __init__(
        self,
        member: Member,
        node: RoleAssignmentNodeConfig,
        handler: RoleAssignmentHandler,
    ) -> None:
        super().__init__(timeout=None)
        self.add_item(RoleSelect(member, node, handler))
