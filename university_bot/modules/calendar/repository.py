# SPDX-License-Identifier: MIT
"""A module providing the repository for calendar data access.

This module defines the CalendarRepository class which encapsulates
database operations for calendar events, such as adding, updating,
deleting, and retrieving events.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Callable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from university_bot import get_logger

from .dto import EventDTO
from .enums import EventVisibility
from .exceptions import RepositoryError

if TYPE_CHECKING:
    from .models import Event

__all__ = ("CalendarRepository",)

_logger = get_logger(__name__)


class CalendarRepository:
    """Repository for accessing calendar events in the database.

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

    async def add_event(self, event_dto: EventDTO) -> None:
        """|coro|

        Adds an event to the database.

        Parameters
        ----------
        event_dto: :class:`EventDTO`
            The data transfer object representing the event.

        Raises
        ------
        RepositoryError
            If an error occurs while adding the event to the database
            or if the event data is invalid.
        """
        try:
            async with self.async_session_factory() as session:
                async with session.begin():
                    session.add(event_dto)
        except SQLAlchemyError as e:
            _logger.exception("Failed to add event to the database.")
            raise RepositoryError("Failed to add event to the database.") from e
        except (AttributeError, TypeError, ValueError) as e:
            _logger.exception("Invalid event data.")
            raise RepositoryError("Invalid event data.") from e

    async def delete_event(self, event_id: str) -> bool:
        """|coro|

        Deletes an event by its ID.

        Parameters
        ----------
        event_id: :class:`str`
            The unique identifier of the event to delete.

        Returns
        -------
        :class:`bool`
            ``True`` if the event was found and deleted, ``False`` otherwise.

        Raises
        ------
        RepositoryError
            If an error occurs while deleting the event from the database
            or if the event ID is invalid.
        """
        try:
            async with self.async_session_factory() as session:
                async with session.begin():
                    event_dto: EventDTO | None = await session.get(EventDTO, event_id)

                    if event_dto is None:
                        return False

                    await session.delete(event_dto)
        except SQLAlchemyError as e:
            _logger.exception("Failed to delete event from the database.")
            raise RepositoryError("Failed to delete event from the database.") from e
        except (AttributeError, TypeError, ValueError) as e:
            _logger.exception("Invalid event ID.")
            raise RepositoryError("Invalid event ID.") from e

        return True

    async def update_event(self, event_id: str, domain_event: Event) -> bool:
        """|coro|

        Updates an event in the database with new data.

        The domain_event is expected to have attributes corresponding to the columns
        in :class:`.EventDTO`.

        Parameters
        ----------
        event_id: :class:`str`
            The unique identifier of the event to update.
        domain_event: :class:`.Event`
            The domain event containing the updated event data.

        Returns
        -------
        :class:`bool`
            ``True`` if the event was found and updated, ``False`` otherwise.

        Raises
        ------
        RepositoryError
            If an error occurs while updating the event in the database
            or if the event data is invalid.
        """
        try:
            async with self.async_session_factory() as session:
                async with session.begin():
                    orig_event: EventDTO | None = await session.get(EventDTO, event_id)

                    if orig_event is None:
                        return False

                    for column in orig_event.__table__.columns:
                        if column.primary_key:
                            continue

                        attr = getattr(domain_event, column.name)
                        setattr(orig_event, column.name, attr)
        except SQLAlchemyError as e:
            _logger.exception("Failed to update event in the database.")
            raise RepositoryError("Failed to update event in the database.") from e
        except (AttributeError, TypeError, ValueError) as e:
            _logger.exception("Invalid event data.")
            raise RepositoryError("Invalid event data.") from e

        return True

    async def get_event_by_id(self, event_id: str) -> EventDTO | None:
        """|coro|

        Retrieves an event by its ID.

        Parameters
        ----------
        event_id: :class:`str`
            The unique identifier of the event to retrieve.

        Returns
        -------
        :class:`.EventDTO` | `None`
            The event DTO if found, `None` otherwise.

        Raises
        ------
        RepositoryError
            If an error occurs while retrieving the event from the database
            or if the event ID is invalid.
        """
        try:
            async with self.async_session_factory() as session:
                return await session.get(EventDTO, event_id)
        except SQLAlchemyError as e:
            _logger.exception("Failed to retrieve event from the database.")
            raise RepositoryError("Failed to retrieve event from the database.") from e
        except (AttributeError, TypeError, ValueError) as e:
            _logger.exception("Invalid event ID.")
            raise RepositoryError("Invalid event ID.") from e

    async def get_events(
        self, visibility: EventVisibility = EventVisibility.ALL
    ) -> Sequence[EventDTO]:
        """|coro|

        Retrieves events from the database filtered by visibility.

        Parameters
        ----------
        visibility: :class:`.EventVisibility`
            The visibility filter to apply (defaults to all events).

        Returns
        -------
        Sequence[:class:`.EventDTO`]
            A sequence of event DTOs matching the visibility filter.

        Raises
        ------
        RepositoryError
            If an error occurs while retrieving events from the database
            or if the visibility filter is invalid.
        """
        try:
            async with self.async_session_factory() as session:
                stmt = select(EventDTO).options(selectinload(EventDTO.reminders))

                if visibility is EventVisibility.VISIBLE:
                    stmt = stmt.where(EventDTO.is_hidden.is_(False))
                elif visibility is EventVisibility.HIDDEN:
                    stmt = stmt.where(EventDTO.is_hidden.is_(True))

                result = await session.execute(stmt)
                return result.scalars().all()
        except SQLAlchemyError as e:
            _logger.exception("Failed to retrieve events from the database.")
            raise RepositoryError("Failed to retrieve events from the database.") from e
        except (AttributeError, TypeError, ValueError) as e:
            _logger.exception("Invalid visibility filter.")
            raise RepositoryError("Invalid visibility filter.") from e

    async def remove_deprecated_events(
        self, today: datetime.date
    ) -> Sequence[EventDTO]:
        """|coro|

        Removes events with a date earlier than today.

        Parameters
        ----------
        today: :class:`datetime.date`
            The reference date; all events with a date less than today will be removed.

        Returns
        -------
        Sequence[:class:`.EventDTO`]
            A sequence of removed event DTOs.

        Raises
        ------
        RepositoryError
            If an error occurs while removing deprecated events from the database.
        """
        try:
            async with self.async_session_factory() as session:
                stmt = select(EventDTO).where(EventDTO.date < today)
                result = await session.execute(stmt)
                deprecated_events: Sequence[EventDTO] = result.scalars().all()

                if deprecated_events:
                    delete_stmt = delete(EventDTO).where(EventDTO.date < today)
                    await session.execute(delete_stmt)
                    await session.commit()
        except SQLAlchemyError as e:
            _logger.exception("Failed to remove deprecated events from the database.")
            raise RepositoryError(
                "Failed to remove deprecated events from the database."
            ) from e

        return deprecated_events
