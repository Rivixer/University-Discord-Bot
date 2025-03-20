# SPDX-License-Identifier: MIT
"""A module providing managers for the calendar UI."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, overload, override

from nextcord import HTTPException, Locale
from nextcord.utils import MISSING

from university_bot import ResourceFetchFailed, get_logger
from university_bot.mixins.timeout import TimeoutManagerMixin
from university_bot.ui import TimeoutMenuEmbed

from .embeds import (
    CopyEventEmbed,
    CreateEventEmbed,
    EditEventEmbed,
    NoEventsEmbed,
    SummaryEventEmbed,
)
from .enums import EventSummaryNavigation
from .modals import EventInformationModal
from .payloads import (
    CopyEventPayload,
    CreateEventPayload,
    EditEventPayload,
    EventInformationModalPayload,
    SummaryEventPayload,
)
from .views import (
    CopyEventView,
    CreateEventView,
    EditEventView,
    NoEventsView,
    SummaryEventView,
)
from ..enums import EventVisibility
from ..models import Event, RawEvent

if TYPE_CHECKING:
    from nextcord import Embed, Message
    from nextcord.ui import View

    from university_bot import Interaction, UniversityBot
    from university_bot.mixins.timeout import TimeoutViewMixin

    from ..config import CalendarDataConfig
    from ..handler import CalendarHandler
    from ...reminder import ReminderCog
    from ...reminder.ui import ReminderManager

    _RefreshFunc = Callable[[Interaction], Awaitable[None]]

__all__ = ("CalendarManager",)

_logger = get_logger(__name__)


@dataclass(slots=True)
class _MenuSummaryData:
    event: Event | None = field(default=None)
    index: int = field(default=0)


class CalendarManager(TimeoutManagerMixin):
    """A calendar manager.

    Attributes
    ----------
    handler: :class:`.CalendarHandler`
        The calendar handler.
    locale: :class:`nextcord.Locale`
        The locale of the interaction.
    reminder_cog: :class:`.ReminderCog` | `None`
        The reminder cog.
    """

    __slots__ = (
        "handler",
        "locale",
        "reminder_cog",
        "_message",
        "_summary_data",
        "_view",
        "_reminder_manager",
    )

    handler: CalendarHandler
    locale: Locale
    reminder_cog: ReminderCog | None
    _message: Message
    _summary_data: _MenuSummaryData
    _view: View | None
    _reminder_manager: ReminderManager | None

    def __init__(
        self,
        handler: CalendarHandler,
        locale: Locale,
        reminder_cog: ReminderCog | None,
        message: Message,
    ) -> None:
        self.handler = handler
        self.locale = locale
        self.reminder_cog = reminder_cog
        self._message = message
        self._summary_data = _MenuSummaryData()
        self._view = None
        self._reminder_manager = None

    @classmethod
    async def create_and_send(
        cls,
        handler: CalendarHandler,
        interaction: Interaction,
        reminder_cog: ReminderCog | None,
    ):
        """|coro|

        Creates a new manager and sends the calendar menu.

        Should be used as an entry point for the calendar menu.

        Parameters
        ----------
        handler: :class:`.CalendarHandler`
            The calendar handler.
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the calendar menu.
        reminder_cog: :class:`.ReminderCog` | `None`
            The reminder cog.

        Returns
        -------
        :class:`.CalendarManager`
            The created manager.
        """
        self = cls(handler, Locale(interaction.locale), reminder_cog, None)  # type: ignore

        if events := await self.handler.service.get_sorted_events(EventVisibility.ALL):
            event = events[0]

            if self.reminder_cog:
                await event.fetch_reminders(self.reminder_cog.service)

            payload = SummaryEventPayload(event, 0, len(events), self.locale, self.data)
            embed = SummaryEventEmbed(payload)
            view = SummaryEventView(self, payload)

            self._summary_data.event = event
            self._summary_data.index = 0
        else:
            embed = NoEventsEmbed(self.locale, self.data)
            view = NoEventsView(self)

        partial_message = await interaction.response.send_message(
            embed=embed, view=view, ephemeral=True
        )

        self._message = await partial_message.fetch()
        self._view = view

        return self

    @property
    def data(self) -> CalendarDataConfig:
        """:class:`.CalendarDataConfig`: The calendar data configuration."""
        return self.handler.service.data

    @property
    def bot(self) -> UniversityBot:
        """:class:`.UniversityBot`: The bot instance."""
        return self.handler.service.bot

    def _get_reminder_cog(self) -> ReminderCog | None:
        cog = self.bot.get_cog("ReminderCog")
        if isinstance(cog, ReminderCog):
            return cog
        return None

    def update_locale(self, interaction: Interaction) -> None:
        """Updates the locale of the manager.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction to update the locale from.
        """
        self.locale = Locale(interaction.locale)

    async def send_message(
        self,
        interaction: Interaction,
        embed: Embed | None,
        view: View | None,
        content: str | None,
    ) -> None:
        """|coro|

        Sends the calendar message.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the command.
        view: :class:`nextcord.ui.View`
            The view to send with the message.
        """
        if self._view:
            self._view.stop()

        partial_message = await interaction.response.send_message(
            content=content,
            embed=embed or MISSING,
            view=view or MISSING,
            ephemeral=True,
        )
        self._message = await partial_message.fetch()
        self._view = view

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
        embed: Embed | None = MISSING,
        embeds: list[Embed] = MISSING,
        view: View | None = MISSING,
        content: str | None = None,
    ) -> None:
        """|coro|

        Edits the message with the provided embed(s), view and content.
        """
        if self._view:
            self._view.stop()
        self._view = view

        kwargs: dict[str, Any] = {"content": content, "view": view}

        if embed is not MISSING:
            kwargs["embed"] = embed
        elif embeds is not MISSING:
            kwargs["embeds"] = embeds

        await self._message.edit(**kwargs)

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
            await self.edit_message(embed=embed, view=None, content=None)

    async def attempt_refresh_calendar(self) -> None:
        """|coro|

        Attempts to refresh the calendar.

        If the refresh fails, the exception is caught and ignored.
        """
        try:
            await self.handler.service.refresh_message(self.handler)
        except (ResourceFetchFailed, HTTPException):
            pass

    async def show_reminder_manager(
        self,
        interaction: Interaction,
        event: RawEvent,
        refresh_method: _RefreshFunc,
    ) -> None:
        """|coro|

        Shows the reminder manager.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        event: :class:`.RawEvent`
            The event to manage the reminders for.
        """
        self.update_locale(interaction)

        try:
            # Import here to avoid circular imports
            # pylint: disable=import-outside-toplevel
            from ...reminder.ui import ReminderManager
        except ImportError:
            _logger.exception("Cannot import the reminder cog.")
            await self.edit_message(
                embed=None,
                view=None,
                content="Error: failed to import the reminder cog.",
            )
            return

        try:
            self._reminder_manager = ReminderManager(self, event, refresh_method)
        except ValueError as e:
            _logger.error("Failed to create the reminder manager: %s", e)
            await self.edit_message(
                embed=None,
                view=None,
                content="Error: failed to create the reminder manager.",
            )
            return

        await self._reminder_manager.show_summary(interaction)

    async def show_no_events(self, interaction: Interaction) -> None:
        """|coro|

        Shows the no events view.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        """
        self.update_locale(interaction)
        embed = NoEventsEmbed(self.locale, self.data)
        view = NoEventsView(self)
        if self._message:
            await self.edit_message(embed=embed, view=view, content=None)
        else:
            await self.send_message(interaction, embed, view, content=None)

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

        If there is no events to display, the

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
        self.update_locale(interaction)
        events = await self.handler.service.get_sorted_events(EventVisibility.ALL)

        if not events:
            return await self.show_no_events(interaction)

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

        assert event is not None

        event_index = events.index(event)
        self._summary_data.event = event
        self._summary_data.index = event_index

        if self.reminder_cog:
            await event.fetch_reminders(self.reminder_cog.service)

        payload = SummaryEventPayload(
            event,
            event_index,
            len(events),
            self.locale,
            self.data,
        )

        embed = SummaryEventEmbed(payload)
        view = SummaryEventView(self, payload)
        await self.edit_message(embed=embed, view=view, content=content)

    @overload
    async def show_create(
        self,
        interaction: Interaction,
        *,
        content: str | None = None,
    ) -> None:
        """|coro|

        Displays the create event view.

        This method displays the create event view with default values.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        content: :class:`str`| `None`
            The content of the message. Defaults to ``None``.
        """

    @overload
    async def show_create(
        self,
        interaction: Interaction,
        raw_event: RawEvent,
        content: str | None = None,
    ) -> None:
        """|coro|

        Displays the create event view.

        This method displays the create event view with the provided raw event.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the view update.
        raw_event: :class:`.RawEvent`
            The raw event to display.
        """

    async def show_create(
        self,
        interaction: Interaction,
        raw_event: RawEvent | None = None,
        content: str | None = None,
    ) -> None:
        """|coro|

        Shows the create event view.
        """
        self.update_locale(interaction)
        if raw_event is None:
            raw_event = RawEvent.default(self.data)

        payload = CreateEventPayload(raw_event, self.locale, self.data)
        embed = CreateEventEmbed(payload)
        view = CreateEventView(self, payload)
        await self.edit_message(embed=embed, view=view, content=content)

    async def show_edit(
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
        self.update_locale(interaction)
        payload = EditEventPayload(event_id, raw_event, self.locale, self.data)
        embed = EditEventEmbed(payload)
        view = EditEventView(self, payload)
        await self.edit_message(embed=embed, view=view, content=content)

    async def show_copy(
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
        self.update_locale(interaction)
        payload = CopyEventPayload(raw_event, self.locale, self.data)
        embed = CopyEventEmbed(payload)
        view = CopyEventView(self, payload)
        await self.edit_message(embed=embed, view=view, content=content)

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
        self.update_locale(interaction)
        payload = EventInformationModalPayload(
            raw_event, self.locale, self.data, refresh_method
        )
        modal = EventInformationModal(self, payload)
        await interaction.response.send_modal(modal)

    async def update_reminders(self, event_id: str, raw_event: RawEvent) -> None:
        """|coro|

        Updates the reminders of the event.

        If the reminder manager is not available, this method does nothing.

        Parameters
        ----------
        event_id: :class:`str`
            The ID of the event to update.
        raw_event: :class:`.RawEvent`
            The raw event to update the reminders from.
        """
        if not self._reminder_manager:
            return

        reminders = [r.to_reminder(event_id, id_=None) for r in raw_event.reminders]
        await self._reminder_manager.service.update_event_reminders(event_id, reminders)
