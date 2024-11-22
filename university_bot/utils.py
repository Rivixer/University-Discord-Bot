# SPDX-License-Identifier: MIT
"""A module containing utility classes and functions."""

from __future__ import annotations

import asyncio
import datetime as dt
import functools
import os
import re
import traceback
from abc import ABC
from collections.abc import Hashable
from dataclasses import KW_ONLY, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Concatenate,
    Generic,
    Literal,
    ParamSpec,
    TypeAlias,
    TypeVar,
    overload,
)

from discord import TextChannel, Interaction, Member, Thread
import discord
from discord.ext import commands

from university_bot.console import Console, FontColour
from university_bot.errors import ExceptionData

if TYPE_CHECKING:
    from nextcord.user import User

    _P = ParamSpec("_P")
    _FUNC = Callable[Concatenate[Any, Interaction, _P], Awaitable[Any]]


class InteractionUtils(ABC):
    """A class containing static methods that can be used to decorate commands.

    This class should not be instantiated.
    """

    @staticmethod
    def _command_name(interaction: Interaction) -> str:
        """Returns the name of the command that was run."""
        command = interaction.application_command
        if command is None:
            raise TypeError("Command was None")
        return command.qualified_name

    @staticmethod
    def with_log(
        colour: FontColour = FontColour.PINK, show_channel: bool = False
    ) -> Callable[[_FUNC], _FUNC]:
        """Logs information about the user who ran a decorated command to the console.

        This decorator should be placed after decorators that set a function as a command.

        If the command is a subcommand, its name will be preceded by its parent name.
        If the command is used in a thread, its name will be preceded
        by the name of the thread's parent channel.

        Parameters
        ----------
        colour: :class:`FontColour`
            The colour of the log message.
        show_channel: :class:`bool`
            Whether to show the channel name in the log message.
        """

        def decorator(func: _FUNC) -> _FUNC:
            @functools.wraps(func)
            async def wrapper(
                self,
                interaction: Interaction,
                *args: _P.args,
                **kwargs: _P.kwargs,
            ) -> Awaitable[Any]:
                type_info = "SLASH_COMMAND"
                command_name = InteractionUtils._command_name(interaction)
                user: Member = interaction.user  # type: ignore

                user_info = f"{MemberUtils.display_name(user)} ({user})"

                kwargs_info = " ".join(
                    f"{k}:{v}" for k, v in kwargs.items() if v is not None
                )

                if show_channel:
                    channel = interaction.channel
                    if isinstance(channel, TextChannel):
                        type_info += f"/{channel.name}"
                    if isinstance(channel, Thread):
                        if parent := channel.parent:
                            type_info += f"/{parent.name}/{channel.name}"

                Console.specific(
                    f"{user_info} used /{command_name} {kwargs_info}",
                    type_info,
                    colour,
                )

                return await func(self, interaction, *args, **kwargs)

            return wrapper

        return decorator

    @staticmethod
    def with_info(
        *,
        before: str | None = None,
        after: str | None = None,
        catch_exceptions: list[type[Exception] | ExceptionData] | None = None,
    ) -> Callable[[_FUNC], _FUNC]:
        """Responds to the interaction an ephemeral message to the user who ran a decorated command.

        This decorator should be placed after decorators that set a function as a command.

        If the interaction has already been responded to, it edits the message content.

        Examples
        --------

        After invoking the command below,
        first response to the interaction will be 'msg_before'.
        Then the response content will be changed to 'msg_foo'
        and finally it will be changed to 'msg_after'. ::

            @nextcord.slash_command()
            @with_info(before='msg_before', after='msg_after')
            async def foo(self, interaction: Interaction) -> None:
                msg = await interaction.original_message()
                await msg.edit(content='msg_foo')

        After invoking the command below,
        if the user sent 0 as 'b' parameter,
        an error will occur and will be printed as an interaction response. ::

            @nextcord.slash_command()
            @with_info(catch_exceptions=[ZeroDivisionError])
            async def foo(self, interaction: Interaction, a: int, b: int) -> None:
                await interaction.respond.send_message(f'{a} / {b} = {a/b})

        If an error occurs while running the command,
        the traceback will be printed by default.
        You can change this by passing an :class:`ExceptionData` instance
        with ``with_traceback_in_response`` and ``with_traceback_in_log`` parameters. ::

            @nextcord.slash_command()
            @with_info(
                catch_exceptions=[
                    ExceptionData(
                        ZeroDivisionError,
                        with_traceback_in_response=False,
                        with_traceback_in_log=False,
                    )
                ]
            ),
            async def foo(self, interaction: Interaction, a: int, b: int) -> None:
                await interaction.respond.send_message(f'{a} / {b} = {a/b})


        Parameters
        ----------
        before: :class:`str`
            The message to send before the command is run.
        after: :class:`str`
            The message to send after the command is run.
        catch_exceptions: list[type[:class:`Exception` | :class:`ExceptionData`]] | `None`
            An optional list of exception or exception data to catch.
            Defaults to `None`.

        Raises
        ------
        TypeError
            If the command is not a slash command.
        """

        def decorator(func: _FUNC) -> _FUNC:
            @functools.wraps(func)
            async def wrapper(
                self,
                interaction: Interaction,
                *args: _P.args,
                **kwargs: _P.kwargs,
            ) -> Awaitable[Any] | None:
                async def catch_error(exc: Exception, exc_data: ExceptionData) -> None:
                    err_msg = f"**[ERROR]** {exc}"

                    if exc_data.with_traceback_in_response:
                        trcbck = traceback.format_exc()
                        err_msg += f"\n```py\n{trcbck}```"

                    if len(err_msg) > 2000:
                        err_msg = f"{err_msg[:496]}\n\n...\n\n{err_msg[-1496:]}"

                    if not interaction.response.is_done():
                        await interaction.response.send_message(err_msg, ephemeral=True)
                    else:
                        try:
                            msg = await interaction.original_message()
                            await msg.edit(content=err_msg)
                        except discord.errors.NotFound:
                            await interaction.send(err_msg, ephemeral=True)

                    comm_name = InteractionUtils._command_name(interaction)
                    if exc_data.with_traceback_in_log:
                        Console.error(f"Error while using /{comm_name}.", exception=exc)
                    else:
                        Console.error(f"Error while using /{comm_name}. {exc}")

                if before:
                    await interaction.response.send_message(
                        before.format(**kwargs), ephemeral=True
                    )

                try:
                    result = await func(self, interaction, *args, **kwargs)
                except Exception as e:  # pylint: disable=broad-except
                    for exc_data in catch_exceptions or []:
                        if isinstance(exc_data, type):
                            exc_data = ExceptionData(exc_data)

                        if isinstance(e, exc_data.type):
                            await catch_error(e, exc_data)
                            break
                    else:
                        raise e
                else:
                    if after:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(
                                after.format(**kwargs), ephemeral=True
                            )
                        else:
                            msg = await interaction.original_message()
                            if not msg.content.startswith("**[ERROR]**"):
                                await msg.edit(content=after.format(**kwargs))

                    return result

            return wrapper

        return decorator


