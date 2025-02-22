# SPDX-License-Identifier: MIT
"""A module to define handler for calendar interactions."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, override

from nextcord import File, Forbidden, HTTPException, InvalidArgument, Locale, NotFound
from sqlalchemy.exc import SQLAlchemyError

from university_bot import InteractionUtils, Localization, get_logger
from university_bot.mixins.configuration import (
    ConfigurationHandlerMixin,
    SaveConfigurationFailedError,
)
from university_bot.utils import (
    MessageDeletionError,
    attempt_message_delete_after_save_failure,
)

from .exceptions import VerificationError, VerificationFailedError
from .ui.embeds import (
    AlreadyVerifiedEmbed,
    ErrorEmbed,
    MemberInformationEmbed,
    RequestAlreadySentEmbed,
)
from .ui.managers import (
    ExternalVerificationManager,
    InternalVerificationManager,
    TargetVerificationManager,
    VerificationManager,
)

if TYPE_CHECKING:
    from nextcord import Embed, Guild, Member, Message, PartialInteractionMessage

    from university_bot import Interaction

    from .service import VerificationService

__all__ = ("VerificationHandler",)

_logger = get_logger(__name__)


class VerificationHandler(ConfigurationHandlerMixin):
    """A class to handle calendar interactions.

    Attributes
    ----------
    service: :class:`.CalendarService`
        The calendar service.
    """

    service: VerificationService
    _verification_messages: dict[
        int, Message | PartialInteractionMessage | VerificationManager
    ]

    def __init__(self, service: VerificationService) -> None:
        self.service = service
        self._verification_messages = {}
        super().__init__(service, _logger)

    @override
    async def _apply_configuration_updates(self, content: str) -> None:
        await super()._apply_configuration_updates(content)
        await self.service.refresh_message(self)

    async def send_message(self, interaction: Interaction, preview: bool) -> None:
        """|coro|

        Handles sending a new verification message.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        preview: :class:`bool`
            Whether to send a preview of the message.

        Raises
        ------
        VerificationError
            - If the command is not used on a messageable channel.
            - If the message sending fails.
            - If the message data is invalid.
            - If saving the message data fails.
        """

        try:
            channel = InteractionUtils.ensure_messageable_channel(interaction)
        except TypeError as e:
            raise VerificationError(
                "Command must be used on a messageable channel."
            ) from e

        channel_id: int = getattr(channel, "id", -1)
        channel_name: str = getattr(channel, "name", "Unknown")
        channel_log = f'"{channel_name}" ({channel_id})'

        try:
            message_data = await self.service.prepare_message_data(
                self, missing=preview
            )
        except ValueError as e:
            _logger.error(
                "Failed to prepare message data for channel %s.",
                channel_log,
                exc_info=True,
            )
            raise VerificationError("Failed to prepare message data.") from e

        if preview:
            await interaction.response.send_message(**message_data, ephemeral=True)
            return

        try:
            message = await channel.send(**message_data)
        except (Forbidden, HTTPException, InvalidArgument) as e:
            _logger.error(
                "Failed to send message on channel %s: %s",
                channel_id,
                e,
                exc_info=True,
            )
            raise VerificationError("Failed to send message.") from e

        try:
            self.service.update_message_data(message)
        except SaveConfigurationFailedError as e:
            _logger.error(
                "Failed to save message data for message %s on channel %s. "
                "Trying to delete message.",
                message.id,
                channel_log,
                exc_info=True,
            )
            try:
                await attempt_message_delete_after_save_failure(message, e, _logger)
            except MessageDeletionError as del_err:
                raise VerificationError(
                    "Failed to save message data and delete message."
                ) from del_err
            raise VerificationError("Failed to save message data.") from e

        _logger.info(
            "Sent calendar message (%s) in channel %s.",
            message.id,
            channel_log,
        )

        try:
            await interaction.response.send_message(
                Localization.get_command_response(
                    interaction, "message_sent", "Calendar message sent."
                ),
                ephemeral=True,
                delete_after=30,
            )
        except HTTPException as e:
            pass

    async def handle_target_verification(self, interaction: Interaction) -> None:
        """|coro|

        Handles the target verification interaction.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the verification process.
        """
        user_id: int = interaction.user.id  # type: ignore

        try:
            if await self.service.is_user_verified(user_id):
                return await self._attempt_send_already_verified_embed(interaction)
            record = await self.service.get_record_with_user_id(user_id)
        except SQLAlchemyError as e:
            _logger.error(
                "Failed to check if user %s is verified or get their record.",
                user_id,
                exc_info=True,
            )
            return await self._attempt_send_error_embed(interaction, e)

        await self._try_cancel_active_verification_message(user_id)

        if record is None:
            manager = await TargetVerificationManager.create_and_send(self, interaction)
        else:
            manager = await TargetVerificationManager.create_and_send_predefined(
                self, interaction, record
            )

        self._verification_messages[user_id] = manager

    async def handle_internal_verification(self, interaction: Interaction) -> None:
        """|coro|

        Handles the internal verification interaction.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the verification process.
        """
        user_id: int = interaction.user.id  # type: ignore

        try:
            if await self.service.is_user_verified(user_id):
                return await self._attempt_send_already_verified_embed(interaction)
            record = await self.service.get_record_with_user_id(user_id)
        except SQLAlchemyError as e:
            _logger.error(
                "Failed to check if user %s is verified or get their record.",
                user_id,
                exc_info=True,
            )
            return await self._attempt_send_error_embed(interaction, e)

        await self._try_cancel_active_verification_message(user_id)

        if record is None:
            manager = await InternalVerificationManager.create_and_send(
                self, interaction
            )
        else:
            manager = await InternalVerificationManager.create_and_send_predefined(
                self, interaction, record
            )

        self._verification_messages[user_id] = manager

    async def handle_external_verification(self, interaction: Interaction) -> None:
        """|coro|

        Handles the external verification interaction.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the verification process.
        """
        user_id: int = interaction.user.id  # type: ignore

        try:
            if await self.service.is_user_verified(user_id):
                return await self._attempt_send_already_verified_embed(interaction)
            if await self.service.is_request_sent(user_id):
                return await self._attempt_send_request_already_sent_embed(interaction)
        except SQLAlchemyError as e:
            _logger.error(
                "Failed to check if user %s is verified.",
                user_id,
                exc_info=True,
            )
            return await self._attempt_send_error_embed(interaction, e)

        await self._try_cancel_active_verification_message(user_id)
        manager = await ExternalVerificationManager.create_and_send(self, interaction)
        self._verification_messages[user_id] = manager

    async def handle_whois(self, interaction: Interaction, user_query: str) -> None:
        """|coro|

        Handles the whois command.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        user_query: :class:`str`
            The query to search for the user.

        Raises
        ------
        VerificationError
            If deferring the response fails.
            If sending the response message fails.
        """
        try:
            await interaction.response.defer(ephemeral=True, with_message=True)
        except HTTPException as e:
            raise VerificationError("Failed to defer response.") from e

        matching_members = await self.service.get_matching_members(user_query)
        if not matching_members:
            try:
                await interaction.edit_original_message(
                    content=Localization.get_command_response(
                        interaction,
                        "not_found",
                        "No user found with query `{query}`.",
                        query=user_query,
                    ),
                )
                await asyncio.sleep(30)
                return await interaction.delete_original_message()
            except HTTPException as e:
                raise VerificationError(
                    "Failed to send whois (not found) message."
                ) from e

        limit = 10
        if len(matching_members) == 1:
            loc_key = "found_one"
            loc_default = "Found user with query `{query}`."
        elif len(matching_members) > limit:
            loc_key = "found_multiple_limited"
            loc_default = (
                "Found `{count}` users with query `{query}`.\nShowing first 10."
            )
            matching_members = matching_members[:limit]
        else:
            loc_key = "found_multiple"
            loc_default = "Found `{count}` users with query `{query}`."

        content = Localization.get_command_response(
            interaction,
            loc_key,
            loc_default,
            count=len(matching_members),
            query=user_query,
            limit=limit,
        )

        locale = self._get_locale_from_interaction(interaction)
        embeds: list[Embed] = [
            MemberInformationEmbed(locale, m) for m in matching_members
        ]

        try:
            await interaction.edit_original_message(content=content, embeds=embeds)
            await asyncio.sleep(180)
            await interaction.delete_original_message()
        except HTTPException as e:
            raise VerificationError("Failed to send whois (found) message.") from e

    async def send_privacy_policy(self, interaction: Interaction) -> None:
        """|coro|

        Sends the privacy policy file to the user as an ephemeral message
        and deletes it after 10 seconds.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.

        Raises
        ------
        DisabledFeatureError
            If the privacy policy is not enabled.
        VerificationError
            If the privacy policy file sending fails.
        """
        fp = self.service.get_privacy_policy_filepath(interaction.locale)
        try:
            await interaction.response.send_message(
                file=File(fp), ephemeral=True, delete_after=10
            )
        except (OSError, HTTPException) as e:
            raise VerificationError("Failed to send privacy policy file.") from e

    async def verify_request(self, interaction: Interaction, raw_user_id: str) -> None:
        """|coro|

        Handles verifying a request.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the verification process.
        raw_user_id: :class:`str`
            The ID of the user to verify.

        Raises
        ------
        ValueError
            If the user ID is not an integer.
        VerificationError
            - If deferring the response fails.
            - If the member is not found.
            - If the verification fails.
            - If the verification request message deletion fails,
                but the verification succeeds.
        """
        user_id = int(raw_user_id)

        try:
            await interaction.response.defer(ephemeral=True)
        except HTTPException as e:
            raise VerificationError("Failed to defer response.") from e

        try:
            guild: Guild = interaction.guild  # type: ignore
            member = await guild.fetch_member(user_id)
        except NotFound:
            raise VerificationError("Member not found.") from None

        try:
            await self.service.verify_request(user_id)
        except (VerificationFailedError, SQLAlchemyError) as e:
            raise VerificationError("Failed to verify user.") from e
        except HTTPException as e:
            raise VerificationError(
                "Failed to delete verification request message."
            ) from e

        content = Localization.get_command_response(
            interaction,
            "success",
            "Successfully verified member {member.mention}.",
            member=member,
        )

        try:
            await interaction.followup.send(content, ephemeral=True)
        except HTTPException as e:
            _logger.error("Failed to send verification success message: %s", e)

    async def handle_member_remove(self, member: Member) -> None:
        """|coro|

        Handles the member remove event.

        Parameters
        ----------
        member: :class:`nextcord.Member`
            The member that left the guild.
        """
        try:
            await self.service.mark_user_left(member.id)
        except SQLAlchemyError as e:
            _logger.error(
                "Failed to mark user %s as left: %s", member.id, e, exc_info=True
            )
        try:
            await self.service.purge_user_by_retention(member.id)
        except SQLAlchemyError as e:
            _logger.error("Failed to purge user %s: %s", member.id, e, exc_info=True)

    @staticmethod
    def _get_locale_from_interaction(interaction: Interaction) -> Locale:
        locale = interaction.locale if interaction.locale else interaction.guild_locale
        return Locale(locale) if locale else Localization.default_locale()

    async def _attempt_send_error_embed(
        self, interaction: Interaction, exception: Exception
    ) -> None:
        user_id = interaction.user.id  # type: ignore
        locale = self._get_locale_from_interaction(interaction)

        await self._try_cancel_active_verification_message(user_id)
        embed = ErrorEmbed(locale, exception)

        try:
            message = await interaction.response.send_message(
                embed=embed, ephemeral=True, delete_after=60
            )
        except HTTPException as e:
            _logger.error("Failed to send error embed: %s", e, exc_info=True)
        else:
            self._verification_messages[user_id] = message

    async def _attempt_send_already_verified_embed(
        self, interaction: Interaction
    ) -> None:
        user_id = interaction.user.id  # type: ignore
        locale = self._get_locale_from_interaction(interaction)

        await self._try_cancel_active_verification_message(user_id)
        embed = AlreadyVerifiedEmbed(locale)

        try:
            message = await interaction.response.send_message(
                embed=embed, ephemeral=True, delete_after=15
            )
        except HTTPException as e:
            _logger.error("Failed to send already verified embed: %s", e, exc_info=True)
        else:
            self._verification_messages[user_id] = message

    async def _attempt_send_request_already_sent_embed(
        self, interaction: Interaction
    ) -> None:
        user_id = interaction.user.id  # type: ignore
        locale = self._get_locale_from_interaction(interaction)

        await self._try_cancel_active_verification_message(user_id)
        embed = RequestAlreadySentEmbed(locale)

        try:
            message = await interaction.response.send_message(
                embed=embed, ephemeral=True, delete_after=15
            )
        except HTTPException as e:
            _logger.error(
                "Failed to send request already sent embed: %s",
                e,
                exc_info=True,
            )
        else:
            self._verification_messages[user_id] = message

    async def _try_cancel_active_verification_message(self, user_id: int) -> None:
        if not (message := self._verification_messages.get(user_id)):
            return

        if isinstance(message, VerificationManager):
            await message.cancel()
        else:
            try:
                await message.delete()
            except NotFound:
                pass
            except HTTPException:
                _logger.warning(
                    "Failed to delete the verification message (user: %s).",
                    user_id,
                    exc_info=True,
                )

        del self._verification_messages[user_id]
