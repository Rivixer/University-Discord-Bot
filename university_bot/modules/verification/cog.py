# SPDX-License-Identifier: MIT
"""A module to define the cog for verification."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

import nextcord
from nextcord import Attachment, SlashOption
from nextcord.ext.commands import Cog

from university_bot import (
    Interaction,
    Localization,
    catch_interaction_exceptions,
    get_logger,
)
from university_bot.exceptions import ConfigurationError, LoadCogError
from university_bot.mixins.cog import SetupMixin

from .config import VerificationConfig
from .exceptions import DisabledFeatureError, VerificationError
from .handler import VerificationHandler
from .service import VerificationService

if TYPE_CHECKING:
    from university_bot import UniversityBot

__all__ = ("VerificationCog",)

_logger = get_logger(__name__)


class VerificationCog(SetupMixin, Cog):
    """A cog for verification."""

    bot: UniversityBot
    config: VerificationConfig
    service: VerificationService
    handler: VerificationHandler

    def __init__(self, bot: UniversityBot) -> None:
        self.bot = bot

        try:
            self.config = VerificationConfig(**bot.config["verification"])
        except KeyError as e:
            raise LoadCogError(self, "Verification configuration not found.") from e
        except ValueError as e:
            raise LoadCogError(self, "Invalid verification configuration.") from e

        try:
            self.service = VerificationService(bot, self.config)
        except ConfigurationError as e:
            raise LoadCogError(self, "Invalid verification configuration.") from e

        self.handler = VerificationHandler(self.service)
        self.bot.loop.create_task(
            self.service.purge_users_and_requests_by_retention_loop()
        )

        if not ((pp := self.service.config.privacy_policy) and pp.enabled):
            self.bot.remove_command(self._privacy_policy)

    @override
    async def setup(self, bot: UniversityBot) -> None:
        """Set up the verification cog."""
        _logger.debug("Setting up verification cog.")
        await self.service.setup_database()
        await self.service.load_view(self.handler)
        _logger.debug("Finished setting up verification cog.")

    @Localization.apply_localizations
    @nextcord.slash_command(name="verification")
    async def _verification(self, interaction: Interaction) -> None:
        """Placeholder for the verification command."""

    @Localization.apply_localizations
    @_verification.subcommand(
        name="send",
        description="Send the verification instructions message.",
    )
    @catch_interaction_exceptions([VerificationError])
    async def _send(
        self,
        interaction: Interaction,
        preview: bool = SlashOption(
            description="Whether to send a preview of the message.",
            default=False,
        ),
    ) -> None:
        await self.handler.send_message(interaction, preview)

    @Localization.apply_localizations
    @_verification.subcommand(
        name="verify_request",
        description="Verify a user.",
    )
    @catch_interaction_exceptions([VerificationError, ValueError])
    async def _verify_request(
        self,
        interaction: Interaction,
        member_id: str = SlashOption(
            description="The ID of the member to verify.",
            required=True,
        ),
    ) -> None:
        await self.handler.verify_request(interaction, member_id)

    @Localization.apply_localizations
    @nextcord.slash_command(
        name="whois",
        description="Show information about a user.",
    )
    @catch_interaction_exceptions([VerificationError])
    async def _whois(
        self,
        interaction: Interaction,
        user_query: str = SlashOption(
            name="user",
            description="A user's first name, last name, index number, "
            "name, nickname or ID.",
            required=True,
        ),
    ) -> None:
        await self.handler.handle_whois(interaction, user_query)

    @Localization.apply_localizations
    @nextcord.slash_command(
        name="privacy_policy",
        description="Get the privacy policy of the server.",
    )
    @catch_interaction_exceptions([DisabledFeatureError, VerificationError])
    async def _privacy_policy(self, interaction: Interaction) -> None:
        await self.handler.send_privacy_policy(interaction)

    @Localization.apply_localizations
    @nextcord.slash_command(
        name="about_me",
        description="Get information about yourself.",
    )
    @catch_interaction_exceptions([VerificationError])
    async def _about_me(self, interaction: Interaction) -> None:
        await self.handler.handle_about_me(interaction)

    @Cog.listener(name="on_member_remove")
    async def _on_member_remove(self, member: nextcord.Member) -> None:
        await self.handler.handle_member_remove(member)

    @Localization.apply_localizations
    @_verification.subcommand(
        name="get_configuration",
        description="Get the configuration of the verification instructions message.",
    )
    @catch_interaction_exceptions([VerificationError, ConfigurationError])
    async def _get_configuration(self, interaction: Interaction) -> None:
        await self.handler.get_configuration(interaction)

    @Localization.apply_localizations
    @_verification.subcommand(
        name="set_configuration",
        description="Set the configuration of the verification instructions message.",
    )
    @catch_interaction_exceptions([VerificationError, ConfigurationError])
    async def _set_configuration(
        self,
        interaction: Interaction,
        attachment: Attachment = SlashOption(
            description="JSON configuration file.",
        ),
    ) -> None:
        await self.handler.set_configuration(interaction, attachment)

    @Localization.apply_localizations
    @_verification.subcommand(
        name="edit_configuration",
        description="Edit the configuration of the verification instructions message.",
    )
    @catch_interaction_exceptions([VerificationError, ConfigurationError])
    async def _edit_configuration(
        self,
        interaction: Interaction,
        indent: int = SlashOption(
            description="JSON identation level (default {default}).",
            min_value=0,
            max_value=8,
            default=2,
        ),
    ) -> None:
        await self.handler.edit_configuration(interaction, indent)
