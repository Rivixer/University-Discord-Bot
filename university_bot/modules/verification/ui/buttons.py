# SPDX-License-Identifier: MIT
"""A module to define buttons for the verification system."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, override

from nextcord import ButtonStyle
from nextcord.ui import Button, View

from university_bot import catch_interaction_exceptions

from ..exceptions import DisabledFeatureError, VerificationError

if TYPE_CHECKING:
    from university_bot import Interaction

    from ..config import PrivacyPolicyConfig, VerificationButtonConfig
    from ..handler import VerificationHandler

__all__ = (
    "VerificationButton",
    "TargetVerificationButton",
    "InternalVerificationButton",
    "ExternalVerificationButton",
    "PrivacyPolicyButton",
)


class VerificationButton(Button[View], ABC):
    """A base class to represent a verification button."""

    handler: VerificationHandler
    config: VerificationButtonConfig

    def __init__(
        self,
        handler: VerificationHandler,
        config: VerificationButtonConfig,
    ) -> None:
        self.handler = handler
        self.config = config

        super().__init__(style=config.style, label=config.label)


class TargetVerificationButton(VerificationButton):
    """A class to represent a target verification button."""

    @override
    async def callback(self, interaction: Interaction) -> None:
        await self.handler.handle_target_verification(interaction)


class InternalVerificationButton(VerificationButton):
    """A class to represent an internal verification button."""

    @override
    async def callback(self, interaction: Interaction) -> None:
        await self.handler.handle_internal_verification(interaction)


class ExternalVerificationButton(VerificationButton):
    """A class to represent an external verification button."""

    @override
    async def callback(self, interaction: Interaction) -> None:
        await self.handler.handle_external_verification(interaction)


class PrivacyPolicyButton(Button[View]):
    """A class to represent a privacy policy button.

    Used for sending the privacy policy file to the user.
    """

    handler: VerificationHandler
    config: PrivacyPolicyConfig

    def __init__(
        self,
        handler: VerificationHandler,
        config: PrivacyPolicyConfig,
    ) -> None:
        super().__init__(style=ButtonStyle.gray, label=config.button_label)
        self.handler = handler
        self.config = config

    @override
    @catch_interaction_exceptions(
        [DisabledFeatureError, VerificationError],
        delete_after=30,
    )
    async def callback(self, interaction: Interaction) -> None:
        await self.handler.send_privacy_policy(interaction)
