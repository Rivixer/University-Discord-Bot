# SPDX-License-Identifier: MIT
"""A module providing managers for the calendar UI."""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, overload, override

from nextcord.utils import MISSING

from university_bot.mixins.timeout import TimeoutManagerMixin

from .embeds import (
    AddReminderEmbed,
    CopyReminderEmbed,
    EditReminderEmbed,
    NoRemindersEmbed,
    ReminderEmbed,
    SummaryReminderEmbed,
)
from .enums import ReminderSummaryNavigation
from .modals import ReminderInformationModal
from .payloads import (
    ConfigReminderPayload,
    ReminderInformationModalPayload,
    SummaryReminderPayload,
)
from .views import (
    AddReminderView,
    CopyReminderView,
    EditReminderView,
    NoRemindersView,
    SummaryReminderView,
)
from ..models import RawReminder

if TYPE_CHECKING:
    from nextcord import Embed, Locale
    from nextcord.ui import View

    from university_bot import Interaction
    from university_bot.mixins.timeout import TimeoutViewMixin

    from ..config import ReminderDataConfig
    from ..handler import ReminderService
    from ..service import ReminderService
    from ...calendar import CalendarDataConfig, RawEvent
    from ...calendar.ui import CalendarManager

    _RefreshFunc = Callable[[Interaction], Awaitable[None]]

__all__ = ("ReminderManager",)


