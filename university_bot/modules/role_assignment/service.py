# SPDX-License-Identifier: MIT
"""A service to manage the role assignment module."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, override

from nextcord import Embed
from nextcord.utils import MISSING
from pydantic import ValidationError

from university_bot import (
    MessageData,
    ResourceFetchFailed,
    fetch_channel,
    fetch_message,
    get_logger,
)
from university_bot.mixins.static_message import StaticViewMixin

from .config import RoleAssignmentDataConfig
from .exceptions import RoleAssignmentFailed
from .handler import RoleAssignmentHandler
from .views import RoleAssignmentView
from ...mixins.configuration import ConfigurationServiceMixin, InvalidConfiguration

if TYPE_CHECKING:
    from nextcord import Member, Role

    from university_bot import UniversityBot

    from .config import RoleAssignmentConfig


_logger = get_logger(__name__)


class RoleAssignmentService(
    ConfigurationServiceMixin[RoleAssignmentDataConfig],
    StaticViewMixin[
        RoleAssignmentHandler,
        RoleAssignmentView,
        RoleAssignmentDataConfig,
    ],
):
    """A service to manage the role assignment configuration and data.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot instance.
    config: :class:`.RoleAssignmentConfig`
        The role assignment configuration.
    data: :class:`.RoleAssignmentDataConfig`
        The role assignment data configuration.
    view: :class:`.RoleAssignmentView` | :class:`None`
        The role assignment view.
    """

    bot: UniversityBot
    config: RoleAssignmentConfig
    data: RoleAssignmentDataConfig
    view: RoleAssignmentView | None

    def __init__(self, bot: UniversityBot, config: RoleAssignmentConfig) -> None:
        self.bot = bot
        self.config = config

        try:
            self.data = RoleAssignmentDataConfig.load(self.config.data_filepath)
        except FileNotFoundError:
            _logger.warning("Data file is missing, creating a new one.")
            self.data = RoleAssignmentDataConfig.get_example()
            self.data.save(self.config.data_filepath, bot, _logger)
        except json.JSONDecodeError as e:
            _logger.error("Data file is invalid.")
            raise InvalidConfiguration("Data file is invalid.") from e

        ConfigurationServiceMixin.__init__(  # type: ignore
            self, bot, self.data, self.config.data_filepath, _logger
        )

        StaticViewMixin.__init__(  # type: ignore
            self,
            bot,
            self.config.data_filepath,
            self.data,
            _logger,
        )

    @override
    def get_data_from_string(self, content: str) -> RoleAssignmentDataConfig:
        return RoleAssignmentDataConfig(**json.loads(content))

    @override
    def create_view(self, handler: RoleAssignmentHandler) -> RoleAssignmentView:
        nodes = list(self.data.nodes.values())
        self.view = RoleAssignmentView(nodes, handler)
        self.bot.add_view(self.view)
        return self.view

    @override
    async def prepare_message_data(
        self,
        handler: RoleAssignmentHandler,
        missing: bool = False,
    ) -> MessageData[Embed, RoleAssignmentView]:
        return MessageData(
            self.data.content or (MISSING if missing else None),
            self.data.embed or (MISSING if missing else None),
            self.create_view(handler),
        )

    @override
    async def validate_data(self, json_content: str) -> None:
        try:
            data = RoleAssignmentDataConfig(**json.loads(json_content))
            if data.channel_id and data.message_id:
                channel = await fetch_channel(self.bot, data.channel_id)
                await fetch_message(channel, data.message_id)
        except (ValidationError, json.JSONDecodeError, ResourceFetchFailed) as e:
            raise InvalidConfiguration("Invalid JSON content.") from e

    @override
    async def refresh_message(self, handler: RoleAssignmentHandler) -> None:
        await self.reload_view(handler)

    async def assign_roles(
        self,
        member: Member,
        selected_roles: list[Role],
        selectable_roles: list[Role],
    ) -> None:
        """Assigns and removes roles for a member.

        Parameters
        ----------
        member: :class:`Member`
            The member to update roles for.
        selected_roles : list[:class:`Role`]
            The roles selected by the member.
        selectable_roles : list[:class:`Role`]
            The roles that can be assigned or removed.

        Raises
        ------
        RoleAssignmentFailed
            Failed to update roles for the member.
        """
        roles_to_delete = [r for r in selectable_roles if r not in selected_roles]
        roles_to_add = [r for r in selected_roles if r not in member.roles]

        results = await asyncio.gather(
            member.add_roles(*roles_to_add),
            member.remove_roles(*roles_to_delete),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                raise RoleAssignmentFailed(
                    "Failed to update roles for user."
                ) from result
