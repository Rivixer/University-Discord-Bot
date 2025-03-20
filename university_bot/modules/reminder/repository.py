# SPDX-License-Identifier: MIT
"""A module providing the repository for reminder data access.

This module defines the ReminderRepository class which encapsulates
database operations for reminders, such as adding, updating, deleting,
and retrieving ReminderDTO instances.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from university_bot import get_logger

from .dto import ReminderDTO
from .exceptions import RepositoryError

__all__ = ("ReminderRepository",)

_logger = get_logger(__name__)


class ReminderRepository:
    """Repository for accessing reminders in the database.

    Attributes
    ----------
    async_session_factory: Callable[[], AsyncSession]
        A callable that returns an instance of an asynchronous SQLAlchemy session.
    """

    async_session_factory: Callable[[], AsyncSession]

    def __init__(self, async_session_factory: Callable[[], AsyncSession]) -> None:
        """Initializes the repository with the given asynchronous session factory.

        Parameters
        ----------
        async_session_factory: Callable[[], :class:`sqlalchemy.ext.asyncio.AsyncSession`]
            A callable that returns an instance of an asynchronous SQLAlchemy session.
        """
        self.async_session_factory = async_session_factory

    async def update_event_reminders(
        self, event_id: str, reminders: list[ReminderDTO]
    ) -> None:
        """|coro|

        Updates the reminders associated with an event.

        Parameters
        ----------
        event_id: :class:`int`
            The unique identifier of the event.
        reminders: list[:class:`ReminderDTO`]
            The reminders to associate with the event.

        Raises
        ------
        RepositoryError
            If an error occurs while updating the event reminders in the database.
        """
        try:
            async with self.async_session_factory() as session:
                async with session.begin():
                    stmt = (
                        select(ReminderDTO)
                        .where(ReminderDTO.event_id == event_id)
                        .with_for_update()
                    )
                    result = await session.execute(stmt)
                    existing_reminders = result.scalars().all()

                    for reminder in existing_reminders:
                        await session.delete(reminder)

                    session.add_all(reminders)
        except SQLAlchemyError as e:
            _logger.exception("Failed to update event reminders in the database.")
            raise RepositoryError(
                "Failed to update event reminders in the database."
            ) from e
        except (AttributeError, TypeError, ValueError) as e:
            _logger.exception(
                "Invalid event reminder data provided while updating event reminders."
            )
            raise RepositoryError(
                "Invalid event reminder data provided while updating event reminders."
            ) from e

    async def update_reminder(
        self,
        reminder_id: str,
        domain_reminder: ReminderDTO,
    ) -> bool:
        """|coro|

        Updates a reminder in the database with new data.

        The domain_reminder is expected to have attributes corresponding to the columns
        in :class:`.ReminderDTO`.

        Parameters
        ----------
        reminder_id: :class:`str`
            The unique identifier of the reminder to update.
        domain_reminder: :class:`.Event`
            The domain reminder containing the updated reminder data.

        Returns
        -------
        :class:`bool`
            ``True`` if the reminder was found and updated, ``False`` otherwise.

        Raises
        ------
        RepositoryError
            If an error occurs while updating the reminder in the database
            or if the reminder data is invalid.
        """
        try:
            async with self.async_session_factory() as session:
                async with session.begin():
                    orig_reminder: ReminderDTO | None = await session.get(
                        ReminderDTO, reminder_id
                    )

                    if orig_reminder is None:
                        return False

                    for column in orig_reminder.__table__.columns:
                        if column.primary_key:
                            continue

                        attr = getattr(domain_reminder, column.name)
                        setattr(orig_reminder, column.name, attr)
        except SQLAlchemyError as e:
            _logger.exception("Failed to update reminder in the database.")
            raise RepositoryError("Failed to update reminder in the database.") from e
        except (AttributeError, TypeError, ValueError) as e:
            _logger.exception("Invalid reminder data.")
            raise RepositoryError("Invalid reminder data.") from e

        return True

    async def get_reminders(self, event_id: str | None = None) -> Sequence[ReminderDTO]:
        """|coro|

        Retrieves reminders from the database.

        Parameters
        ----------
        event_id: :class:`str` | `None`
            If provided, only reminders associated with the given event ID will be retrieved.
            Defaults to retrieving all reminders.

        Returns
        -------
        Sequence[:class:`.ReminderDTO`]
            A sequence of reminder DTOs.

        Raises
        ------
        RepositoryError
            If an error occurs while retrieving reminders from the database.
        """
        try:
            async with self.async_session_factory() as session:
                stmt = select(ReminderDTO).options(selectinload(ReminderDTO.event))
                if event_id is not None:
                    stmt = stmt.where(ReminderDTO.event_id == event_id)
                result = await session.execute(stmt)
                return result.scalars().all()
        except SQLAlchemyError as e:
            _logger.exception("Failed to retrieve reminders from the database.")
            raise RepositoryError(
                "Failed to retrieve reminders from the database."
            ) from e
        except (AttributeError, TypeError, ValueError) as e:
            _logger.exception("Invalid parameters provided while retrieving reminders.")
            raise RepositoryError(
                "Invalid parameters provided while retrieving reminders."
            ) from e
