# SPDX-License-Identifier: MIT
"""
university_bot.models.configs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains the configuration models for the bot.
"""

from pydantic import BaseModel

from .basic import BasicConfig, TemporaryFilesConfig  # type: ignore
from .presence import PresenceConfig
from .role_assignment import RoleAssignmentConfig
from .voice_channel_manager import VoiceChannelManagerConfig


class BotConfig(BaseModel):
    """The bot configuration"""

    version: tuple[int, int, int]
    basic: BasicConfig
    role_assignment: RoleAssignmentConfig
    presence: PresenceConfig
    voice_channel_manager: VoiceChannelManagerConfig
