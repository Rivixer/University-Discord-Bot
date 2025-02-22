# SPDX-License-Identifier: MIT
"""A module providing managers for the verification UI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, override

from nextcord import HTTPException, Locale, NotFound
from nextcord.utils import MISSING
from sqlalchemy.exc import SQLAlchemyError

from university_bot import get_logger
from university_bot.mixins.timeout import TimeoutManagerMixin, TimeoutViewMixin
from university_bot.ui import TimeoutMenuEmbed

from .embeds import (
    CodeSentEmbed,
    ErrorEmbed,
    ExternalDataSummaryEmbed,
    IndexTakenEmbed,
    InternalDataSummaryEmbed,
    MaxAttemptsEmbed,
    TargetDataSummaryEmbed,
    VerificationRequestSentEmbed,
    VerificationSuccessEmbed,
)
from .enums import CodeStatus
from .modals import (
    ExternalDataInputModal,
    IndexInputModal,
    InternalDataInputModal,
    TargetDataInputModal,
)
from .models import (
    ExternalVerificationData,
    ExternalVerificationInputData,
    InternalVerificationData,
    InternalVerificationInputData,
    TargetVerificationData,
    TargetVerificationInputData,
)
from .payloads import (
    DataInputPayload,
    ExternalDataSummaryPayload,
    InternalDataSummaryPayload,
    SendEmailPayload,
    TargetDataSummaryPayload,
)
from .views import CodeSentView, DataSummaryView
from ..dto import VerificationDTO
from ..email.generator import MailGenerator
from ..email.service import MailService
from ..exceptions import MailGeneratorError, SMTPError

if TYPE_CHECKING:
    from nextcord import Embed, Member, Message
    from nextcord.ui import View

    from university_bot import Interaction

    from ..config import VerificationConfig
    from ..handler import VerificationHandler
    from ..service import VerificationService

__all__ = (
    "VerificationManager",
    "CodeVerificationManager",
    "TargetVerificationManager",
    "InternalVerificationManager",
    "ExternalVerificationManager",
)

_logger = get_logger(__name__)


class VerificationManager(TimeoutManagerMixin, ABC):
    """A base class to represent a verification manager."""

    handler: VerificationHandler
    member: Member
    locale: Locale
    _message: Message
    _view: View | None = None
    _error_handled: bool = False

    def __init__(
        self,
        handler: VerificationHandler,
        locale: Locale,
        member: Member,
        message: Message,
    ) -> None:
        self.handler = handler
        self.locale = locale
        self.member = member
        self._message = message

    @property
    def service(self) -> VerificationService:
        """The verification service."""
        return self.handler.service

    @property
    def config(self) -> VerificationConfig:
        """The verification configuration."""
        return self.handler.service.config

    def _update_locale(self, interaction: Interaction) -> None:
        self.locale = Locale(interaction.locale)

    def _update_member(self, interaction: Interaction) -> None:
        self.member = interaction.user  # type: ignore

    async def cancel(self) -> None:
        """|coro|

        Cancels the verification process.

        If the view is set, the view is stopped.
        If the message is set, the message is deleted.
        """
        if self._view:
            self._view.stop()

        if self._message:
            try:
                await self._message.delete()
            except NotFound:
                pass
            except HTTPException:
                _logger.warning(
                    "Failed to delete the verification message (user: %s).",
                    self.member.id,
                )

    async def edit_message(
        self,
        embed: Embed | None,
        view: View | None,
        content: str | None = None,
        *,
        delete_after: int | None = None,
    ):
        """|coro|

        Edits the message with the provided embed, view and content.

        If the view is set, the previous view is stopped.

        If an error occurs during the process,
        the error is handled and an error embed is sent.

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

        try:
            await self._message.edit(
                content=content,
                embed=embed,
                view=view,
                delete_after=delete_after,
            )
        except HTTPException as e:
            await self.handle_error(None, e)

    async def edit_or_send_message(  # pylint: disable=too-many-arguments
        self,
        interaction: Interaction,
        embed: Embed | None,
        view: View | None,
        content: str | None = None,
        *,
        delete_after: int | None = None,
    ):
        """|coro|

        Edits the message with the provided embed, view and content,
        or sends a new message if the message is not set.

        If an error occurs during the process,
        the error is handled and an error embed is sent.

        Parameters
        ----------
        embed: :class:`nextcord.Embed` | `None`
            The embed to send or edit the message with.
        view: :class:`nextcord.ui.View` | `None`
            The view to send or edit the message with.
        content: :class:`str` | `None`
            The content to send or edit the message with. Defaults to ``None``
        delete_after: :class:`int` | `None`
            The time in seconds to delete the message after. Defaults to ``None``.
        """

        if self._message:
            return await self.edit_message(
                embed, view, content, delete_after=delete_after
            )

        if self._view:
            self._view.stop()

        self._view = view

        try:
            if interaction.response.is_done():
                self._message = await interaction.followup.send(
                    content=content or MISSING,
                    embed=embed or MISSING,
                    view=view or MISSING,
                    delete_after=delete_after,
                    ephemeral=True,
                    wait=True,
                )
            else:
                partial_message = await interaction.response.send_message(
                    content=content,
                    embed=embed if embed else MISSING,
                    view=view if view else MISSING,
                    ephemeral=True,
                    delete_after=delete_after,
                )
                self._message = await partial_message.fetch()
        except HTTPException as e:
            await self.handle_error(interaction, e)

    async def handle_error(
        self,
        interaction: Interaction | None,
        exception: Exception | str,
    ) -> None:
        """|coro|

        Handles the error that occurred during the verification process
        and sends an error embed.

        The error message edits the current message.
        If the interaction is provided and the message is not set,
        the error message is sent as a new message.

        Parameters
        ----------
        interaction: :class:`.Interaction` | `None`
            The interaction that triggered the command.
        exception: :class:`Exception`
            The exception that occurred.
        """
        if self._error_handled:
            return  # Prevents infinite error loops

        _logger.error(
            "An error occurred during the verification process (user: %s).",
            self.member.id,
            exc_info=True,
        )

        self._error_handled = True
        embed = ErrorEmbed(self.locale, exception)

        if interaction:
            await self.edit_or_send_message(
                interaction,
                embed,
                view=None,
                content=None,
                delete_after=60,
            )
        else:
            await self.edit_message(
                embed,
                view=None,
                content=None,
                delete_after=60,
            )

    @override
    async def on_timeout(self, view: View | TimeoutViewMixin) -> None:
        """|coro|

        Handles the timeout of the view.

        If the view that timed out is the current view,
        the timeout embed is shown.

        Parameters
        ----------
        view: :class:`nextcord.ui.View` | :class:`.TimeoutViewMixin`
            The view that timed out.
        """
        if self._view is view:
            embed = TimeoutMenuEmbed(self.locale)
            await self.edit_message(embed, None)

    @abstractmethod
    async def show_data_input_modal(
        self,
        interaction: Interaction,
    ) -> None:
        """|coro|

        Shows the data input modal.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        """

    @abstractmethod
    async def handle_confirm(self, interaction: Interaction) -> None:
        """|coro|

        Handles the confirmation of the data.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        """


