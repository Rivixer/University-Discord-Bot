"""
UI Components Type Aliases

This module defines type aliases for UI components used in the bot gateway.
"""

from nextcord.ui import Button as NextcordButton
from nextcord.ui import View as NextcordView

__all__ = ("Button",)

Button = NextcordButton[NextcordView]
