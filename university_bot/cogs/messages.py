# SPDX-License-Identifier: MIT
"""A module to control bot messages."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any, Optional

import nextcord
from nextcord.application_command import SlashOption
from nextcord.channel import TextChannel
from nextcord.embeds import Embed
from nextcord.errors import DiscordException
from nextcord.ext import commands
from nextcord.file import File
from nextcord.interactions import Interaction
from nextcord.message import Attachment, MessageReference
from nextcord.threads import Thread

from university_bot.console import Console, FontColour
from university_bot.errors import AttachmentError, ExceptionData
from university_bot.utils import InteractionUtils, MemberUtils

if TYPE_CHECKING:
    from university_bot import UniversityBot


class MessagingCog(commands.Cog):
    """A cog to control bot messages."""

    __slots__ = ("_bot",)

    _bot: UniversityBot

    def __init__(self, bot: UniversityBot) -> None:
        self._bot = bot

    @staticmethod
    async def _convert_attachment_to_file(attachment: Attachment) -> File:
        return File(io.BytesIO(await attachment.read()), filename=attachment.filename)

    @staticmethod
    async def _convert_attachment_to_embed(attachment: Attachment) -> Embed:
        if not attachment.filename.endswith(".json"):
            raise AttachmentError("The attachment must be a JSON file")
        return Embed.from_dict(json.loads(io.BytesIO(await attachment.read()).read()))

    @commands.Cog.listener(name="on_message")
    async def _on_message(self, message: nextcord.Message) -> None:
        author = message.author

        if message.content != "":
            Console.specific(
                message.content,
                f"{MemberUtils.display_name(author)}/{author}/{message.channel}",
                FontColour.CYAN,
            )

        if message.attachments:
            for attachment in message.attachments:
                Console.specific(
                    attachment.url,
                    f"{MemberUtils.display_name(author)}/{author}/{message.channel}",
                    FontColour.CYAN,
                )

    @nextcord.slash_command(
        name="message",
        description="Manage bot messages.",
        dm_permission=False,
    )
    async def _message(self, *_) -> None:
        """A command to manage bot messages.

        This command is a placeholder for the subcommands.
        """

    @_message.subcommand(name="send", description="Send a message to a channel.")
    @InteractionUtils.with_info(
        before="Sending a message...",
        after="The message has been sent.",
        catch_exceptions=[ValueError, DiscordException, AttachmentError],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _send(  # pylint: disable=too-many-arguments
        self,
        interaction: Interaction,
        text: str = SlashOption(
            description="The message content.",
            required=False,
            default="",
        ),
        reply_to_msg_id: Optional[str] = SlashOption(
            description="The ID of the message to reply to.",
            required=False,
            default=None,
        ),
        embed: Optional[Attachment] = SlashOption(
            name="embed",
            description="The JSON file representing an embed.",
            required=False,
            default=None,
        ),
        attachment: Optional[Attachment] = SlashOption(
            name="file",
            description="The attachment to send.",
            required=False,
            default=None,
        ),
        preview: bool = SlashOption(
            description="Whether to preview the message.",
            required=False,
            default=False,
        ),
    ) -> None:
        message_kwargs: dict[str, Any] = {
            "content": text.replace("\\n", "\n").replace("\\t", "\t")
        }

        if reply_to_msg_id and preview:
            raise ValueError("Cannot preview a reply")

        channel = interaction.channel
        if not isinstance(channel, (TextChannel, Thread)):
            raise ValueError("Cannot send messages to non-text channels")

        if reply_to_msg_id:
            message_kwargs["reference"] = MessageReference(
                channel_id=channel.id,
                message_id=int(reply_to_msg_id),
            )

        if embed:
            message_kwargs["embed"] = await self._convert_attachment_to_embed(embed)

        if attachment:
            message_kwargs["file"] = await self._convert_attachment_to_file(attachment)

        if preview:
            await interaction.send(**message_kwargs, ephemeral=True)
            return

        await channel.send(**message_kwargs)

    @_message.subcommand(
        name="edit",
        description="Edit a message sent by the bot.",
    )
    @InteractionUtils.with_info(
        before="Editing the message...",
        after="The message has been edited.",
        catch_exceptions=[ValueError, DiscordException, AttachmentError],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _edit(  # pylint: disable=too-many-arguments
        self,
        interaction: Interaction,
        message_id: str = SlashOption(
            description="The ID of the message to edit.",
            required=True,
        ),
        text: Optional[str] = SlashOption(
            description="The new message content.",
            required=False,
            default=None,
        ),
        embed: Optional[Attachment] = SlashOption(
            name="embed",
            description="The new JSON file representing an embed.",
            required=False,
            default=None,
        ),
        attachment: Attachment = SlashOption(
            name="file",
            description="Edit file",
            default=None,
            required=False,
        ),
    ) -> None:
        message_kwargs: dict[str, Any] = {}

        channel = interaction.channel
        if not isinstance(channel, (TextChannel, Thread)):
            raise ValueError("Cannot edit messages in non-text channels")

        message = await channel.fetch_message(int(message_id))

        if text:
            message_kwargs["content"] = text.replace("\\n", "\n").replace("\\t", "\t")

        if embed:
            message_kwargs["embed"] = await self._convert_attachment_to_embed(embed)

        if attachment:
            message_kwargs["file"] = await self._convert_attachment_to_file(attachment)

        await message.edit(**message_kwargs)

    @_message.subcommand(
        name="delete",
        description="Delete a message sent by the bot.",
    )
    @InteractionUtils.with_info(
        before="Deleting the message...",
        after="The message has been deleted.",
        catch_exceptions=[
            ValueError,
            DiscordException,
            ExceptionData(
                PermissionError,
                with_traceback_in_log=False,
                with_traceback_in_response=False,
            ),
        ],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _delete(
        self,
        interaction: Interaction,
        message_id: str = SlashOption(
            description="The ID of the message to delete.",
            required=True,
        ),
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, (TextChannel, Thread)):
            raise ValueError("Cannot delete messages in non-text channels")

        message = await channel.fetch_message(int(message_id))

        if message.author != self._bot.user:
            raise PermissionError("Cannot delete messages not sent by the bot")

        await message.delete()

    @_message.subcommand(
        name="remove_element",
        description="Remove an element from a message sent by the bot.",
    )
    @InteractionUtils.with_info(
        before="Removing element(s) from the message...",
        after="The message has been edited.",
        catch_exceptions=[ValueError, DiscordException, AttachmentError],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _remove_element(
        self,
        interaction: Interaction,
        message_id: str = SlashOption(
            description="The ID of the message to edit.",
            required=True,
        ),
        text: bool = SlashOption(
            description="Remove the text.",
            required=False,
            default=False,
        ),
        embed: bool = SlashOption(
            description="Remove the embed.",
            required=False,
            default=False,
        ),
        attachments: bool = SlashOption(
            description="Remove all attachments.",
            required=False,
            default=False,
        ),
    ) -> None:
        if not any((text, embed, attachments)):
            raise ValueError("At least one element must be selected as True.")

        channel = interaction.channel
        if not isinstance(channel, (TextChannel, Thread)):
            raise ValueError("Cannot edit messages in non-text channels")

        message = await channel.fetch_message(int(message_id))
        message_kwargs: dict[str, Any] = {}

        if text:
            message_kwargs["content"] = None

        if embed:
            message_kwargs["embed"] = None

        if attachments:
            message_kwargs["attachments"] = []

        await message.edit(**message_kwargs)

    @_message.subcommand(
        name="add_attachment", description="Add an attachment to a message."
    )
    @InteractionUtils.with_info(
        before="Adding the attachment...",
        after="The attachment has been added.",
        catch_exceptions=[ValueError, DiscordException, AttachmentError],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _add_attachment(
        self,
        interaction: Interaction,
        message_id: str = SlashOption(
            description="The ID of the message to add the attachment to.",
            required=True,
        ),
        attachment: Attachment = SlashOption(
            name="file",
            description="The attachment to add.",
            required=True,
        ),
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, (TextChannel, Thread)):
            raise ValueError("Cannot send messages to non-text channels")

        original_message = await channel.fetch_message(int(message_id))
        message_attachments = original_message.attachments

        new_attachments = message_attachments + [attachment]
        files = [await self._convert_attachment_to_file(a) for a in new_attachments]

        await original_message.edit(files=files)

    @_message.subcommand(
        name="add_reaction",
        description="Add a reaction to a message.",
    )
    @InteractionUtils.with_info(
        before="Adding the reaction... {emoji}",
        after="The reaction {emoji} has been added.",
        catch_exceptions=[ValueError, DiscordException],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _add_reaction(
        self,
        interaction: Interaction,
        message_id: str = SlashOption(
            description="The ID of the message to add the reaction to.",
            required=True,
        ),
        emoji: str = SlashOption(
            description="The emoji to add.",
            required=True,
        ),
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, (TextChannel, Thread)):
            raise ValueError("Cannot edit messages in non-text channels")

        message = await channel.fetch_message(int(message_id))

        await message.add_reaction(emoji)

    @_message.subcommand(
        name="add_reactions",
        description="Add reactions to a message.",
    )
    @InteractionUtils.with_info(
        before="Adding reactions... {emojis}",
        after="Reactions {emojis} have been added.",
        catch_exceptions=[ValueError, DiscordException],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _add_reactions(
        self,
        interaction: Interaction,
        message_id: str = SlashOption(
            description="The ID of the message to add the reaction to.",
            required=True,
        ),
        emojis: str = SlashOption(
            description="The emojis to add separated by a space.",
            required=True,
        ),
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, (TextChannel, Thread)):
            raise ValueError("Cannot edit messages in non-text channels")

        message = await channel.fetch_message(int(message_id))

        emojis_to_add = emojis.split(" ")
        unadded_emojis: dict[str, nextcord.DiscordException] = {}

        for emoji in emojis_to_add:
            try:
                await message.add_reaction(emoji)
            except nextcord.DiscordException as e:
                unadded_emojis[emoji] = e

        if unadded_emojis:
            reason = "\n".join(f"{emoji}: {e}" for emoji, e in unadded_emojis.items())
            raise ValueError(f"Could not add the following emojis:\n{reason}")

    @_message.subcommand(
        name="remove_reaction",
        description="Remove a reaction from a message sent by the bot.",
    )
    @InteractionUtils.with_info(
        before="Removing the reaction... {emoji}",
        after="The reaction {emoji} has been removed.",
        catch_exceptions=[ValueError, DiscordException],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _remove_reaction(
        self,
        interaction: Interaction,
        message_id: str = SlashOption(
            description="The ID of the message to remove the reaction from.",
            required=True,
        ),
        emoji: str = SlashOption(
            description="The emoji to remove.",
            required=True,
        ),
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, (TextChannel, Thread)):
            raise ValueError("Cannot edit messages in non-text channels")

        message = await channel.fetch_message(int(message_id))

        await message.remove_reaction(emoji, self._bot.user)  # type: ignore

    @_message.subcommand(
        name="get_embed",
        description="Get the JSON file representing an embed from a message sent by the bot.",
    )
    @InteractionUtils.with_info(
        before="Getting the embed...",
        catch_exceptions=[ValueError, DiscordException],
    )
    @InteractionUtils.with_log(show_channel=True)
    async def _get_embed(
        self,
        interaction: Interaction,
        message_id: str = SlashOption(
            description="The ID of the message to get the embed from.",
            required=True,
        ),
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, (TextChannel, Thread)):
            raise ValueError("Cannot edit messages in non-text channels")

        message = await channel.fetch_message(int(message_id))

        if not message.embeds:
            raise ValueError("The message does not contain an embed.")

        embed = message.embeds[0]
        embed_json = embed.to_dict()

        msg = await interaction.original_message()
        await msg.edit(
            file=nextcord.File(
                io.BytesIO(json.dumps(embed_json, indent=4).encode("utf-8")),
                filename="embed.json",
            )
        )


def setup(bot: UniversityBot) -> None:
    """Loads the Messaging cog."""
    bot.add_cog(MessagingCog(bot))
