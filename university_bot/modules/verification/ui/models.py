# SPDX-License-Identifier: MIT
"""A module to define models for the verification UI."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass

from university_bot.modules.verification.ui.enums import CodeStatus

__all__ = (
    "VerificationInputData",
    "TargetVerificationInputData",
    "InternalVerificationInputData",
    "ExternalVerificationInputData",
    "TargetVerificationData",
    "InternalVerificationData",
    "ExternalVerificationData",
)


@dataclass(slots=True, frozen=True)
class VerificationInputData(ABC):
    """A class to represent a verification input data."""

    first_name: str = ""
    last_name: str = ""


@dataclass(slots=True, frozen=True)
class TargetVerificationInputData(VerificationInputData):
    """A class to represent a target verification input data."""

    code: str = ""


@dataclass(slots=True, frozen=True)
class InternalVerificationInputData(VerificationInputData):
    """A class to represent an internal verification input data."""

    code: str = ""
    study_info: str = ""
    reason: str = ""


@dataclass(slots=True, frozen=True)
class ExternalVerificationInputData(VerificationInputData):
    """A class to represent an external verification input data."""

    reason: str = ""


@dataclass(slots=True)
class TargetVerificationData:
    """A class to represent a target verification data."""

    code_status: CodeStatus = CodeStatus.UNKNOWN
    first_name: str = ""
    last_name: str = ""
    index: str = ""

    def update_from_input(self, data: TargetVerificationInputData) -> None:
        """Updates the target verification data from the input data."""
        self.first_name = data.first_name
        self.last_name = data.last_name


@dataclass(slots=True)
class InternalVerificationData:
    """A class to represent an internal verification data."""

    code_status: CodeStatus = CodeStatus.UNKNOWN
    first_name: str = ""
    last_name: str = ""
    study_info: str = ""
    reason: str = ""
    index: str = ""

    def update_from_input(self, data: InternalVerificationInputData) -> None:
        """Updates the internal verification data from the input data."""
        self.first_name = data.first_name
        self.last_name = data.last_name
        self.study_info = data.study_info
        self.reason = data.reason


@dataclass(slots=True)
class ExternalVerificationData:
    """A class to represent an external verification data."""

    first_name: str = ""
    last_name: str = ""
    reason: str = ""

    def update_from_input(self, data: ExternalVerificationInputData) -> None:
        """Updates the external verification data from the input data."""
        self.first_name = data.first_name
        self.last_name = data.last_name
        self.reason = data.reason
