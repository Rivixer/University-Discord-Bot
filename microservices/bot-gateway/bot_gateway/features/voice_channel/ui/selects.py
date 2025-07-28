"""
Voice Channel Select UI Components
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from nextcord import CategoryChannel, SelectOption
from nextcord.ui import Select

if TYPE_CHECKING:
    from bot_gateway.types import Interaction

    from .views import VoiceChannelConfigView


class CategorySelect(Select):
    """Select for choosing a voice channel category."""

    parent_view: VoiceChannelConfigView

    def __init__(
        self,
        view: VoiceChannelConfigView,
        categories: list[CategoryChannel],
        row: int = 0,
    ) -> None:
        self.parent_view = view

        options = [
            SelectOption(
                label="No category (disable feature)",
                value="0",
            ),
        ] + [
            SelectOption(
                label=category.name,
                value=str(category.id),
            )
            for category in categories
        ]

        super().__init__(
            placeholder="Select a category",
            min_values=1,
            max_values=1,
            row=row,
            options=options,
        )

    def set_default(self, category_id: int | None) -> None:
        """Sets the default selected category.

        Parameters
        ----------
        category_id : int | None
            The ID of the category to set as default.
            If None, "No category" is selected.
        """
        for option in self.options:
            option.default = (
                option.value == str(category_id) if category_id else option.value == "0"
            )

    @override
    async def callback(self, interaction: Interaction) -> None:
        if self.values[0] == "0":
            self.parent_view.category_id_temp = None
        else:
            self.parent_view.category_id_temp = int(self.values[0])

        await self.parent_view.edit_message(interaction)