class CodeVerificationManager(VerificationManager, ABC):
    """A base class to represent a verification
    manager with code verification.
    """

    _student_index: str | None = None
    _incorrect_attempts: int = 0
    _email_payload: SendEmailPayload | None = None

    async def send_email(
        self,
        interaction: Interaction,
        payload: SendEmailPayload,
    ) -> None:
        """|coro|

        Sends the verification email.

        If an error occurs during the process,
        the error is handled and an error embed is sent.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        payload: :class:`.SendEmail`
            The email payload.
        """

        mail_generator = MailGenerator(payload.config)

        try:
            message = mail_generator.generate_verification_message(
                payload.member,
                payload.email,
                payload.code,
                payload.locale,
            )
        except MailGeneratorError as e:
            return await self.handle_error(interaction, e)

        mail_service = MailService(payload.config.smtp, payload.email)

        try:
            await mail_service.send_message(message)
            self._email_payload = payload
        except SMTPError as e:
            return await self.handle_error(interaction, e)

    async def resend_email(
        self,
        interaction: Interaction,
    ) -> None:
        """|coro|

        Resends the email.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.

        Raises
        ------
        ValueError
            No email payload to resend.
        """
        if self._email_payload is None:
            raise ValueError("No email payload to resend.")

        await self.send_email(interaction, self._email_payload)

    async def handle_index_input(self, interaction: Interaction, index: str) -> None:
        """|coro|

        Handles the index input.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        index: :class:`str`
            The index number provided by the user.
        """
        self._update_locale(interaction)
        self._update_member(interaction)

        await interaction.response.defer(ephemeral=True, with_message=True)

        try:
            index_taken = await self.service.is_index_taken(index)
        except SQLAlchemyError as e:
            return await self.handle_error(interaction, e)

        if index_taken:
            embed = IndexTakenEmbed(
                self.locale, self.service.data.external_button.label
            )
            return await self.edit_or_send_message(
                interaction, embed, view=None, delete_after=30
            )

        try:
            email = self.config.email_message.address_template.format(index=index)
        except KeyError as e:
            return await self.handle_error(interaction, e)

        code_length = self.config.code_length
        code = self.service.generate_verification_code(code_length)

        payload = SendEmailPayload(
            config=self.config,
            member=self.member,
            email=email,
            code=code,
            locale=self.locale,
        )

        await self.send_email(interaction, payload)
        await self.show_code_sent(interaction)

    async def show_code_sent(self, interaction: Interaction) -> None:
        """|coro|

        Shows the code sent embed.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        """
        self._update_locale(interaction)
        if self._email_payload is None:
            raise ValueError("No email payload to show code sent.")

        embed = CodeSentEmbed(self._email_payload.email, self.locale)
        view = CodeSentView(self, self.locale)
        await self.edit_or_send_message(interaction, embed, view)

    async def show_max_incorrect_attempts(self, interaction: Interaction) -> None:
        """|coro|

        Shows the max incorrect attempts embed.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        """
        self._update_locale(interaction)
        embed = MaxAttemptsEmbed(self.locale)
        await self.edit_message(embed, view=None, content=None, delete_after=15)

    async def _register_incorrect_attempt(self) -> None:
        """|coro|

        Registers an incorrect attempt.
        """
        self._incorrect_attempts += 1

    def _get_code_status(self, provided_code: str) -> CodeStatus:
        """Gets the code status.

        Parameters
        ----------
        provided_code: :class:`str`
            The provided code.

        Returns
        -------
        :class:`.CodeStatus`
            The code status.
        """
        if self._email_payload is None:
            return CodeStatus.UNKNOWN
        if provided_code == self._email_payload.code:
            return CodeStatus.VALID
        return CodeStatus.INVALID


