# SPDX-License-Identifier: MIT
"""
A module to control the registration process.

The registration process is used to register new users.
"""

# pylint: disable=too-many-lines


from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import random
import string
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import aiosmtplib
import nextcord
from nextcord.application_command import SlashOption
from nextcord.channel import TextChannel
from nextcord.colour import Colour
from nextcord.embeds import Embed
from nextcord.enums import TextInputStyle
from nextcord.errors import DiscordException
from nextcord.ext import commands
from nextcord.interactions import Interaction
from nextcord.member import Member
from nextcord.ui import Modal, TextInput

from sggwbot.console import Console, FontColour
from sggwbot.errors import ExceptionData, RegistrationError
from sggwbot.models import Model
from sggwbot.utils import InteractionUtils, Matcher, MemberUtils, SmartDict

if TYPE_CHECKING:
    from nextcord.guild import Guild
    from nextcord.message import Message
    from nextcord.role import Role
    from sggw_bot import SGGWBot


class RegistrationCog(commands.Cog):
    """A cog to control the registration process."""

    __slots__ = (
        "_bot",
        "_model",
    )

    _bot: SGGWBot
    _model: RegistrationModel

    def __init__(self, bot: SGGWBot) -> None:
        """Initializes the :class:`.RegistractionCog` class."""
        self._bot = bot
        self._model = RegistrationModel(bot)

    @commands.Cog.listener("on_message")
    async def _on_message(self, message: Message) -> None:
        """Deletes message if it's not from the bot
        and is in the registration channel.
        """
        if message.channel.id != self._model.registration_channel_id:
            return

        if message.author == self._bot.user:
            return

        try:
            await message.delete()
        except nextcord.DiscordException:
            return

    async def _clear_messages_on_channel(self) -> None:
        """Clears all messages on the registration channel, except the bot's messages."""
        channel = self._model.registration_channel
        messages = await channel.history(limit=None).flatten()
        to_delete: list[Message] = []
        for message in messages:
            if message.author != self._bot.user:
                to_delete.append(message)

        await asyncio.gather(*(msg.delete() for msg in to_delete))

    @commands.Cog.listener(name="on_ready")
    async def _on_ready(self) -> None:
        await self._clear_messages_on_channel()

    @nextcord.slash_command(
        name="register",
        description="Komenda do zarejestrowania się (dla studentów SGGW).",
        dm_permission=False,
    )
    @InteractionUtils.with_info(
        catch_exceptions=[
            ExceptionData(
                DiscordException,
                with_traceback_in_response=False,
            ),
            ExceptionData(
                RegistrationError,
                with_traceback_in_response=False,
            ),
        ]
    )
    @InteractionUtils.with_log(FontColour.GREEN)
    async def _register(
        self,
        interaction: Interaction,
        index: str = SlashOption(
            name="nr_indeksu",
            description="Twój nr indeksu. Same cyfry np. `123456`.",
            min_length=6,
            max_length=6,
        ),
    ) -> None:
        """The command to register on the server.

        Should be used by the new users.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        index: :class:`str`
            The user's index number.

        Raises
        ------
        RegistrationError
            If the registration failed.
        """
        if not index.isdigit():
            await interaction.response.send_message(
                "Numer indeksu musi zawierać 6 cyfr!",
                ephemeral=True,
            )
            return

        member: Member = interaction.user  # type: ignore
        try:
            with CodeController(index, member) as ctrl:
                code_model = ctrl.code_model
                if reason := code_model.check_if_blocked(index):
                    await interaction.response.send_message(reason, ephemeral=True)
                    return

                mail_ctrl = MailController(member, index, code_model)
                destination_address = mail_ctrl.destination_address

                async def send_mail_if_should() -> None:
                    if code_model.should_send_email(index):
                        await mail_ctrl.send_mail()

                async def send_modal() -> None:
                    verifided_role = self._model.get_verified_role(member.guild)
                    if verifided_role is None:
                        raise RegistrationError("Verified role not found.")

                    modal = CodeModal(
                        self._bot,
                        verifided_role,
                        code_model,
                        MemberData.from_registration(member, index),
                        destination_address,
                    )
                    await interaction.response.send_modal(modal)

                await asyncio.gather(
                    send_mail_if_should(),
                    send_modal(),
                )
        except RegistrationError as e:

            async def send_error_to_member() -> None:
                await member.send(
                    "Wysłanie maila z kodem, potrzebnym "
                    "do zarejestrowania się na serwerze "
                    f"**{self._bot.get_default_guild().name}**, "
                    "nie powiodło się.\n"
                    "Administracja została powiadomiona o problemie.\n"
                    "Spróbuj ponownie później.\n"
                    "Przepraszamy za problemy.",
                    delete_after=600,
                )

            async def send_error_to_bot_channel() -> None:
                bot_channel = self._bot.get_bot_channel()
                default_role = self._bot.get_default_guild().default_role
                await bot_channel.send(
                    f"{default_role.mention}\n"
                    f"**Sending email to {member.mention} failed!**\n"
                    f"```{str(e)[-3800:]}```",
                )

            Console.error("Sending email failed.", exception=e)

            await asyncio.gather(
                send_error_to_member(),
                send_error_to_bot_channel(),
            )

    @nextcord.slash_command(
        name="register_guest",
        description="Komenda do wysłania prośby o rejestrację (jeśli nie jesteś studentem SGGW).",
        dm_permission=False,
    )
    @InteractionUtils.with_info(
        catch_exceptions=[
            ExceptionData(
                DiscordException,
                with_traceback_in_response=False,
            ),
            ExceptionData(
                RegistrationError,
                with_traceback_in_response=False,
            ),
        ]
    )
    @InteractionUtils.with_log(FontColour.GREEN)
    async def _register_guest(self, interaction: Interaction) -> None:
        modal = InfoModal(self._bot)
        await interaction.response.send_modal(modal)

    @nextcord.slash_command(
        name="whois",
        description="Show information about a member.",
        dm_permission=False,
    )
    @InteractionUtils.with_info(catch_exceptions=[DiscordException])
    @InteractionUtils.with_log()
    async def _whois(
        self,
        interaction: Interaction,
        argument: str = SlashOption(
            description="Member's ID, first name, last name, index or nick."
        ),
    ) -> None:
        matching_members = self._model.find_matching_members(argument)

        if not matching_members:
            await interaction.response.send_message(
                f"No members found matching the argument: {argument}",
                ephemeral=True,
            )
            return

        # Reverse the list to show the most relevant members at the end.
        matching_members = matching_members[::-1]

        embeds = []
        for member_data in matching_members:
            embeds.append(member_data.to_embed())

        message = (
            f"Found **{len(embeds)}** member(s) matching the argument: **{argument}**"
        )

        if len(embeds) > 10:
            await interaction.response.send_message(
                message + "\n**Showing only 10.**",
                embeds=embeds[:10],
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                message, embeds=embeds, ephemeral=True
            )

    @nextcord.slash_command(
        name="edit_member_data",
        description="Edit the member data.",
        dm_permission=False,
    )
    @InteractionUtils.with_info(catch_exceptions=[DiscordException])
    @InteractionUtils.with_log()
    async def _edit_member_data(
        self,
        interaction: Interaction,
        member_id: str = SlashOption(description="The member's ID."),
    ) -> None:
        """Edits the member data.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        member_id: :class:`str`
            The member's ID.
        """
        modal = EditMemberInfoModal(self._model, member_id)
        await interaction.response.send_modal(modal)


