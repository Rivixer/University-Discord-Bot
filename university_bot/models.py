# SPDX-License-Identifier: MIT
"""A module containing base classes for models and controllers.

Examples
-------- ::

    class ClassModel(Model):
        def __init__(self) -> None:
            super().__init__()

    class ClassController(Controller):
        def __init__(self, model: Model) -> None:
            super().__init__(model)

    class ClassEmbedModel(EmbedModel):
        def __init__(self, model: Model, guild: Guild) -> None:
            super().__init__(model, guild)


"""

from __future__ import annotations

import io
import json
from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import nextcord
from nextcord.channel import TextChannel
from nextcord.embeds import Embed
from nextcord.errors import DiscordException

from .console import Console
from .errors import UpdateEmbedError
from .utils import PathUtils

if TYPE_CHECKING:
    from nextcord.emoji import Emoji
    from nextcord.message import Attachment, Message

    from .university_bot import UniversityBot


class Model(ABC):
    """Base class for Model classes.

    Examples
    -------- ::

        class ClassModel(Model):
            def __init__(self) -> None:
                super().__init__()

    Attributes
    ----------
    data: dict[:class:`str`, :class:`Any`]
        The data loaded from the `settings.json` file.
    """

    __slots__ = ("_data",)

    _data: dict[str, Any]

    def __init__(self) -> None:
        self._load_settings()

    @property
    def _settings_directory(self) -> Path:
        directory = Path("data/settings/")
        if not directory.exists():
            directory.mkdir()
            Console.warn(f"The directory '{directory}' has been created.")
        return directory

    @property
    def _settings_path(self) -> Path:
        filename = PathUtils.convert_classname_to_filename(self) + "_settings"

        path = self._settings_directory / f"{filename}.json"
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                json.dump({}, f)
            Console.warn(f"The file '{path}' has been created.")
        return path

    def _load_settings(self) -> None:
        with open(self._settings_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    @property
    def data(self) -> dict[str, Any]:
        """The data loaded from the `settings.json` file."""
        return self._data

    def reload_settings(self) -> None:
        """Reloads data from the `settings.json` file.

        The data can be retrieved from :attr:`.data` property.

        Raises
        ------
        OSError
            Cannot open the json file.
        JSONDecodeError
            Json file is corrupted.
        """
        with open(self._settings_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def update_settings(self, key: str, value: Any, *, force: bool = False) -> None:
        """Updates the :attr:`.data` dictionary and the `settings.json` file.

        Parameters
        ----------
        key: :class:`str`
            The key in the json file.
        value: :class:`Any`
            The value that will be stored in the key.
        force: :class:`bool`
            Whether to force adding a key.

        Raises
        ------
        OSError
            Cannot open the file.
        KeyError
            Invalid key.
        """

        if not force and key not in self._data.keys():
            raise KeyError(f"Invalid key ({key}) when updating {self._settings_path}.")

        self._data[key] = value
        with open(self._settings_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=True, indent=4, default=str)


@dataclass(slots=True)
class Controller(ABC):
    """Base class for Controller classes.

    Examples
    -------- ::

        class ClassController(Controller):
            def __init__(self, model: Model) -> None:
                super().__init__(model)

    Attributes
    ----------
    model: :class:`.Model`
        The model of the function.
    """

    model: Model


@dataclass(slots=True)
class EmbedModel(ABC):
    """Base class for EmbedModel classes.

    Examples
    -------- ::

        class ClassEmbedModel(EmbedModel):
            def __init__(self, model: Model, guild: Guild) -> None:
                super().__init__(model, guild)

    Attributes
    ----------
    model: :class:`.Model`
        The model of the function.
    bot: :class:`UniversityBot`
        The Discord bot instance.
    """

    model: Model
    bot: UniversityBot

    @property
    def _embeds_directory(self) -> Path:
        directory = Path("data/embeds/")
        if not directory.exists():
            directory.mkdir()
            Console.warn(f"The directory '{directory}' has been created.")
        return directory

    @property
    def embed_path(self) -> Path:
        """Path to the `embed.json` file."""
        filename = PathUtils.convert_classname_to_filename(self)
        path = self._embeds_directory / f"{filename}.json"
        if not path.exists():
            path.touch()
            with open(path, "w", encoding="utf-8") as f:
                json.dump({}, f)
            Console.warn(f"The file '{path}' has been created.")
        return path

    @property
    def reactions(self) -> list[Emoji | str]:
        """List of reactions to be added to the embed."""
        return []

    def generate_embed(self, **replaces) -> Embed:
        """Generates an embed saved in the `embed.json` file.

        Replaces:
        - `{CURRENT_TIME}` with `datetime (dd.mm.yyyy HH:MM)`
        - `{KEY}` with `{VALUE}` sent in `replaces` parameter

        Examples
        --------
        The embed.json file: ::

            {
                "title": "Test",
                "description": "{MyKey}"
            }

        After called `generate_embed(MyKey="MyDescription")`: ::

            {
                "title": "Test",
                "description": "MyDescription"
            }

        Parameters
        ----------
        replaces: dict[:class:`str`, `Any`]
            The dictionary where keys represent strings to be replaced
            and values represent substitutions.
        """

        with open(self.embed_path, "r", encoding="utf-8") as f:
            raw_data: str = f.read()

        current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        raw_data = raw_data.replace(r"{CURRENT_TIME}", current_time)

        for k, v in replaces.items():
            raw_data = raw_data.replace(f"{{{k}}}", str(v))

        data: dict = json.loads(raw_data)
        return Embed.from_dict(data)


class ControllerWithEmbed(Controller, ABC):
    """Class for Controller classes which also control an embed.

    Examples
    -------- ::

        class ClassControllerWithEmbed(ControllerWithEmbed):
            def __init__(self, model: Model, embed_model: EmbedModel) -> None:
                super().__init__(model, embed_model)

    Attributes
    ----------
    model: :class:`.Model`
        Model of the function.
    embed_model: :class:`EmbedModel`
        Model of the embed.
    """

    embed_model: EmbedModel
    model: Model

    def __init__(self, model: Model, embed_model: EmbedModel) -> None:
        super().__init__(model)
        self.embed_model = embed_model

    @property
    def message_id(self) -> int | None:
        """Message ID with an embed."""
        embed_data: dict[str, int] = self.model.data.get("embed_message", {})
        return embed_data.get("message_id")

    async def _add_reactions_to_message(self, message: Message) -> None:
        for reaction in self.embed_model.reactions:
            await message.add_reaction(reaction)

    async def send_embed(self, channel: TextChannel) -> Message:
        """|coro|

        Sends embed with reactions in the text channel.

        Saves message data in `data/settings/...`.

        Parameters
        ----------
        channel: :class:`TextChannel`
            The channel where the message will be sent.

        Returns
        -------
        :class:`Message`
            Sent message.
        """

        embed = self.embed_model.generate_embed()
        message = await channel.send(embed=embed)
        self._save_message_data_in_settings(message)
        await self._add_reactions_to_message(message)
        return message

    async def update_embed(self, reload_reactions: bool = True) -> Message:
        """|coro|

        Updates the sent embed.

        Reloads the data from `settings.json`.

        Parameters
        ----------
        reload_reactions: :class:`bool`
            Whether to clear reactions and add them again.

        Raises
        ------
        UpdateEmbedError
            The message cannot be updated.

        Returns
        -------
        :class:`Message`
            Updated message.
        """

        try:
            self.model.reload_settings()
            message = await self._get_message_from_settings()
            embed = self.embed_model.generate_embed()
            message = await message.edit(embed=embed)
            if reload_reactions:
                await message.clear_reactions()
                await self._add_reactions_to_message(message)
        except (DiscordException, TypeError) as e:
            raise UpdateEmbedError(*e.args) from e
        return message

    @property
    def embed_json(self) -> nextcord.File:
        """:class:`nextcord.File` with the embed json."""
        return nextcord.File(self.embed_model.embed_path)

    async def set_embed_json(self, file: Attachment) -> None:
        """|coro|

        Saves the attachment in the `data/embeds/...` path.

        Parameters
        ----------
        file: :class:`Attachment`
            The JSON file sent in the command.

        Raises
        ------
        TypeError
            The attachment must have a `.json` extension.
        ~nextcord.HTTPException
            Saving the attachment failed.
        """

        if not file.filename.lower().endswith(".json"):
            raise TypeError("The attachment must have a `.json` extension")
        try:
            json.loads(io.BytesIO(await file.read()).read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise TypeError("The attachment must be a valid JSON file") from e
        await file.save(self.embed_model.embed_path)

    def _save_message_data_in_settings(self, message: Message) -> None:
        data = {"channel_id": message.channel.id, "message_id": message.id}
        self.model.update_settings("embed_message", data, force=True)

    async def _get_message_from_settings(self) -> Message:
        """|coro|

        Returns a message fetched from a text channel.
        Channel and message IDs will be retrived from :attr:`model.data`.

        Raises
        ------
        TypeError
            Channel is not a :class:`TextChannel`.
        ~nextcord.DiscordException
            Message cannot be fetched.
        """

        data: dict[str, int] = self.model.data.get("embed_message", {})
        channel_id = data.get("channel_id", -1)
        msg_id = data.get("message_id", -1)
        channel = self.embed_model.bot.get_channel(channel_id)

        if not isinstance(channel, TextChannel):
            raise TypeError("Channel must be TextChannel")

        message = await channel.fetch_message(msg_id)
        return message
