# SPDX-License-Identifier: MIT
"""A module to control the 'role_assignment' embeds.

Each 'role_assignment' embed is identified by its identifier.
The identifier is the name of the file in the
'data/settings/role_assignment' directory.
The embed must also have a corresponding json file in the
'data/embeds/role_assignment' directory.

The 'role_assignment' embed is used to assign roles to users
based on their groups (e.g. laboratory group, faculty group, etc.).

Users' roles are updated when they react to the embed
with an emoji corresponding to their group.

The 'role_assignment' embed is sent to the channel
where the command '/role_assignment send' was used.
"""

from __future__ import annotations

import asyncio
import functools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Concatenate, ParamSpec

import nextcord
from nextcord.application_command import SlashOption
from nextcord.channel import TextChannel
from nextcord.embeds import Embed
from nextcord.emoji import Emoji
from nextcord.errors import DiscordException
from nextcord.ext import commands, tasks
from nextcord.interactions import Interaction
from nextcord.message import Attachment

from university_bot.errors import UpdateEmbedError
from university_bot.models import ControllerWithEmbed, EmbedModel, Model
from university_bot.utils import Console, FontColour, InteractionUtils

if TYPE_CHECKING:
    from nextcord.member import Member
    from nextcord.partial_emoji import PartialEmoji
    from nextcord.raw_models import RawReactionActionEvent
    from nextcord.role import Role

    from university_bot import UniversityBot

_P = ParamSpec("_P")
_FUNC = Callable[Concatenate[Any, Interaction, str, _P], Awaitable[Any]]


