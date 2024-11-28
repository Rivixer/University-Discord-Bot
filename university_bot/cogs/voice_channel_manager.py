# SPDX-License-Identifier: MIT
"""A module for managing voice channels.

This module provides functionality to manage voice channels on a server.
The server has a category dedicated to voice channels, where only one
channel can be empty at a time. If a member joins an empty channel,
a new channel is created. If a member leaves a channel and makes
it empty, the channel is automatically deleted.

This module also provides commands to change
the name and limit of the voice channel.
"""

from __future__ import annotations

import asyncio
import functools
import random
from typing import TYPE_CHECKING, Any, Callable, Generator

from discord import (
    CategoryChannel,
    DiscordException,
    Interaction,
    SlashOption,
    VoiceChannel,
    slash_command,
)
from nextcord.ext import commands
from pydantic import BaseModel, Field, ValidationError, model_validator

from university_bot import (
    ExceptionData,
    InteractionUtils,
    MemberUtils,
    NoVoiceConnection,
    SlashCommandUtils,
    get_logger,
)

if TYPE_CHECKING:
    from discord import Guild, Member, VoiceState

    from university_bot import UniversityBot

_logger = get_logger(__name__)


class Config(BaseModel):
    """The voice channel manager config."""

    is_enabled: bool
    managed_category_id: int
    channel_order_strategy: str = Field(..., pattern=r"(?i)^(random|first available)$")
    ensure_unique_names: bool
    overflow_channel_name: str
    available_channel_names: list[str]
    commands: CommandsConfig
    listeners: ListenersConfig
    _category: CategoryChannel | None = None

    @property
    def category(self) -> CategoryChannel:
        """The managed category channel."""
        assert self._category is not None, "Category is not set."
        return self._category

    def set_and_validate_category(self, guild: Guild):
        """Sets and validates the `category` field."""
        category = self._validate_category_id(guild)
        self._validate_category_permissions(guild, category)
        self._category = category
        return self

    def _validate_category_id(self, guild: Guild) -> CategoryChannel:
        """Validates and retrieves the category channel."""
        category = guild.get_channel(self.managed_category_id)
        if not category or not isinstance(category, CategoryChannel):
            raise ValueError(
                f"Invalid `category_id`: {self.managed_category_id}. It must reference a category."
            )
        return category

    def _validate_category_permissions(self, guild: Guild, category: CategoryChannel):
        """Validates permissions for the bot in the category."""
        if not category.permissions_for(guild.me).manage_channels:
            raise ValueError(
                "The bot lacks `manage_channels` permissions in the specified category."
            )

    @model_validator(mode="before")
    @classmethod
    def _normalize_channel_order_strategy(
        cls, values: dict[str, Any]
    ) -> dict[str, Any]:
        if (order := values.get("channel_order_strategy")) and isinstance(order, str):
            values["channel_order_strategy"] = order.lower()
        return values

    @model_validator(mode="after")
    def _validate_overflow_channel_name(self):
        if self.ensure_unique_names and "{number}" not in self.overflow_channel_name:
            raise ValueError(
                "`overflow_channel_name` must contain '{number}' "
                "if `ensure_unique_names` is True."
            )
        return self


class CommandsConfig(BaseModel):
    """The voice channel manager commands config."""

    limit: bool
    name: bool


class ListenersConfig(BaseModel):
    """The voice channel manager listeners config."""

    log_channel_events: bool
    log_member_events: bool