class EditMemberInfoModal(Modal):
    """The modal to edit the member info."""

    __slots__ = (
        "model",
        "member_id",
    )

    model: RegistrationModel
    member_id: str

    def __init__(self, model: RegistrationModel, member_id: str) -> None:
        super().__init__("Edit member info.", timeout=None)

        self.model = model
        self.member_id = member_id
        member_data = model.get_member_data(member_id)

        first_name = member_data.get("FirstName", "")
        self.add_item(
            TextInput("First name:", default_value=first_name, required=False)
        )

        last_name = member_data.get("LastName", "")
        self.add_item(TextInput("Last name:", default_value=last_name, required=False))

        student_id = member_data.get("StudentID", "")
        self.add_item(
            TextInput("Student ID:", default_value=student_id, required=False)
        )

        non_student_reason = member_data.get("Non-student reason", "")
        self.add_item(
            TextInput(
                "Non-student reason", default_value=non_student_reason, required=False
            )
        )

        other_account_reason = member_data.get("Another account reason", "")
        self.add_item(
            TextInput(
                "Another account reason",
                default_value=other_account_reason,
                required=False,
            )
        )

    async def callback(self, interaction: Interaction) -> None:
        """The callback to edit the member info."""

        member_data = self.model.get_member_data(self.member_id)
        data = {
            "FirstName": self.children[0],
            "LastName": self.children[1],
            "StudentID": self.children[2],
            "Non-student reason": self.children[3],
            "Another account reason": self.children[4],
        }

        for data_name, data_value in data.items():
            assert isinstance(data_value, TextInput)
            member_data[data_name] = data_value.value or None

        self.model.set_member_data(self.member_id, member_data)
        await interaction.response.send_message(
            "The member's data has been edited.", ephemeral=True
        )


