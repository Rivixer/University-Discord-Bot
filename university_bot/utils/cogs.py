# SPDX-License-Identifier: MIT
"""A module containing utilities for cogs."""

from collections.abc import Callable

from nextcord.ext.commands import Cog

__all__ = ("load_after", "entry_cog")


LOAD_AFTER_ATTR = "__cog_dependencies__"


def load_after[T: Cog](*cogs: type[Cog] | str) -> Callable[[type[T]], type[T]]:
    """A decorator to specify cog dependencies.

    This decorator marks a cog to be loaded after the specified cogs. The dependency
    information is used to determine the correct load order, ensuring that all
    required dependencies are loaded before the decorated cog.

    Parameters
    ----------
    *cogs: type[:class:`nextcord.ext.commands.Cog`] | :class:`str`
        One or more cog classes or their names
        that must be loaded before the decorated cog.

    Returns
    -------
    Callable[[type[`T`]], type[`T`]]
        A decorator that sets the '__cog_dependencies__' attribute on the cog class.
    """

    def decorator(cls: type[T]) -> type[T]:
        setattr(cls, LOAD_AFTER_ATTR, cogs)
        return cls

    return decorator


ENTRY_COG_ATTR = "__entry_cog__"


def entry_cog[T: Cog](cls: type[T]) -> type[T]:
    """A decorator to mark a cog as the entry point for loading.

    When multiple cog classes are found in a module, the one decorated with this
    decorator will be selected for loading. If no cog is marked as the entry point,
    the first discovered cog is used by default.

    Parameters
    ----------
    cls: type[:class:`nextcord.ext.commands.Cog`]
        The cog class to mark as the entry point for loading.

    Returns
    -------
    type[:class:`nextcord.ext.commands.Cog`]
        The original cog class with the '__entry_cog__' attribute set.
    """
    setattr(cls, ENTRY_COG_ATTR, True)
    return cls
