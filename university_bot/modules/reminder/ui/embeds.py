# SPDX-License-Identifier: MIT
"""A module providing embeds for the reminder UI."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from nextcord import Color, Embed

from university_bot import Localization
from university_bot.mixins import LocalizedMixin

from .payloads import ConfigReminderPayload, ReminderPayload, SummaryReminderPayload
from ...calendar import Event, RawEvent

if TYPE_CHECKING:
    from nextcord import Locale

    from university_bot import EmbedDict

    from ..config import ReminderDataConfig
    from ..models import RawReminder, Reminder
    from ..service import ReminderService
    from ...calendar import CalendarDataConfig

__all__ = (
    "ReminderEmbed",
    "AddReminderEmbed",
    "EditReminderEmbed",
    "CopyReminderEmbed",
    "SummaryReminderEmbed",
    "NoRemindersEmbed",
)

_loc = Localization.get_group("ui.reminder.embeds")


def _get_embed_dict(
    service: ReminderService,
    reminder: Reminder | RawReminder,
    event: Event | RawEvent,
) -> EmbedDict:
    embed_dict: EmbedDict = service.data.embed.to_dict()  # type: ignore
    embed_dict = service.format_content(embed_dict, event, reminder)

    # Remove fields with empty values
    embed_dict["fields"] = [f for f in embed_dict["fields"] if f["value"]]

    return embed_dict


class ReminderEmbed(Embed):
    """An embed to display a reminder."""

    @classmethod
    def create(cls, payload: ReminderPayload, preview: bool = False) -> ReminderEmbed:
        """Creates a new reminder embed.

        If `preview` is set to `True`, the title will be appended with "(preview)".
        If the payload is a `ConfigReminderPayload`, the title will be appended with
        the preview locale.

        Parameters
        ----------
        payload: :class:`.ReminderPayload`
            The payload to create the embed with.
        preview: :class:`bool`
            Whether to create a preview embed.

        Returns
        -------
        :class:`.ReminderEmbed`
            The created reminder embed.
        """
        embed_dict = _get_embed_dict(payload.service, payload.reminder, payload.event)
        if preview:
            if isinstance(payload, ConfigReminderPayload):
                locale = payload.locale
                embed_dict["title"] += f" ({_loc.get(locale, "preview", "preview")})"
            else:
                embed_dict["title"] += " (preview)"

        return super().from_dict(embed_dict)


class _ConfigReminderEmbed(LocalizedMixin, Embed, ABC):

    def __init__(
        self,
        payload: ConfigReminderPayload,
        type_loc_key: str,
        *,
        edit_view: bool,
    ) -> None:
        LocalizedMixin.__init__(self, payload.locale, _loc.get_group("config"))

        configuration_text = self.get_loc("configuration", "Configuration")
        type_text = self.get_loc(f"type.{type_loc_key}", type_loc_key)
        title = f"{configuration_text} ({type_text})"

        Embed.__init__(self, title=title)

        reminder = payload.reminder

        # Datetime
        if reminder.parsed_datetime:
            ts = str(int(reminder.parsed_datetime.timestamp()))
            datetime = f"<t:{ts}:F> (<t:{ts}:R>)"
            if edit_view and reminder.is_datetime_in_past():
                datetime = f"**(!)** {datetime}"
        else:
            datetime = "**(!)**"

        self.add_field(
            name=self.get_loc("datetime", "Datetime") + ":",
            value=datetime,
            inline=False,
        )

        # Channel
        channel = f"<#{reminder.channel_id}>" if reminder.channel_id else "**(!)**"
        self.add_field(
            name=self.get_loc("channel", "Channel") + ":",
            value=channel,
            inline=False,
        )

        # Roles
        roles = (
            ", ".join(map(lambda i: f"<@&{i}>", reminder.role_ids))
            if reminder.role_ids
            else "-"
        )
        self.add_field(
            name=self.get_loc("roles", "Roles") + ":",
            value=roles,
            inline=False,
        )

        # Message link
        if reminder.channel_id and reminder.message_id:
            guild_id = payload.guild_id
            channel_id = reminder.channel_id
            message_id = reminder.message_id
            self.add_field(
                name=self.get_loc("message", "Message") + ":",
                value=f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}",
                inline=False,
            )


class AddReminderEmbed(_ConfigReminderEmbed):
    """An embed to display when adding a reminder."""

    def __init__(self, payload: ConfigReminderPayload) -> None:
        super().__init__(payload, "add", edit_view=True)
        self.color = Color.green()


class EditReminderEmbed(_ConfigReminderEmbed):
    """An embed to display when editing a reminder."""

    def __init__(self, payload: ConfigReminderPayload) -> None:
        super().__init__(payload, "edit", edit_view=True)
        self.color = Color.blurple()


class CopyReminderEmbed(_ConfigReminderEmbed):
    """An embed to display when copying a reminder."""

    def __init__(self, payload: ConfigReminderPayload) -> None:
        super().__init__(payload, "copy", edit_view=True)
        self.color = Color.magenta()


class SummaryReminderEmbed(_ConfigReminderEmbed):
    """An embed to display a summary of a reminder."""

    def __init__(self, payload: SummaryReminderPayload) -> None:
        super().__init__(payload, "summary", edit_view=False)
        self.title = f"{self.title} [{payload.index+1}/{payload.total}]"
        self.color = Color.orange()


class NoRemindersEmbed(LocalizedMixin, Embed):
    """An embed to display when there are no reminders to show."""

    def __init__(
        self,
        locale: Locale,
        data: ReminderDataConfig,
        calendar_data: CalendarDataConfig,
        event: Event | RawEvent,
    ) -> None:
        LocalizedMixin.__init__(self, locale, _loc.get_group("no_reminders"))

        title = self.get_loc("title", "No reminders")
        description = self.get_loc("description", "There are no reminders to display.")

        Embed.__init__(
            self,
            title=title,
            description=description,
            color=Color.red(),
        )

        if isinstance(event, RawEvent):
            event = event.to_event(id_=None)

        self.add_field(
            name=calendar_data.format_repr_date(event.date) + ":",
            value=event.to_calendar_repr(calendar_data),
        )

        self.set_thumbnail(url=data.embed.thumbnail.url)
