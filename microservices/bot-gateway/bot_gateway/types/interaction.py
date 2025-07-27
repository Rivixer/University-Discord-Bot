"""
Interaction Type Alias

This module defines a type alias for the Interaction class used in the bot gateway.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nextcord import Interaction as NextcordInteraction
    from nextcord.ext.commands import Bot

    Interaction = NextcordInteraction[Bot]
else:
    from nextcord import Interaction  # noqa: F401

__all__ = ("Interaction",)
