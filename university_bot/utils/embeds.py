# SPDX-License-Identifier: MIT
"""A module providing embed utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, overload

from nextcord import Embed

if TYPE_CHECKING:
    from nextcord.types.embed import Embed as EmbedData

    from university_bot import EmbedDict

__all__ = ("format_embed_values",)


@overload
def format_embed_values(embed: Embed, safely: bool = True, **kwargs: Any) -> Embed:
    """Formats the values of the embed with the given keyword arguments.

    Parameters
    ----------
    embed: :class:`nextcord.Embed`
        The embed to format.
    safely: :class:`bool`
        Whether to ignore missing keys in the format string. Defaults to `True`.
    **kwargs
        The keyword arguments to format the embed values with.

    Returns
    -------
    :class:`nextcord.Embed`
        The formatted embed.

    Raises
    ------
    KeyError
        If `safely` is `False` and a key is missing in the format string.
    """


@overload
def format_embed_values(
    embed: EmbedDict | EmbedData, safely: bool = True, **kwargs: Any
) -> EmbedDict | EmbedData:
    """Formats the values of the embed with the given keyword arguments.

    Parameters
    ----------
    embed: dict[:class:`str`, :class:`Any`] | :class:`nextcord.types.embed.Embed`
        The embed dictionary to format.
    safely: :class:`bool`
        Whether to ignore missing keys in the format string. Defaults to `True`.
    **kwargs
        The keyword arguments to format the embed values with.

    Returns
    -------
    dict[:class:`str`, :class:`Any`]
        The formatted embed dictionary.

    Raises
    ------
    KeyError
        If `safely` is `False` and a key is missing in the format string.
    """


def format_embed_values(
    embed: Embed | EmbedDict | EmbedData, safely: bool = True, **kwargs: Any
) -> Embed | EmbedDict | EmbedData:
    """Formats the values of the embed with the given keyword arguments."""

    class _DefaultDict(dict[str, Any]):

        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    def _format(value: str, **kwargs: Any) -> str:
        try:
            return value.format_map(_DefaultDict(kwargs) if safely else kwargs)
        except KeyError as e:
            if not safely:
                raise e
            return value

    def _recursive_format(obj: ...) -> Any:
        if isinstance(obj, str):
            return _format(obj, **kwargs)
        if isinstance(obj, list):
            return [_recursive_format(item) for item in obj]  # type: ignore
        if isinstance(obj, dict):
            return {k: _recursive_format(v) for k, v in obj.items()}  # type: ignore
        return obj

    embed_dict = embed.to_dict() if isinstance(embed, Embed) else embed

    formatted_embed = _recursive_format(embed_dict)
    return (
        Embed.from_dict(formatted_embed)
        if isinstance(embed, Embed)
        else formatted_embed
    )