class RegistrationModel(Model):
    """The model for :class:`.RegistrationCog`"""

    bot: SGGWBot

    def __init__(self, bot: SGGWBot) -> None:
        Model.__init__(self)
        self.bot = bot

    @property
    def registration_channel_id(self) -> int:
        """The ID of the registration channel."""
        channel_id = self.data.get("channel_id")
        if channel_id is None:
            raise KeyError(f"channel_id in {self._settings_path} is empty")
        return channel_id

    @property
    def registration_channel(self) -> TextChannel:
        """The registration channel."""
        channel_id = self.registration_channel_id
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, TextChannel):
            raise TypeError("Registration channel must be TextChannel")
        return channel

    def get_verified_role(self, guild: Guild) -> Role | None:
        """Returns the verified role for the guild.

        Parameters
        ----------
        guild: :class:`nextcord.Guild`
            The guild to get the role for.

        Returns
        -------
        :class:`nextcord.Role` | `None`
            The verified role for the guild or `None` if it doesn't exist.
        """
        role_id = self.data.get("verified_role_id", 0)
        return guild.get_role(role_id)

    @property
    def _registered_users_path(self) -> Path:
        return Path("data/registration/registered_users.json")

    def get_member_data(self, member_id: str) -> dict[str, Any]:
        """Returns the member data."""
        path = self._registered_users_path
        with open(path, "r", encoding="utf-8") as f:
            data: dict[str, dict[str, Any]] = json.load(f)
        return data.get(member_id, {})

    def set_member_data(self, member_id: str, member_data: dict[str, Any]) -> None:
        """Sets the member data."""
        path = self._registered_users_path
        with open(path, "r", encoding="utf-8") as f:
            data: dict[str, dict[str, Any]] = json.load(f)
        data[member_id] = member_data
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def find_matching_members(self, argument: str) -> list[MemberData]:
        """Finds the matching members.

        Parameters
        ----------
        argument: :class:`str`
            The argument to match the members with.

        Returns
        -------
        list[:class:`.MemberData`]
            The matching members.

        Notes
        -----
        The argument can be:
            - member's ID
            - member's name
            - member's surname
            - member's index
            - member's nick
        """
        guild = self.bot.get_default_guild()

        if len(argument) == 6 and argument.isdigit():
            return self._find_members_by_index(argument, guild)

        argument = argument.lower()
        results = SmartDict[MemberData, float](lambda a, b: a > b)
        matcher = Matcher[MemberData](
            list(map(MemberData, guild.members)), ignore_case=True
        )
        keys: list[Callable[[MemberData], str]] = [
            lambda i: i.index,
            lambda i: str(i.member.id),
            lambda i: i.member.name,
            lambda i: MemberUtils.display_name(i.member),
            lambda i: i.first_name,
            lambda i: i.last_name,
            lambda i: i.first_name + i.last_name,
            lambda i: i.last_name + i.first_name,
        ]

        for key in keys:
            for i in matcher.match_all(argument, key=key):
                results[i.item] = i.ratio

        if (max_ratio := max(results.values())) <= 0.5:
            return []

        results = dict(sorted(results.items(), key=lambda i: i[1], reverse=True))

        return [i[0] for i in results.items() if i[1] > max_ratio * 0.9]

    def _find_members_by_index(self, index: str, guild: Guild) -> list[MemberData]:
        matching_members = []
        for member in guild.members:
            member_data = MemberData(member)
            if member_data.index == index:
                matching_members.append(member_data)
        return matching_members