class VoiceChannelManager(commands.Cog):
    """A cog to manage voice channels."""

    __slots__ = (
        "bot",
        "config",
    )

    bot: UniversityBot
    config: Config

    def __init__(self, bot: UniversityBot) -> None:
        """Initializes the voice channel manager cog.

        Parameters
        ----------
        bot: :class:`UniversityBot`
            The bot client instance.
        """

        self.bot = bot

        try:
            self.config = Config(**self.bot.config["voice_channel_manager"])
            self.config.set_and_validate_category(bot.guild)
        except (ValidationError, ValueError):
            _logger.error("Voice channel manager config is invalid!")
            raise

        self.bot.loop.create_task(self.check_voice_channels())

    @property
    def voice_channels(self) -> Generator[VoiceChannel, None, None]:
        """A generator of voice channels in the managed category."""
        return VoiceChannelUtils.filter_channels_by_category(
            self.bot.guild.voice_channels, self.config.category
        )

    def get_empty_channels(self) -> Generator[VoiceChannel, None, None]:
        """Returns a generator of empty voice channels in the managed category.

        Returns
        -------
        :class:`Generator`[:class:`VoiceChannel`, `None`, `None`]
            A generator of empty voice channels in the managed category.
        """
        return (i for i in self.voice_channels if not i.members)

    def get_voice_channel_with_name(self, name: str) -> VoiceChannel | None:
        """Returns a voice channel with the specified name.

        Parameters
        ----------
        name: :class:`str`
            The name of the voice channel.

        Returns
        -------
        :class:`VoiceChannel` | `None`
            The voice channel with the specified name,
            or `None` if not found.
        """
        return next((ch for ch in self.voice_channels if ch.name == name), None)

    def get_next_voice_channel_name(self) -> str:
        """Returns the next available voice channel name.

        Returns
        -------
        :class:`str`
            The next available voice channel name.
        """

        names = self.config.available_channel_names

        if self.config.channel_order_strategy == "random":
            random.shuffle(names)

        for name in names:
            if not self.get_voice_channel_with_name(name):
                return name

        def get_overflow_name(number: int | None) -> str:
            if number is None:
                return self.config.overflow_channel_name
            return self.config.overflow_channel_name.replace("{number}", str(number))

        if self.config.ensure_unique_names:
            if self.config.channel_order_strategy == "random":
                number = random.randint(1, 100)
            elif self.config.channel_order_strategy == "first available":
                number = 1
            else:
                raise ValueError("Invalid order")

            while self.get_voice_channel_with_name(get_overflow_name(number)):
                number += 1
        else:
            number = None

        return get_overflow_name(number)

    async def check_voice_channels(self) -> None:
        """Ensures only one empty voice channel exists
        in the managed category.
        """

        empty_channels = list(self.get_empty_channels())

        for channel in empty_channels[1:]:
            await VoiceChannelUtils.delete(channel)

        if not empty_channels:
            _logger.info("No empty channels found.")
            category = self.config.category
            name = self.get_next_voice_channel_name()
            channel = await VoiceChannelUtils.create(category, name)
            EventLogger.log_channel_creation(channel)


