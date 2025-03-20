# SPDX-License-Identifier: MIT
"""A module to define handler for reminder interactions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from university_bot import get_logger
from university_bot.mixins.configuration import ConfigurationHandlerMixin

if TYPE_CHECKING:
    from .service import ReminderService


_logger = get_logger(__name__)


class ReminderHandler(ConfigurationHandlerMixin):
    """A class to handle reminder interactions.

    Attributes
    ----------
    service: :class:`.ReminderService`
        The reminder service.
    """

    service: ReminderService

    def __init__(self, service: ReminderService) -> None:
        self.service = service
        super().__init__(service, _logger)
