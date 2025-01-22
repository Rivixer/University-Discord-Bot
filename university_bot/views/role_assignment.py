# SPDX-License-Identifier: MIT
"""A module to define views for role assignment."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from nextcord import Member, SelectOption
from nextcord.ui import Button, Select, View

from .. import catch_interaction_exceptions
from ..exceptions.role_assignment import RoleAssignmentError

if TYPE_CHECKING:
    from .. import Interaction
    from ..handlers.role_assignment import RoleAssignmentHandler
    from ..models.configs.role_assignment import RoleAssignmentNodeConfig


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


class RoleAssignmentButton(Button[RoleAssignmentView]):
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


class RoleSelect(Select):
    """A dropdown menu for selecting roles.

    Parameters
    ----------
    member: :class:`nextcord.Member`
        The member who is selecting the role.
    node: :class:`.RoleAssignmentNodeConfig`
        The role assignment node.
    handler: :class:`.RoleAssignmentHandler`
        The role assignment handler.
    """

    node: RoleAssignmentNodeConfig
    handler: RoleAssignmentHandler

    def __init__(
        self,
        member: Member,
        node: RoleAssignmentNodeConfig,
        handler: RoleAssignmentHandler,
    ) -> None:
        self.node = node
        self.handler = handler

        options = [
            SelectOption(
                label=role.label,
                emoji=role.emoji,
                description=role.description,
                value=str(role.id_),
                default=role.id_ in (r.id for r in member.roles),
            )
            for role in node.roles
        ]

        super().__init__(
            placeholder=node.placeholder,
            min_values=node.min_selections or 0,
            max_values=min(node.max_selections or 25, len(options)),
            options=options,
        )

    @override
    @catch_interaction_exceptions([RoleAssignmentError], delete_after=15)
    async def callback(self, interaction: Interaction) -> None:
        await self.handler.handle_role_selection(interaction, self.node, self.values)
