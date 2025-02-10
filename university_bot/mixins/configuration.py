# SPDX-License-Identifier: MIT
"""A module to define configuration mixin extensions for bot modules.

This module provides a set of base classes, exceptions, and modal interfaces to support
the editing and management of configuration files for bot modules. It offers functionality
for reading, validating, updating, and saving configuration data, while integrating with
Discord interactions via modals to enable user-friendly configuration editing.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from logging import Logger
from typing import TYPE_CHECKING, Any, Generic, TypeVar, override

from nextcord import File, HTTPException, InteractionResponded, TextInputStyle
from nextcord.ui import Modal, TextInput

from university_bot import catch_interaction_exceptions

if TYPE_CHECKING:
    from pathlib import Path

    from nextcord import Attachment

    from ..abc import DataConfigBaseModel
    from ..bot import UniversityBot
    from ..types import Interaction


class ConfigurationError(Exception):
    """Base exception for configuration errors."""


class InvalidConfiguration(ConfigurationError):
    """Raised when the configuration is invalid.

    Subclass of :exc:`ConfigurationError`.
    """


class ConfigurationFileNotFound(ConfigurationError):
    """Raised when the configuration file is missing.

    Subclass of :exc:`ConfigurationError`.
    """


class ConfigurationInvalidJSON(ConfigurationError):
    """Raised when the configuration file contains invalid JSON.

    Subclass of :exc:`ConfigurationError`.
    """


class SendConfigurationFailed(ConfigurationError):
    """Raised when sending the configuration file fails.

    Subclass of :exc:`ConfigurationError`.
    """


class ReadAttachmentFailed(ConfigurationError):
    """Raised when reading the attachment fails.

    Subclass of :exc:`ConfigurationError`.
    """


class ApplyConfigurationFailed(ConfigurationError):
    """Raised when applying the configuration updates fails.

    Subclass of :exc:`ConfigurationError`.
    """


class SaveConfigurationFailed(ConfigurationError):
    """Raised when saving the configuration updates fails.

    Subclass of :exc:`ConfigurationError`.
    """


class ModalInteractionFailed(ConfigurationError):
    """Raised when there is an issue with sending or processing a modal interaction.

    Subclass of :exc:`ConfigurationError`.
    """


class ContentTooLongError(ModalInteractionFailed):
    """Raised when the content is too long to be displayed in a TextInput.

    Subclass of :exc:`ModalInteractionFailed`.
    """


if TYPE_CHECKING:
    _ModalCallableT = Callable[
        ["EditConfigurationModal", Interaction, str], Coroutine[None, None, None]
    ]


class EditConfigurationModal(Modal):
    """Represents a modal for editing a configuration file.

    Attributes
    ----------
    callback_fn: :class:`Callable`
        The callback function to handle the interaction.
    """

    callback_fn: _ModalCallableT

    def __init__(
        self,
        content: str,
        callback_fn: _ModalCallableT,
        title: str = "Edit configuration",
        label: str = "File content",
    ) -> None:
        super().__init__(title=title)

        if len(content) > 4000:
            raise ContentTooLongError(
                "Configuration content is too long to be displayed in a TextInput."
            )

        self.callback_fn = callback_fn

        self.add_item(  # type: ignore
            TextInput(
                label=label,
                default_value=content,
                style=TextInputStyle.paragraph,
            )
        )

    @override
    async def callback(self, interaction: Interaction) -> None:
        text_input: TextInput = self.children[0]  # type: ignore
        content: str = text_input.value  # type: ignore
        await self.callback_fn(self, interaction, content)


class ConfigurationHandlerMixin(ABC):
    """Base class to define the handler for bot modules with configuration mixin support.

    This class provides methods for editing the configuration of a module,
    including sending, setting, and editing the configuration file.
    """

    __logger: Logger
    __service: ConfigurationServiceMixin[DataConfigBaseModel]

    def __init__(self, service: Any, logger: Logger) -> None:
        self.__service = service
        self.__logger = logger

    async def get_configuration(self, interaction: Interaction) -> None:
        """|coro|

        Sends the current configuration file.

        This method attempts to send the configuration file associated with the module.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.

        Raises
        ------
        ConfigurationFileNotFound
            If the configuration file is missing.
        SendConfigurationFailed
            If sending the configuration file fails.
        """
        try:
            file = File(self.__service.data_filepath)
        except FileNotFoundError as e:
            self.__logger.error("Failed to get configuration file. %s", e)
            raise ConfigurationFileNotFound("Failed to get configuration file.") from e

        try:
            await interaction.response.send_message(file=file, ephemeral=True)
        except HTTPException as e:
            self.__logger.error(
                "Failed to send configuration file. %s", e, exc_info=True
            )
            raise SendConfigurationFailed("Failed to send configuration file.") from e

    async def set_configuration(
        self,
        interaction: Interaction,
        attachment: Attachment,
    ) -> None:
        """|coro|

        Sets a new configuration from an attachment.

        This method reads the configuration content from the provided attachment,
        applies the configuration updates, and sends a success message if the update is successful.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        attachment: :class:`nextcord.Attachment`
            The attachment containing the new configuration.

        Raises
        ------
        ReadAttachmentFailed
            If reading the attachment fails.
        ApplyConfigurationFailed
            If applying the configuration updates fails.
        """
        try:
            content = await attachment.read()
            content = content.decode("utf-8")
        except HTTPException as e:
            self.__logger.error(
                "Failed to read attachment %s. %s",
                attachment.id,
                e,
                exc_info=True,
            )
            raise ReadAttachmentFailed("Failed to read attachment.") from e

        await self._apply_configuration_updates(content)
        await self._attempt_send_set_configuration_success_message(interaction)

    async def edit_configuration(self, interaction: Interaction, indent: int) -> None:
        """|coro|

        Initiates the interaction for editing configuration.

        This method retrieves the current configuration content, displays it in a modal for editing,
        and processes the modal submission to update the configuration.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        indent: :class:`int`
            The indentation level for the JSON content.

        Raises
        ------
        ConfigurationFileNotFound
            If the configuration file is missing.
        ConfigurationInvalidJSON
            If the configuration file contains invalid JSON.
        ContentTooLongError
            If the content is too long to be displayed in a TextInput.
        ModalInteractionFailed
            If there is an issue with sending or processing a modal interaction.
        ApplyConfigurationFailed
            If applying the configuration updates fails.
        """
        try:
            content = self.__service.get_config_content(indent)
        except FileNotFoundError as e:
            self.__logger.error("Failed to get config content. %s", e)
            raise ConfigurationFileNotFound("Failed to get config content.") from e
        except ValueError as e:
            self.__logger.error("Failed to get config content. %s", e)
            raise ConfigurationInvalidJSON("Failed to get config content.") from e

        @catch_interaction_exceptions([Exception])
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
            raise ModalInteractionFailed("Failed to send modal.") from e

    async def _attempt_send_set_configuration_success_message(
        self, interaction: Interaction
    ) -> None:
        """|coro|

        Attempts to send a success message after configuration update.

        This method sends a message indicating that the configuration was updated successfully.
        If sending the message fails, the error is logged.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction for which to send the success message.
        """
        send_message = (
            interaction.followup.send
            if interaction.response.is_done()
            else interaction.response.send_message
        )

        try:
            await send_message("Configuration updated successfully.", ephemeral=True)
        except HTTPException as e:
            self.__logger.error(
                "Failed to send success message for configuration update to %s. %s",
                interaction.user.id if interaction.user else "Unknown",
                e,
                exc_info=True,
            )

    async def _apply_configuration_updates(self, content: str) -> None:
        """|coro|

        Applies configuration updates from the provided content.

        This method validates the new configuration, updates the service data,
        and saves the configuration.

        Parameters
        ----------
        content: :class:`str`
            The new configuration content in JSON format.

        Raises
        ------
        ApplyConfigurationFailed
            If applying the configuration updates fails.
        """
        try:
            await self.__service.validate_data(content)
            self.__service.data = self.__service.get_data_from_string(content)
            self.__service.save_data()
        except (InvalidConfiguration, SaveConfigurationFailed) as e:
            self.__logger.error(
                "Failed to save configuration updates. %s",
                e,
                exc_info=True,
            )
            raise ApplyConfigurationFailed(
                "Failed to save configuration updates."
            ) from e


if TYPE_CHECKING:
    DataConfigT = TypeVar("DataConfigT", bound=DataConfigBaseModel)
else:
    DataConfigT = TypeVar("DataConfigT")


class ConfigurationServiceMixin(ABC, Generic[DataConfigT]):
    """Base class to define the service for bot modules with configuration mixin support.

    This class supplies the necessary methods for editing the configuration of a module.
    It provides functionality to read, validate, and save configuration data.
    """

    bot: UniversityBot
    data: DataConfigT
    data_filepath: Path | str
    __logger: Logger

    def __init__(
        self,
        bot: UniversityBot,
        data: DataConfigT,
        data_filepath: Path | str,
        logger: Logger,
    ) -> None:
        self.bot = bot
        self.data = data
        self.data_filepath = data_filepath
        self.__logger = logger

    @abstractmethod
    def get_data_from_string(self, content: str) -> DataConfigT:
        """Reads and returns the data from a JSON string.

        Parameters
        ----------
        content: :class:`str`
            The JSON content to set.

        Raises
        ------
        ValueError
            If the content is invalid or validation fails.
        """

    def save_data(self) -> None:
        """Saves the data to the file.

        Raises
        ------
        SaveConfigurationFailed
            If saving the configuration updates fails.
        """
        self.data.save(self.data_filepath, self.bot, self.__logger)

    async def validate_data(self, json_content: str) -> None:
        """|coro|

        Validates and saves the data from a JSON string.

        Parameters
        ----------
        json_content: :class:`str`
            The JSON content to validate and save.

        Raises
        ------
        InvalidConfiguration
            If the content is invalid.
        """
        try:
            self.get_data_from_string(json_content)
        except InvalidConfiguration as e:
            raise InvalidConfiguration("Invalid JSON content.") from e

    def get_config_content(self, indent: int = 4) -> str:
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
            If the configuration file is missing.
        ValueError
            If the configuration file contains invalid JSON.
        """
        try:
            data = self.data.load(self.data_filepath)
            return json.dumps(data.model_dump(), indent=indent)
        except FileNotFoundError as e:
            raise FileNotFoundError("Configuration file not found.") from e
        except json.JSONDecodeError as e:
            raise ValueError("Configuration file contains invalid JSON.") from e
