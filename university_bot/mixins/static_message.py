# SPDX-License-Identifier: MIT
"""Module for static message and view mixin functionality.

This module defines abstract mixin classes for managing a static message on Discord
which is modified during the bot's runtime. All operations, such as editing the message
content or managing interactive views, are performed on this central static message.
These mixins can be incorporated into module service classes to add persistent static
message functionality.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from nextcord import HTTPException
from nextcord.ui import View

from university_bot.exceptions import ResourceFetchFailed, ViewNotLoaded
from university_bot.models import DataConfigBaseModel
from university_bot.utils import fetch_channel, fetch_message

if TYPE_CHECKING:
    from nextcord import Message

    from university_bot import UniversityBot
    from university_bot.models import MessageData


class StaticMessageDataConfig(DataConfigBaseModel, ABC):
    """Base class for static message configuration data.

    Attributes
    ----------
    channel_id: :class:`int` | `None`
        The ID of the channel containing the static message.
    message_id: :class:`int` | `None`
        The ID of the static message.
    """

    channel_id: int | None
    message_id: int | None

    async def ensure_valid_message(self, bot: UniversityBot) -> None:
        """|coro|

        Ensures that the static message configuration is valid.

        This method checks whether the provided `channel_id` and `message_id`
        correspond to an existing message in Discord. If either ID is `None`,
        the validation is skipped. If the message cannot be fetched, a
        ResourceFetchFailed exception is raised.

        Parameters
        ----------
        bot: UniversityBot
            The bot instance used to fetch the channel and message.

        Raises
        ------
        ResourceFetchFailed
            If the channel or message cannot be fetched.
        """
        if self.channel_id is None or self.message_id is None:
            return

        channel = await fetch_channel(bot, self.channel_id)
        await fetch_message(channel, self.message_id)


# Fix type hinting
HandlerT = TypeVar("HandlerT")
DataT = TypeVar("DataT")
EmbedT = TypeVar("EmbedT")
ViewT = TypeVar("ViewT")


class StaticMessageMixin[HandlerT, DataT: StaticMessageDataConfig](ABC):
    """Base mixin class for managing a static message.

    This mixin is responsible for handling operations on a static message, such as
    fetching, refreshing, and updating the message. The static message represents a fixed
    message on Discord that can be modified during the bot's runtime.

    Should be used by service classes that require a static message to be managed.

    Attributes
    ----------
    bot: UniversityBot
        The bot instance.
    data_filepath: :class:`Path` | `str`
        The file path to the configuration data.
    data: DataT
        The static message configuration data.
    """

    bot: UniversityBot
    data_filepath: Path | str
    data: DataT
    __logger: Logger

    def __init__(
        self,
        bot: UniversityBot,
        data_filepath: Path | str,
        data: DataT,
        logger: Logger,
    ) -> None:
        self.bot = bot
        self.data_filepath = data_filepath
        self.data = data
        self.__logger = logger

    async def _fetch_message(self, *, missing_ok: bool = False) -> Message | None:
        """|coro|

        Fetches the static message from Discord.

        This method retrieves the static message using the stored channel and message IDs.
        If either ID is missing and ``missing_ok`` is False,
        a :exc:`ResourceFetchFailed` exception is raised.

        Parameters
        ----------
        missing_ok: :class:`bool` | `None`
            If True, returns None when the channel or message ID is missing (default is False).

        Returns
        -------
        :class:`nextcord.Message` | `None`
            The fetched message if available, or None if the IDs are missing
            and ``missing_ok`` is True.

        Raises
        ------
        ResourceFetchFailed
            If either the channel or message ID is missing and ``missing_ok`` is False.
        """
        channel_id = self.data.channel_id
        message_id = self.data.message_id

        if channel_id is None or message_id is None:
            if not missing_ok:
                raise ResourceFetchFailed("Channel ID or message ID is missing.")
            return None

        channel = await fetch_channel(self.bot, channel_id)
        return await fetch_message(channel, message_id)

    @abstractmethod
    async def prepare_message_data(
        self,
        handler: ...,
        missing: bool = False,
    ) -> MessageData[Any, Any]:
        """|coro|

        Prepares the message data for updating the static message.

        Parameters
        ----------
        handler: :class:`.Handler`
            The handler instance.
        missing: :class:`bool` | `None`
            Whether to include missing values in the message data (default is False).

        Returns
        -------
        :class:`MessageData`
            The prepared message data.
        """

    def update_message_data(self, message: Message) -> None:
        """Updates the static message configuration with new IDs.

        This method updates the channel and message IDs based on the provided message
        and saves the updated configuration.

        Parameters
        ----------
        message: :class:`nextcord.Message`
            The message used to update the configuration.

        Raises
        ------
        ConfigurationSaveFailed
            If saving the configuration fails.
        """
        self.data.message_id = message.id
        self.data.channel_id = message.channel.id
        self.data.save(self.data_filepath, self.bot, self.__logger)

    async def refresh_message(self, handler: HandlerT) -> None:
        """|coro|

        Refreshes the static message by editing it.

        This method fetches the current static message and updates it
        using the prepared message data.

        Parameters
        ----------
        handler: :class:`.Handler`
            The handler instance used to prepare the message data.

        Raises
        ------
        ResourceFetchFailed
            If the static message cannot be fetched.
        HTTPException
            If the message fails to update on Discord.
        """
        try:
            message = await self._fetch_message()
            assert message is not None
        except ResourceFetchFailed as e:
            self.__logger.error("Failed to refresh message: %s", e)
            raise e

        message_data = await self.prepare_message_data(handler)

        try:
            await message.edit(**message_data)
        except HTTPException as e:
            self.__logger.error("Failed to refresh message: %s", e)
            raise e  # TODO: Consider raising a custom exception


class StaticViewMixin[HandlerT, ViewT: View, DataT: StaticMessageDataConfig](
    StaticMessageMixin[HandlerT, DataT], ABC
):
    """Base mixin class for managing a static view attached to a static message.

    This mixin extends the static message mixin by adding methods for creating, loading,
    unloading, and reloading interactive views (e.g., buttons) on the static message.

    Should be used by service classes that require an interactive view to be managed.

    Attributes
    ----------
    bot: UniversityBot
        The bot instance.
    data_filepath: :class:`Path` | `str`
        The file path to the configuration data.
    data: DataT
        The static message configuration data.
    view: :class:`ViewT` | `None`
        The currently active view, or None if no view is loaded.
    """

    bot: UniversityBot
    data_filepath: Path | str
    data: DataT
    view: ViewT | None
    __logger: Logger

    def __init__(
        self,
        bot: UniversityBot,
        data_filepath: Path | str,
        data_config: DataT,
        logger: Logger,
    ) -> None:
        super().__init__(bot, data_filepath, data_config, logger)
        self.view = None
        self.__logger = logger

    @abstractmethod
    def create_view(self, handler: HandlerT) -> ViewT:
        """Creates and registers a new view with the bot.

        This method is responsible for instantiating and registering
        a new interactive view for the static message.

        Parameters
        ----------
        handler: :class:`.Handler`
            The handler instance used to create the view.

        Returns
        -------
        :class:`ViewT`
            The created view.
        """

    async def load_view(self, handler: HandlerT) -> None:
        """|coro|

        Loads the view by updating the static message.

        This method fetches the static message and edits it
        using the prepared message data.

        Parameters
        ----------
        handler: :class:`.Handler`
            The handler instance used to prepare the message data.
        """
        try:
            message = await self._fetch_message()
            assert message is not None
        except ResourceFetchFailed as e:
            self.__logger.error("Failed to load view: %s", e)
            return

        message_data = await self.prepare_message_data(handler)

        try:
            await message.edit(**message_data)
        except HTTPException as e:
            self.__logger.error("Failed to edit view message: %s", e)
        else:
            self.__logger.info("View loaded.")

    def unload_view(self, *, missing_ok: bool = False) -> None:
        """Unloads the currently loaded view.

        This method removes the active view from the bot. If no view is loaded and
        ``missing_ok`` is False, it raises a ViewNotLoaded exception.

        Parameters
        ----------
        missing_ok: :class:`bool` | `None`
            If True, does not raise an exception if no view is loaded (default is False).

        Raises
        ------
        ViewNotLoaded
            If no view is loaded and ``missing_ok`` is False.
        """
        if self.view is None:
            if not missing_ok:
                raise ViewNotLoaded("View is not loaded.")
            return

        self.__logger.debug("Unloading view.")
        self.bot.remove_view(self.view)
        self.__logger.info("View unregistered from bot.")
        self.view = None
        self.__logger.info("View unloaded.")

    async def reload_view(self, handler: HandlerT) -> None:
        """|coro|

        Reloads the view attached to the static message.

        This method unloads the current view (if any) and then
        loads a new view by updating the message.

        Parameters
        ----------
        handler: :class:`.Handler`
            The handler instance used to prepare the new view.
        """
        self.unload_view(missing_ok=True)
        await self.load_view(handler)