@dataclass(slots=True)
class MailLog:
    """Represents a log of sending an email to a user.

    Attributes
    ----------
    provided_index: :class:`str`
        The index number that the user provided.
    mails_sent_time: list[:class:`datetime.datetime`]
        The list of times when the email was sent.
    """

    provided_index: str
    mails_sent_time: list[dt.datetime] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Returns a dictionary representation of the object."""
        return {
            "provided_index": self.provided_index,
            "mails_sent_time": [t.timestamp() for t in self.mails_sent_time],
        }


@dataclass(slots=True)
class CodeModel:
    """Represents a model for a code.

    Attributes
    ----------
    code: :class:`str`
        The code that the user has to provide.
    generation_time: :class:`datetime.datetime`
        The time when the code was generated.
    mail_logs: list[:class:`.MailLog`]
        The list of logs of sending emails to the user.
    expire: :class:`str`
        The date and time when the code expires.
    is_valid: :class:`bool`
        Whether the code is still valid.
    """

    code: str
    generation_time: dt.datetime = field(default_factory=dt.datetime.now)
    mail_logs: list[MailLog] = field(default_factory=list)
    _valid_until: dt.datetime = field(init=False)

    def __post_init__(self) -> None:
        self._valid_until = self.generation_time + dt.timedelta(hours=8)

    @property
    def expire(self) -> str:
        """The date and time when the code expires."""
        return self._valid_until.strftime("%d.%m.%Y %H:%M:%S")

    @property
    def is_valid(self) -> bool:
        """Returns ``True`` if the code is still valid."""
        return self._valid_until > dt.datetime.now()

    def should_send_email(self, index: str) -> bool:
        """Checks if the email should be sent.

        Parameters
        ----------
        index: :class:`str`
            The index number that the user provided.

        Returns
        -------
        :class:`bool`
            ``True`` if the email should be sent.

        Notes
        -----
        The email should be sent if it's the first email for this index number
        or the previous email was sent more than 5 minutes ago.
        """
        if index not in [log.provided_index for log in self.mail_logs]:
            return True

        five_minutes_ago = dt.datetime.now() - dt.timedelta(minutes=5)
        for log in self.mail_logs:
            if log.provided_index == index:
                for time in log.mails_sent_time:
                    if time > five_minutes_ago:
                        return False
                return True

        return True  # pragma: no cover

    def check_if_blocked(self, index: str) -> str | None:
        """Checks if the registration should be blocked.

        Returns
        -------
        :class:`str` | `None`
            The reason why the registration is blocked or `None` if it's not.

        Notes
        -----
        The registration will be temporarily blocked if the user has sent
        more than 3 emails to the same index number.
        The registration will be permanently blocked if the user has sent
        3 emails to different index numbers and the next index is different than previous.
        """
        for log in self.mail_logs:
            if log.provided_index == index:
                if (
                    self.is_valid
                    and len(log.mails_sent_time) >= 3
                    and self.should_send_email(index)
                ):
                    return (
                        "Wysłałano zbyt wiele próśb o rejestrację.\n"
                        "Rejestracja została **tymczasowo zablokowana**.\n"
                        f"Następna możliwa próba: {self.expire}"
                    )
                break

        provided_indexes = {log.provided_index for log in self.mail_logs}
        if len(provided_indexes) >= 3 and index not in provided_indexes:
            return (
                "Podano 3 razy inny indeks.\n"
                "Rejestracja została **permanentnie zablokowana**.\n"
                "Jeśli chcesz się odwołać, znajdź Admina z listy po prawej "
                "i napisz do niego prywatną wiadomość."
            )
        return None

    def add_mail_sent_time(self, index: str) -> None:
        """Adds the time to logs when the email was sent."""
        dt_now = dt.datetime.now().replace(microsecond=0)
        for log in self.mail_logs:
            if log.provided_index == index:
                log.mails_sent_time.append(dt_now)
                return
        self.mail_logs.append(MailLog(index, [dt_now]))

    def to_dict(self) -> dict[str, Any]:
        """Returns a dictionary representation of the object."""
        return {
            "code": self.code,
            "generation_time": self.generation_time.timestamp(),
            "mail_logs": [log.to_dict() for log in self.mail_logs],
        }


class CodeController:
    """Represents a controller for code.

    The code is generated when `with` statement is used.

    Attributes
    ----------
    index: :class:`str`
        The index number that the user provided.
    member: :class:`.MemberData`
        The data of the member.
    code_model: :class:`.CodeModel`
        The model of the code.

    Examples
    -------- ::

        with CodeController(index, member) as controller:
            code_model = controller.code_model
            code = code_model.code
    """

    __slots__ = (
        "index",
        "member",
        "code_model",
    )

    index: str
    member: Member
    code_model: CodeModel

    def __init__(self, index: str, member: Member) -> None:
        self.index = index
        self.member = member

    @property
    def _registration_path(self) -> Path:
        path = Path("data/registration/")
        if not path.exists():
            path.mkdir()
            Console.warn(f"Dictionary {path} has been created.")
        return path

    @property
    def _codes_path(self) -> Path:
        path = self._registration_path / "codes.json"
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                f.write(r"{}")
            Console.warn(f"File {path} has been created.")
        return path

    @property
    def _codes_data(self) -> dict[str, CodeModel]:
        with open(self._codes_path, "r", encoding="utf-8") as f:
            data: dict[str, dict[str, Any]] = json.load(f)

        ret = {}
        for k, v in data.items():
            logs = []
            for log in v["mail_logs"]:
                mail_log = MailLog(
                    log["provided_index"],
                    [dt.datetime.fromtimestamp(i) for i in log["mails_sent_time"]],
                )
                logs.append(mail_log)
            ret[k] = CodeModel(
                v["code"], dt.datetime.fromtimestamp(v["generation_time"]), logs
            )
        return ret

    @staticmethod
    def _generate_code() -> str:
        return "".join([random.choice(string.ascii_letters) for _ in range(8)])

    def __enter__(self) -> CodeController:
        member_id = self.member.id
        code_model = self._codes_data.get(str(member_id))
        if code_model is None or code_model.is_valid is False:
            code = self._generate_code()
            code_model = CodeModel(code)
        self.code_model = code_model
        return self

    def __exit__(self, *_) -> None:
        data = self._codes_data
        data[str(self.member.id)] = self.code_model
        with open(self._codes_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False, default=CodeModel.to_dict)


@dataclass(slots=True)
class MemberData:  # pylint: disable=too-many-instance-attributes
    """Represents the data of the member.

    Attributes
    ----------
    member: :class:`nextcord.Member`
        The member.
    index: :class:`str`
        The member index number.
    first_name: :class:`str`
        The first name of the user.
    last_name: :class:`str`
        The last name of the user.
    is_student: :class:`bool`
        Whether the user is a student or not.
    non_student_reason: :class:`str` | `None`
        The reason why the user is not a student.
    other_accounts: list[:class:`nextcord.Member`]
        The list of other accounts that the user has.
    other_account_reason: :class:`str` | `None`
        The reason why the user has other accounts.
    """

    member: Member
    index: str = field(init=False)
    first_name: str = field(init=False)
    last_name: str = field(init=False)
    is_student: bool = field(init=False)
    non_student_reason: str | None = field(init=False)
    other_accounts: list[Member] = field(init=False)
    other_account_reason: str | None = field(init=False)

    def __post_init__(self) -> None:
        with open(self._registered_users_path, "r", encoding="utf-8") as f:
            data: dict[str, dict[str, Any]] = json.load(f)
        member_data = data.get(str(self.member.id), {})
        self.index = member_data.get("StudentID", "")
        self.first_name = member_data.get("FirstName", "")
        self.last_name = member_data.get("LastName", "")
        with open(self._student_indexes_path, "r", encoding="utf-8") as f:
            self.is_student = self.index in f.read().splitlines()
        self.non_student_reason = member_data.get("Non-student reason")
        self.other_accounts = self._get_other_accounts(data)
        self.other_account_reason = member_data.get("Another account reason")

    def __hash__(self) -> int:
        return hash(self.member)

    @classmethod
    def from_registration(cls, member: Member, index: str) -> MemberData:
        """Creates a new instance of :class:`.MemberData` from registration."""
        self = cls(member)
        self.index = index
        return self

    def to_embed(self) -> Embed:
        """Converts the member data to an embed."""
        member = self.member

        embed = Embed(
            title="User information:",
            description=f"{member} ({member.mention})",
            colour=member.top_role.colour,
        ).set_thumbnail(
            url=member.avatar.url if member.avatar else member.default_avatar.url
        )

        info = {
            "First name": self.first_name,
            "Last name": self.last_name,
            "Student ID": self.index,
            "Non-student reason": self.non_student_reason,
            "Another account reason": self.other_account_reason,
        }

        for k, v in info.items():
            if v is not None:
                embed.add_field(name=k, value=v)

        embed.add_field(name="ID", value=self.member.id, inline=False)

        everyone = member.guild.default_role
        roles = [role.mention for role in member.roles if role != everyone][::-1]
        embed.add_field(name="Roles", value=", ".join(roles), inline=False)

        return embed

    @property
    def _student_indexes_path(self) -> Path:
        path = Path("data/registration/student_indexes.txt")
        if not path.exists():
            path.touch()
            Console.warn(f"File {path} has been created.")
        return path

    @property
    def _registered_users_path(self) -> Path:
        path = Path("data/registration/registered_users.json")
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                f.write(r"{}")
            Console.warn(f"File {path} has been created.")
        return path

    def _is_student(self) -> bool:
        with open(self._student_indexes_path, "r", encoding="utf-8") as f:
            return self.index in f.read().splitlines()

    def _get_other_accounts(self, data: dict[str, dict[str, Any]]) -> list[Member]:
        return [
            member
            for k, v in data.items()
            if (
                v.get("StudentID") == self.index
                and int(k) != self.member.id
                and (member := self.member.guild.get_member(int(k))) is not None
            )
        ]


class InfoModal(Modal):
    """Represents a Modal for entering information about non-student member."""

    __slots__ = ("_bot",)

    _bot: SGGWBot

    def __init__(self, bot: SGGWBot) -> None:
        super().__init__(title="Rejestracja", timeout=None)
        self._bot = bot

        self.add_item(
            TextInput(
                label="Podaj informacje o sobie",
                placeholder="Kim jesteś? Dlaczego potrzebujesz dostępu do serwera?",
                style=TextInputStyle.paragraph,
                required=True,
                max_length=1024,
            )
        )

    async def callback(self, interaction: Interaction) -> None:
        """Callback for the modal."""

        info_input = self.children[0]
        assert isinstance(info_input, TextInput)

        await interaction.response.send_message(
            "**Dziękujemy za zgłoszenie!**\n\n"
            "Wiadomość o treści:\n"
            f"***{info_input.value}***\n"
            "została przesłana do Administracji.\n\n"
            "**Po weryfikacji zostaniesz zarejestrowany.**",
            ephemeral=True,
        )

        member = interaction.user
        assert isinstance(member, Member)

        Console.specific(
            f"User {member} has subbited a registration request, "
            f"providing the following reason: {info_input.value}.",
            "Registration",
            FontColour.CYAN,
            bold_type=True,
            bold_text=True,
        )

        embed = (
            Embed(
                title="New registration request!",
                description=member.mention,
                color=Colour.blurple(),
            )
            .add_field(name="Name", value=f"{member}")
            .add_field(name="Reason", value=info_input.value, inline=False)
            .add_field(name="ID", value=member.id, inline=False)
            .set_thumbnail(
                url=member.avatar.url if member.avatar else member.default_avatar.url
            )
        )

        if member.nick or member.global_name:
            embed.insert_field_at(
                1, name="Nick", value=MemberUtils.display_name(member)
            )

        bot_channel = self._bot.get_bot_channel()
        await bot_channel.send(embed=embed)


class CodeModal(Modal):
    """Represents a Modal for entering the code sent by email."""

    __slots__ = (
        "_bot",
        "_verified_role",
        "_code_model",
        "_member_data",
        "_destination_address",
    )

    _bot: SGGWBot
    _verified_role: Role
    _code_model: CodeModel
    _member_data: MemberData
    _destination_address: str

    def __init__(  # pylint: disable=too-many-arguments
        self,
        bot: SGGWBot,
        verified_role: Role,
        code_model: CodeModel,
        member_data: MemberData,
        destination_address: str,
    ) -> None:
        super().__init__(title="Rejestracja", timeout=None)
        self._bot = bot
        self._verified_role = verified_role
        self._member_data = member_data
        self._code_model = code_model
        self._destination_address = destination_address

        self.add_item(self._code_input)

        if not self._member_data.is_student:
            self.add_item(self._non_student_info)

        if self._member_data.other_accounts:
            self.add_item(self._other_account_info)

    @property
    def _code_input(self) -> TextInput:
        """A TextInput with a field to enter the code sent by mail."""

        return TextInput(
            label="Wprowadź kod:",
            placeholder=f"wysłany na {self._destination_address}",
            required=True,
            min_length=8,
            max_length=8,
        )

    @property
    def _non_student_info(self) -> TextInput:
        """A TextInput with a field to enter additional information
        as to why a non-student wants to register.
        """

        return TextInput(
            label="Dlaczego tu jesteś?",
            placeholder="Nie ma Cię na liście.\n"
            "Jesteś z roku niżej/wyżej? Twierdzisz, że to błąd?\n"
            "Powiadom nas o tym tutaj!",
            style=TextInputStyle.paragraph,
            required=True,
            max_length=1024,
        )

    @property
    def _other_account_info(self) -> TextInput:
        """A TextInput with a field to input info about the second account."""

        other_account_number = len(self._member_data.other_accounts)
        return TextInput(
            label="Do czego Ci kolejne konto?",
            placeholder=f"Masz już {other_account_number}.\n"
            "Być może streamujesz z tabletu?\n"
            "Daj znać! Które konto ma być Twoim głównym?",
            style=TextInputStyle.paragraph,
            required=True,
            max_length=1024,
        )

    async def callback(self, interaction: Interaction) -> None:
        """Callback for the modal."""

        code_input = self.children[0]
        assert isinstance(code_input, TextInput)

        data = {}
        if not self._member_data.is_student:
            data["Non-student reason"] = self.children[1]
            if self._member_data.other_accounts:
                data["Another account reason"] = self.children[2]
        elif self._member_data.other_accounts:
            data["Another account reason"] = self.children[1]

        for data_value in data.values():
            assert isinstance(data_value, TextInput)

        if code_input.value != self._code_model.code:
            await interaction.response.send_message(
                "**Wpisany kod jest niepoprawny!**",
                ephemeral=True,
                delete_after=30,
            )
            return

        ctrl_data = (self._code_model, self._member_data, self._verified_role)
        with RegisterController(*ctrl_data) as ctrl:
            await ctrl.register_user(self.children[1:])  # type: ignore

        await interaction.response.send_message(
            "**Zarejestrowano.**\nOdwiedź ***#informacje*** po więcej informacji.",
            ephemeral=True,
            delete_after=30,
        )

        Console.specific(
            f"User {self._member_data.member} has been registered.",
            "Registration",
            FontColour.CYAN,
            bold_type=True,
            bold_text=True,
        )

        member = self._member_data.member
        index = self._member_data.index
        bot_channel = self._bot.get_bot_channel()

        embed = (
            Embed(
                title="New registration!",
                description=member.mention,
                colour=Colour.fuchsia(),
            )
            .add_field(name="Name", value=f"{member}")
            .add_field(name="Index", value=index)
            .add_field(name="ID", value=member.id, inline=False)
            .set_thumbnail(
                url=member.avatar.url if member.avatar else member.default_avatar.url
            )
        )

        if member.nick or member.global_name:
            embed.insert_field_at(
                1, name="Nick", value=MemberUtils.display_name(member)
            )

        v: TextInput
        for k, v in data.items():
            embed.add_field(name=k, value=v.value, inline=False)

        await bot_channel.send(embed=embed)


@dataclass(slots=True)
class RegisterController:
    """Represents controller for register users.

    Examples
    -------- ::

        # Inside callback in the Modal class.
        with RegisterController(code_model, member_data) as ctrl:
            ctrl.register_user(self.children)
    """

    _code_model: CodeModel
    _member_data: MemberData
    _verified_role: Role
    _data: dict[str, dict[str, Any]] = field(init=False)

    @property
    def _registered_users_path(self) -> Path:
        path = Path("data/registration/registered_users.json")
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                f.write(r"{}")
            Console.warn(f"File {path} has been created.")
        return path

    def _load_data(self) -> None:
        path = self._registered_users_path
        with open(path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def _save_data(self) -> None:
        path = self._registered_users_path
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=True, indent=4)

    def __enter__(self) -> RegisterController:
        self._load_data()
        return self

    def __exit__(self, *_) -> None:
        self._save_data()

    async def register_user(self, other_info: list[TextInput]) -> None:
        """|coro|

        Registers the member.

        Parameters
        ----------
        other_info: list[:class:`TextInput`]
            The other info provided by member.
        """

        info = other_info.copy()
        member_data = self._member_data
        member = member_data.member
        member_id = str(member.id)
        data = self._data

        try:
            data[member_id]["StudentID"] = member_data.index
        except KeyError:
            data[member_id] = {"StudentID": member_data.index}

        if not member_data.is_student:
            data[member_id]["Non-student reason"] = info.pop(0).value
        if member_data.other_accounts:
            data[member_id]["Another account reason"] = info.pop(0).value

        self._data = data
        self._save_data()
        await member.add_roles(self._verified_role)


@dataclass(slots=True)
class MailController:
    """Represents a controller for sending mails."""

    _member: Member
    _index: str
    _code_model: CodeModel
    _destination_domain: str = field(init=False)

    def __post_init__(self) -> None:
        self._load_destination_domain()

    @property
    def destination_address(self) -> str:
        """Returns the destination address."""
        return f"s{self._index}@{self._destination_domain}"

    def _load_destination_domain(self) -> None:
        env_name = "DESTINATION_MAIL_DOMAIN"
        domain = os.environ.get(env_name)
        if domain is None:
            raise RegistrationError(f"{env_name} in .env is empty")
        self._destination_domain = domain

    @property
    def _mail_text(self) -> MIMEText:
        path = Path("data/registration/email.html")
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        text = (
            text.replace(
                "{{USER_DISPLAY_NAME}}", f"{MemberUtils.display_name(self._member)}"
            )
            .replace("{{REGISTRATION_CODE}}", self._code_model.code)
            .replace("{{DISCORD_NAME}}", self._member.guild.name)
            .replace("{{CODE_EXPIRATION}}", self._code_model.expire)
        )

        server_icon = self._member.guild.icon
        user_avatar = self._member.avatar

        if user_avatar:
            text = text.replace("{{USER_AVATAR}}", user_avatar.url)

        if server_icon:
            text = text.replace("{{DISCORD_LOGO}}", server_icon.url)

        return MIMEText(text, "html", "utf-8")

    def _generate_message(self) -> MIMEMultipart:
        message = MIMEMultipart()
        message["Subject"] = "Rejestracja Discord"
        message["From"] = "noreply"
        message["To"] = f"s{self._index}@{self._destination_domain}"
        message.attach(self._mail_text)
        return message

    async def send_mail(self) -> None:
        """|coro|

        Sends an email with a code.

        Raises
        ------
        RegistrationError
            Sending email failed.
        """

        username = os.environ.get("MAIL_ADDRESS")
        password = os.environ.get("MAIL_PASSWORD")

        if username is None or password is None:
            raise RegistrationError("MAIL_ADRESS or MAIL_PASSWORD in .env is empty")

        async with aiosmtplib.SMTP(
            hostname="smtp.gmail.com", port=465, use_tls=True
        ) as smtp:
            try:
                await smtp.login(username, password)
                message = self._generate_message()
                await smtp.send_message(message)
                self._code_model.add_mail_sent_time(self._index)
            except (ValueError, aiosmtplib.errors.SMTPException) as e:
                raise RegistrationError(*e.args) from e

        Console.specific(
            f"Email with code {self._code_model.code} has been sent to "
            f"{self.destination_address}",
            "Registration",
            FontColour.CYAN,
            bold_type=True,
            bold_text=True,
        )


def setup(bot: SGGWBot) -> None:
    """Loads the RegistrationCog cog."""
    bot.add_cog(RegistrationCog(bot))
