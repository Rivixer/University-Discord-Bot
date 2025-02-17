# SPDX-License-Identifier: MIT
"""A module providing managers for the calendar UI."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, overload, override

from nextcord import HTTPException, Locale

from university_bot import ResourceFetchFailed
from university_bot.mixins.timeout import TimeoutManagerMixin
from university_bot.ui import TimeoutMenuEmbed

from .embeds import (
    AddEventEmbed,
    CalendarMenuEmbed,
    CopyEventEmbed,
    EditEventEmbed,
    SummaryEventEmbed,
)
from .enums import EventSummaryNavigation
from .modals import EventInformationModal
from .payloads import (
    AddEventPayload,
    CopyEventPayload,
    EditEventPayload,
    EventInformationModalPayload,
    SummaryEventPayload,
)
from .views import (
    AddEventView,
    CalendarMenuView,
    CopyEventView,
    EditEventView,
    SummaryEventView,
)
from ..enums import EventVisibility
from ..models import Event, RawEvent

if TYPE_CHECKING:
    from nextcord import Embed, Message
    from nextcord.ui import View

    from university_bot import Interaction
    from university_bot.mixins.timeout import TimeoutViewMixin

    from ..config import CalendarDataConfig
    from ..handler import CalendarHandler

    _RefreshFunc = Callable[[Interaction], Awaitable[None]]

__all__ = ("CalendarMenuViewManager",)


@dataclass(slots=True)
class _MenuSummaryData:
    event: Event | None = field(default=None)
    index: int = field(default=0)


class CalendarMenuViewManager(TimeoutManagerMixin):
    """A manager for the calendar menu view.

    Attributes
    ----------
    handler: :class:`.CalendarHandler`
        The calendar handler.
    locale: :class:`nextcord.Locale`
        The locale of the interaction.
    """

    __slots__ = (
        "handler",
        "locale",
        "_message",
        "_summary_data",
        "_view",
    )

    handler: CalendarHandler
    locale: Locale
    _message: Message
    _summary_data: _MenuSummaryData
    _view: View | None

    def __init__(
        self,
        handler: CalendarHandler,
        locale: Locale,
        message: Message,
    ) -> None:
        self.handler = handler
        self.locale = locale
        self._message = message
        self._summary_data = _MenuSummaryData()
        self._view = None

    @classmethod
    async def create_and_send(cls, handler: CalendarHandler, interaction: Interaction):
        """|coro|

        Creates a new manager and sends the calendar menu.

        Should be used as an entry point for the calendar menu.

        Parameters
        ----------
        handler: :class:`.CalendarHandler`
            The calendar handler.
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the calendar menu.

        Returns
        -------
        :class:`.CalendarMenuViewManager`
            The created manager.
        """
        self = cls(handler, Locale(interaction.locale), None)  # type: ignore

        events = await self.handler.service.get_sorted_events(EventVisibility.ALL)
        embed = CalendarMenuEmbed(self.locale, self.config)
        view = CalendarMenuView(self, summary_btn_disabled=not bool(events))

        partial_message = await interaction.response.send_message(
            embed=embed, view=view, ephemeral=True
        )

        self._message = await partial_message.fetch()
        self._view = view

        return self

    @property
    def config(self) -> CalendarDataConfig:
        """The calendar data configuration."""
        return self.handler.service.data

    def _update_locale(self, interaction: Interaction) -> None:
        self.locale = Locale(interaction.locale)

    async def edit_message(
        self,
        embed: Embed | None,
        view: View | None,
        content: str | None = None,
    ):
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
        if self._view:
            self._view.stop()
        self._view = view
        await self._message.edit(content=content, embed=embed, view=view)

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
        if self._view is view:
            embed = TimeoutMenuEmbed(self.locale)
            await self.edit_message(embed, None)

    async def attempt_refresh_calendar(self) -> None:
        """|coro|

        Attempts to refresh the calendar.

        If the refresh fails, the exception is caught and ignored.
        """
        try:
            await self.handler.service.refresh_message(self.handler)
        except (ResourceFetchFailed, HTTPException):
            pass

    async def show_menu(
        self,
        interaction: Interaction,
        content: str | None = None,
        *,
        summary_btn_disabled: bool | None = None,
    ) -> None:
        """|coro|

        Displays the calendar menu.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        content: :class:`str` | `None`
            The content of the message. Defaults to ``None``.
        summary_btn_disabled: :class:`bool` | `None`
            Whether the summary button should be disabled.
            If ``None`` (default), this method will attempt to determine the value
            by retrieving the events.
        """
        self._update_locale(interaction)

        if summary_btn_disabled is None:
            events = await self.handler.service.get_sorted_events(EventVisibility.ALL)
            summary_btn_disabled = not bool(events)

        embed = CalendarMenuEmbed(self.locale, self.config)
        view = CalendarMenuView(self, summary_btn_disabled=summary_btn_disabled)
        await self.edit_message(embed, view, content)

    @overload
    async def show_summary(
        self,
        interaction: Interaction,
        *,
        content: str | None = None,
    ) -> None:
        """|coro|

        Displays the events summary.

        This method displays the summary based on the last event that was shown.
        If no event has been shown yet or the previous event cannot be found,
        the first event is displayed.

        If there is no events to display, the menu is shown instead.

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
        event: Event,
        *,
        content: str | None = None,
    ) -> None:
        """|coro|

        Displays the events summary.

        If there is no events to display, the menu is shown instead.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        event: :class:`.Event`
            The event to display.
        content: :class:`str`| `None`
            The content of the message. Defaults to ``None``.
        """

    @overload
    async def show_summary(
        self, interaction: Interaction, event: EventSummaryNavigation
    ) -> None:
        """|coro|

        Displays the events summary.

        This method uses the provided navigation type
        to determine which event to display.

        If there is no events to display, the menu is shown instead.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        event: :class:`.EventSummaryNavigation`
            The navigation directive indicating which event to display.
        """

    async def show_summary(
        self,
        interaction: Interaction,
        event: EventSummaryNavigation | Event | None = None,
        content: str | None = None,
    ) -> None:
        """|coro|

        Shows the events summary.
        """
        self._update_locale(interaction)
        events = await self.handler.service.get_sorted_events(EventVisibility.ALL)

        if not events:
            return await self.show_menu(interaction, content, summary_btn_disabled=True)

        if isinstance(event, EventSummaryNavigation):
            match event:
                case EventSummaryNavigation.FIRST:
                    event = events[0]
                case EventSummaryNavigation.PREVIOUS:
                    if self._summary_data.event:
                        event_index = events.index(self._summary_data.event)
                        event = events[event_index - 1]
                case EventSummaryNavigation.NEXT:
                    if self._summary_data.event:
                        event_index = events.index(self._summary_data.event)
                        event = events[event_index + 1]
                case EventSummaryNavigation.LAST:
                    event = events[-1]

        if not isinstance(event, Event):
            event = self._summary_data.event

        if event not in events:
            event = events[min(max(0, self._summary_data.index), len(events) - 1)]
        if event not in events:
            event = events[0]

        event_index = events.index(event)
        self._summary_data.event = event
        self._summary_data.index = event_index

        payload = SummaryEventPayload(
            event,
            event_index,
            len(events),
            self.locale,
            self.config,
        )

        embed = SummaryEventEmbed(payload)
        view = SummaryEventView(self, payload)
        await self.edit_message(embed, view, content)

    @overload
    async def show_add_event(
        self,
        interaction: Interaction,
        *,
        content: str | None = None,
    ) -> None:
        """|coro|

        Displays the add event view.

        This method displays the add event view with default values.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        content: :class:`str`| `None`
            The content of the message. Defaults to ``None``.
        """

    @overload
    async def show_add_event(
        self,
        interaction: Interaction,
        raw_event: RawEvent,
        content: str | None = None,
    ) -> None:
        """|coro|

        Displays the add event view.

        This method displays the add event view with the provided raw event.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        raw_event: :class:`.RawEvent`
            The raw event to display.
        """

    async def show_add_event(
        self,
        interaction: Interaction,
        raw_event: RawEvent | None = None,
        content: str | None = None,
    ) -> None:
        """|coro|

        Shows the add event view.
        """
        self._update_locale(interaction)
        if raw_event is None:
            raw_event = RawEvent(self.config)

        payload = AddEventPayload(raw_event, self.locale, self.config)
        embed = AddEventEmbed(payload)
        view = AddEventView(self, payload)
        await self.edit_message(embed, view, content)

    async def show_edit_event(
        self,
        interaction: Interaction,
        event_id: str,
        raw_event: RawEvent,
        content: str | None = None,
    ) -> None:
        """|coro|

        Shows the edit event view.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        event_id: :class:`str`
            The ID of the event to edit.
        raw_event: :class:`.RawEvent`
            The raw event to display.
        content: :class:`str`| `None`
            The content of the message. Defaults to ``None``.
        """
        self._update_locale(interaction)
        payload = EditEventPayload(event_id, raw_event, self.locale, self.config)
        embed = EditEventEmbed(payload)
        view = EditEventView(self, payload)
        await self.edit_message(embed, view, content)

    async def show_copy_event(
        self,
        interaction: Interaction,
        raw_event: RawEvent,
        content: str | None = None,
    ) -> None:
        """|coro|

        Shows the copy event view.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        raw_event: :class:`.RawEvent`
            The raw event to display.
        content: :class:`str`| `None`
            The content of the message. Defaults to ``None``.
        """
        self._update_locale(interaction)
        payload = CopyEventPayload(raw_event, self.locale, self.config)
        embed = CopyEventEmbed(payload)
        view = CopyEventView(self, payload)
        await self.edit_message(embed, view, content)

    async def show_information_modal(
        self,
        interaction: Interaction,
        raw_event: RawEvent,
        refresh_method: _RefreshFunc,
    ) -> None:
        """|coro|

        Shows the event information modal.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        raw_event: :class:`.RawEvent`
            The raw event to display.
        refresh_method: Callable[[:class:`nextcord.Interaction`], Awaitable[`None`]]
            The method to call to refresh the embed after the modal is submitted.
        """
        self._update_locale(interaction)
        payload = EventInformationModalPayload(
            raw_event, self.locale, self.config, refresh_method
        )
        modal = EventInformationModal(self, payload)
        await interaction.response.send_modal(modal)
