"""
Database models for the voice channel service.

Two schema-contained tables:
- `voice_channel.state`: Tracks the state of voice channels.
- `voice_channel.config`: Stores configuration for voice channels per guild.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import Index


class Base(DeclarativeBase):
    """Base class for all models in the voice channel service."""


_SCHEMA = "voice_channel"


class ChannelState(Base):
    """Tracks the dynamic state of voice channels.

    Attributes
    ----------
    channel_id : int
        Primary key. The Discord ID of the voice channel.
    guild_id : int
        The Discord ID of the guild this channel belongs to.
    active_users : int
        The number of active users in this channel.
    pending_deletion : bool
        Whether the request to delete this channel is pending.
    last_rename_at : datetime | None
        The timestamp of the last successful rename operation, or None if never renamed.
    rename_count : int
        The number of renames performed in the current window.
    rename_window_start : datetime | None
        The start of the current rename-count window for throttling.
    """

    __tablename__ = "state"
    __table_args__ = (
        Index("ix_vcs_guild_id", "guild_id"),
        {"schema": _SCHEMA},
    )

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_deletion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    last_rename_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rename_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rename_window_start: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )


class ServiceConfig(Base):
    """Stores configuration for voice channels per guild.

    Attributes
    ----------
    guild_id : int
        Primary key. The Discord ID of the guild.
    category_id : int
        The Discord ID of the category under which voice channels are created.
    default_name_template : str
        The template for generating default channel names.
    available_names : list[str]
        List of available names for voice channels in this guild.
    """

    __tablename__ = "config"
    __table_args__ = {"schema": _SCHEMA}

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    default_name_template: Mapped[str] = mapped_column(
        String, nullable=False, default="Room {n}"
    )
    available_names: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSONB),
        nullable=False,
        default=list,
    )