class TargetVerificationManager(CodeVerificationManager):
    """A class to represent a target verification manager."""

    _verification_data: TargetVerificationData
    _input_data: TargetVerificationInputData

    @classmethod
    async def create_and_send(
        cls,
        handler: VerificationHandler,
        interaction: Interaction,
    ) -> TargetVerificationManager:
        """|coro|

        Creates a new instance of the target verification manager
        and sends the index input modal.

        Parameters
        ----------
        handler: :class:`.VerificationHandler`
            The verification handler.
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the verification process.

        Returns
        -------
        :class:`.TargetVerificationManager`
            The created target verification manager.
        """
        member: Member = interaction.user  # type: ignore
        instance = cls(handler, Locale(interaction.locale), member, None)  # type: ignore
        instance._input_data = TargetVerificationInputData()
        instance._verification_data = TargetVerificationData()
        modal = IndexInputModal(instance, instance.locale, handler.service.config)
        await interaction.response.send_modal(modal)
        return instance

    @classmethod
    async def create_and_send_predefined(
        cls,
        handler: VerificationHandler,
        interaction: Interaction,
        dto: VerificationDTO,
    ) -> TargetVerificationManager:
        """|coro|

        Creates a new instance of the target verification manager
        with predefined data and sends the data summary.

        This method should be used when the verification data is predefined
        and the target verification manager is created from the verification data.

        Parameters
        ----------
        handler: :class:`.VerificationHandler`
            The verification handler.
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the verification process.
        dto: :class:`.VerificationDTO`
            The verification data dto (for predefined data).

        Returns
        -------
        :class:`.TargetVerificationManager`
            The created target verification manager.

        Raises
        ------
        ValueError
            If the dto.index is not provided.
        """
        member: Member = interaction.user  # type: ignore
        instance = cls(handler, Locale(interaction.locale), member, None)  # type: ignore

        if dto.index is None:
            raise ValueError("The dto.index must be provided.")

        instance._input_data = TargetVerificationInputData(
            first_name=dto.first_name,
            last_name=dto.last_name,
        )

        instance._verification_data = TargetVerificationData(
            code_status=CodeStatus.UNNECESSARY,
            first_name=dto.first_name,
            last_name=dto.last_name,
            index=dto.index,
        )

        await instance.show_data_summary(interaction)
        return instance

    @override
    async def show_data_input_modal(
        self,
        interaction: Interaction,
    ) -> None:
        self._update_locale(interaction)

        payload = DataInputPayload(
            self.locale,
            self.config,
            self._email_payload.email if self._email_payload else None,
            self._input_data,
        )

        modal = TargetDataInputModal(self, payload)
        await interaction.response.send_modal(modal)

    @override
    async def handle_index_input(self, interaction: Interaction, index: str) -> None:
        self._verification_data.index = index
        return await super().handle_index_input(interaction, index)

    async def handle_target_data_input(
        self,
        interaction: Interaction,
        data: TargetVerificationInputData,
    ) -> None:
        """|coro|

        Handles the target data input.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        data: :class:`.TargetVerificationInputData`
            The target verification input data.
        """
        self._update_locale(interaction)

        self._input_data = data
        self._verification_data.update_from_input(data)

        if self._verification_data.code_status is not CodeStatus.UNNECESSARY:
            self._verification_data.code_status = self._get_code_status(data.code)

        if self._verification_data.code_status is CodeStatus.INVALID:
            self._incorrect_attempts += 1

        if self._incorrect_attempts >= self.config.max_attempts:
            return await self.show_max_incorrect_attempts(interaction)

        await self.show_data_summary(interaction)

    async def show_data_summary(self, interaction: Interaction) -> None:
        """|coro|

        Shows the data summary.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        """
        self._update_locale(interaction)

        payload = TargetDataSummaryPayload(
            first_name=self._verification_data.first_name,
            last_name=self._verification_data.last_name,
            index=self._verification_data.index,
            code_status=self._verification_data.code_status,
            locale=self.locale,
            config=self.config,
        )

        embed = TargetDataSummaryEmbed(payload)
        view = DataSummaryView(self, payload)
        await self.edit_or_send_message(interaction, embed, view)

    @override
    async def handle_confirm(self, interaction: Interaction) -> None:
        self._update_locale(interaction)

        await self.service.verify_target_member(
            self.member,
            self._verification_data,
        )

        embed = VerificationSuccessEmbed(self.locale)
        await self.edit_message(embed, view=None, content=None, delete_after=60)


