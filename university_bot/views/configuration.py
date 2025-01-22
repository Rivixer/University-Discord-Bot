# SPDX-License-Identifier: MIT
from collections.abc import Callable, Coroutine
from typing import override

from nextcord import TextInputStyle
from nextcord.ui import Modal, TextInput

from .. import Interaction
from ..exceptions.configuration_view import ContentTooLongError

_Callback = Callable[
    ["EditConfigurationModal", Interaction, str], Coroutine[None, None, None]
]


class EditConfigurationModal(Modal):
    """Represents a modal for editing a configuration file."""

    callback_fn: _Callback

    def __init__(
        self,
        content: str,
        callback_fn: _Callback,
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
