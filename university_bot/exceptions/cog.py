# SPDX-License-Identifier: MIT
"""A module to define exceptions related to cogs."""

from nextcord.ext.commands import Cog

__all__ = ("CogError", "LoadCogError")


class CogError(Exception):
    """Base exception for cog errors."""


class LoadCogError(CogError):
    """An exception raised when loading a cog fails.

    Attributes
    ----------
    cog: :class:`nextcord.ext.commands.Cog`
        The cog that failed to load.
    """

    cog: Cog

    def __init__(self, cog: Cog, *args: object) -> None:
        self.cog = cog
        super().__init__(*args)
