# SPDX-License-Identifier: MIT
"""An example plugin cog.

This cog is an example of how to create a plugin cog.
It is ignored and cannot be loaded by the bot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import nextcord
from nextcord.ext import commands
from nextcord.interactions import Interaction

if TYPE_CHECKING:
    from university_bot import UniversityBot


class ExampleCog(commands.Cog):
    """An example plugin cog."""

    __slots__ = ("bot",)

    _bot: UniversityBot

    def __init__(self, bot: UniversityBot):
        self._bot = bot

    @nextcord.slash_command(name="example", description="Example command")
    async def _example(self, interaction: Interaction) -> None:
        await interaction.response.send_message("Hello, world!", ephemeral=True)


def setup(bot: UniversityBot):
    """Loads the ExampleCog cog."""
    bot.add_cog(ExampleCog(bot))
