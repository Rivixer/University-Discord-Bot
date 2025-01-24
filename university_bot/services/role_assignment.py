# SPDX-License-Identifier: MIT
"""A service to manage the role assignment module."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from nextcord import (
    Forbidden,
    HTTPException,
    InvalidData,
    NotFound,
    TextChannel,
    Thread,
)
from nextcord.utils import MISSING
from pydantic import ValidationError

from .. import get_logger
from ..exceptions.role_assignment import (
    ConfigurationSaveFailed,
    InvalidConfiguration,
    ResourceFetchFailed,
    RoleAssignmentFailed,
    ViewNotLoaded,
)
from ..handlers.role_assignment import RoleAssignmentHandler
from ..models.configs.role_assignment import RoleAssignmentDataConfig
from ..views.role_assignment import RoleAssignmentView

if TYPE_CHECKING:
    from nextcord import Embed, Member, Message, Role

    from .. import UniversityBot
    from ..models.configs.role_assignment import RoleAssignmentConfig

_logger = get_logger(__name__)


class RoleAssignmentService:
    """A service to manage the role assignment configuration and data.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot instance.
    config: :class:`.RoleAssignmentConfig`
        The role assignment configuration.
    data: :class:`.RoleAssignmentDataConfig`
        The role assignment data configuration.
    """

    __slots__ = (
        "bot",
        "config",
        "data",
        "_view",
    )

    bot: UniversityBot
    config: RoleAssignmentConfig
    data: RoleAssignmentDataConfig
    _view: RoleAssignmentView | None

    def __init__(self, bot: UniversityBot, config: RoleAssignmentConfig) -> None:
        self.bot = bot
        self.config = config
        self._view = None

        try:
            self.data = RoleAssignmentDataConfig(**self._load_data())
        except FileNotFoundError:
            _logger.warning("Data file is missing, creating a new one.")
            self.data = RoleAssignmentDataConfig.get_example()
            self._save_data()
        except json.JSONDecodeError as e:
            _logger.error("Data file is invalid.")
            raise InvalidConfiguration("Data file is invalid.") from e

    def update_message_data(self, message: Message) -> None:
        """Updates the message ID and channel ID of the role assignment.

        Parameters
        ----------
        message: :class:`Message`
            The message of the role assignment.

        Raises
        ------
        ConfigurationSaveFailed
            Failed to save the data.
        """
        self.data.message_id = message.id
        self.data.channel_id = message.channel.id
        self._save_data()

    def create_view(self, handler: RoleAssignmentHandler) -> RoleAssignmentView:
        """Creates a new view and registers it to the bot.

        If a view already exists, it will be unloaded first.

        Returns
        -------
        :class:`.RoleAssignmentView`
            The new role assignment view.
        """
        if self._view is not None:
            self.unload_view()

        nodes = list(self.data.nodes.values())
        self._view = RoleAssignmentView(nodes, handler)
        _logger.debug("View created.")

        self.bot.add_view(self._view)
        _logger.info("View registered to bot.")

        return self._view

    async def load_view(self, handler: RoleAssignmentHandler) -> None:
        """Loads the view for role assignment."""
        await self.bot.wait_until_ready()

        _logger.debug("Loading view.")

        if (channel_id := self.data.channel_id) is None:
            _logger.warning("Channel ID is missing, loading view skipped.")
            return

        if (message_id := self.data.message_id) is None:
            _logger.warning("Message ID is missing, loading view skipped.")
            return

        try:
            channel = await self._fetch_channel(self.bot, channel_id)
            message = await self._fetch_message(channel, message_id)
        except ResourceFetchFailed as e:
            _logger.error("Failed to load view: %s", e)
            return

        message_data = self.prepare_message_data(handler)
        try:
            await message.edit(**message_data.to_dict())
        except HTTPException as e:
            _logger.error("Failed to edit view message: %s", e)
        else:
            _logger.info("View loaded.")

    def unload_view(self) -> None:
        """Unloads the view for role assignment.

        Raises
        ------
        ViewNotLoaded
            The view is not loaded.
        """

        if self._view is None:
            raise ViewNotLoaded("View is not loaded.")

        _logger.debug("Unloading view.")
        self.bot.remove_view(self._view)
        _logger.info("View unregistered from bot.")
        self._view = None
        _logger.info("View unloaded.")

    async def reload_view(self, handler: RoleAssignmentHandler) -> None:
        """Reloads the view for role assignment.

        If the view is already loaded, it will be unloaded first.
        """
        if self._view is not None:
            self.unload_view()
        await self.load_view(handler)

    def _save_data(self) -> None:
        try:
            with self.bot.temporary_files_config.context() as ctx:
                with ctx.open("w", encoding="utf-8") as f:
                    json.dump(self.data.model_dump(), f, indent=4)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(ctx, self.config.data_filepath)
            _logger.debug("Data saved successfully.")
        except Exception as e:
            _logger.error("Failed to save data.", exc_info=True)
            raise ConfigurationSaveFailed("Failed to save data.") from e

    def _load_data(self) -> dict[str, Any]:
        with open(self.config.data_filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def prepare_message_data(
        self,
        handler: RoleAssignmentHandler,
        missing: bool = False,
    ) -> MessageData:
        """Prepares the data required for sending a message.

        Parameters
        ----------
        handler: :class:`.RoleAssignmentHandler`
            The role assignment handler.
        missing: :class:`bool`
            Whether to include missing values in the data,
            instead of returning `None`.


        Returns
        -------
        :class:`.MessageData`
            The message data.
        """
        return MessageData(
            self.data.content or (MISSING if missing else None),
            self.data.embed or (MISSING if missing else None),
            self.create_view(handler),
        )

    async def validate_and_save_data(self, json_content: str) -> None:
        """Validates and saves the data from a JSON string.

        Parameters
        ----------
        json_content: :class:`str`
            The JSON content to validate and save.

        Raises
        ------
        InvalidConfiguration
            The content is invalid.
        ConfigurationSaveFailed
            Failed to save the data.
        """

        try:
            data = RoleAssignmentDataConfig(**json.loads(json_content))
            if data.channel_id and data.message_id:
                channel = await self._fetch_channel(self.bot, data.channel_id)
                await self._fetch_message(channel, data.message_id)
        except (ValidationError, json.JSONDecodeError, ResourceFetchFailed) as e:
            raise InvalidConfiguration("Invalid JSON content.") from e

        current_data = self.data

        try:
            self.data = data
            self._save_data()
        except ConfigurationSaveFailed as e:
            self.data = current_data
            raise e

    def get_config_content(self, indent: int) -> str:
        """Reads and returns the configuration as a formatted JSON string.

        Parameters
        ----------
        indent: :class:`int`
            The number of spaces to indent the JSON content.

        Returns
        -------
        :class:`str`
            The formatted JSON content.

        Raises
        ------
        FileNotFoundError
            The configuration file is missing.
        ValueError
            The configuration file contains invalid JSON.
        """
        try:
            return json.dumps(self._load_data(), indent=indent)
        except FileNotFoundError as e:
            raise FileNotFoundError("Configuration file not found.") from e
        except json.JSONDecodeError as e:
            raise ValueError("Configuration file contains invalid JSON.") from e

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

    @staticmethod
    async def _fetch_channel(
        bot: UniversityBot, channel_id: int
    ) -> TextChannel | Thread:
        try:
            channel = await bot.guild.fetch_channel(channel_id)
        except NotFound as e:
            raise ResourceFetchFailed(
                "channel", f"Channel {channel_id} does not exist in guild."
            ) from e
        except Forbidden as e:
            raise ResourceFetchFailed(
                "channel", f"Permission denied for channel {channel_id}."
            ) from e
        except (HTTPException, InvalidData) as e:
            raise ResourceFetchFailed(
                "channel", f"An error occurred while fetching channel {channel_id}: {e}"
            ) from e

        if not isinstance(channel, TextChannel | Thread):
            raise ResourceFetchFailed(
                "channel", f"Channel {channel_id} is not a text channel or thread."
            )

        return channel

    @staticmethod
    async def _fetch_message(channel: TextChannel | Thread, message_id: int) -> Message:
        try:
            return await channel.fetch_message(message_id)
        except Forbidden as e:
            raise ResourceFetchFailed(
                "message", f"Permission denied for message {message_id}."
            ) from e
        except NotFound as e:
            raise ResourceFetchFailed(
                "message",
                f"Message {message_id} does not exist in channel {channel.id}.",
            ) from e
        except HTTPException as e:
            raise ResourceFetchFailed(
                "message", f"An error occurred while fetching message {message_id}: {e}"
            ) from e


@dataclass(slots=True)
class MessageData:
    """Data for sending a message.

    Attributes
    ----------
    content: :class:`str` | None
        The message content.
    embed: :class:`nextcord.Embed` | None
        The message embed.
    view: :class:`.RoleAssignmentView`
        The message view.
    """

    content: str | None
    embed: Embed | None
    view: RoleAssignmentView

    def to_dict(self) -> dict[str, Any]:
        """Returns the data as a dictionary."""
        return {
            "content": self.content,
            "embed": self.embed,
            "view": self.view,
        }
