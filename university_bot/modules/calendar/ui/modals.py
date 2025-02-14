# SPDX-License-Identifier: MIT
"""A module providing modals for the calendar UI."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, override

from nextcord.ui import Modal, TextInput, View

from university_bot import Localization
from university_bot.mixins import LocalizedMixin

from ..config import EventFieldLimits

if TYPE_CHECKING:
    from university_bot import Interaction

    from .managers import CalendarMenuViewManager
    from .payloads import EventInformationModalPayload
    from ..models import RawEvent

__all__ = ("EventInformationModal",)

_loc = Localization.get_group("ui.calendar.modals")


@dataclass(slots=True, frozen=True)
class _EventInformationModalTextInputs[T: View]:
    description: TextInput[T]
    date: TextInput[T]
    time: TextInput[T]
    prefix: TextInput[T]
    location: TextInput[T]

    def add_items(self, modal: Modal) -> None:
        """Adds the text inputs to the modal.

        Parameters
        ----------
        modal: :class:`nextcord.ui.Modal`
            The modal to add the text inputs to.
        """
        for fld in fields(self):
            input_ = getattr(self, fld.name)
            modal.add_item(input_)  # type: ignore

    def update_values(self, raw_event: RawEvent) -> None:
        """Updates the raw event with the text input values.

        Parameters
        ----------
        raw_event: :class:`.RawEvent`
            The raw event to update.
        """
        raw_event.description = self.description.value
        raw_event.date = self.date.value
        raw_event.time = self.time.value
        raw_event.prefix = self.prefix.value
        raw_event.location = self.location.value


class EventInformationModal(LocalizedMixin, Modal):
    """A modal responsible for editing event information.

    It is used to edit the description, date, time, prefix, and location of an event.
    """

    _manager: CalendarMenuViewManager
    _payload: EventInformationModalPayload
    _text_inputs: _EventInformationModalTextInputs[View]

    def __init__(
        self,
        manager: CalendarMenuViewManager,
        payload: EventInformationModalPayload,
    ) -> None:
        loc_group = _loc.get_group("event_information")
        LocalizedMixin.__init__(self, payload.locale, loc_group)
        Modal.__init__(self, title=self.get_loc("title", "Event information"))

        self._manager = manager
        self._payload = payload

        inputs_loc = self.get_loc_group("text_inputs")
        raw_event = payload.raw_event
        config = payload.config

        description = TextInput[View](
            label=inputs_loc.get("description.label", "Description:"),
            placeholder=inputs_loc.get("description.placeholder", "The description"),
            default_value=raw_event.description,
            max_length=EventFieldLimits.DESCRIPTION,
            required=True,
        )

        date = TextInput[View](
            label=inputs_loc.get("date.label", "Date:"),
            placeholder=config.date_input_format,
            default_value=raw_event.date,
            max_length=len(config.date_input_format),
            required=True,
        )

        time = TextInput[View](
            label=inputs_loc.get("time.label", "Time:"),
            placeholder=config.time_input_format,
            default_value=raw_event.time,
            max_length=len(config.time_input_format),
            required=False,
        )

        prefix = TextInput[View](
            label=inputs_loc.get("prefix.label", "Prefix:"),
            placeholder=inputs_loc.get("prefix.placeholder", "The prefix"),
            default_value=raw_event.prefix,
            max_length=EventFieldLimits.PREFIX,
            required=False,
        )

        location = TextInput[View](
            label=inputs_loc.get("location.label", "Location:"),
            placeholder=inputs_loc.get("location.placeholder", "The location"),
            default_value=raw_event.location,
            max_length=EventFieldLimits.LOCATION,
            required=False,
        )

        self._text_inputs = _EventInformationModalTextInputs(
            description=description,
            date=date,
            time=time,
            prefix=prefix,
            location=location,
        )

        self._text_inputs.add_items(self)

    @override
    async def callback(self, interaction: Interaction) -> None:
        self._text_inputs.update_values(self._payload.raw_event)
        await self._payload.refresh_method(interaction)
