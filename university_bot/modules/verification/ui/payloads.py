# SPDX-License-Identifier: MIT
"""A module providing payloads for the verification UI."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from .enums import CodeStatus
from .models import VerificationInputData

if TYPE_CHECKING:
    from nextcord import Locale, Member

    from ..config import VerificationConfig

__all__ = (
    "DataInputPayload",
    "DataSummaryPayload",
    "TargetDataSummaryPayload",
    "InternalDataSummaryPayload",
    "ExternalDataSummaryPayload",
    "SendEmailPayload",
)


@dataclass(slots=True, frozen=True)
class DataInputPayload[T: VerificationInputData]:
    """A class to represent a data input payload."""

    locale: Locale
    config: VerificationConfig
    email: str | None
    data: T


@dataclass(slots=True, frozen=True)
class DataSummaryPayload(ABC):
    """A class to represent a data summary payload."""

    first_name: str
    last_name: str
    locale: Locale
    config: VerificationConfig

    def is_valid(self) -> bool:
        """Return whether the data summary payload is valid."""
        return bool(self.first_name) and bool(self.last_name)


@dataclass(slots=True, frozen=True)
class TargetDataSummaryPayload(DataSummaryPayload):
    """A class to represent a target data summary payload."""

    index: str
    code_status: CodeStatus

    @override
    def is_valid(self) -> bool:
        return (
            DataSummaryPayload.is_valid(self)
            and bool(self.index)
            and self.code_status in (CodeStatus.VALID, CodeStatus.UNNECESSARY)
        )


@dataclass(slots=True, frozen=True)
class InternalDataSummaryPayload(DataSummaryPayload):
    """A class to represent an internal data summary payload."""

    index: str
    study_info: str
    reason: str
    code_status: CodeStatus

    def is_valid(self) -> bool:
        return (
            DataSummaryPayload.is_valid(self)
            and bool(self.index)
            and bool(self.study_info)
            and bool(self.reason)
            and self.code_status in (CodeStatus.VALID, CodeStatus.UNNECESSARY)
        )


@dataclass(slots=True, frozen=True)
class ExternalDataSummaryPayload(DataSummaryPayload):
    """A class to represent an external data summary payload."""

    reason: str

    def is_valid(self) -> bool:
        return DataSummaryPayload.is_valid(self) and bool(self.reason)


@dataclass(slots=True, frozen=True)
class SendEmailPayload:
    """A class to represent a send email payload."""

    config: VerificationConfig
    member: Member
    email: str
    code: str
    locale: Locale
