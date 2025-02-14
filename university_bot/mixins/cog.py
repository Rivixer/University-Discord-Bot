# SPDX-License-Identifier: MIT
"""A module providing the cog mixins."""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from nextcord.ext.commands import CogMeta

if TYPE_CHECKING:
    from university_bot import UniversityBot


class SetupMixin(metaclass=CogMeta):  # pylint: disable=too-few-public-methods
    """A mixin for setting up cogs.

    This mixin provides an abstract method for setting up cogs.

    The setup method is called when the cog is loaded,
    immediately after creating the cog instance.
    """

    @abstractmethod
    async def setup(self, bot: UniversityBot) -> None:
        """Sets up the cog.

        This method is called when the cog is loaded,
        immediately after creating the cog instance.

        Parameters
        ----------
        bot: :class:`.UniversityBot`
            The bot instance.
        """
