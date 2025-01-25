# SPDX-License-Identifier: MIT
"""A module that contains the voice channel manager service."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Concatenate

from nextcord import HTTPException, NotFound

from .. import PhraseFilter, get_logger, get_voice_channel_by_name
from ..exceptions.voice_channel_manager import (
    InvalidConfiguration,
    MissingPermissions,
    RateLimitExceeded,
    UnmanagedCategory,
    VoiceChannelManagerException,
)

if TYPE_CHECKING:
    from nextcord import CategoryChannel, Guild, Member, VoiceChannel, VoiceState

    from .. import UniversityBot
    from ..models.configs.voice_channel_manager import VoiceChannelManagerConfig

_logger = get_logger(__name__)


class VoiceChannelManagerService:
    """A class to manage the voice channels in a category.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot instance.
    config: :class:`.VoiceChannelManagerConfig`
        The voice channel manager configuration.
    """

    __slots__ = (
        "bot",
        "config",
    )

    bot: UniversityBot
    config: VoiceChannelManagerConfig

    def __init__(self, bot: UniversityBot, config: VoiceChannelManagerConfig) -> None:
        self.bot = bot
        self.config = config

        try:
            self.config.set_category(self.guild)
            self.config.validate_category_permissions(self.category)
        except (ValueError, MissingPermissions) as e:
            raise InvalidConfiguration("Invalid category.") from e

    @property
    def guild(self) -> Guild:
        """:class:`nextcord.Guild`: The bot's guild."""
        return self.bot.guild

    @property
    def category(self) -> CategoryChannel:
        """:class:`nextcord.CategoryChannel`: The managed category."""
        return self.config.category

    @property
    def voice_channels(self) -> Generator[VoiceChannel, None, None]:
        """Generator[:class:`nextcord.VoiceChannel`, `None`, `None`]:
        The voice channels in the managed category.
        """
        yield from self.category.voice_channels

    @property
    def empty_voice_channels(self) -> Generator[VoiceChannel, None, None]:
        """Generator[:class:`nextcord.VoiceChannel`, None, None]:
        The empty voice channels.
        """
        yield from (i for i in self.voice_channels if not i.members)

    @property
    def _event_logger(self) -> Callable[Concatenate[str, ...], None]:
        return _logger.info if self.config.logging.channel_events else _logger.debug

    @property
    def _rate_limit_logger(self) -> Callable[Concatenate[str, ...], None]:
        return _logger.error if self.config.logging.rate_limit else _logger.debug

    def is_channel_empty(self, channel: VoiceChannel) -> bool:
        """Checks if a voice channel is empty.

        If the bot is configured to ignore bots, they are not counted.

        Parameters
        ----------
        channel: :class:`nextcord.VoiceChannel`
            The voice channel to check.

        Returns
        -------
        :class:`bool`
            Whether the channel is empty.
        """
        return not any(
            member
            for member in channel.members
            if not (self.config.ignore_bots and member.bot)
        )

    def is_channel_in_managed_category(self, channel: VoiceChannel) -> bool:
        """Checks if a voice channel is in the managed category.

        Parameters
        ----------
        channel: :class:`nextcord.VoiceChannel`
            The voice channel to check.

        Returns
        -------
        :class:`bool`
            Whether the channel is in the managed category.
        """
        return channel.category == self.category

    async def check_voice_channels(self) -> None:
        """|coro|

        Ensures only one empty channel exists in the managed category.

        If no empty channels exist, a new channel is created.
        If more than one empty channel exists, all but one are deleted.

        If an error occurs while deleting or creating a channel,
        it is silently ignored.
        """

        empty_channels = list(self.empty_voice_channels)

        if len(empty_channels) > 1:
            await asyncio.gather(
                *(self.delete_channel(channel) for channel in empty_channels[1:]),
                return_exceptions=True,
            )

        if not empty_channels:
            try:
                await self.create_channel()
            except VoiceChannelManagerException:
                pass

        _logger.info("Checked voice channels.")

    async def set_limit(self, channel: VoiceChannel, value: int) -> None:
        """|coro|

        Sets the user limit of a voice channel.

        Parameters
        ----------
        channel: :class:`nextcord.VoiceChannel`
            The channel to set the limit.
        value: :class:`int`
            The user limit to set.

        Raises
        ------
        ValueError
            If the limit is not between 0 and 99.
        WrongCategory
            If the channel is not in the managed category.
        VoiceChannelManagerException
            Setting the user limit failed.
        """

        if not 0 <= value <= 99:
            raise ValueError("The limit must be between 0 and 99.")

        if not self.is_channel_in_managed_category(channel):
            raise UnmanagedCategory("The channel is not in the managed category.")

        try:
            await channel.edit(user_limit=value)
        except HTTPException as e:
            _logger.error(
                'Failed to set user limit of "%s" (%s) to %d.',
                channel.name,
                channel.id,
                value,
            )
            raise VoiceChannelManagerException("Failed to set the user limit.") from e

        self._event_logger(
            'Set user limit of "%s" (%s) to %d.',
            channel.name,
            channel.id,
            value,
        )

    async def rename(self, channel: VoiceChannel, name: str) -> None:
        """|coro|

        Renames a voice channel.

        Parameters
        ----------
        channel: :class:`nextcord.VoiceChannel`
            The channel to rename.
        name: :class:`str`
            The new name of the channel.

        Raises
        ------
        WrongCategory
            If the channel is not in the managed category.
        RateLimitExceeded
            If the rate limit is exceeded.
        VoiceChannelManagerException
            Renaming the channel failed.
        """

        if not self.is_channel_in_managed_category(channel):
            raise UnmanagedCategory("The channel is not in the managed category.")

        original_name = channel.name

        http_logger = get_logger("nextcord.http")
        rate_limit_filter = PhraseFilter(
            r"rate limit exceeded",
            r"Hit retry 5/5 on ('PATCH',",
        )
        http_logger.addFilter(rate_limit_filter)
        _logger.debug("Added rate limit filter to the nextcord.http logger.")

        try:
            await channel.edit(name=name)
        except HTTPException as e:
            if e.status == 429:
                self._rate_limit_logger(
                    'Failed to rename "%s" (%s) to "%s" due to a rate limit.',
                    channel.name,
                    channel.id,
                    name,
                )
                raise RateLimitExceeded("Rate limit exceeded.") from e
            _logger.error(
                'Failed to rename "%s" (%s) to "%s".',
                original_name,
                channel.id,
                name,
            )
            raise VoiceChannelManagerException("Failed to set the user limit.") from e
        finally:
            http_logger.removeFilter(rate_limit_filter)
            _logger.debug("Removed rate limit filter from the nextcord.http logger.")

        self._event_logger(
            'Renamed "%s" to "%s" (%s).',
            original_name,
            channel.name,
            channel.id,
        )

    async def create_channel(self) -> VoiceChannel:
        """|coro|

        Creates a new voice channel in the managed category.

        Returns
        -------
        :class:`nextcord.VoiceChannel`
            The created voice channel.

        Raises
        ------
        VoiceChannelManagerException
            Creating a voice channel failed.
        """

        name = self._get_next_channel_name()

        try:
            channel = await self.guild.create_voice_channel(
                name, category=self.config.category
            )
        except HTTPException as e:
            _logger.error(
                'Failed to create a voice channel "%s" in the category %s.',
                name,
                self.category.id,
            )
            raise VoiceChannelManagerException(
                "Failed to create a voice channel."
            ) from e

        self._event_logger('Created "%s" (%s).', channel.name, channel.id)

        return channel

    async def delete_channel(self, channel: VoiceChannel) -> None:
        """Deletes a voice channel.

        Parameters
        ----------
        channel: :class:`nextcord.VoiceChannel`
            The channel to delete.

        Raises
        ------
        WrongCategory
            If the channel is not in the managed category.
        VoiceChannelManagerException
            Deleting the voice channel failed.
        """

        if channel.category != self.category:
            raise UnmanagedCategory("The channel is not in the managed category.")

        try:
            await channel.delete()
        except NotFound:
            pass
        except HTTPException as e:
            _logger.error("Failed to delete the voice channel `%s`.", channel.name)
            raise VoiceChannelManagerException(
                "Failed to delete a voice channel."
            ) from e

        self._event_logger('Deleted "%s" (%s).', channel.name, channel.id)

    @staticmethod
    def log_user_movement(
        member: Member,
        before: VoiceState,
        after: VoiceState,
    ) -> None:
        """Logs a user moving between voice channels.

        Parameters
        ----------
        member: :class:`nextcord.Member`
            The member who moved.
        before: :class:`nextcord.VoiceState`
            The voice state before the move.
        after: :class:`nextcord.VoiceState`
            The voice state after the move.
        """

        display_name = member.display_name
        if before.channel and after.channel:
            _logger.info(
                '"%s" (%s) moved from "%s" (%s) to "%s" (%s).',
                display_name,
                member.id,
                before.channel,
                before.channel.id,
                after.channel,
                after.channel.id,
            )
        elif before.channel:
            _logger.info(
                '"%s" (%s) left "%s" (%s).',
                display_name,
                member.id,
                before.channel,
                before.channel.id,
            )
        elif after.channel:
            _logger.info(
                '"%s" (%s) joined "%s" (%s).',
                display_name,
                member.id,
                after.channel,
                after.channel.id,
            )

    def _get_next_channel_name(self) -> str:
        match self.config.channel_order_strategy:
            case "random":
                return self._get_random_channel_name()
            case "first available":
                return self._get_first_available_channel_name()

    def _get_random_channel_name(self) -> str:
        available_names = self.config.available_channel_names
        names = random.sample(available_names, len(available_names))
        for name in names:
            if not get_voice_channel_by_name(self.category, name):
                return name
        return self._get_overflow_name()

    def _get_first_available_channel_name(self) -> str:
        for name in self.config.available_channel_names:
            if not get_voice_channel_by_name(self.category, name):
                return name
        return self._get_overflow_name()

    def _get_overflow_name(self) -> str:
        number = 1
        while True:
            name = self.config.overflow_channel_name.replace("{number}", str(number))
            if not get_voice_channel_by_name(self.category, name):
                return name
            number += 1
