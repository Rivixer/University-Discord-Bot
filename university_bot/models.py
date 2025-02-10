# SPDX-License-Identifier: MIT
"""A module with custom models."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nextcord import Embed
from nextcord.ui import View
from pydantic import BaseModel

if TYPE_CHECKING:
    from logging import Logger

    from university_bot import UniversityBot


__all__ = (
    "DataConfigBaseModel",
    "MessageData",
)


class DataConfigBaseModel(BaseModel, ABC):
    """Base model for the data configuration."""

    def save(self, filepath: Path | str, bot: UniversityBot, logger: Logger) -> None:
        """Saves the data configuration to the file.

        Parameters
        ----------
        filepath: :class:`Path` | :class:`str`
            The path to the file.
        bot: :class:`UniversityBot`
            The bot instance.
        logger: :class:`Logger`
            The logger instance.

        Raises
        ------
        OSError
            Failed to save the data.
        """

        try:
            with bot.temporary_files_config.context() as ctx:
                with ctx.open("w", encoding="utf-8") as f:
                    json.dump(self.model_dump(), f, indent=4)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(ctx, filepath)
            logger.debug("Data saved successfully.")
        except Exception as e:  # TODO: Should we catch more specific exceptions?
            logger.error("Failed to save data.", exc_info=True)
            raise OSError("Failed to save data.") from e

    @staticmethod
    @abstractmethod
    def load(path: Path | str) -> DataConfigBaseModel:
        """Loads the data configuration from the file.

        Parameters
        ----------
        path: :class:`Path` | :class:`str`
            The path to the file.

        Returns
        -------
        :class:`DataConfig`
            The loaded data configuration.
        """


@dataclass(slots=True)
class MessageData[E: Embed | None, V: View | None]:
    """Data for sending a message.

    Attributes
    ----------
    content: :class:`str` | None
        The message content.
    embed: :class:`nextcord.Embed` | None
        The message embed.
    view: :class:`nextcord.ui.View` | None
        The message view.
    """

    content: str | None
    embed: E | None
    view: V | None

    def to_dict(self) -> dict[str, Any]:
        """Returns the data as a dictionary."""
        return {
            "content": self.content,
            "embed": self.embed,
            "view": self.view,
        }
