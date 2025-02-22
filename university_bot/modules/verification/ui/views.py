# SPDX-License-Identifier: MIT
"""A module to define views for the verification cog."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from nextcord import ButtonStyle, Locale
from nextcord.ui import Button, View, button

from university_bot import Interaction, Localization
from university_bot.mixins import LocalizedViewMixin
from university_bot.mixins.timeout import TimeoutViewMixin

from .buttons import (
    ExternalVerificationButton,
    InternalVerificationButton,
    PrivacyPolicyButton,
    TargetVerificationButton,
)

if TYPE_CHECKING:
    from .managers import CodeVerificationManager, VerificationManager
    from .payloads import DataSummaryPayload
    from ..handler import VerificationHandler

__all__ = (
    "VerificationView",
    "CodeSentView",
    "DataSummaryView",
)

_loc = Localization.get_group("ui.verification.views")


class VerificationView(View, ABC):
    """A view representing the calendar menu.

    This view provides buttons for adding events and viewing a summary.
    """

    handler: VerificationHandler

    def __init__(self, handler: VerificationHandler) -> None:
        super().__init__(timeout=None)
        self.handler = handler

        data = handler.service.data
        self.add_item(TargetVerificationButton(handler, data.target_button))  # type: ignore
        self.add_item(InternalVerificationButton(handler, data.internal_button))  # type: ignore
        self.add_item(ExternalVerificationButton(handler, data.external_button))  # type: ignore


class CodeSentView(TimeoutViewMixin, LocalizedViewMixin, View, ABC):
    """A base class for views that support code verification."""

    _manager: CodeVerificationManager

    def __init__(
        self,
        manager: CodeVerificationManager,
        locale: Locale | str | None,
    ) -> None:

        View.__init__(self, timeout=manager.config.view_timeout)
        TimeoutViewMixin.__init__(self, manager)
        LocalizedViewMixin.__init__(self, locale, _loc.get_group("code_sent"))
        self._manager = manager

        if privacy_policy_config := manager.config.privacy_policy:
            self.add_item(
                PrivacyPolicyButton(
                    self._manager.handler,
                    privacy_policy_config,
                ),  # type: ignore
            )

    @LocalizedViewMixin.localized_button("buttons.code_received")
    @button(label="I have the code!", style=ButtonStyle.green)
    async def _code_received(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_data_input_modal(interaction)

    @LocalizedViewMixin.localized_button("buttons.resend_code")
    @button(label="Resend code", style=ButtonStyle.blurple)
    async def _resend_code(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.resend_email(interaction)


class DataSummaryView(TimeoutViewMixin, LocalizedViewMixin, View):
    """A view for displaying a data summary."""

    _manager: VerificationManager

    def __init__(
        self,
        manager: VerificationManager,
        payload: DataSummaryPayload,
    ) -> None:
        View.__init__(self, timeout=manager.config.view_timeout)
        TimeoutViewMixin.__init__(self, manager)
        LocalizedViewMixin.__init__(
            self, payload.locale, _loc.get_group("data_summary")
        )
        self._manager = manager

        if privacy_policy_config := self._manager.config.privacy_policy:
            self.add_item(
                PrivacyPolicyButton(
                    self._manager.handler,
                    privacy_policy_config,
                ),  # type: ignore
            )

        confirm_btn: Button = self.children[0]  # type: ignore
        confirm_btn.disabled = not payload.is_valid()

    @LocalizedViewMixin.localized_button("buttons.confirm")
    @button(label="Confirm", disabled=True, style=ButtonStyle.green)
    async def _confirm(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.handle_confirm(interaction)

    @LocalizedViewMixin.localized_button("buttons.edit")
    @button(label="Edit", style=ButtonStyle.red)
    async def _edit(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_data_input_modal(interaction)
