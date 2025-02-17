# SPDX-License-Identifier: MIT
"""A module to define basic embeds for the UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nextcord import Color, Embed

from university_bot import Localization
from university_bot.mixins import LocalizedMixin

if TYPE_CHECKING:
    from nextcord import Locale

__all__ = ("TimeoutMenuEmbed",)


class TimeoutMenuEmbed(LocalizedMixin, Embed):
    """An embed for displaying a timeout message."""

    def __init__(self, locale: Locale) -> None:
        LocalizedMixin.__init__(
            self,
            locale,
            Localization.get_group("ui.timeout.embeds"),
        )

        Embed.__init__(
            self,
            title=self.get_loc("title", "Timeout"),
            description=self.get_loc("description", "The operation has timed out."),
            color=Color.red(),
        )