class PathUtils(ABC):  # pylint: disable=too-few-public-methods
    """A class containing utility methods for paths."""

    @staticmethod
    def convert_classname_to_filename(obj: object) -> str:
        """Converts a class name to a filename.

        If classname ends with 'Model', the last word is removed.

        Parameters
        ----------
        obj: :class:`object`
            The object to convert.

        Returns
        -------
        :class:`str`
            The converted class name.

        Examples
        -------- ::

            class ClassFoo:
                pass

            obj = ClassFoo()
            convert_classname_to_filename(obj)  # 'class_foo'

        Notes
        -----
        This method is used to convert a class name to a filename
        when saving a class to a file.
        """

        ret = re.sub("(?<!^)(?=[A-Z])", "_", obj.__class__.__name__).lower()
        if ret.endswith("_model"):
            return "_".join(ret.split("_")[:-1])
        return ret


class SlashCommandUtils(ABC):  # pylint: disable=too-few-public-methods
    """A class containing utility methods for slash commands."""

    @staticmethod
    def unregister_disabled_commands(
        cog: commands.Cog,
        commands_config: dict[str, bool],
    ) -> None:
        """Unregisters slash commands that are disabled in the config.

        Parameters
        ----------
        cog: :class:`commands.Cog`
            The cog to unregister the commands from.
        mapping: :class:`dict`[:class:`str`, :class:`bool`]
            A mapping of command names to their enabled/disabled status.
        """
        mapping = {cmd.name: cmd for cmd in cog.application_commands}
        config = {name: getattr(commands_config, name, True) for name in mapping.keys()}

        for name, command in mapping.items():
            if not config.get(name, True) and command in cog.application_commands:
                cog.application_commands.remove(command)


