# SPDX-License-Identifier: MIT
"""A module to provide verification services."""

from __future__ import annotations

import asyncio
import datetime
import json
import random
import string
from collections.abc import Callable
from typing import TYPE_CHECKING, Sequence, override

import sqlalchemy
from nextcord import Embed, HTTPException, Locale, Member
from nextcord.ui import View
from nextcord.utils import MISSING
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from university_bot import MessageData, ResourceFetchFailed, get_logger
from university_bot.database import create_tables_if_not_exist
from university_bot.mixins.configuration import (
    ConfigurationServiceMixin,
    InvalidConfigurationError,
)
from university_bot.mixins.static_message import StaticViewMixin
from university_bot.modules.verification.enums import VerificationType
from university_bot.modules.verification.models import MatchingMember
from university_bot.modules.verification.ui.embeds import VerificationRequestEmbed
from university_bot.modules.verification.ui.models import (
    ExternalVerificationData,
    InternalVerificationData,
    TargetVerificationData,
)
from university_bot.utils2 import Matcher, SmartDict
from university_bot.utils.fetches import fetch_guild_member, fetch_message
from university_bot.utils.localization import Localization

from .config import VerificationConfig, VerificationDataConfig
from .dto import Base, VerificationDTO, VerificationRequestDTO
from .exceptions import (
    DisabledFeatureError,
    MissingPermissionsError,
    VerificationFailedError,
)
from .handler import VerificationHandler
from .ui import VerificationView

if TYPE_CHECKING:
    from pathlib import Path

    from university_bot import UniversityBot


__all__ = ("VerificationService",)

_logger = get_logger(__name__)


