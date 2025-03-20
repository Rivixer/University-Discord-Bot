# SPDX-License-Identifier: MIT
"""A module providing modals for the calendar UI."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, override

from nextcord import TextInputStyle
from nextcord.ui import Modal, TextInput, View

from university_bot import Localization
from university_bot.mixins import LocalizedMixin

from ..config import ReminderFieldLimits

if TYPE_CHECKING:
    from university_bot import Interaction

    from .manager import ReminderManager
    from .payloads import ReminderInformationModalPayload
    from ..models import RawReminder

__all__ = ("ReminderInformationModal",)

_loc = Localization.get_group("ui.reminder.modals")


@dataclass(slots=True, frozen=True)
class _ReminderInformationModalTextInputs[T: View]:
    description: TextInput[T]
    date: TextInput[T]
    time: TextInput[T]
    additional_info: TextInput[T]

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

    def update_values(self, reminder: RawReminder) -> None:
        """Updates the raw reminder with the text input values.

        Parameters
        ----------
        reminder: :class:`.RawReminder`
            The raw reminder to update.
        """
        reminder.description = self.description.value
        reminder.date = self.date.value
        reminder.time = self.time.value
        reminder.additional_info = self.additional_info.value


class ReminderInformationModal(LocalizedMixin, Modal):
    """A modal responsible for editing event information.

    It is used to edit the description, date, time, and additional information of a reminder.
    """

    _manager: ReminderManager
    _payload: ReminderInformationModalPayload
    _text_inputs: _ReminderInformationModalTextInputs[View]

    def __init__(
        self,
        manager: ReminderManager,
        payload: ReminderInformationModalPayload,
    ) -> None:
        loc_group = _loc.get_group("reminder_information")
        LocalizedMixin.__init__(self, payload.locale, loc_group)
        Modal.__init__(self, title=self.get_loc("title", "Reminder information"))

        self._manager = manager
        self._payload = payload

        inputs_loc = self.get_loc_group("text_inputs")
        reminder = payload.reminder
        calendar_data = payload.calendar_data

        description = TextInput[View](
            label=inputs_loc.get("description.label", "Description:"),
            placeholder=inputs_loc.get("description.placeholder", "The description"),
            default_value=reminder.description,
            max_length=ReminderFieldLimits.DESCRIPTION,
            required=True,
        )

        date = TextInput[View](
            label=inputs_loc.get("date.label", "Date:"),
            placeholder=calendar_data.date_input_format,
            default_value=reminder.date,
            max_length=len(calendar_data.date_input_format),
            required=True,
        )

        time = TextInput[View](
            label=inputs_loc.get("time.label", "Time:"),
            placeholder=calendar_data.time_input_format,
            default_value=reminder.time,
            max_length=len(calendar_data.time_input_format),
            required=True,
        )

        additional_info = TextInput[View](
            label=inputs_loc.get("additional_info.label", "Additional information:"),
            style=TextInputStyle.paragraph,
            default_value=reminder.additional_info,
            max_length=ReminderFieldLimits.ADDITIONAL_INFO,
            required=False,
        )

        self._text_inputs = _ReminderInformationModalTextInputs(
            description=description,
            date=date,
            time=time,
            additional_info=additional_info,
        )

        self._text_inputs.add_items(self)

    @override
    async def callback(self, interaction: Interaction) -> None:
        self._text_inputs.update_values(self._payload.reminder)
        await self._payload.refresh_method(interaction)