class Listeners(commands.Cog):
    """Handles voice state updates."""

    manager: VoiceChannelManager

    def __init__(self, manager: VoiceChannelManager) -> None:
        self.manager = manager

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Ensures only one empty voice channel exists
        in the managed category when the connection is established.
        """
        await self.manager.check_voice_channels()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ):
        """Handles when a user joins or leaves a voice channel."""
        if member.bot or before.channel == after.channel:
            return

        EventLogger.log_user_movement(member, before, after)

        if after.channel and isinstance(after.channel, VoiceChannel):
            await self.handle_channel_join(after.channel)

        if before.channel and isinstance(before.channel, VoiceChannel):
            await self.handle_channel_leave(before.channel)

    async def handle_channel_leave(self, channel: VoiceChannel) -> None:
        """Handles logic for when a member leaves a channel.

        If the channel is empty and in the managed category, it is deleted.

        Parameters
        ----------
        channel: :class:`VoiceChannel`
            The voice channel that the member left.
        """

        if (
            len(channel.members) == 0
            and channel.category == self.manager.config.category
        ):
            empty_channels = self.manager.get_empty_channels()
            if any(empty_channels):
                await VoiceChannelUtils.delete(channel)

                if self.manager.config.listeners.log_channel_events:
                    EventLogger.log_channel_deletion(channel)

    async def handle_channel_join(self, channel: VoiceChannel) -> None:
        """Handles logic for when a member joins a channel.

        If the channel was empty and in the managed category,
        a new channel is created.

        Parameters
        ----------
        channel: :class:`VoiceChannel`
            The voice channel that the member joined.
        """

        if (
            len(channel.members) == 1
            and channel.category == self.manager.config.category
        ):
            created_channel = await VoiceChannelUtils.create(
                self.manager.config.category,
                self.manager.get_next_voice_channel_name(),
            )

            if self.manager.config.listeners.log_channel_events:
                EventLogger.log_channel_creation(created_channel)


class Commands(commands.Cog):
    """Represents voice channel commands."""

    manager: VoiceChannelManager

    def __init__(self, manager: VoiceChannelManager) -> None:
        self.manager = manager
        config = self.manager.config
        SlashCommandUtils.unregister_disabled_commands(self, config.commands)

    @staticmethod
    def _raise_if_not_in_voice(func: Callable[..., Any]) -> Callable[..., Any]:

        @functools.wraps(func)
        async def wrapper(
            self: Commands,
            interaction: Interaction[commands.Bot],
            *args: Any,
            **kwargs: Any,
        ) -> Callable[..., Any]:
            member: Member = interaction.user  # type: ignore
            if not (
                member.voice
                and isinstance(member.voice.channel, VoiceChannel)
                and member.voice.channel.category == self.manager.config.category
            ):
                raise NoVoiceConnection("You are not connected to a voice channel.")
            return await func(self, interaction, *args, **kwargs)

        return wrapper

    @slash_command(
        name="limit",
        description="Set the limit of the voice channel you are in.",
        dm_permission=False,
    )
    @InteractionUtils.with_info(
        before="**Setting the limit to `{limit}`...**",
        after="**The limit has been set to `{limit}`.**",
        catch_exceptions=[
            ExceptionData(
                DiscordException,
                with_traceback_in_response=False,
            ),
            ExceptionData(
                NoVoiceConnection,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ],
    )
    @InteractionUtils.with_log()
    @_raise_if_not_in_voice
    async def _limit(
        self,
        interaction: Interaction[commands.Bot],
        limit: int = SlashOption(
            name="new_voice_channel_user_limit",
            min_value=0,
            max_value=99,
        ),
    ) -> None:
        """Sets the limit of the voice channel the member is in.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        limit: :class:`int`
            The limit to be set.
        """
        channel: VoiceChannel = interaction.user.voice.channel  # type: ignore
        await channel.edit(user_limit=limit)

    @slash_command(
        name="name",
        description="Set the name of the voice channel you are in.",
        dm_permission=False,
    )
    @InteractionUtils.with_info(
        before="**Setting the voice channel name to `{name}`...**",
        after="**The voice channel name has been set to `{name}`.**",
        catch_exceptions=[
            ExceptionData(
                DiscordException,
                with_traceback_in_response=False,
            ),
            ExceptionData(
                TimeoutError,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
            ExceptionData(
                NoVoiceConnection,
                with_traceback_in_response=False,
                with_traceback_in_log=False,
            ),
        ],
    )
    @InteractionUtils.with_log()
    @_raise_if_not_in_voice
    async def _name(
        self,
        interaction: Interaction[commands.Bot],
        name: str = SlashOption(
            name="new_voice_channel_name",
            description="The name to be set.",
            required=True,
        ),
    ) -> None:
        """Sets the name of the voice channel the member is in.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        name: :class:`str`
            The name to be set.
        """
        channel: VoiceChannel = interaction.user.voice.channel  # type: ignore

        try:
            await VoiceChannelUtils.change_name(channel, name, timeout=2.5)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                "The name of the channel can be changed max 2 times "
                "per 10 minutes (Discord rate limit)."
            ) from exc


class EventLogger:
    """Utility class for logging events."""

    @staticmethod
    def log_user_movement(
        member: Member, before: VoiceState, after: VoiceState
    ) -> None:
        """Logs when a member joins or leaves a voice channel.

        Parameters
        ----------
        member: :class:`Member`
            The member who joined or left the voice channel.
        before: :class:`VoiceState`
            The voice state before the update.
        after: :class:`VoiceState`
            The voice state after the update.
        """

        display_name = MemberUtils.display_name(member)
        if before.channel and after.channel:
            _logger.info(
                "Member `%s` moved from `%s` to `%s`.",
                display_name,
                before.channel.name,
                after.channel.name,
            )
        elif before.channel:
            _logger.info("Member `%s` left `%s`.", display_name, before.channel.name)
        elif after.channel:
            _logger.info("Member `%s` joined `%s`.", display_name, after.channel.name)

    @staticmethod
    def log_channel_creation(channel: VoiceChannel) -> None:
        """Logs when a voice channel is created.

        Parameters
        ----------
        channel: :class:`VoiceChannel`
            The voice channel that was created.
        """

        _logger.info("Created voice channel `%s`.", channel.name)

    @staticmethod
    def log_channel_deletion(channel: VoiceChannel) -> None:
        """Logs when a voice channel is deleted.

        Parameters
        ----------
        channel: :class:`VoiceChannel`
            The voice channel that was deleted.
        """

        _logger.info("Deleted voice channel `%s`.", channel.name)


class VoiceChannelUtils:
    """Utility methods for managing voice channels."""

    @staticmethod
    def filter_channels_by_category(
        channels: list[VoiceChannel], category: CategoryChannel
    ) -> Generator[VoiceChannel, None, None]:
        """Filters voice channels by category.

        Parameters
        ----------
        channels: :class:`list`[:class:`VoiceChannel`]
            The list of voice channels to filter.
        category: :class:`CategoryChannel`
            The category channel to filter by.

        Returns
        -------
        :class:`Generator`[:class:`VoiceChannel`, `None`, `None`]
            A generator of voice channels filtered by category.
        """
        return (c for c in channels if c.category == category)

    @staticmethod
    def find_channel_by_name(
        channels: list[VoiceChannel], name: str
    ) -> VoiceChannel | None:
        """Finds a voice channel by name.

        Parameters
        ----------
        channels: :class:`list`[:class:`VoiceChannel`]
            The list of voice channels to search.
        name: :class:`str`
            The name of the voice channel to find.

        Returns
        -------
        :class:`VoiceChannel` | `None`
            The voice channel with the specified name,
            or `None` if not found.
        """
        return next((ch for ch in channels if ch.name == name), None)

    @staticmethod
    async def create(
        category: CategoryChannel,
        name: str,
        timeout: float = 5,
        **options: Any,
    ) -> VoiceChannel:
        """|coro|

        Creates a new voice channel with a timeout.

        Parameters
        ----------
        category: :class:`CategoryChannel`
            The category channel where the voice channel will be created.
        name: :class:`str`
            The name of the voice channel.
        timeout: :class:`int`
            The timeout for creating the voice channel.
        options: :class:`dict`
            Additional options for creating the voice channel.

        Returns
        -------
        :class:`VoiceChannel`
            The created voice channel.
        """
        try:
            return await asyncio.wait_for(
                category.create_voice_channel(name=name, **options),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            _logger.error("Failed to create a new voice channel due to timeout.")
            raise

    @staticmethod
    async def delete(channel: VoiceChannel, timeout: float = 5) -> None:
        """|coro|

        Deletes a voice channel with a timeout.

        Parameters
        ----------
        channel: :class:`VoiceChannel`
            The voice channel to be deleted.
        timeout: :class:`float`
            The timeout for deleting the voice channel.
        """

        try:
            await asyncio.wait_for(channel.delete(), timeout=timeout)
        except asyncio.TimeoutError:
            _logger.error("Failed to delete channel %s due to timeout.", channel.name)
            raise

    @staticmethod
    async def change_name(channel: VoiceChannel, name: str, timeout: float = 5) -> None:
        """|coro|

        Changes the name of a voice channel with a timeout.

        Parameters
        ----------
        channel: :class:`VoiceChannel`
            The voice channel to be changed.
        name: :class:`str`
            The new name of the voice channel.
        timeout: :class:`float`
            The timeout for changing the voice channel name.
        """
        try:
            await asyncio.wait_for(
                channel.edit(name=name),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            _logger.error("Failed to change the voice channel name due to timeout.")
            raise


def setup(bot: UniversityBot) -> None:
    """Loads the voice channel manager cog.

    Parameters
    ----------
    bot: :class:`UniversityBot`
        The bot client instance.
    """
    manager_cog = VoiceChannelManager(bot)
    bot.add_cog(manager_cog)

    listeners_cog = Listeners(manager_cog)
    bot.add_cog(listeners_cog)

    commands_cog = Commands(manager_cog)
    bot.add_cog(commands_cog)
