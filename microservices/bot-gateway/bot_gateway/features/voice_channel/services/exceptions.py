"""
Voice Channel Exceptions

Provides exceptions specific to the voice channel service.
"""

from bot_gateway.core.exceptions import DiscordManagerError


class DiscordVoiceChannelManagerError(DiscordManagerError):
    """Base exception for voice channel errors."""