class MemberUtils(ABC):  # pylint: disable=too-few-public-methods
    """A class containing utility methods for members."""

    @overload
    @staticmethod
    def display_name(user: Member) -> str:
        """Returns the display name of the member.

        Due to the bug in the `nextcord.Member.display_name` property,
        this method should be used instead of it.

        The bug is that `nextcord.Member.display_name` property does not return
        the global name of the member if the member has no nickname on the server.

        Result of this method is specified using the following hierarchy:
        1. Guild specific nickname
        2. Global name
        3. Username

        Parameters
        ----------
        user: :class:`nextcord.Member`
            The member to retrieve the display name for.

        Returns
        -------
        :class:`str`
            The display name of the member.

        .. versionadded:: 0.8.2
            The version of the Nextcord package at the time of adding this method is 2.6.0.
        """

    @overload
    @staticmethod
    def display_name(user: User) -> str:
        """Returns the display name of the user.

        Due to the bug in the `nextcord.User.display_name` property,
        this method should be used instead of it.

        The bug is that `nextcord.User.display_name` property does not return
        the global name of the user.

        Result of this method is specified using the following hierarchy:
        1. Global name
        2. Username

        Parameters
        ----------
        user: :class:`nextcord.User`
            The user to retrieve the display name for.

        Returns
        -------
        :class:`str`
            The display name of the user.

        .. versionadded:: 0.8.2
            The version of the Nextcord package at the time of adding this method is 2.6.0.
        """

    @staticmethod
    def display_name(user: User | Member) -> str:
        """Returns the display name of the user or member."""
        if isinstance(user, Member):
            return user.nick or user.global_name or user.name
        return user.global_name or user.name


