# SPDX-License-Identifier: MIT
"""A module provides views for the calendar UI."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, override

from nextcord import ButtonStyle
from nextcord.ui import Button, View, button

from university_bot import Localization, get_logger
from university_bot.mixins import LocalizedViewMixin
from university_bot.mixins.timeout import TimeoutViewMixin

from .enums import EventSummaryNavigation
from ..models import RawEvent

if TYPE_CHECKING:
    from university_bot import Interaction

    from .managers import CalendarMenuViewManager
    from .payloads import (
        AddEventPayload,
        CopyEventPayload,
        EditEventPayload,
        SummaryEventPayload,
    )

__all__ = (
    "CalendarMenuView",
    "AddEventView",
    "EditEventView",
    "CopyEventView",
    "SummaryEventView",
)

_loc = Localization.get_group("ui.calendar.views")
_logger = get_logger(__name__)


class CalendarMenuView(TimeoutViewMixin, LocalizedViewMixin, View):
    """A view representing the calendar menu.

    This view provides buttons for adding events and viewing a summary.
    """

    _manager: CalendarMenuViewManager

    def __init__(
        self,
        manager: CalendarMenuViewManager,
        *,
        summary_btn_disabled: bool,
    ) -> None:
        View.__init__(self)
        TimeoutViewMixin.__init__(self, manager)
        LocalizedViewMixin.__init__(self, manager.locale, _loc.get_group("menu"))
        self._manager = manager

        summary_btn: Button = self.children[1]  # type: ignore
        summary_btn.disabled = summary_btn_disabled

    @LocalizedViewMixin.localized_button("buttons.add_event")
    @button(label="Add event", style=ButtonStyle.primary)
    async def _add_event(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_add_event(interaction)

    @LocalizedViewMixin.localized_button("buttons.summary")
    @button(label="Summary", style=ButtonStyle.secondary)
    async def _summary(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction)


class _EventView(TimeoutViewMixin, LocalizedViewMixin, View, ABC):
    """A base view for handling events."""

    _manager: CalendarMenuViewManager
    _raw_event: RawEvent

    def __init__(
        self,
        manager: CalendarMenuViewManager,
        raw_event: RawEvent,
    ) -> None:
        View.__init__(self)
        TimeoutViewMixin.__init__(self, manager)
        LocalizedViewMixin.__init__(self, manager.locale, _loc.get_group("event"))

        self._manager = manager
        self._raw_event = raw_event

        hide_show_btn: Button = self.children[2]  # type: ignore
        self._set_hide_show_btn_label(hide_show_btn)  # type: ignore

        save_btn: Button = self.children[3]  # type: ignore
        save_btn.disabled = not raw_event.is_valid()

    @LocalizedViewMixin.localized_button("buttons.information")
    @button(label="Information", style=ButtonStyle.blurple)
    async def _information(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_information_modal(
            interaction, self._raw_event, self._refresh
        )

    @LocalizedViewMixin.localized_button("buttons.reminder")
    @button(label="Reminder", style=ButtonStyle.gray, disabled=True)
    async def _reminder(self, _: Button[View], interaction: Interaction) -> None:
        _logger.error("Reminder not implemented yet.")

    @button(label="Hide/Show", style=ButtonStyle.gray)
    async def _hide_show(self, btn: Button[View], interaction: Interaction) -> None:
        self._raw_event.is_hidden ^= True
        self._set_hide_show_btn_label(btn)
        await self._refresh(interaction)

    @abstractmethod
    async def _on_save(self, interaction: Interaction) -> None:
        pass

    @LocalizedViewMixin.localized_button("buttons.save")
    @button(label="Save", style=ButtonStyle.green)
    async def _save(self, _: Button[View], interaction: Interaction) -> None:
        await self._on_save(interaction)

    @abstractmethod
    async def _on_cancel(self, interaction: Interaction) -> None:
        pass

    @LocalizedViewMixin.localized_button("buttons.cancel")
    @button(label="Cancel", style=ButtonStyle.red)
    async def _cancel(self, _: Button[View], interaction: Interaction) -> None:
        await self._on_cancel(interaction)

    def _set_hide_show_btn_label(self, btn: Button[View]) -> None:
        if self._raw_event.is_hidden:
            btn.label = self.get_loc("buttons.show", "Show")
        else:
            btn.label = self.get_loc("buttons.hide", "Hide")

    @abstractmethod
    async def _refresh(self, interaction: Interaction) -> None:
        pass


class AddEventView(_EventView):
    """A view for adding a new event."""

    def __init__(
        self,
        manager: CalendarMenuViewManager,
        payload: AddEventPayload,
    ) -> None:
        super().__init__(manager, payload.raw_event)

    @override
    async def _refresh(self, interaction: Interaction) -> None:
        await self._manager.show_add_event(interaction, self._raw_event)

    @override
    async def _on_save(self, interaction: Interaction) -> None:
        event = self._raw_event.to_event(id_=None)
        await self._manager.handler.service.add_event(event)

        content = self.get_loc("messages.add.success", "Event added successfully.")
        await asyncio.gather(
            self._manager.show_summary(interaction, event, content=content),
            self._manager.attempt_refresh_calendar(),
        )

    @override
    async def _on_cancel(self, interaction: Interaction) -> None:
        await self._manager.show_menu(interaction)


class EditEventView(_EventView):
    """A view for editing an event."""

    _event_id: str

    def __init__(
        self,
        manager: CalendarMenuViewManager,
        payload: EditEventPayload,
    ) -> None:
        super().__init__(manager, payload.raw_event)
        self._event_id = payload.event_id

    @override
    async def _refresh(self, interaction: Interaction) -> None:
        await self._manager.show_edit_event(
            interaction, self._event_id, self._raw_event
        )

    @override
    async def _on_save(self, interaction: Interaction) -> None:
        event = self._raw_event.to_event(self._event_id)
        await self._manager.handler.service.update_event(event.id, self._raw_event)

        content = self.get_loc("messages.edit.success", "Event edited successfully.")
        await asyncio.gather(
            self._manager.show_summary(interaction, event, content=content),
            self._manager.attempt_refresh_calendar(),
        )

    @override
    async def _on_cancel(self, interaction: Interaction) -> None:
        await self._manager.show_summary(interaction)


class CopyEventView(_EventView):
    """A view for copying an event."""

    def __init__(
        self,
        manager: CalendarMenuViewManager,
        payload: CopyEventPayload,
    ) -> None:
        super().__init__(manager, payload.raw_event)

    @override
    async def _refresh(self, interaction: Interaction) -> None:
        await self._manager.show_copy_event(interaction, self._raw_event)

    @override
    async def _on_save(self, interaction: Interaction) -> None:
        event = self._raw_event.to_event(id_=None)
        await self._manager.handler.service.add_event(event)

        content = self.get_loc("messages.copy.success", "Event copied successfully.")
        await asyncio.gather(
            self._manager.show_summary(interaction, event, content=content),
            self._manager.attempt_refresh_calendar(),
        )

    @override
    async def _on_cancel(self, interaction: Interaction) -> None:
        await self._manager.show_summary(interaction)


class SummaryEventView(TimeoutViewMixin, LocalizedViewMixin, View):
    """A view providing a navigable summary view of calendar events.

    It allows users to navigate through events using buttons for first, previous, next,
    last, and offers options to return to the menu, edit, copy, or delete events.
    """

    _manager: CalendarMenuViewManager
    _payload: SummaryEventPayload

    def __init__(
        self, manager: CalendarMenuViewManager, payload: SummaryEventPayload
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

    @button(label="<<<", style=ButtonStyle.gray)
    async def _first(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, EventSummaryNavigation.FIRST)

    @button(label="<", style=ButtonStyle.gray)
    async def _previous(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, EventSummaryNavigation.PREVIOUS)

    @button(label=">", style=ButtonStyle.gray)
    async def _next(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, EventSummaryNavigation.NEXT)

    @button(label=">>>", style=ButtonStyle.gray)
    async def _last(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_summary(interaction, EventSummaryNavigation.LAST)

    @LocalizedViewMixin.localized_button("buttons.return")
    @button(label="Return", style=ButtonStyle.gray)
    async def _return(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.show_menu(interaction)

    @LocalizedViewMixin.localized_button("buttons.edit")
    @button(label="Edit", style=ButtonStyle.blurple)
    async def _edit(self, _: Button[View], interaction: Interaction) -> None:
        event_id = self._payload.event.id
        raw_event = self._payload.raw_event
        await self._manager.show_edit_event(interaction, event_id, raw_event)

    @LocalizedViewMixin.localized_button("buttons.copy")
    @button(label="Copy", style=ButtonStyle.green)
    async def _copy(self, _: Button[View], interaction: Interaction) -> None:
        raw_event = self._payload.raw_event
        await self._manager.show_copy_event(interaction, raw_event)

    @LocalizedViewMixin.localized_button("buttons.delete")
    @button(label="Delete", style=ButtonStyle.red)
    async def _delete(self, _: Button[View], interaction: Interaction) -> None:
        await self._manager.handler.service.delete_event(self._payload.event)

        content = self.get_loc("messages.delete.success", "Event deleted successfully.")
        await asyncio.gather(
            self._manager.show_summary(
                interaction, self._payload.event, content=content
            ),
            self._manager.attempt_refresh_calendar(),
        )
