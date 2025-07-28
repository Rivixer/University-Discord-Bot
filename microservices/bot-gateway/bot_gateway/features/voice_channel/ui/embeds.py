"""
Voice Channel Panel Embed
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nextcord import Embed, VoiceChannel
from nextcord.utils import format_dt

if TYPE_CHECKING:
    from shared.models.voice_channel import RenameStatusResponse


class VoiceChannelPanelEmbed(Embed):
    """Embed for the voice channel panel."""

    def __init__(
        self, channel: VoiceChannel, rename_status: RenameStatusResponse
    ) -> None:
        title = channel.name

        members = channel.members
        member_list = (
            "\n".join(
                f"- {m.mention}" for m in sorted(members, key=lambda m: m.display_name)
            )
            or "No members in this channel"
        )

        if (user_limit := channel.user_limit) > 0:
            description = f"Members ({len(members)}/{user_limit}):\n{member_list}"
        else:
            description = f"Members ({len(members)}):\n{member_list}"

        super().__init__(title=title, description=description, color=0x73767C)

        self.set_thumbnail(
            url="https://cdn3.emoji.gg/emojis/66643-badlydrawnvoicechannel.png"
        )

        self.add_field(
            name="Remaining renames:",
            value=f"{rename_status.remaining_renames} of {rename_status.max_remaining_renames}",
            inline=False,
        )

        if rename_status.cooldown_reset_at:
            self.add_field(
                name="Rename cooldown reset:",
                value=format_dt(rename_status.cooldown_reset_at, "R"),
                inline=False,
            )


class VoiceChannelConfigEmbed(Embed):
    """Embed for the voice channel configuration."""

    def __init__(self, default_name_template: str, available_names: list[str]) -> None:
        title = "Configuration for Voice Channel Service"
        super().__init__(title=title, color=0x5865F2)

        self.set_thumbnail(
            url="https://cdn3.emoji.gg/emojis/6770-discord-voice-from-vega.png"
        )

        self.add_field(
            name="Available names:",
            value="\n".join(available_names),
            inline=False,
        )

        self.add_field(
            name="Default name template:",
            value=default_name_template,
            inline=False,
        )