class RoleAssignment(commands.Cog):
    """A cog to control the role assignment embed."""

    __slots__ = (
        "_bot",
        "_ctrl",
    )

    _bot: UniversityBot
    _controllers: dict[str, RoleAssignmentController]

    def __init__(self, bot: UniversityBot) -> None:
        """Initialize the cog."""

        self._bot = bot
        self._load_controllers_task.start()  # pylint: disable=no-member

    @staticmethod
    def _validate_identifier(func: _FUNC) -> _FUNC:
        @functools.wraps(func)
        async def decorator(
            self: RoleAssignment,
            interaction: Interaction,
            identifier: str,
            *args: _P.args,
            **kwargs: _P.kwargs,
        ):
            controllers = self._controllers.keys()  # pylint: disable=protected-access
            if identifier in controllers:
                return await func(self, interaction, identifier, *args, **kwargs)
            raise ValueError(f"Identifier '{identifier}' not exists")

        return decorator

    @nextcord.slash_command(
        name="role_assignment",
        description="The role_assignment embed.",
        dm_permission=False,
    )
    async def _role_assignment(self, *_) -> None:
        """The role_assignment embed.

        This command is a placeholder for the subcommands.
        """

    @_role_assignment.subcommand(
        name="send",
        description="Send a new role_assignment embed.",
    )
    @InteractionUtils.with_info(
        before="Sending role_assignment embed...",
        after="The role_assignment embed has been sent.",
        catch_exceptions=[DiscordException, ValueError],
    )
    @InteractionUtils.with_log(show_channel=True)
    @_validate_identifier
    async def _send(self, interaction: Interaction, identifier: str) -> None:
        """Sends a new role_assignment embed.

        The role_assignment embed is sent to the channel where the command was used.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        identifier: :class:`str`
            The identifier of the role assignment.
        """

        channel = interaction.channel
        if isinstance(channel, TextChannel):
            await self._controllers[identifier].send_embed(channel)

    @_role_assignment.subcommand(
        name="update",
        description="Update the role_assignment embed.",
    )
    @InteractionUtils.with_info(
        before="Updating role_assignment embed...",
        after="The role_assignment embed has been updated.",
        catch_exceptions=[UpdateEmbedError, ValueError],
    )
    @InteractionUtils.with_log()
    @_validate_identifier
    async def _update(
        self,
        interaction: Interaction,  # pylint: disable=unused-argument
        identifier: str,
    ) -> None:
        """Updates the role_assignment embed.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        identifier: :class:`str`
            The identifier of the role assignment.

        Raises
        ------
        UpdateEmbedError
            The embed could not be updated.
        """
        await self._controllers[identifier].update_embed()

    @_role_assignment.subcommand(
        name="get_json",
        description="Get the role_assignment embed json.",
    )
    @InteractionUtils.with_info(
        before="Getting role_assignment embed json...",
        catch_exceptions=[DiscordException, ValueError],
    )
    @InteractionUtils.with_log()
    @_validate_identifier
    async def _get_json(self, interaction: Interaction, identifier: str) -> None:
        """Gets the json file representing the role_assignment embed.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        identifier: :class:`str`
            The identifier of the role assignment.
        """
        msg = await interaction.original_message()
        await msg.edit(content=None, file=self._controllers[identifier].embed_json)

    @_role_assignment.subcommand(
        name="set_json",
        description="Set the role_assignment embed json and update the embed.",
    )
    @InteractionUtils.with_info(
        before="Setting role_assignment embed json and updating the embed...",
        after="The role_assignment embed and json file have been updated.",
        catch_exceptions=[TypeError, ValueError, DiscordException, UpdateEmbedError],
    )
    @InteractionUtils.with_log()
    @_validate_identifier
    async def _set_json(
        self,
        interaction: Interaction,  # pylint: disable=unused-argument
        identifier: str,
        file: Attachment = SlashOption(
            description="JSON file "
            "downloaded from `/role_assignment get_json` and updated"
        ),
    ) -> None:
        """Sets the json file representing the role_assignment embed and updates this embed.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        identifier: :class:`str`
            The identifier of the role assignment.
        file: :class:`Attachment`
            The json file downloaded from `/role_assignment get_json` and updated.

        Raises
        ------
        UpdateEmbedError
            The embed could not be updated.
        """
        ctrl = self._controllers[identifier]
        await ctrl.set_embed_json(file)
        await ctrl.update_embed()

    @_role_assignment.subcommand(
        name="get_identifiers",
        description="Get the identifiers of the role assignments.",
    )
    @InteractionUtils.with_log()
    async def _get_identifiers(
        self,
        interaction: Interaction,  # pylint: disable=unused-argument
    ) -> None:
        """Gets the identifiers of the role assignments.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        """

        result = "Identifiers:" + "".join(map(lambda i: f"\n- {i}", self._controllers))
        await interaction.response.send_message(result, ephemeral=True)

    @commands.Cog.listener(name="on_raw_reaction_add")
    async def _on_raw_reaction_add(self, payload: RawReactionActionEvent) -> None:
        """Handles the reaction add event.

        Parameters
        ----------
        payload: :class:`RawReactionActionEvent`
            The payload of the reaction add event.
        """

        emoji = payload.emoji
        member = payload.member
        if member is None or member.bot:
            return

        channel = self._bot.get_channel(payload.channel_id)
        if not isinstance(channel, TextChannel):
            return

        for controller in self._controllers.values():
            if payload.message_id == controller.message_id:
                break
        else:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
            if emoji.is_custom_emoji():
                reaction = nextcord.utils.get(message.reactions, emoji=emoji)
            else:
                reaction = nextcord.utils.get(message.reactions, emoji=emoji.name)

            async def remove_reaction():
                await message.remove_reaction(emoji, member)

            if (
                reaction is None
                or self._bot.user not in await reaction.users().flatten()
            ):
                return await remove_reaction()

            async def change_role():
                added_role = await controller.change_role(emoji, member)
                if added_role is not None:
                    Console.specific(
                        f"{member} changed their group to {added_role.name}.",
                        "roles",
                        colour=FontColour.GREEN,
                    )
                else:
                    Console.specific(
                        f"{member} reset {controller.model.identifier} roles.",
                        "roles",
                        colour=FontColour.GREEN,
                    )

            await asyncio.gather(
                change_role(),
                remove_reaction(),
            )
        except nextcord.DiscordException:
            return

    @_role_assignment.subcommand(
        name="reload_controllers",
        description="Reload the role_assignment controllers.",
    )
    @InteractionUtils.with_log()
    @InteractionUtils.with_info(
        before="Reloading role_assignment controllers...",
        after="The role_assignment controllers have been reloaded.",
    )
    async def _reload_controllers(self, _: Interaction) -> None:
        """Reloads the role_assignment controllers.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction that triggered the command.
        """
        self._controllers = await self._load_controllers()

    @tasks.loop(count=1)
    async def _load_controllers_task(self):
        await self._bot.wait_until_ready()
        self._controllers = await self._load_controllers()

    async def _load_controllers(self) -> dict[str, RoleAssignmentController]:
        controllers = {}
        for path in RoleAssignmentModel.get_settings_directory().iterdir():
            identifier = path.stem
            model = RoleAssignmentModel(identifier)
            embed_model = RoleAssignmentEmbedModel(model, self._bot)
            controllers[identifier] = RoleAssignmentController(model, embed_model)
            Console.specific(
                f"'{identifier}' controller has been loaded.",
                "RoleAssignment",
                FontColour.GREEN,
                bold_type=True,
                bold_text=True,
            )
        return controllers


# pylint: disable=no-member


@dataclass(slots=True, frozen=True)
class ServerRole:
    """Represents a role on the server.

    Attributes
    ----------
    role_id: :class:`int`
        The ID of the role.
    description: :class:`str`
        The description of the role.
        Used to inform the user in embed what this role is for.
    emoji: :class:`str`
        The emoji that represents the role.
    """

    role_id: int
    description: str
    emoji: str
    additional_role_ids_to_remove: list[int] = field(default_factory=list)

    @property
    def info(self) -> str:
        """Role's emoji with its description."""
        return f"{self.emoji} - {self.description}"


