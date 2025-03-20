# SPDX-License-Identifier: MIT
"""A module provides views for the reminder UI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, override

from nextcord import ButtonStyle
from nextcord.ui import Button, Select, View, button

from university_bot import Localization
from university_bot.mixins import LocalizedViewMixin
from university_bot.mixins.localization import LocalizedMixin
from university_bot.mixins.timeout import TimeoutViewMixin

from .enums import ReminderSummaryNavigation
from ..models import RawReminder
from ...calendar import RawEvent

if TYPE_CHECKING:
    from university_bot import Interaction

    from .manager import ReminderManager
    from .payloads import ConfigReminderPayload, SummaryReminderPayload

    _RefreshFunc = Callable[[Interaction], Awaitable[None]]

__all__ = (
    "NoRemindersView",
    "AddReminderView",
    "EditReminderView",
    "CopyReminderView",
    "SummaryReminderView",
)

_loc = Localization.get_group("ui.reminder.views")


class NoRemindersView(TimeoutViewMixin, LocalizedViewMixin, View):
    """A view displayed when there are no reminders to display."""

    _manager: ReminderManager

    def __init__(self, manager: ReminderManager) -> None:
        View.__init__(self)
        TimeoutViewMixin.__init__(self, manager)
        LocalizedViewMixin.__init__(
            self, manager.locale, _loc.get_group("no_reminders")
        )
        self._manager = manager

    @LocalizedViewMixin.localized_button("buttons.add")
    @button(label="Add", style=ButtonStyle.green)
    async def _create(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_add(interaction)

    @LocalizedViewMixin.localized_button("buttons.return")
    @button(label="Return", style=ButtonStyle.gray)
    async def _return(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.go_back(interaction)


class _ReminderView(TimeoutViewMixin, LocalizedViewMixin, View, ABC):
    """A base view for handling events."""

    _manager: ReminderManager
    _raw_reminder: RawReminder

    def __init__(
        self,
        manager: ReminderManager,
        reminder: RawReminder,
    ) -> None:
        View.__init__(self)
        TimeoutViewMixin.__init__(self, manager)
        LocalizedViewMixin.__init__(self, manager.locale, _loc.get_group("reminder"))

        self._manager = manager
        self._raw_reminder = reminder

        save_btn: Button = self.children[1]  # type: ignore
        save_btn.disabled = not reminder.is_valid() or (
            reminder.is_datetime_in_past() or False
        )

        channel_select = _ChannelSelect(manager, reminder, self._refresh, row=0)
        self.add_item(channel_select)  # type: ignore

        role_select = _RoleSelect(manager, reminder, self._refresh, row=1)
        self.add_item(role_select)  # type: ignore

    @LocalizedViewMixin.localized_button("buttons.edit_properties")
    @button(label="Edit properties", style=ButtonStyle.blurple, row=2)
    async def _edit_properties(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_information_modal(
            interaction, self._raw_reminder, self._refresh
        )

    @abstractmethod
    async def _on_save(self, interaction: Interaction) -> None:
        pass

    @LocalizedViewMixin.localized_button("buttons.save")
    @button(label="Save", style=ButtonStyle.green, row=2)
    async def _save(self, _: Button[View], interaction: Interaction) -> None:
        await self._on_save(interaction)

    @LocalizedViewMixin.localized_button("buttons.cancel")
    @button(label="Cancel", style=ButtonStyle.red, row=2)
    async def _cancel(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction)

    @abstractmethod
    async def _refresh(self, interaction: Interaction) -> None:
        pass


class AddReminderView(_ReminderView):
    """A view for adding a new reminder."""

    event: RawEvent

    def __init__(
        self,
        manager: ReminderManager,
        payload: ConfigReminderPayload,
    ) -> None:
        super().__init__(manager, payload.reminder)
        assert isinstance(payload.event, RawEvent)
        self.event = payload.event

    @override
    async def _refresh(self, interaction: Interaction) -> None:
        await self._manager.show_add(interaction, self._raw_reminder)

    @override
    async def _on_save(self, interaction: Interaction) -> None:
        self.event.reminders.append(self._raw_reminder)
        content = self.get_loc(
            "messages.add.success",
            "Reminder created successfully. Remeber to save the event.",
        )
        await self._manager.show_summary(
            interaction,
            self._raw_reminder,
            content=content,
        )


class EditReminderView(_ReminderView):
    """A view for editing a reminder."""

    orig_reminder: RawReminder
    event: RawEvent

    def __init__(
        self,
        manager: ReminderManager,
        payload: ConfigReminderPayload,
    ) -> None:
        super().__init__(manager, payload.reminder)
        self.orig_reminder = payload.reminder
        assert isinstance(payload.event, RawEvent)
        self.event = payload.event

    @override
    async def _refresh(self, interaction: Interaction) -> None:
        await self._manager.show_edit(interaction, self._raw_reminder)

    @override
    async def _on_save(self, interaction: Interaction) -> None:
        self.event.reminders.remove(self.orig_reminder)
        self.event.reminders.append(self._raw_reminder)
        content = self.get_loc(
            "messages.edit.success",
            "Reminder edited successfully. Remeber to save the event.",
        )
        await self._manager.show_summary(interaction, content=content)


class CopyReminderView(_ReminderView):
    """A view for copying a reminder."""

    event: RawEvent

    def __init__(
        self,
        manager: ReminderManager,
        payload: ConfigReminderPayload,
    ) -> None:
        super().__init__(manager, payload.reminder)
        assert isinstance(payload.event, RawEvent)
        self.event = payload.event

    @override
    async def _refresh(self, interaction: Interaction) -> None:
        await self._manager.show_copy(interaction, self._raw_reminder)

    @override
    async def _on_save(self, interaction: Interaction) -> None:
        self.event.reminders.append(self._raw_reminder)
        content = self.get_loc(
            "messages.copy.success",
            "Reminder copied successfully. Remeber to save the event.",
        )
        await self._manager.show_summary(interaction, content=content)


class SummaryReminderView(TimeoutViewMixin, LocalizedViewMixin, View):
    """A view providing a navigable summary view of calendar events.

    It allows users to navigate through events using buttons for first, previous, next,
    last, and offers options to return to the menu, edit, copy, or delete events.
    """

    _manager: ReminderManager
    _payload: SummaryReminderPayload

    def __init__(
        self,
        manager: ReminderManager,
        payload: SummaryReminderPayload,
    ) -> None:
        View.__init__(self)
        TimeoutViewMixin.__init__(self, manager)
        LocalizedViewMixin.__init__(self, payload.locale, _loc.get_group("summary"))

        self._manager = manager
        self._payload = payload

        first_btn: Button = self.children[0]  # type: ignore
        previous_btn: Button = self.children[1]  # type: ignore
        first_btn.disabled = previous_btn.disabled = payload.index == 0

        next_btn: Button = self.children[2]  # type: ignore
        last_btn: Button = self.children[3]  # type: ignore
        next_btn.disabled = last_btn.disabled = payload.index == payload.total - 1

        edit_btn: Button = self.children[5]  # type: ignore
        edit_btn.disabled = payload.reminder.sent

    @button(label="<<<", style=ButtonStyle.gray, row=0)
    async def _first(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, ReminderSummaryNavigation.FIRST)

    @button(label="<", style=ButtonStyle.gray, row=0)
    async def _previous(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(
            interaction, ReminderSummaryNavigation.PREVIOUS
        )

    @button(label=">", style=ButtonStyle.gray, row=0)
    async def _next(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, ReminderSummaryNavigation.NEXT)

    @button(label=">>>", style=ButtonStyle.gray, row=0)
    async def _last(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, ReminderSummaryNavigation.LAST)

    @LocalizedViewMixin.localized_button("buttons.add")
    @button(label="Add", style=ButtonStyle.green, row=1)
    async def _add(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_add(interaction)

    @LocalizedViewMixin.localized_button("buttons.edit")
    @button(label="Edit", style=ButtonStyle.blurple, row=1)
    async def _edit(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_edit(interaction, self._payload.reminder)

    @LocalizedViewMixin.localized_button("buttons.copy")
    @button(label="Copy", style=ButtonStyle.gray, row=1)
    async def _copy(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_copy(interaction, self._payload.reminder)

    @LocalizedViewMixin.localized_button("buttons.delete")
    @button(label="Delete", style=ButtonStyle.red, row=1)
    async def _delete(self, _: Button[View], interaction: Interaction) -> None:
        reminder = self._payload.reminder
        self._payload.event.reminders.remove(reminder)

        content = self.get_loc(
            "messages.delete.success",
            "Reminder deleted successfully. Remeber to save the event.",
        )
        await self._manager.show_summary(interaction, reminder, content=content)

    @LocalizedViewMixin.localized_button("buttons.return_to_event")
    @button(label="Return to event configuration", style=ButtonStyle.gray, row=2)
    async def _return(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.go_back(interaction)


class _ChannelSelect(LocalizedMixin, Select):

    _manager: ReminderManager
    _reminder: RawReminder
    _refresh_func: _RefreshFunc

    def __init__(
        self,
        manager: ReminderManager,
        reminder: RawReminder,
        refresh_func: _RefreshFunc,
        *,
        row: int,
    ) -> None:
        LocalizedMixin.__init__(self, manager.locale, _loc.get_group("channel_select"))

        placeholder = self.get_loc("placeholder", "Choose a channel...")
        Select.__init__(  # type: ignore
            self,
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            row=row,
        )

        self._manager = manager
        self._reminder = reminder
        self._refresh_func = refresh_func

        guild = manager.service.bot.guild
        channels = manager.data.get_channels(guild) or [
            channel
            for channel in guild.text_channels
            if channel.permissions_for(guild.me).send_messages
        ]

        for channel in channels:
            self.add_option(
                label=f"#{channel.name}",
                description=channel.category.name if channel.category else None,
                value=str(channel.id),
                default=channel.id == reminder.channel_id,
            )

    @override
    async def callback(self, interaction: Interaction) -> None:
        self._reminder.channel_id = int(self.values[0])
        await self._refresh_func(interaction)


class _RoleSelect(LocalizedMixin, Select):

    _manager: ReminderManager
    _reminder: RawReminder
    _refresh_func: _RefreshFunc

    def __init__(
        self,
        manager: ReminderManager,
        reminder: RawReminder,
        refresh_func: _RefreshFunc,
        *,
        row: int,
    ) -> None:
        LocalizedMixin.__init__(self, manager.locale, _loc.get_group("role_select"))

        guild = manager.service.bot.guild
        roles = manager.data.get_roles(guild)
        placeholder = self.get_loc("placeholder", "Choose roles...")

        Select.__init__(  # type: ignore
            self,
            placeholder=placeholder,
            min_values=0,
            max_values=min(25, len(roles)),
            row=row,
        )

        self._manager = manager
        self._reminder = reminder
        self._refresh_func = refresh_func

        members_lbl = self.get_loc("members", "Members")
        for role in roles:
            self.add_option(
                label=f"@{role.name}",
                description=f"{members_lbl}: {len(role.members)}",
                value=str(role.id),
                default=role.id in reminder.role_ids,
            )

    @override
    async def callback(self, interaction: Interaction) -> None:
        self._reminder.role_ids = [int(i) for i in self.values]
        await self._refresh_func(interaction)