class ReminderManager(TimeoutManagerMixin):

    service: ReminderService
    event: RawEvent
    guild_id: int
    _reminder_index: int
    _back_method: _RefreshFunc

    def __init__(
        self,
        calendar_manager: CalendarManager,
        event: RawEvent,
        back_method: _RefreshFunc,
    ) -> None:
        self.calendar_manager = calendar_manager

        if calendar_manager.reminder_cog is None:
            raise ValueError("Reminder cog is not loaded.")

        self.service = calendar_manager.reminder_cog.service
        self.event = event
        self.guild_id = calendar_manager.bot.guild.id
        self._reminder_index = 0
        self._back_method = back_method

    @property
    def locale(self) -> Locale:
        """:class:`nextcord.Locale``: The locale of the interaction."""
        return self.calendar_manager.locale

    @property
    def data(self) -> ReminderDataConfig:
        """:class:`.ReminderDataConfig``: The reminder data configuration."""
        return self.service.data

    @property
    def calendar_data(self) -> CalendarDataConfig:
        """:class:`.CalendarDataConfig``: The calendar data configuration."""
        return self.calendar_manager.data

    @overload
    async def edit_message(
        self,
        *,
        embed: Embed | None,
        view: View | None,
        content: str | None = None,
    ) -> None:
        """|coro|

        Edits the message with the provided embed, view and content.

        Parameters
        ----------
        embed: :class:`nextcord.Embed` | `None`
            The embed to edit the message with.
        view: :class:`nextcord.ui.View` | `None`
            The view to edit the message with.
        content: :class:`str` | `None`
            The content to edit the message with. Defaults to ``None``.
        """

    @overload
    async def edit_message(
        self,
        *,
        embeds: list[Embed],
        view: View | None,
        content: str | None = None,
    ) -> None:
        """|coro|

        Edits the message with the provided embeds, view and content.

        Parameters
        ----------
        embed: list[:class:`nextcord.Embed`]
            The embeds to edit the message with.
        view: :class:`nextcord.ui.View` | `None`
            The view to edit the message with.
        content: :class:`str` | `None`
            The content to edit the message with. Defaults to ``None``.
        """

    async def edit_message(
        self,
        *,
        embed: Embed | None = MISSING,
        embeds: list[Embed] = MISSING,
        view: View | None = MISSING,
        content: str | None = None,
    ) -> None:
        """|coro|

        Edits the message with the provided embed(s), view and content.
        """
        if embeds is not MISSING:
            await self.calendar_manager.edit_message(
                embeds=embeds, view=view, content=content
            )
        else:
            await self.calendar_manager.edit_message(
                embed=embed, view=view, content=content
            )

    @override
    async def on_timeout(self, view: View | TimeoutViewMixin) -> None:
        """|coro|

        Handles the timeout of the view.

        If the view that timed out is the current view,
        the timeout embed is shown.

        Parameters
        ----------
        view: :class:`nextcord.ui.View`
            The view that timed out.
        """
        await self.calendar_manager.on_timeout(view)

    async def go_back(self, interaction: Interaction) -> None:
        """|coro|

        Returns to the previous view.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        """
        await self._back_method(interaction)

    @overload
    async def show_summary(
        self,
        interaction: Interaction,
        *,
        content: str | None = None,
    ) -> None:
        """|coro|

        Displays the reminders summary.

        This method displays the summary based on the last reminder that was shown.
        If no reminder has been shown yet or the previous reminder cannot be found,
        the first reminder is displayed.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        content: :class:`str`| `None`
            The content of the message. Defaults to ``None``.
        """

    @overload
    async def show_summary(
        self,
        interaction: Interaction,
        reminder: RawReminder,
        *,
        content: str | None = None,
    ) -> None:
        """|coro|

        Displays the reminders summary.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        reminder: :class:`.RawReminder`
            The reminder to display.
        content: :class:`str`| `None`
            The content of the message. Defaults to ``None``.
        """

    @overload
    async def show_summary(
        self,
        interaction: Interaction,
        reminder: ReminderSummaryNavigation,
    ) -> None:
        """|coro|

        Displays the reminders summary.

        This method uses the provided navigation type
        to determine which reminder to display.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        reminder: :class:`.EventSummaryNavigation`
            The navigation directive indicating which reminder to display.
        """

    async def show_summary(
        self,
        interaction: Interaction,
        reminder: ReminderSummaryNavigation | RawReminder | None = None,
        content: str | None = None,
    ) -> None:
        """|coro|

        Shows the reminders summary.
        """
        self.calendar_manager.update_locale(interaction)
        reminders = self.event.reminders

        if not reminders:
            embed = NoRemindersEmbed(
                self.locale, self.data, self.calendar_data, self.event
            )
            view = NoRemindersView(self)
            await self.edit_message(embed=embed, view=view, content=content)
            return

        index = self._reminder_index
        if isinstance(reminder, ReminderSummaryNavigation):
            match reminder:
                case ReminderSummaryNavigation.FIRST:
                    index = 0
                case ReminderSummaryNavigation.PREVIOUS:
                    index -= 1
                case ReminderSummaryNavigation.NEXT:
                    index += 1
                case ReminderSummaryNavigation.LAST:
                    index = len(reminders) - 1

        if not isinstance(reminder, RawReminder):
            try:
                reminder = reminders[index]
            except IndexError:
                reminder = reminders[index := 0]

        if reminder not in reminders:
            index = min(max(0, index), len(reminders) - 1)
            reminder = reminders[index]

        if reminder not in reminders:
            reminder = reminders[index := 0]

        self._reminder_index = index

        payload = SummaryReminderPayload(
            reminder=reminder,
            event=self.event,
            service=self.service,
            index=index,
            total=len(reminders),
            locale=self.locale,
            guild_id=self.guild_id,
        )

        embeds: list[Embed] = [
            ReminderEmbed.create(payload),
            SummaryReminderEmbed(payload),
        ]

        view = SummaryReminderView(self, payload)
        await self.edit_message(embeds=embeds, view=view, content=content)

    @overload
    async def show_add(
        self,
        interaction: Interaction,
        *,
        content: str | None = None,
    ) -> None:
        """|coro|

        Displays the add reminder view.

        This method displays the add reminder view with default values.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        content: :class:`str`| `None`
            The content of the message. Defaults to ``None``.
        """

    @overload
    async def show_add(
        self,
        interaction: Interaction,
        reminder: RawReminder,
        content: str | None = None,
    ) -> None:
        """|coro|

        Displays the add reminder view.

        This method displays the add reminder view with the provided raw reminder.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        reminder: :class:`.RawReminder`
            The raw reminder to display.
        """

    async def show_add(
        self,
        interaction: Interaction,
        reminder: RawReminder | None = None,
        content: str | None = None,
    ) -> None:
        """|coro|

        Shows the add reminder view.
        """
        self.calendar_manager.update_locale(interaction)

        if reminder is None:
            reminder = RawReminder.default(self.calendar_manager.data)
            reminder.description = self.event.description

            if date := self.event.parsed_date:
                reminder.date = self.calendar_data.format_input_date(
                    date - datetime.timedelta(days=1)
                )

                if time := self.event.parsed_time:
                    reminder.time = self.calendar_data.format_input_time(time)
                else:
                    reminder.time = "00:00"

        payload = ConfigReminderPayload(
            reminder=reminder,
            event=self.event,
            service=self.service,
            locale=self.locale,
            guild_id=self.guild_id,
        )

        embeds: list[Embed] = [
            ReminderEmbed.create(payload),
            AddReminderEmbed(payload),
        ]

        view = AddReminderView(self, payload)
        await self.edit_message(embeds=embeds, view=view, content=content)

    async def show_edit(
        self,
        interaction: Interaction,
        reminder: RawReminder,
        content: str | None = None,
    ) -> None:
        self.calendar_manager.update_locale(interaction)

        payload = ConfigReminderPayload(
            reminder=reminder,
            event=self.event,
            service=self.service,
            locale=self.locale,
            guild_id=self.guild_id,
        )

        embeds: list[Embed] = [
            ReminderEmbed.create(payload),
            EditReminderEmbed(payload),
        ]

        view = EditReminderView(self, payload)
        await self.edit_message(embeds=embeds, view=view, content=content)

    async def show_copy(
        self,
        interaction: Interaction,
        reminder: RawReminder,
        content: str | None = None,
    ) -> None:
        self.calendar_manager.update_locale(interaction)

        reminder = RawReminder(
            self.calendar_manager.data,
            date=reminder.date,
            time=reminder.time,
            description=reminder.description,
            additional_info=reminder.additional_info,
            channel_id=reminder.channel_id,
            role_ids=reminder.role_ids,
            message_id=None,
        )

        payload = ConfigReminderPayload(
            reminder=reminder,
            event=self.event,
            service=self.service,
            locale=self.locale,
            guild_id=self.guild_id,
        )

        embeds: list[Embed] = [
            ReminderEmbed.create(payload),
            CopyReminderEmbed(payload),
        ]

        view = CopyReminderView(self, payload)
        await self.edit_message(embeds=embeds, view=view, content=content)

    async def show_information_modal(
        self,
        interaction: Interaction,
        reminder: RawReminder,
        refresh_method: _RefreshFunc,
    ) -> None:
        """|coro|

        Shows the reminder information modal.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        reminder: :class:`.RawReminder`
            The raw reminder to display.
        refresh_method: Callable[[:class:`nextcord.Interaction`], Awaitable[`None`]]
            The method to call to refresh the embed after the modal is submitted.
        """
        self.calendar_manager.update_locale(interaction)
        payload = ReminderInformationModalPayload(
            reminder,
            self.locale,
            self.calendar_manager.data,
            refresh_method,
        )
        modal = ReminderInformationModal(self, payload)
        await interaction.response.send_modal(modal)
