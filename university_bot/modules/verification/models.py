# SPDX-License-Identifier: MIT
"""A module to define models for the verification system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from nextcord import Member

if TYPE_CHECKING:
    import datetime

    from .dto import VerificationDTO
    from .enums import VerificationType

__all__ = (
    "VerificationData",
    "MatchingMember",
)


@dataclass(slots=True, frozen=True)
class VerificationData:  # pylint: disable=too-many-instance-attributes
    """Represents a verification data."""

    user_id: int
    first_name: str
    last_name: str
    verified_at: datetime.datetime | None
    left_at: datetime.datetime | None
    index: str | None
    reason: str | None
    study_info: str | None
    type: VerificationType

    @classmethod
    def from_dto(cls, dto: VerificationDTO) -> VerificationData:
        """Creates a verification data from a data transfer object."""
        return cls(
            user_id=dto.user_id,
            first_name=dto.first_name,
            last_name=dto.last_name,
            verified_at=dto.verified_at,
            left_at=dto.left_at,
            index=dto.index,
            reason=dto.reason,
            study_info=dto.study_info,
            type=dto.type,
        )

    def to_dto(self) -> VerificationDTO:
        """Converts the verification data to a data transfer object."""
        return VerificationDTO(
            user_id=self.user_id,
            first_name=self.first_name,
            last_name=self.last_name,
            verified_at=self.verified_at,
            left_at=self.left_at,
            index=self.index,
            reason=self.reason,
            study_info=self.study_info,
            type=self.type,
        )


@dataclass(slots=True, frozen=True)
class MatchingMember:
    """Represents a matching member.

    Attributes
    ----------
    verification_data: :class:`VerificationData`
        The member's verification data.
    member: :class:`nextcord.Member`
        The member.
    """

    verification_data: VerificationData
    member: Member