class InternalVerificationManager(CodeVerificationManager):
    """A class to represent an internal verification manager."""

    _verification_data: InternalVerificationData
    _input_data: InternalVerificationInputData

    @classmethod
    async def create_and_send(
        cls,
        handler: VerificationHandler,
        interaction: Interaction,
    ) -> InternalVerificationManager:
        """|coro|

        Creates a new instance of the internal verification manager
        and sends the index input modal.

        Parameters
        ----------
        handler: :class:`.VerificationHandler`
            The verification handler.
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the verification process.

        Returns
        -------
        :class:`.InternalVerificationManager`
            The created internal verification manager.
        """
        member: Member = interaction.user  # type: ignore
        instance = cls(handler, Locale(interaction.locale), member, None)  # type: ignore
        instance._input_data = InternalVerificationInputData()
        instance._verification_data = InternalVerificationData()
        modal = IndexInputModal(instance, instance.locale, handler.service.config)
        await interaction.response.send_modal(modal)
        return instance

    @classmethod
    async def create_and_send_predefined(
        cls,
        handler: VerificationHandler,
        interaction: Interaction,
        dto: VerificationDTO,
    ) -> InternalVerificationManager:
        """|coro|

        Creates a new instance of the internal verification manager
        with predefined data and sends the data summary.

        This method should be used when the verification data is predefined
        and the internal verification manager is created from the verification data.

        Parameters
        ----------
        handler: :class:`.VerificationHandler`
            The verification handler.
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the verification process.
        dto: :class:`.VerificationDTO`
            The verification data dto (for predefined data).

        Returns
        -------
        :class:`.InternalVerificationManager`
            The created internal verification manager.

        Raises
        ------
        ValueError
            If the dto.index is not provided.
        """
        member: Member = interaction.user  # type: ignore
        instance = cls(handler, Locale(interaction.locale), member, None)  # type: ignore

        if not dto.index:
            raise ValueError("The dto.index must be provided.")

        instance._input_data = InternalVerificationInputData(
            first_name=dto.first_name,
            last_name=dto.last_name,
            study_info=dto.study_info or "",
            reason=dto.reason or "",
        )

        instance._verification_data = InternalVerificationData(
            code_status=CodeStatus.UNNECESSARY,
            first_name=dto.first_name,
            last_name=dto.last_name,
            study_info=dto.study_info or "",
            reason=dto.reason or "",
            index=dto.index,
        )

        await instance.show_data_summary(interaction)
        return instance

    @override
    async def show_data_input_modal(
        self,
        interaction: Interaction,
    ) -> None:
        self._update_locale(interaction)

        payload = DataInputPayload(
            self.locale,
            self.config,
            self._email_payload.email if self._email_payload else None,
            self._input_data,
        )

        modal = InternalDataInputModal(self, payload)
        await interaction.response.send_modal(modal)

    @override
    async def handle_index_input(self, interaction: Interaction, index: str) -> None:
        self._verification_data.index = index
        return await super().handle_index_input(interaction, index)

    async def handle_internal_data_input(
        self,
        interaction: Interaction,
        data: InternalVerificationInputData,
    ) -> None:
        """|coro|

        Handles the internal data input.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        data: :class:`.InternalVerificationInputData`
            The internal verification input data.
        """
        self._update_locale(interaction)

        self._input_data = data
        self._verification_data.update_from_input(data)

        if self._verification_data.code_status is not CodeStatus.UNNECESSARY:
            self._verification_data.code_status = self._get_code_status(data.code)

        if self._verification_data.code_status is CodeStatus.INVALID:
            self._incorrect_attempts += 1

        if self._incorrect_attempts >= self.config.max_attempts:
            return await self.show_max_incorrect_attempts(interaction)

        await self.show_data_summary(interaction)

    async def show_data_summary(self, interaction: Interaction) -> None:
        """|coro|

        Shows the data summary.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        """
        self._update_locale(interaction)

        payload = InternalDataSummaryPayload(
            first_name=self._verification_data.first_name,
            last_name=self._verification_data.last_name,
            index=self._verification_data.index,
            study_info=self._verification_data.study_info,
            reason=self._verification_data.reason,
            code_status=self._verification_data.code_status,
            locale=self.locale,
            config=self.config,
        )

        embed = InternalDataSummaryEmbed(payload)
        view = DataSummaryView(self, payload)
        await self.edit_or_send_message(interaction, embed, view)

    @override
    async def handle_confirm(self, interaction: Interaction) -> None:
        self._update_locale(interaction)

        await self.service.verify_internal_member(
            self.member,
            self._verification_data,
        )

        embed = VerificationSuccessEmbed(self.locale)
        await self.edit_message(embed, view=None, content=None, delete_after=60)