class VerificationService(
    ConfigurationServiceMixin[VerificationDataConfig],
    StaticViewMixin[
        VerificationHandler,
        VerificationView,
        VerificationDataConfig,
    ],
):
    """A service to manage the verification system.

    Attributes
    ----------
    bot: :class:`.UniversityBot`
        The bot instance.
    config: :class:`.VerificationConfig`
        The verification configuration.
    data: :class:`.VerificationDataConfig`
        The verification data configuration.
    """

    bot: UniversityBot
    config: VerificationConfig
    data: VerificationDataConfig

    def __init__(self, bot: UniversityBot, config: VerificationConfig) -> None:
        self.bot = bot
        self.config = config

        try:
            self.config.assigned_roles.set_roles(bot.guild)
            self.config.assigned_roles.validate_all_roles_permissions()
        except (ValueError, MissingPermissionsError) as e:
            raise InvalidConfigurationError("Invalid verified role.") from e

        if not self.config.assigned_roles.is_any_role_provided:
            _logger.warning("No roles are provided for verification.")

        try:
            self.data = VerificationDataConfig.load(self.config.data_filepath)
        except FileNotFoundError:
            _logger.warning("Data file is missing, creating a new one.")
            self.data = VerificationDataConfig.get_example()
            self.data.save(self.config.data_filepath, bot, _logger)
        except (ValueError, json.JSONDecodeError) as e:
            _logger.error("Data file is invalid.")
            raise InvalidConfigurationError("Data file is invalid.") from e

        ConfigurationServiceMixin.__init__(  # type: ignore
            self, bot, self.data, self.config.data_filepath, _logger
        )

        StaticViewMixin.__init__(  # type: ignore
            self,
            bot,
            self.config.data_filepath,
            self.data,
            _logger,
        )

    @override
    def get_data_from_string(self, content: str) -> VerificationDataConfig:
        return VerificationDataConfig(**json.loads(content))

    @override
    async def validate_data(self, json_content: str) -> None:
        try:
            data = self.get_data_from_string(json_content)
            await data.ensure_valid_message(self.bot)
        except (ValueError, json.JSONDecodeError, ResourceFetchFailed) as e:
            raise InvalidConfigurationError("Invalid JSON content.") from e

    async def setup_database(self) -> None:
        """|coro|

        Sets up the verification database.

        Raises
        ------
        RuntimeError
            If the database initialization fails.
        """
        try:
            async with self.bot.database.engine.begin() as session:
                await create_tables_if_not_exist(session, _logger, Base)
            async with self.bot.database.async_session_factory() as session:
                async with session.begin():
                    await self._mark_users_left(session)
                    await self._purge_users_by_retention(session)
                    await self._purge_verification_requests_by_retention(session)
        except SQLAlchemyError as e:
            _logger.error("Failed to initialize the database.", exc_info=True)
            raise RuntimeError("Failed to initialize the database.") from e

    async def _mark_users_left(self, session: AsyncSession) -> None:
        """|coro|

        Checks which verification records correspond to users
        who are no longer present on the server, and sets
        their 'left_at' timestamp to the current time.

        This function is intended to be called at server startup to update the database
        with the departure time of users who are no longer members.

        Parameters
        ----------
        session: :class:`sqlalchemy.ext.asyncio.AsyncSession`
            The active asynchronous database session.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        guild = self.bot.guild
        member_ids = {member.id for member in guild.members}

        stmt = (
            sqlalchemy.update(VerificationDTO)
            .where(
                VerificationDTO.user_id.notin_(member_ids),
                VerificationDTO.verified_at.is_not(None),
                VerificationDTO.left_at.is_(None),
            )
            .values(left_at=now)
        )
        result = await session.execute(stmt)
        if result.rowcount:
            _logger.info("Marked %d verification records as left.", result.rowcount)

    async def mark_user_left(self, user_id: int) -> None:
        """|coro|

        Sets the 'left_at' field for the verification record corresponding
        to the given user_id to the current time, if it is not already set.

        Parameters
        ----------
        user_id: :class:`int`
            The ID of the user to update.

        Raises
        ------
        sqlalchemy.exc.SQLAlchemyError
            If an error occurred while executing the query.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        async with self.bot.database.async_session_factory() as session:
            async with session.begin():
                stmt = (
                    sqlalchemy.update(VerificationDTO)
                    .where(
                        VerificationDTO.user_id == user_id,
                        VerificationDTO.verified_at.is_not(None),
                        VerificationDTO.left_at.is_(None),
                    )
                    .values(left_at=now)
                )
                result = await session.execute(stmt)
                if result.rowcount:
                    _logger.info("Marked user with id %s as left.", user_id)

    async def purge_user_by_retention(self, user_id: int) -> None:
        """|coro|

        Deletes the verification record corresponding to the given user ID
        if the retention period has passed.

        The retention period is defined in the configuration file.

        A record is deleted if the date portion of its 'left_at' timestamp
        is earlier than or equal to the cutoff date calculated as:
        current_date - retention_period.

        Parameters
        ----------
        user_id: :class:`int`
            The ID of the user to purge.

        Raises
        ------
        sqlalchemy.exc.SQLAlchemyError
            If an error occurred while executing the query.
        """
        async with self.bot.database.async_session_factory() as session:
            async with session.begin():
                stmt = sqlalchemy.select(VerificationDTO).where(
                    VerificationDTO.user_id == user_id
                )
                result = await session.execute(stmt)
                if (record := result.scalar_one_or_none()) is None:
                    return

                retention = self.config.retention_period.get(record.type)
                now = datetime.datetime.now(datetime.timezone.utc)
                cutoff = now.date() - datetime.timedelta(days=retention)

                stmt = sqlalchemy.delete(VerificationDTO).where(
                    VerificationDTO.user_id == user_id,
                    VerificationDTO.left_at.isnot(None),
                    sqlalchemy.func.date(VerificationDTO.left_at) <= cutoff.isoformat(),
                )
                result = await session.execute(stmt)
                if result.rowcount:
                    _logger.info("Deleted %d verification records.", result.rowcount)

    async def _purge_users_by_retention(self, session: AsyncSession) -> None:
        """|coro|

        Deletes verification records from the VerificationDTO table
        if the retention period has passed. Comparison is done only
        on the date portion of the 'left_at' timestamp, which is useful
        if the cleanup is scheduled to run once per day.

        The retention period is defined in the configuration file.

        A record is deleted if the date portion of its 'left_at' timestamp
        is earlier than or equal to the cutoff date calculated as:
        current_date - retention_period.

        Parameters
        ----------
        session: class:`sqlalchemy.ext.asyncio.AsyncSession`
            The active asynchronous database session.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        async def _purge(v_type: VerificationType, retention: int):
            cutoff = now.date() - datetime.timedelta(days=retention)
            stmt = sqlalchemy.delete(VerificationDTO).where(
                VerificationDTO.left_at.isnot(None),
                VerificationDTO.type == v_type,
                sqlalchemy.func.date(VerificationDTO.left_at) <= cutoff.isoformat(),
            )
            result_ext = await session.execute(stmt)
            if result_ext.rowcount:
                _logger.info(
                    "Deleted %d %s verification records.",
                    result_ext.rowcount,
                    v_type,
                )

        await _purge(VerificationType.EXTERNAL, self.config.retention_period.external)
        await _purge(VerificationType.INTERNAL, self.config.retention_period.internal)
        await _purge(VerificationType.TARGET, self.config.retention_period.target)

    async def _purge_verification_requests_by_retention(
        self, session: AsyncSession
    ) -> None:
        """|coro|

        Deletes verification request records from the VerificationRequestDTO table
        if the retention period has passed. Comparison is done only on the date
        portion of the 'requested_at' timestamp, which is useful if the cleanup
        is scheduled to run once per day.

        The retention period is defined in the configuration file.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now.date() - datetime.timedelta(
            days=self.config.retention_period.external_request
        )
        stmt = sqlalchemy.select(VerificationRequestDTO).where(
            sqlalchemy.func.date(VerificationRequestDTO.requested_at)
            <= cutoff.isoformat()
        )

        result = await session.execute(stmt)
        records = result.scalars().all()

        await asyncio.gather(
            *(self._try_delete_request_embed(r.request_message_id) for r in records)
        )

        stmt = sqlalchemy.delete(VerificationRequestDTO).where(
            sqlalchemy.func.date(VerificationRequestDTO.requested_at)
            <= cutoff.isoformat()
        )
        result = await session.execute(stmt)
        if result.rowcount:
            _logger.info("Deleted %d verification request records.", result.rowcount)

    async def _try_delete_request_embed(self, message_id: int) -> None:
        try:
            message = await fetch_message(self.bot.bot_channel, message_id)
            await message.delete()
        except ResourceFetchFailed:
            pass
        except HTTPException:
            _logger.error(
                "Failed to delete verification request message.", exc_info=True
            )

    async def purge_users_and_requests_by_retention_loop(self) -> None:
        """|coro|

        A loop that periodically purges verification records from the database
        based on the retention period defined in the configuration file.

        The loop runs once per day at midnight, and deletes records that have
        been marked as left for a period longer than the retention period.
        """
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            now = datetime.datetime.now(datetime.timezone.utc)
            tomorrow = now + datetime.timedelta(days=1)
            midnight = datetime.datetime.combine(
                tomorrow.date(), datetime.time.min, tzinfo=datetime.timezone.utc
            )
            seconds_until_midnight = (midnight - now).total_seconds()

            await asyncio.sleep(seconds_until_midnight)

            async with self.bot.database.async_session_factory() as session:
                async with session.begin():
                    await self._purge_users_by_retention(session)
                    await self._purge_verification_requests_by_retention(session)

    async def is_index_taken(self, index: str) -> bool:
        """|coro|

        Checks if the given index is already taken.

        The index is considered taken if there is a verification record
        with the given index, 'left_at' field is not set and the user
        corresponding to the record is still present on the server.

        Parameters
        ----------
        index: :class:`str`
            The index to check.

        Returns
        -------
        :class:`bool`
            Whether the index is taken.

        Raises
        ------
        sqlalchemy.exc.SQLAlchemyError
            If an error occurred while executing the query.
        """
        record = await self.get_record_with_index(index)

        if record is None or record.left_at is not None:
            return False

        try:
            return await fetch_guild_member(self.bot.guild, record.user_id) is not None
        except ResourceFetchFailed:
            return False

    async def get_record_with_index(self, index: str) -> VerificationDTO | None:
        """|coro|

        Retrieves a verification record with the given index.

        Parameters
        ----------
        index: :class:`str`
            The index to search for.

        Returns
        -------
        :class:`.VerificationDTO` | `None`
            The verification record with the given index.

        Raises
        ------
        sqlalchemy.exc.SQLAlchemyError
            If an error occurred while executing the query.
        """
        async with self.bot.database.async_session_factory() as session:
            stmt = sqlalchemy.select(VerificationDTO).where(
                VerificationDTO.index == index
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_record_with_user_id(self, user_id: int) -> VerificationDTO | None:
        """|coro|

        Retrieves a verification record with the given user ID.

        Parameters
        ----------
        user_id: :class:`int`
            The user ID to search for.

        Returns
        -------
        :class:`.VerificationDTO` | `None`
            The verification record with the given user ID.

        Raises
        ------
        sqlalchemy.exc.SQLAlchemyError
            If an error occurred while executing the query.
        """
        async with self.bot.database.async_session_factory() as session:
            stmt = sqlalchemy.select(VerificationDTO).where(
                VerificationDTO.user_id == user_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def is_user_verified(self, user_id: int) -> bool:
        """|coro|

        Checks if the given user is verified.

        A user is considered verified if there is a verification record
        with the given user ID and the 'left_at' field is not set.

        Parameters
        ----------
        user_id: :class:`int`
            The user ID to check.

        Returns
        -------
        :class:`bool`
            Whether the user is verified.

        Raises
        ------
        sqlalchemy.exc.SQLAlchemyError
            If an error occurred while executing the query.
        """
        record = await self.get_record_with_user_id(user_id)
        return (
            record is not None
            and record.verified_at is not None
            and record.left_at is None
        )

    async def is_request_sent(self, user_id: int) -> bool:
        """|coro|

        Checks if the given user has sent a verification request.

        A user is considered to have sent a request if there is a verification request
        record with the given user ID and the 'request_message_id' field is set.

        Parameters
        ----------
        user_id: :class:`int`
            The user ID to check.

        Returns
        -------
        :class:`bool`
            Whether the user has sent a request.

        Raises
        ------
        sqlalchemy.exc.SQLAlchemyError
            If an error occurred while executing the query.
        """
        async with self.bot.database.async_session_factory() as session:
            stmt = sqlalchemy.select(VerificationRequestDTO).where(
                VerificationRequestDTO.user_id == user_id
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            return record is not None

    @override
    def create_view(self, handler: VerificationHandler) -> VerificationView:
        self.view = VerificationView(handler)
        self.bot.add_view(self.view)
        return self.view

    @override
    async def prepare_message_data(
        self, handler: VerificationHandler, missing: bool = False
    ) -> MessageData[Embed | None, View | None]:
        return MessageData(
            content=self.data.content or (MISSING if missing else None),
            embed=self.data.embed,
            view=self.create_view(handler),
        )

    def generate_verification_code(self, length: int) -> str:
        """Generates a random verification code.

        Parameters
        ----------
        length: :class:`int`
            The length of the code.

        Returns
        -------
        :class:`str`
            The generated code.
        """
        return "".join([random.choice(string.ascii_letters) for _ in range(length)])

    def get_privacy_policy_filepath(self, locale: Locale | str | None) -> Path:
        """Returns the privacy policy filepath for the given locale.

        Parameters
        ----------
        locale: :class:`nextcord.Locale` | :class:`str` | `None`
            The locale to get the filepath for.

        Returns
        -------
        :class:`str`
            The filepath to the privacy policy.

        Raises
        ------
        :class:`.DisabledFeatureError`
            If the privacy policy feature is disabled.
        """
        if isinstance(locale, str):
            locale = Locale(locale)
        elif locale is None:
            locale = Locale(l) if (l := self.bot.guild.preferred_locale) else None
            locale = locale or Localization.default_locale()

        if not self.config.privacy_policy:
            raise DisabledFeatureError("Privacy policy feature is disabled.")

        localized_config = self.config.privacy_policy.get_localized(locale)
        return localized_config.filepath

    async def _assign_verified_roles(
        self, member: Member, type_: VerificationType
    ) -> None:
        to_assign = self.config.assigned_roles.get(type_)
        to_remove = self.config.assigned_roles.all_roles - to_assign
        await asyncio.gather(
            member.remove_roles(*to_remove, reason="User verification."),
            member.add_roles(*to_assign, reason="User verification."),
        )

    async def _send_verification_success_embed(self, member: Member) -> None:
        pass

    async def _remove_verification_request(
        self, member_id: int, session: AsyncSession
    ) -> None:
        stmt = sqlalchemy.delete(VerificationRequestDTO).where(
            VerificationRequestDTO.user_id == member_id
        )
        await session.execute(stmt)

    async def verify_target_member(
        self,
        member: Member,
        data: TargetVerificationData,
    ) -> None:
        """|coro|

        Verifies a target member.

        This method creates a new verification record in the database
        and assigns the verified roles to the member.

        Parameters
        ----------
        member: :class:`nextcord.Member`
            The member to verify.
        data: :class:`.TargetVerificationData`
            The target verification data.
        """
        async with self.bot.database.async_session_factory() as session:
            async with session.begin():
                stmt = sqlalchemy.select(VerificationDTO).where(
                    VerificationDTO.user_id == member.id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

                if record is None:
                    record = VerificationDTO(user_id=member.id)
                    session.add(record)

                record.first_name = data.first_name
                record.last_name = data.last_name
                record.index = data.index
                record.type = VerificationType.TARGET
                record.verified_at = datetime.datetime.now(datetime.timezone.utc)
                record.left_at = None
                record.study_info = None
                record.reason = None

                await self._remove_verification_request(member.id, session)
                await session.flush()

        await self._assign_verified_roles(member, VerificationType.TARGET)

        _logger.info(
            "Created new target verification for user id %d.",
            member.id,
        )

    async def verify_internal_member(
        self,
        member: Member,
        data: InternalVerificationData,
    ) -> None:
        """|coro|

        Verifies an internal member.

        This method creates a new verification record in the database
        and assigns the verified roles to the member.

        Parameters
        ----------
        member: :class:`nextcord.Member`
            The member to verify.
        data: :class:`.InternalVerificationData`
            The internal verification data.
        """
        async with self.bot.database.async_session_factory() as session:
            async with session.begin():
                stmt = sqlalchemy.select(VerificationDTO).where(
                    VerificationDTO.user_id == member.id
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

                if record is None:
                    record = VerificationDTO(user_id=member.id)
                    session.add(record)

                record.first_name = data.first_name
                record.last_name = data.last_name
                record.index = data.index
                record.type = VerificationType.INTERNAL
                record.verified_at = datetime.datetime.now(datetime.timezone.utc)
                record.left_at = None
                record.study_info = data.study_info
                record.reason = data.reason

                await self._remove_verification_request(member.id, session)
                await session.flush()

        await self._assign_verified_roles(member, VerificationType.INTERNAL)

        _logger.info(
            "Created new internal verification for user id %d.",
            member.id,
        )

    async def handle_guest_verification_request(
        self,
        member: Member,
        data: ExternalVerificationData,
    ):
        """|coro|

        Handles a guest verification request.

        This method creates a new verification request record in the database
        and sends a verification request message to the bot channel.

        Parameters
        ----------
        member: :class:`nextcord.Member`
            The member who requested verification.
        data: :class:`.ExternalVerificationData`
            The external verification data.
        """
        locale = (
            Locale(self.bot.guild.preferred_locale)
            if self.bot.guild.preferred_locale
            else None
        ) or Localization.default_locale()

        embed = VerificationRequestEmbed(locale, member, data)
        message = await self.bot.bot_channel.send(embed=embed)

        try:
            async with self.bot.database.async_session_factory() as session:
                async with session.begin():
                    stmt = sqlalchemy.select(VerificationRequestDTO).where(
                        VerificationRequestDTO.user_id == member.id
                    )
                    result = await session.execute(stmt)
                    record = result.scalar_one_or_none()

                    if record is None:
                        record = VerificationRequestDTO(user_id=member.id)
                        session.add(record)

                    record.first_name = data.first_name
                    record.last_name = data.last_name
                    record.reason = data.reason
                    record.requested_at = datetime.datetime.now(datetime.timezone.utc)
                    record.request_message_id = message.id

                    await session.flush()
        except SQLAlchemyError:
            try:
                await message.delete()
            except HTTPException:
                _logger.error(
                    "Failed to delete verification request message.", exc_info=True
                )
            raise

    async def verify_request(self, member_id: int) -> None:
        """|coro|

        Verifies a user based on a verification request.

        This method retrieves the verification request record from the database,
        verifies the user and deletes the request message.

        Parameters
        ----------
        member_id: :class:`int`
            The ID of the user to verify.

        Raises
        ------
        :class:`VerificationFailedError`
            If the verification request is not found or the member is not found.
        :class:`nextcord.HTTPException`
            If an error occurred while deleting the request message.
        :class:`sqlalchemy.exc.SQLAlchemyError`
            If an error occurred while executing the query.
        """
        async with self.bot.database.async_session_factory() as session:
            async with session.begin():
                stmt = sqlalchemy.select(VerificationRequestDTO).where(
                    VerificationRequestDTO.user_id == member_id
                )
                result = await session.execute(stmt)
                request = result.scalar_one_or_none()

                if request is None:
                    raise VerificationFailedError("Verification request not found.")

                member = await fetch_guild_member(self.bot.guild, member_id)
                if member is None:
                    raise VerificationFailedError("Member not found.")

                stmt = sqlalchemy.select(VerificationDTO).where(
                    VerificationDTO.user_id == member.id
                )
                result = await session.execute(stmt)
                data = result.scalar_one_or_none()

                if data is None:
                    data = VerificationDTO(user_id=member.id)
                    session.add(data)

                data.first_name = request.first_name
                data.last_name = request.last_name
                data.type = VerificationType.EXTERNAL
                data.verified_at = datetime.datetime.now(datetime.timezone.utc)
                data.left_at = None
                data.reason = request.reason

                await session.delete(request)
                await session.flush()

        await asyncio.gather(
            self._assign_verified_roles(member, VerificationType.EXTERNAL),
            self._try_delete_request_embed(request.request_message_id),
            self._send_verification_success_embed(member),
        )

    async def get_all_users(self) -> Sequence[VerificationDTO]:
        """|coro|

        Retrieves all verification records from the database.

        Returns
        -------
        :class:`list`[:class:`.VerificationDTO`]
            A list of all verification records.
        """
        async with self.bot.database.async_session_factory() as session:
            stmt = sqlalchemy.select(VerificationDTO)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_matching_members(self, query: str) -> list[MatchingMember]:
        """|coro|

        Retrieves a list of members whose names, nicknames, IDs or indices
        match the given query.

        The query is compared against the first name, last name, full name,
        ID, name and nickname of each member. The results are sorted by
        the similarity ratio of the query to the member's name.

        Parameters
        ----------
        query: :class:`str`
            The query to search for.

        Returns
        -------
        list[:class:`nextcord.MatchingMember`]
            A list of matching members.
        """

        guild_members = [m async for m in self.bot.guild.fetch_members(limit=None)]
        guild_members_dict = {m.id: m for m in guild_members}

        members: list[MatchingMember] = []
        for dto in await self.get_all_users():
            member = guild_members_dict.get(dto.user_id)
            if member is None:
                continue
            members.append(MatchingMember(dto, member))

        index_result = [m for m in members if m.verification_data.index == query]
        keys: list[Callable[[MatchingMember], str]] = [
            lambda i: i.verification_data.first_name,
            lambda i: i.verification_data.last_name,
            lambda i: (d := i.verification_data).first_name + " " + d.last_name,
            lambda i: (d := i.verification_data).last_name + " " + d.first_name,
            lambda i: str(i.member.id),
            lambda i: i.member.name,
            lambda i: i.member.display_name,
        ]

        results = SmartDict[MatchingMember, float](lambda a, b: a > b)
        matcher = Matcher[MatchingMember](members, ignore_case=True)

        for key in keys:
            for i in matcher.match_all(query, key=key):
                results[i.item] = i.ratio

        # If the max ratio is less than 50%, return an empty list.
        if not results or (max_ratio := max(results.values())) <= 0.5:
            return []

        results = dict(sorted(results.items(), key=lambda i: i[1], reverse=True))

        # If the index is found and the ratio is less than 1.0, return only the index result.
        if index_result and max_ratio < 1.0:
            return index_result

        # Return the index result and all members with a ratio greater than 90% of the max ratio.
        return index_result + [i[0] for i in results.items() if i[1] > max_ratio * 0.9]