class ProjectUtils(ABC):  # pylint: disable=too-few-public-methods
    """A class containing utility methods for the project.

    This class should not be instantiated.
    """

    @staticmethod
    def lines_of_code() -> int:
        """Returns the number of lines of code in the project.

        Returns
        -------
        :class:`int`
            The number of lines of code in the project.

        Notes
        -----
        This method counts lines of code in the project
        by counting lines of code in all Python files
        in the project directory except for the ones
        that are ignored by the '.gitignore' file.
        """

        try:
            with open(".gitignore", "r", encoding="utf-8") as f:
                ignored = f.read().split("\n")
        except OSError as e:
            ignored = []
            Console.warn(
                "Cannot open the '.gitignore' file to count lines of code properly.",
                exception=e,
            )

        ignored.extend([".git", ".gitignore"])
        result = [0]

        def count(path: Path, result: list[int]) -> None:
            for item in os.listdir(path):
                if item in ignored:
                    continue
                current_path = path / item
                if current_path.is_dir():
                    count(current_path, result)
                if item.endswith(".py"):
                    try:
                        with open(current_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                    except OSError as e:
                        Console.warn(
                            f"Cannot open {current_path} to count lines of code.",
                            exception=e,
                        )
                    else:
                        result[0] += len(lines)

        root_dir = Path(os.path.abspath(os.curdir))
        count(root_dir, result)
        return result[0]


_MatcherT = TypeVar("_MatcherT")
_MatcherResultT = TypeVar("_MatcherResultT")


@dataclass(slots=True)
class Matcher(Generic[_MatcherT]):
    """A class for matching items to a given value.

    All methods use `SequenceMatcher` to find the closest match to the given value.

    Attributes
    ----------
    items: :class:`list`[:class:`_MatcherT`]
        A list of items to find the closest match to the given value.
    ignore_case: :class:`bool`
        Whether to ignore the case of the items. Defaults to `False`.

    Methods
    -------
    match_max(value: `str`, key: Callable[[`_MatcherT`], `str`]) -> `Matcher.Result`[`_MatcherT`]
        Finds the closest match to the given value.
    match_all(value: `str`, key: Callable[[`_MatcherT`], `str`]) -> list[`Finder.Result`[`_MatcherT`]]
        Finds all matches to the given value.

    Examples
    --------
    Arrange the items in the `Matcher` class: ::

        @dataclass
        class TestClass:
            field: str

        cls1 = TestClass("aaaa")
        cls2 = TestClass("bbbb")
        cls3 = TestClass("cccc")
        matcher = Matcher[TestClass]([cls1, cls2, cls3])

    Find the closest match to the given value: ::

        result = matcher.match_max("cccb", key=lambda x: x.field)
        result.item  # cls3
        result.ratio # 0.75

    Find all matches to the given value: ::

        results = matcher.match_all("cccb", key=lambda x: x.field)
        results[0] # (item=cls1, ratio=0.25)
        results[1] # (item=cls2, ratio=0.8)
        results[2] # (item=cls3, ratio=0.75)
    """

    items: list[_MatcherT]
    _: KW_ONLY
    ignore_case: bool = False

    @dataclass(slots=True)
    class Result(Generic[_MatcherResultT]):
        """A class representing a result of the `Matcher` class.

        Attributes
        ----------
        item: :class:`_MatcherResultT`
            The item that was found.
        ratio: :class:`float`
            The ratio of the match.
        """

        item: _MatcherResultT
        ratio: float

    def match_max(
        self,
        value: str,
        key: Callable[[_MatcherT], str] = str,
    ) -> Matcher.Result[_MatcherT]:
        """Finds the closest match to the given value.

        This function uses `SequenceMatcher` to find
        the closest match to the given value.

        Parameters
        ----------
        value: :class:`_MatcherT`
            The value to find.
        key: Callable[[:class:`_MatcherT`], :class:`str`]
            A function to convert the items to strings. Defaults to `str`.

        Returns
        -------
        :class:`Finder.Result`[:class:`_MatcherT`]
            The closest match to the given value.
        """
        matches = self.match_all(value, key)
        return max(matches, key=lambda match: match.ratio)

    def match_all(
        self,
        value: str,
        key: Callable[[_MatcherT], str] = str,
    ) -> list[Matcher.Result[_MatcherT]]:
        """Finds all matches to the given value.

        This function uses `SequenceMatcher` to find
        all matches to the given value.

        Parameters
        ----------
        value: :class:`_MatcherT`
            The value to find.
        key: Callable[[:class:`_MatcherT`], :class:`str`]
            A function to convert the items to strings. Defaults to `str`.

        Returns
        -------
        list[:class:`Finder.Result`[:class:`_MatcherT`]]
            A list of all matches to the given value.
        """

        return [
            Matcher.Result(
                item,
                SequenceMatcher(
                    lambda i: i.isspace(),
                    value.lower() if self.ignore_case else value,
                    key(item).lower() if self.ignore_case else value,
                ).ratio(),
            )
            for item in self.items
        ]


_KeyT = TypeVar("_KeyT", bound=Hashable)
_RatioT = TypeVar("_RatioT", int, float)
_CompareMethod: TypeAlias = Callable[[_RatioT, _RatioT], bool]


class SmartDict(dict[_KeyT, _RatioT]):
    """A dictionary-like structure with smart key replacement based on comparison method.

    This class is used to store items with a key that is a hashable type.

    Attributes
    ----------
    compare_method: :class:`_CompareMethod`
        A method to compare the values.

    Examples
    --------
    Create a `SmartDict` instance: ::

        smart_dict = SmartDict[int, float](lambda x, y: x > y)

    Set the value of the key if the compare method returns `True`: ::

        smart_dict[1] = 2.0
        smart_dict[1]  # 2.0
        smart_dict[1] = 1.0
        smart_dict[1]  # 2.0 (1.0 was not set because 1.0 < 2.0)
        smart_dict[1] = 3.0
        smart_dict[1]  # 3.0 (3.0 was set because 3.0 > 2.0)
    """

    compare_method: _CompareMethod

    def __init__(self, compare_method: _CompareMethod) -> None:
        self.compare_method = compare_method

    def __setitem__(self, key: _KeyT, value: _RatioT) -> None:
        if key not in self or self.compare_method(value, self[key]):
            super().__setitem__(key, value)


async def wait_until_midnight() -> Literal[True]:
    """|coro|

    Waits until midnight and returns ``True``.

    Examples
    --------

    Run a code at midnight: ::

        async def foo():
            await wait_until_midnight()
            print("It's midnight!")

    Run a code every midnight: ::

        while await wait_until_midnight():
            print("It's midnight!")
    """

    today = dt.datetime.now()
    tomorrow = today + dt.timedelta(days=1)
    midnight = dt.datetime(
        year=tomorrow.year,
        month=tomorrow.month,
        day=tomorrow.day,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    time_until_midnight = midnight - today
    await asyncio.sleep(
        time_until_midnight.seconds + time_until_midnight.microseconds / 1_000_000
    )
    return True
