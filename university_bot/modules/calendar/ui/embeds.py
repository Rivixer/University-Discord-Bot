# SPDX-License-Identifier: MIT
"""A module providing embeds for the calendar UI."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from babel.dates import format_date
from nextcord import Color, Embed

from university_bot import Localization
from university_bot.mixins import LocalizedMixin
from university_bot.utils import format_embed_values

if TYPE_CHECKING:

    from nextcord import Locale

    from .payloads import (
        AddEventPayload,
        CopyEventPayload,
        EditEventPayload,
        SummaryEventPayload,
    )
    from ..config import CalendarDataConfig
    from ..models import Event, RawEvent

__all__ = (
    "CalendarEmbed",
    "CalendarMenuEmbed",
    "AddEventEmbed",
    "EditEventEmbed",
    "CopyEventEmbed",
    "SummaryEventEmbed",
)

_loc = Localization.get_group("ui.calendar.embeds")


class CalendarEmbed(Embed):
    """An embed to display the calendar events.

    It groups the events by date and displays them in the embed fields.
    """

    @classmethod
    def create(
        cls,
        data: CalendarDataConfig,
        sorted_grouped_events: dict[datetime.date, list[Event]],
    ) -> CalendarEmbed:
        """Creates a new calendar embed.

        This method builds an embed using the base embed configuration and adds
        a field for each date, listing all events on that day with proper formatting.

        Parameters
        ----------
        data: :class:`.CalendarDataConfig`
            The calendar data configuration.
        sorted_grouped_events: dict[datetime.date, list[:class:`.Event`]]
            The sorted and grouped events.

        Returns
        -------
        :class:`.CalendarEmbed`
            The created calendar embed.
        """

        embed_dict = data.embed.to_dict()
        formatted_embed_dict = format_embed_values(
            embed_dict,
            modified=data.format_modified(data.modified or datetime.datetime.now()),
        )

        self = super().from_dict(formatted_embed_dict)

        for event_date, events in sorted_grouped_events.items():
            formatted_date = format_date(
                event_date,
                format=data.date_repr_format,
                locale=data.locale,
            )
            event_descriptions = "\n".join(
                event.to_calendar_repr(data, with_indent=True) for event in events
            )
            self.add_field(
                name=f"{formatted_date}:",
                value=event_descriptions[:1024],
                inline=False,
            )

        return self


class CalendarMenuEmbed(LocalizedMixin, Embed):
    """An embed representing the calendar menu.

    This embed is used to display the calendar menu with the available options.
    """

    def __init__(self, locale: Locale, config: CalendarDataConfig) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("menu"))

        title = self.get_loc("title", "Calendar Menu")
        description = self.get_loc("description", "Select an option below.")

        Embed.__init__(
            self,
            title=title,
            description=description,
            color=Color.orange(),
        )

        self.add_field(
            name=self.get_loc("fields.add_event.name", "Add Event"),
            value=self.get_loc("fields.add_event.value", "Add a new event."),
            inline=False,
        ).add_field(
            name=self.get_loc("fields.summary.name", "Summary"),
            value=self.get_loc("fields.summary.value", "View the events summary."),
            inline=False,
        )

        self.set_thumbnail(url=config.embed.thumbnail.url)


class _BaseEventEmbed(LocalizedMixin, Embed):

    _event: RawEvent

    def __init__(self, locale: Locale, raw_event: RawEvent) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("event"))
        Embed.__init__(self)
        self._event = raw_event

    def _build(self, color: Color, *, edit_view: bool) -> None:
        self._set_color(color)
        self._build_fields(edit_view)

        if edit_view:
            self.set_footer(text=f"* {self.get_loc('other.required', 'required')}")

    def _set_color(self, color: Color) -> None:
        factor = 0.6 if self._event.is_hidden else 1.0
        self.color = Color.from_rgb(
            int(color.r * factor),
            int(color.g * factor),
            int(color.b * factor),
        )

    def _build_fields(self, edit_view: bool) -> None:
        fields_loc = self.get_loc_group("fields")

        # Description
        name = fields_loc.get("description.name", "Description:")
        if edit_view:
            name += "*"
        value = self._event.description
        self.add_field(name=name, value=value or "-", inline=False)

        # Date
        name = fields_loc.get("date.name", "Date:")
        if edit_view:
            name += "*"
        value = self._event.date
        if edit_view and value and not self._event.is_date_valid():
            value = f"**(!)** {value}"
        self.add_field(name=name, value=value or "-", inline=False)

        # Time
        name = fields_loc.get("time.name", "Time:")
        value = self._event.time
        if edit_view and value and not self._event.is_time_valid():
            value = f"**(!)** {value}"
        self.add_field(name=name, value=value or "-", inline=True)

        # Prefix
        name = fields_loc.get("prefix.name", "Prefix:")
        value = self._event.prefix or "-"
        self.add_field(name=name, value=value, inline=True)

        # Location
        name = fields_loc.get("location.name", "Location:")
        value = self._event.location or "-"
        self.add_field(name=name, value=value, inline=True)

        # Hidden
        name = fields_loc.get("is_hidden.name", "Hidden:")
        if self._event.is_hidden:
            value = fields_loc.get("is_hidden.yes", "Yes")
        else:
            value = fields_loc.get("is_hidden.no", "No")
        self.add_field(name=name, value=value, inline=False)


class AddEventEmbed(_BaseEventEmbed):
    """An embed for adding a new event."""

    def __init__(self, payload: AddEventPayload) -> None:
        super().__init__(payload.locale, payload.raw_event)
        self.title = self.get_loc("titles.add", "Add event")
        self._build(Color.magenta(), edit_view=True)
        self.set_thumbnail(url=payload.config.embed.thumbnail.url)


class EditEventEmbed(_BaseEventEmbed):
    """An embed for editing an event."""

    def __init__(self, payload: EditEventPayload) -> None:
        super().__init__(payload.locale, payload.raw_event)
        self.title = self.get_loc("titles.edit", "Edit event")
        self._build(Color.blurple(), edit_view=True)
        self.set_thumbnail(url=payload.config.embed.thumbnail.url)


class CopyEventEmbed(_BaseEventEmbed):
    """An embed for copying an event."""

    def __init__(self, payload: CopyEventPayload) -> None:
        super().__init__(payload.locale, payload.raw_event)
        self.title = self.get_loc("titles.copy", "Copy event")
        self._build(Color.green(), edit_view=True)
        self.set_thumbnail(url=payload.config.embed.thumbnail.url)


class SummaryEventEmbed(_BaseEventEmbed):
    """An embed for displaying a summary of an event."""

    def __init__(self, payload: SummaryEventPayload):
        super().__init__(payload.locale, payload.raw_event)

        title = self.get_loc("titles.summary", "Event summary")
        title += f" [{payload.index+1}/{payload.total}]"
        self.title = title

        self._build(Color.orange(), edit_view=False)
        self.set_thumbnail(url=payload.config.embed.thumbnail.url)
