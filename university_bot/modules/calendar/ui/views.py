# SPDX-License-Identifier: MIT
"""A module provides views for the calendar UI."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, override

from nextcord import ButtonStyle
from nextcord.ui import Button, View, button

from university_bot import Localization
from university_bot.mixins import LocalizedViewMixin
from university_bot.mixins.timeout import TimeoutViewMixin

from .enums import EventSummaryNavigation

if TYPE_CHECKING:
    from university_bot import Interaction

    from .manager import CalendarManager
    from .payloads import (
        CopyEventPayload,
        CreateEventPayload,
        EditEventPayload,
        SummaryEventPayload,
    )
    from ..models import RawEvent

__all__ = (
    "NoEventsView",
    "CreateEventView",
    "EditEventView",
    "CopyEventView",
    "SummaryEventView",
)

_loc = Localization.get_group("ui.calendar.views")


class NoEventsView(TimeoutViewMixin, LocalizedViewMixin, View):
    """A view displayed when there are no events to display."""

    _manager: CalendarManager

    def __init__(self, manager: CalendarManager) -> None:
        View.__init__(self)
        TimeoutViewMixin.__init__(self, manager)
        LocalizedViewMixin.__init__(self, manager.locale, _loc.get_group("no_events"))
        self._manager = manager

    @LocalizedViewMixin.localized_button("buttons.create")
    @button(label="Create", style=ButtonStyle.green)
    async def _create(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_create(interaction)


class _EventView(TimeoutViewMixin, LocalizedViewMixin, View, ABC):
    """A base view for handling events."""

    _manager: CalendarManager
    _raw_event: RawEvent

    def __init__(
        self,
        manager: CalendarManager,
        raw_event: RawEvent,
    ) -> None:
        View.__init__(self)
        TimeoutViewMixin.__init__(self, manager)
        LocalizedViewMixin.__init__(self, manager.locale, _loc.get_group("event"))

        self._manager = manager
        self._raw_event = raw_event

        event_valid = raw_event.is_valid()

        reminder_cog_enabled = manager.bot.get_cog("ReminderCog") is not None
        reminder_btn: Button = self.children[1]  # type: ignore
        reminder_btn.disabled = not reminder_cog_enabled or not event_valid

        hide_show_btn: Button = self.children[2]  # type: ignore
        self._set_hide_show_btn_label(hide_show_btn)  # type: ignore

        save_btn: Button = self.children[3]  # type: ignore
        save_btn.disabled = not event_valid

    @LocalizedViewMixin.localized_button("buttons.properties")
    @button(label="Properties", style=ButtonStyle.blurple, row=0)
    async def _properties(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_information_modal(
            interaction, self._raw_event, self._refresh
        )

    @LocalizedViewMixin.localized_button("buttons.reminders")
    @button(label="Reminders", style=ButtonStyle.gray, row=0, disabled=True)
    async def _reminders(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_reminder_manager(
            interaction, self._raw_event, self._refresh
        )

    @button(label="Hide/Show", style=ButtonStyle.gray, row=0)
    async def _hide_show(self, btn: Button[View], interaction: Interaction) -> None:
        self._raw_event.is_hidden ^= True
        self._set_hide_show_btn_label(btn)
        await self._refresh(interaction)

    @abstractmethod
    async def _on_save(self, interaction: Interaction) -> None:
        pass

    @LocalizedViewMixin.localized_button("buttons.save")
    @button(label="Save", style=ButtonStyle.green, row=1)
    async def _save(self, _: Button[View], interaction: Interaction) -> None:
        await self._on_save(interaction)

    @LocalizedViewMixin.localized_button("buttons.cancel")
    @button(label="Cancel", style=ButtonStyle.red, row=1)
    async def _cancel(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction)

    def _set_hide_show_btn_label(self, btn: Button[View]) -> None:
        if self._raw_event.is_hidden:
            btn.label = self.get_loc("buttons.show", "Show")
        else:
            btn.label = self.get_loc("buttons.hide", "Hide")

    @abstractmethod
    async def _refresh(self, interaction: Interaction) -> None:
        pass


class CreateEventView(_EventView):
    """A view for creating a new event."""

    def __init__(
        self,
        manager: CalendarManager,
        payload: CreateEventPayload,
    ) -> None:
        super().__init__(manager, payload.event)

    @override
    async def _refresh(self, interaction: Interaction) -> None:
        await self._manager.show_create(interaction, self._raw_event)

    @override
    async def _on_save(self, interaction: Interaction) -> None:
        event = self._raw_event.to_event(id_=None)
        await self._manager.handler.service.add_event(event)
        await self._manager.update_reminders(event.id, self._raw_event)

        content = self.get_loc("messages.create.success", "Event created successfully.")
        await asyncio.gather(
            self._manager.show_summary(interaction, event, content=content),
            self._manager.attempt_refresh_calendar(),
        )


class EditEventView(_EventView):
    """A view for editing an event."""

    _event_id: str

    def __init__(
        self,
        manager: CalendarManager,
        payload: EditEventPayload,
    ) -> None:
        super().__init__(manager, payload.event)
        self._event_id = payload.event_id

    @override
    async def _refresh(self, interaction: Interaction) -> None:
        await self._manager.show_edit(interaction, self._event_id, self._raw_event)

    @override
    async def _on_save(self, interaction: Interaction) -> None:
        event = self._raw_event.to_event(self._event_id)
        await self._manager.handler.service.update_event(event.id, self._raw_event)
        await self._manager.update_reminders(event.id, self._raw_event)

        content = self.get_loc("messages.edit.success", "Event edited successfully.")
        await asyncio.gather(
            self._manager.show_summary(interaction, event, content=content),
            self._manager.attempt_refresh_calendar(),
        )


class CopyEventView(_EventView):
    """A view for copying an event."""

    def __init__(
        self,
        manager: CalendarManager,
        payload: CopyEventPayload,
    ) -> None:
        super().__init__(manager, payload.event)

    @override
    async def _refresh(self, interaction: Interaction) -> None:
        await self._manager.show_copy(interaction, self._raw_event)

    @override
    async def _on_save(self, interaction: Interaction) -> None:
        event = self._raw_event.to_event(id_=None)
        await self._manager.handler.service.add_event(event)
        await self._manager.update_reminders(event.id, self._raw_event)

        content = self.get_loc("messages.copy.success", "Event copied successfully.")
        await asyncio.gather(
            self._manager.show_summary(interaction, event, content=content),
            self._manager.attempt_refresh_calendar(),
        )


class SummaryEventView(TimeoutViewMixin, LocalizedViewMixin, View):
    """A view providing a navigable summary view of calendar events.

    It allows users to navigate through events using buttons for first, previous, next,
    last, and offers options to create, edit, copy, or delete events.
    """

    _manager: CalendarManager
    _payload: SummaryEventPayload

    def __init__(self, manager: CalendarManager, payload: SummaryEventPayload) -> None:
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

    @button(label="<<<", style=ButtonStyle.gray, row=0)
    async def _first(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, EventSummaryNavigation.FIRST)

    @button(label="<", style=ButtonStyle.gray, row=0)
    async def _previous(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, EventSummaryNavigation.PREVIOUS)

    @button(label=">", style=ButtonStyle.gray, row=0)
    async def _next(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, EventSummaryNavigation.NEXT)

    @button(label=">>>", style=ButtonStyle.gray, row=0)
    async def _last(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, EventSummaryNavigation.LAST)

    @LocalizedViewMixin.localized_button("buttons.create")
    @button(label="Create", style=ButtonStyle.green, row=1)
    async def _new(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_create(interaction)

    @LocalizedViewMixin.localized_button("buttons.edit")
    @button(label="Edit", style=ButtonStyle.blurple, row=1)
    async def _edit(self, _: Button[View], interaction: Interaction) -> None:
        event_id = self._payload.event.id
        raw_event = self._payload.raw_event
        await self._manager.show_edit(interaction, event_id, raw_event)

    @LocalizedViewMixin.localized_button("buttons.copy")
    @button(label="Copy", style=ButtonStyle.gray, row=1)
    async def _copy(self, _: Button[View], interaction: Interaction) -> None:
        raw_event = self._payload.raw_event
        await self._manager.show_copy(interaction, raw_event)

    @LocalizedViewMixin.localized_button("buttons.delete")
    @button(label="Delete", style=ButtonStyle.red, row=1)
    async def _delete(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.handler.service.delete_event(self._payload.event)

        content = self.get_loc("messages.delete.success", "Event deleted successfully.")
        await asyncio.gather(
            self._manager.show_summary(
                interaction, self._payload.event, content=content
            ),
            self._manager.attempt_refresh_calendar(),
        )
