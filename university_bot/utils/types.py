# SPDX-License-Identifier: MIT
"""A module to define types used in the code."""

from typing import TYPE_CHECKING, Any

from nextcord import Interaction as NextcordInteraction

if TYPE_CHECKING:
    from nextcord.ext.commands import Bot

    Interaction = NextcordInteraction[Bot]
else:
    Interaction = NextcordInteraction

if TYPE_CHECKING:
    EmbedDict = dict[str, Any]