class RoleAssignmentModel(Model):
    """Represents the role_assignment model.

    Attributes
    ----------
    roles: list[:class:`Group`]
        The list of roles.
    identifier: :class:`str`
        The identifier of the role assignment.

    Notes
    -----
    The role_assignment model is a singleton.
    """

    __slots__ = ("_roles", "_identifier")

    _roles: list[ServerRole]
    _identifier: str

    def __init__(self, identifier: str) -> None:
        """Initializes the role_assignment model."""
        self._identifier = identifier
        super().__init__()
        self._load_roles()

    @property
    def _settings_directory(self) -> Path:
        return RoleAssignmentModel.get_settings_directory()

    @property
    def _settings_path(self) -> Path:
        path = self._settings_directory / f"{self._identifier}.json"
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                json.dump({}, f)
            Console.warn(f"The file '{path}' has been created.")
        return path

    @property
    def _roles_data(self) -> dict[str, Any]:
        """The roles data from the settings.json file."""
        roles_data = self.data.get("roles")
        if not isinstance(roles_data, dict):
            raise TypeError("roles in settings.json must be dict")
        return roles_data

    def _load_roles(self) -> None:
        """Loads the roles data from the settings.json file."""
        roles_data = self._roles_data
        self._roles = []

        for role_name in roles_data.keys():
            role = self._load_role(role_name)
            self.roles.append(role)

    def _load_role(self, key: str) -> ServerRole:
        role_data = self._roles_data.get(key)
        if role_data is None:
            raise KeyError(f"Key '{key}' not exists in {self._settings_path}")
        return ServerRole(**role_data)

    def reload_settings(self) -> None:
        """Reloads the settings.json file and reloads roles."""
        super().reload_settings()
        self._load_roles()

    @property
    def roles(self) -> list[ServerRole]:
        """Role list."""
        return self._roles

    @property
    def identifier(self) -> str:
        """Identifier of the role assignment."""
        return self._identifier

    @staticmethod
    def get_settings_directory() -> Path:
        """Path to the settings directory."""
        directory = Path("data/settings/role_assignment")
        if not directory.exists():
            directory.mkdir()
            Console.warn(f"The directory '{directory}' has been created.")
        return directory


class RoleAssignmentEmbedModel(EmbedModel):
    """Represents the role_assignment embed model.

    Attributes
    ----------
    model: :class:`RoleAssignmentModel`
        The role_assignment model.

    Notes
    -----
    The role_assignment embed model is a singleton.
    """

    model: RoleAssignmentModel

    @property
    def embed_path(self) -> Path:
        """Path to the `embed.json` file."""

        directory = self._embeds_directory / "role_assignment"
        if not directory.exists():
            directory.mkdir()
            Console.warn(f"The directory '{directory}' has been created.")

        path = directory / f"{self.model.identifier}.json"
        if not path.exists():
            path.touch()
            with open(path, "w", encoding="utf-8") as f:
                json.dump({}, f)
            Console.warn(f"The file '{path}' has been created.")
        return path

    def generate_embed(self, **_) -> Embed:
        roles_info = "\\n".join(map(lambda i: i.info, self.model.roles))
        return super().generate_embed(GROUP_DESCRIPTION=roles_info)

    @property
    def reactions(self) -> list[Emoji | str]:
        return list(map(lambda i: i.emoji, self.model.roles))


class RoleAssignmentController(ControllerWithEmbed):
    """Represents the role_assignment controller.

    Attributes
    ----------
    model: :class:`RoleAssignmentModel`
        The role_assignment model.
    embed_model: :class:`RoleAssignmentEmbedModel`
        The role_assignment embed model.

    Methods
    -------
    change_role(emoji: :class:`nextcord.PartialEmoji`, member: :class:`nextcord.Member`)

    Notes
    -----
    The role_assignment controller is a singleton.
    """

    embed_model: RoleAssignmentEmbedModel
    model: RoleAssignmentModel

    async def change_role(self, emoji: PartialEmoji, member: Member) -> Role | None:
        """|coro|

        Assigns the member the role corresponding to the emoji and removes other roles.

        Parameters
        ----------
        emoji: :class:`nextcord.PartialEmoji`
            The emoji that the user reacted to.
        member: :class:`nextcord.Member`
            The member who reacted to the embed message.

        Returns
        -------
        :class:`nextcord.Role`
            The role that has been assigned to the member.

        Raises
        ------
        AttributeError
            The role corresponding to the emoji does not exist.
        """

        role_to_add: Role | None = None
        roles_to_remove: list[Role] = []
        reaction = str(emoji)
        only_reset = False

        for server_role in self.model.roles:
            role = member.guild.get_role(server_role.role_id)
            if role is None:
                if server_role.role_id == 0 and reaction == server_role.emoji:
                    only_reset = True
                continue  # pragma: no cover

            if reaction == server_role.emoji:
                role_to_add = role
                for member_role in member.roles:
                    if member_role.id in server_role.additional_role_ids_to_remove:
                        roles_to_remove.append(member_role)
            elif role in member.roles:
                roles_to_remove.append(role)

        if role_to_add is None and not only_reset:
            raise AttributeError(f"Role with '{emoji}' not exists")

        async def add_role():
            if role_to_add is not None:
                await member.add_roles(role_to_add)

        await asyncio.gather(
            member.remove_roles(*roles_to_remove),
            add_role(),
        )

        return role_to_add


def setup(bot: UniversityBot):
    """Loads the RoleAssignment cog."""
    bot.add_cog(RoleAssignment(bot))
