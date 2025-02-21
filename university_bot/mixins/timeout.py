# SPDX-License-Identifier: MIT
"""A module to define mixins for managing timeouts in views."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nextcord.ui import View

# pylint: disable=too-few-public-methods

__all__ = ("TimeoutManagerMixin", "TimeoutViewMixin")


class TimeoutManagerMixin(ABC):
    """A mixin for managing timeouts in views."""

    @abstractmethod
    async def on_timeout(self, view: View | TimeoutViewMixin) -> None:
        """|coro|

        A method called when a view times out.

        Parameters
        ----------
        view: :class:`nextcord.ui.View` | :class:`TimeoutViewMixin`
            The view that timed out.
        """


class TimeoutViewMixin(ABC):
    """A mixin for views that can time out.

    When a view times out, the :meth:`on_timeout` method is called.
    By default, this method calls the `on_timeout` method of the manager.
    """

    __manager: TimeoutManagerMixin

    def __init__(self, manager: TimeoutManagerMixin) -> None:
        self.__manager = manager

    async def on_timeout(self) -> None:
        """|coro|

        A method called when the view times out.

        By default, this method calls the `on_timeout` method of the manager.
        """
        await self.__manager.on_timeout(self)
