# SPDX-License-Identifier: MIT
"""A module that contains the voice channel manager handler."""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from nextcord import HTTPException, VoiceChannel

from .. import get_logger
from ..exceptions.voice_channel_manager import (
    RateLimitExceeded,
    UnmanagedCategory,
    VoiceChannelManagerException,
)

if TYPE_CHECKING:
    from nextcord import Member, VoiceState

    from .. import Interaction
    from ..services.voice_channel_manager import VoiceChannelManagerService

_logger = get_logger(__name__)


class VoiceChannelManagerHandler:
    """A class to handle the voice channel commands and events.

    Attributes
    ----------
    service: :class:`.VoiceChannelManagerService`
        The voice channel manager service.
    """

    __slots__ = ("service",)

    service: VoiceChannelManagerService
    _channel_lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, service: VoiceChannelManagerService) -> None:
        self.service = service

    async def on_ready(self) -> None:
        """|coro|

        Handles the bot's ready event.
        """
        async with self._channel_lock:
            _logger.info("Checking voice channels on ready.")
            await self.service.check_voice_channels()

    async def on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ) -> None:
        """|coro|

        Handles the voice state update event.

        Parameters
        ----------
        member: :class:`nextcord.Member`
            The member that triggered the event.
        before: :class:`nextcord.VoiceState`
            The voice state before the update.
        after: :class:`nextcord.VoiceState`
            The voice state after the update.
        """
        if before.channel == after.channel:
            return

        if self.service.config.logging.member_events:
            self.service.log_user_movement(member, before, after)

        tasks: list[Coroutine[Any, Any, None]] = []

        if isinstance(before.channel, VoiceChannel):
            tasks.append(self._handle_channel_leave(before.channel))

        if isinstance(after.channel, VoiceChannel):
            tasks.append(self._handle_channel_join(after.channel))

        await asyncio.gather(*tasks)

    async def set_limit(self, interaction: Interaction, value: int) -> None:
        """|coro|

        Sets the user limit for the voice channel.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        value: :class:`int`
            The user limit to set.

        Raises
        ------
        VoiceChannelManagerException
            If setting the user limit failed.
        """

        if not (channel := await self._get_user_channel(interaction)):
            return

        try:
            await self.service.set_limit(channel, value)
        except UnmanagedCategory:
            await self._attempt_send_message(
                interaction,
                "You cannot set the limit of this channel.",
            )
        except ValueError as e:
            raise VoiceChannelManagerException("Invalid user limit.") from e
        else:
            await self._attempt_send_message(
                interaction,
                f"{channel.mention} User limit has been set to `{value}`.",
            )

    async def reset_limit(self, interaction: Interaction) -> None:
        """|coro|

        Resets the user limit for the voice channel.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.

        Raises
        ------
        VoiceChannelManagerException
            If resetting the user limit failed.
        """

        if not (channel := await self._get_user_channel(interaction)):
            return

        try:
            await self.service.set_limit(channel, 0)
        except UnmanagedCategory:
            await self._attempt_send_message(
                interaction,
                "You cannot reset the limit of this channel.",
            )
        else:
            await self._attempt_send_message(
                interaction,
                f"{channel.mention} User limit has been reset.",
            )

    async def rename(self, interaction: Interaction, name: str) -> None:
        """|coro|

        Renames the voice channel.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        name: :class:`str`
            The new name of the voice channel.

        Raises
        ------
        VoiceChannelManagerException
            If renaming the voice channel failed.
        """

        if not (channel := await self._get_user_channel(interaction)):
            return

        try:
            await self.service.rename(channel, name)
        except UnmanagedCategory:
            await self._attempt_send_message(
                interaction,
                "You cannot rename this channel.",
            )
        except RateLimitExceeded:
            await self._attempt_send_message(
                interaction,
                "Failed to rename the channel. "
                "You can only rename a channel twice every 10 minutes.",
            )
        else:
            await self._attempt_send_message(
                interaction,
                f"{channel.mention} Voice channel has been renamed.",
            )

    async def _get_user_channel(self, interaction: Interaction) -> VoiceChannel | None:
        member: Member = interaction.user  # type: ignore
        if not member.voice:
            await self._attempt_send_message(
                interaction,
                "You must be in a voice channel to use this command.",
            )
            return None
        return member.voice.channel  # type: ignore

    async def _handle_channel_join(self, channel: VoiceChannel) -> None:
        if not self.service.is_channel_in_managed_category(channel):
            return

        async with self._channel_lock:
            if not any(self.service.empty_voice_channels):
                try:
                    await self.service.create_channel()
                except VoiceChannelManagerException:
                    pass

    async def _handle_channel_leave(self, channel: VoiceChannel) -> None:
        if not self.service.is_channel_in_managed_category(channel):
            return

        if not self.service.is_channel_empty(channel):
            return

        async with self._channel_lock:
            try:
                await self.service.delete_channel(channel)
            except VoiceChannelManagerException:
                pass

            if not any(self.service.empty_voice_channels):
                try:
                    await self.service.create_channel()
                except VoiceChannelManagerException:
                    pass

    async def _attempt_send_message(
        self,
        interaction: Interaction,
        content: str,
        delete_after: float | None = 5.0,
    ) -> None:
        send_message = (
            interaction.followup.send
            if interaction.response.is_done()
            else interaction.response.send_message
        )

        try:
            await send_message(content, ephemeral=True, delete_after=delete_after)
        except HTTPException as e:
            _logger.error(
                "Failed to send message to %s. %s",
                interaction.user.id if interaction.user else "Unknown",
                e,
                exc_info=True,
            )
