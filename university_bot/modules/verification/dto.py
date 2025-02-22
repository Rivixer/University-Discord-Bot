# SPDX-License-Identifier: MIT
"""A module providing data transfer objects for the calendar."""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, DateTime, Enum, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column

from university_bot.modules.verification.config import InputLimits

from .enums import VerificationType

# pylint: disable=too-few-public-methods

__all__ = (
    "VerificationDTO",
    "VerificationRequestDTO",
)

Base = declarative_base()


class VerificationDTO(Base):
    """A class to represent a verification."""

    __tablename__ = "verifications"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    first_name: Mapped[str] = mapped_column(
        String(InputLimits.FIRST_NAME),
        nullable=False,
    )
    last_name: Mapped[str] = mapped_column(
        String(InputLimits.LAST_NAME),
        nullable=False,
    )
    verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        nullable=True,  # For predefined verifications
    )
    left_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    index: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    study_info: Mapped[str | None] = mapped_column(
        String(InputLimits.STUDY_INFO),
        nullable=True,
    )
    type: Mapped[VerificationType] = mapped_column(
        Enum(VerificationType, native_enum=False, create_constraint=True),
        nullable=False,
    )


class VerificationRequestDTO(Base):
    """A class to represent a verification request."""

    __tablename__ = "verification_requests"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    first_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    last_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    requested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    request_message_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