class ExternalVerificationManager(VerificationManager):
    """A class to represent an internal verification manager."""

    _verification_data: ExternalVerificationData
    _input_data: ExternalVerificationInputData

    @classmethod
    async def create_and_send(
        cls,
        handler: VerificationHandler,
        interaction: Interaction,
    ) -> ExternalVerificationManager:
        """|coro|

        Creates a new instance of the external verification manager
        and sends the index input modal.

        Parameters
        ----------
        handler: :class:`.VerificationHandler`
            The verification handler.
        interaction: :class:`nextcord.Interaction`
            The interaction that triggered the verification process.

        Returns
        -------
        :class:`.ExternalVerificationManager`
            The created internal verification manager.
        """
        member: Member = interaction.user  # type: ignore
        instance = cls(handler, Locale(interaction.locale), member, None)  # type: ignore
        instance._input_data = ExternalVerificationInputData()
        instance._verification_data = ExternalVerificationData()
        await instance.show_data_input_modal(interaction)
        return instance

    @override
    async def show_data_input_modal(
        self,
        interaction: Interaction,
    ) -> None:
        self._update_locale(interaction)

        payload = DataInputPayload(
            self.locale,
            self.config,
            email=None,
            data=self._input_data,
        )

        modal = ExternalDataInputModal(self, payload)
        await interaction.response.send_modal(modal)

    async def handle_external_data_input(
        self,
        interaction: Interaction,
        data: ExternalVerificationInputData,
    ) -> None:
        """|coro|

        Handles the external data input.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        data: :class:`.ExternalVerificationInputData`
            The external verification input data.
        """
        self._update_locale(interaction)

        self._input_data = data
        self._verification_data.update_from_input(data)

        await self.show_data_summary(interaction)

    async def show_data_summary(self, interaction: Interaction) -> None:
        """|coro|

        Shows the data summary.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction.
        """
        self._update_locale(interaction)

        payload = ExternalDataSummaryPayload(
            first_name=self._verification_data.first_name,
            last_name=self._verification_data.last_name,
            reason=self._verification_data.reason,
            locale=self.locale,
            config=self.config,
        )

        embed = ExternalDataSummaryEmbed(payload)
        view = DataSummaryView(self, payload)
        await self.edit_or_send_message(interaction, embed, view)

    @override
    async def handle_confirm(self, interaction: Interaction) -> None:
        self._update_locale(interaction)
        self._update_member(interaction)

        await self.service.handle_guest_verification_request(
            self.member, self._verification_data
        )

        embed = VerificationRequestSentEmbed(self.locale)
        await self.edit_message(embed, view=None, content=None)
