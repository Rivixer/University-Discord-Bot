# SPDX-License-Identifier: MIT
"""A module that contains the voice channel utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, overload

if TYPE_CHECKING:
    from nextcord import CategoryChannel, Guild, VoiceChannel

__all__ = ("get_voice_channel_by_name",)


@overload
def get_voice_channel_by_name(source: Guild, name: str) -> VoiceChannel | None:
    """Returns the voice channel with the specified name in the guild.

    If more than one voice channel has the same name, the first one found is returned.

    Parameters
    ----------
    source: :class:`nextcord.Guild`
        The guild where the voice channel
    name: :class:`str`
        The name of the voice channel.

    Returns
    -------
    :class:`nextcord.VoiceChannel` | `None`
        The voice channel with the specified name.

    Raises
    ------
    ValueError
        If the name is empty or only spaces.
    """


@overload
def get_voice_channel_by_name(
    source: CategoryChannel, name: str
) -> VoiceChannel | None:
    """Returns the voice channel with the specified name in the category.

    If more than one voice channel has the same name, the first one found is returned.

    Parameters
    ----------
    source: :class:`nextcord.CategoryChannel`
        The category where the voice channel is located.
    name: :class:`str`
        The name of the voice channel.

    Returns
    -------
    :class:`nextcord.VoiceChannel` | `None`
        The voice channel with the specified name.

    Raises
    ------
    ValueError
        If the name is empty or only spaces.
    """


def get_voice_channel_by_name(
    source: Guild | CategoryChannel, name: str
) -> VoiceChannel | None:
    """Returns the voice channel with the specified name.

    Parameters
    ----------
    source: :class:`nextcord.Guild` | :class:`nextcord.CategoryChannel`
        The source where the voice channel is located.
    name: :class:`str`
        The name of the voice channel.

    Returns
    -------
    :class:`nextcord.VoiceChannel` | `None`
        The voice channel with the specified name.

    Raises
    ------
    ValueError
        If the name is empty or only spaces.
    """

    if not name.strip():
        raise ValueError(
            "The name of the voice channel cannot be empty or only spaces."
        )

    for vc in source.voice_channels:
        if vc.name == name:
            return vc
    return None
