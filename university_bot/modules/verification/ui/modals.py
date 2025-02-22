# SPDX-License-Identifier: MIT
"""A module containing the verification UI modals."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar, override

from nextcord import TextInputStyle
from nextcord.ui import Modal, TextInput, View

from university_bot import Localization
from university_bot.mixins import LocalizedMixin
from university_bot.utils import LocalizedGroup

from .models import (
    ExternalVerificationInputData,
    InternalVerificationInputData,
    TargetVerificationInputData,
)
from ..config import InputLimits

if TYPE_CHECKING:
    from nextcord import Locale

    from university_bot import Interaction

    from .managers import (
        CodeVerificationManager,
        ExternalVerificationManager,
        InternalVerificationManager,
        TargetVerificationManager,
        VerificationManager,
    )
    from .payloads import DataInputPayload
    from ..config import VerificationConfig

    _ManagerT = TypeVar("_ManagerT", bound=VerificationManager)
else:
    TargetVerificationManager = object
    InternalVerificationManager = object
    ExternalVerificationManager = object
    _ManagerT = TypeVar("_ManagerT")

__all__ = (
    "IndexInputModal",
    "TargetDataInputModal",
    "InternalDataInputModal",
    "ExternalDataInputModal",
)

_loc = Localization.get_group("ui.verification.modals")


class IndexInputModal(LocalizedMixin, Modal):
    """An input modal for the index number."""

    _manager: CodeVerificationManager
    _config: VerificationConfig
    _text_input: TextInput[View]

    def __init__(
        self,
        manager: CodeVerificationManager,
        locale: Locale,
        config: VerificationConfig,
    ) -> None:
        loc_group = _loc.get_group("index_input")
        LocalizedMixin.__init__(self, locale, loc_group)
        Modal.__init__(self, title=self.get_loc("title", "Student registration"))

        self._manager = manager
        self._config = config

        inputs_loc = self.get_loc_group("text_inputs")
        self._text_input = TextInput[View](
            label=inputs_loc.get("index.label", "Your index number:"),
            placeholder=config.index_placeholder,
            min_length=config.index_min_length,
            max_length=config.index_max_length,
            required=True,
        )

        self.add_item(self._text_input)  # type: ignore

    @override
    async def callback(self, interaction: Interaction) -> None:
        await self._manager.handle_index_input(
            interaction, self._text_input.value or ""
        )


class _DataInputModel(LocalizedMixin, Modal, Generic[_ManagerT], ABC):
    """A base class for the data input modals."""

    _manager: _ManagerT
    _config: VerificationConfig
    _inputs_loc: LocalizedGroup

    def __init__(
        self,
        manager: _ManagerT,
        config: VerificationConfig,
        loc_group_key: str,
        title_default: str,
    ) -> None:
        loc_group = _loc.get_group(loc_group_key)
        LocalizedMixin.__init__(self, manager.locale, loc_group)
        Modal.__init__(
            self,
            title=self.get_loc("title", title_default),
        )

        self._manager = manager
        self._config = config

        self._inputs_loc = self.get_loc_group("text_inputs")

    def _create_code_input(self, default_value: str, email: str) -> TextInput[View]:
        return TextInput[View](
            label=self._inputs_loc.get("code.label", "Code:"),
            placeholder=self._inputs_loc.get(
                "code.placeholder",
                "Sent to {email}",
            ).replace("{email}", email),
            default_value=default_value,
            min_length=self._config.code_length,
            max_length=self._config.code_length,
            required=True,
        )

    def _create_first_name_input(self, default_value: str) -> TextInput[View]:
        return TextInput[View](
            label=self._inputs_loc.get("first_name.label", "First name:"),
            placeholder=self._inputs_loc.get("first_name.placeholder", "John"),
            default_value=default_value,
            max_length=InputLimits.FIRST_NAME,
            required=True,
        )

    def _create_last_name_input(self, default_value: str) -> TextInput[View]:
        return TextInput[View](
            label=self._inputs_loc.get("last_name.label", "Last name:"),
            placeholder=self._inputs_loc.get("last_name.placeholder", "Doe"),
            default_value=default_value,
            max_length=InputLimits.LAST_NAME,
            required=True,
        )

    def _create_study_info_input(self, default_value: str) -> TextInput[View]:
        return TextInput[View](
            label=self._inputs_loc.get("study_info.label", "Study information:"),
            placeholder=self._inputs_loc.get(
                "study_info.placeholder",
                "faculty, major, degree type (BSc/BEng/MSc/Integrated), "
                "study mode (full-time/part-time), year",
            ),
            default_value=default_value,
            style=TextInputStyle.paragraph,
            max_length=InputLimits.STUDY_INFO,
            required=True,
        )

    def _create_reason_input(
        self, default_value: str, placeholder: str
    ) -> TextInput[View]:
        return TextInput[View](
            label=self._inputs_loc.get("reason.label", "Reason for joining:"),
            placeholder=placeholder,
            default_value=default_value,
            style=TextInputStyle.paragraph,
            max_length=1024,
            required=True,
        )


@dataclass(slots=True)
class _TargetDataTextInputs:
    code: TextInput[View] | None
    first_name: TextInput[View]
    last_name: TextInput[View]

    def add_items(self, modal: Modal) -> None:
        """Adds the text inputs to the modal."""
        if self.code:
            modal.add_item(self.code)  # type: ignore
        modal.add_item(self.first_name)  # type: ignore
        modal.add_item(self.last_name)  # type: ignore

    def get_data(self) -> TargetVerificationInputData:
        """Returns the input data from the text inputs."""
        assert self.first_name.value is not None, "First name is required"
        assert self.last_name.value is not None, "Last name is required"
        return TargetVerificationInputData(
            first_name=self.first_name.value,
            last_name=self.last_name.value,
            code=self.code.value if self.code and self.code.value else "",
        )


class TargetDataInputModal(_DataInputModel[TargetVerificationManager]):
    """An input modal for the target data."""

    def __init__(
        self,
        manager: TargetVerificationManager,
        payload: DataInputPayload[TargetVerificationInputData],
    ) -> None:
        super().__init__(
            manager,
            payload.config,
            "target_data_input",
            "Student registration",
        )

        if payload.email is not None:
            code_input = self._create_code_input(payload.data.code, payload.email)
        else:
            code_input = None

        first_name_input = self._create_first_name_input(payload.data.first_name)
        last_name_input = self._create_last_name_input(payload.data.last_name)

        self._text_inputs = _TargetDataTextInputs(
            code=code_input,
            first_name=first_name_input,
            last_name=last_name_input,
        )

        self._text_inputs.add_items(self)

    @override
    async def callback(self, interaction: Interaction) -> None:
        data = self._text_inputs.get_data()
        await self._manager.handle_target_data_input(interaction, data)


@dataclass(slots=True)
class _InternalDataTextInputs:
    code: TextInput[View] | None
    first_name: TextInput[View]
    last_name: TextInput[View]
    study_info: TextInput[View]
    reason: TextInput[View]

    def add_items(self, modal: Modal) -> None:
        """Adds the text inputs to the modal."""
        if self.code:
            modal.add_item(self.code)  # type: ignore
        modal.add_item(self.first_name)  # type: ignore
        modal.add_item(self.last_name)  # type: ignore
        modal.add_item(self.study_info)  # type: ignore
        modal.add_item(self.reason)  # type: ignore

    def get_data(self) -> InternalVerificationInputData:
        """Returns the input data from the text inputs."""
        assert self.first_name.value is not None, "First name is required"
        assert self.last_name.value is not None, "Last name is required"
        assert self.study_info.value is not None, "Study is required"
        assert self.reason.value is not None, "Reason is required"
        return InternalVerificationInputData(
            first_name=self.first_name.value,
            last_name=self.last_name.value,
            code=self.code.value if self.code and self.code.value else "",
            study_info=self.study_info.value,
            reason=self.reason.value,
        )


class InternalDataInputModal(_DataInputModel[InternalVerificationManager]):
    """An input modal for the internal data."""

    def __init__(
        self,
        manager: InternalVerificationManager,
        payload: DataInputPayload[InternalVerificationInputData],
    ) -> None:

        super().__init__(
            manager,
            payload.config,
            "internal_data_input",
            "Student (guest) registration",
        )

        if payload.email is not None:
            code_input = self._create_code_input(payload.data.code, payload.email)
        else:
            code_input = None

        first_name_input = self._create_first_name_input(payload.data.first_name)
        last_name_input = self._create_last_name_input(payload.data.last_name)
        study_input = self._create_study_info_input(payload.data.study_info)

        placeholder = self._inputs_loc.get(
            "reason.placeholder",
            "I'm a lower-year student and would like to access your study materials.",
        )
        reason_input = self._create_reason_input(payload.data.reason, placeholder)

        self._text_inputs = _InternalDataTextInputs(
            code=code_input,
            first_name=first_name_input,
            last_name=last_name_input,
            study_info=study_input,
            reason=reason_input,
        )

        self._text_inputs.add_items(self)

    @override
    async def callback(self, interaction: Interaction) -> None:
        data = self._text_inputs.get_data()
        await self._manager.handle_internal_data_input(interaction, data)


@dataclass(slots=True)
class _ExternalDataTextInputs:
    first_name: TextInput[View]
    last_name: TextInput[View]
    reason: TextInput[View]

    def add_items(self, modal: Modal) -> None:
        """Adds the text inputs to the modal."""
        modal.add_item(self.first_name)  # type: ignore
        modal.add_item(self.last_name)  # type: ignore
        modal.add_item(self.reason)  # type: ignore

    def get_data(self) -> ExternalVerificationInputData:
        """Returns the input data from the text inputs."""
        assert self.first_name.value is not None, "First name is required"
        assert self.last_name.value is not None, "Last name is required"
        assert self.reason.value is not None, "Reason is required"
        return ExternalVerificationInputData(
            first_name=self.first_name.value,
            last_name=self.last_name.value,
            reason=self.reason.value,
        )


class ExternalDataInputModal(_DataInputModel[ExternalVerificationManager]):
    """An input modal for the external data."""

    def __init__(
        self,
        manager: ExternalVerificationManager,
        payload: DataInputPayload[ExternalVerificationInputData],
    ) -> None:

        super().__init__(
            manager,
            payload.config,
            "external_data_input",
            "Guest registration",
        )

        first_name_input = self._create_first_name_input(payload.data.first_name)
        last_name_input = self._create_last_name_input(payload.data.last_name)

        placeholder = self._inputs_loc.get(
            "reason.placeholder",
            "I study at X university and would like to access your study materials.",
        )
        reason_input = self._create_reason_input(payload.data.reason, placeholder)

        self._text_inputs = _ExternalDataTextInputs(
            first_name=first_name_input,
            last_name=last_name_input,
            reason=reason_input,
        )

        self._text_inputs.add_items(self)

    @override
    async def callback(self, interaction: Interaction) -> None:
        data = self._text_inputs.get_data()
        await self._manager.handle_external_data_input(interaction, data)
