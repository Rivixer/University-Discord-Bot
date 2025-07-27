"""
Voice Channel Service Settings Module

This module defines the settings for the voice channel service.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for the voice channel service.

    Attributes
    ----------
    log_level : str
        The logging level for the service.
        Can be 'DEBUG', 'INFO', 'WARNING', 'ERROR', or 'CRITICAL'.
    database_url : str
        The database connection URL.
    redis_url : str
        The Redis connection URL.
    redis_channel_base : str
        The base channel name for Redis.
    redis_guild_base : str
        The base guild name for Redis.
    uvicorn_host : str
        The host for the Uvicorn server.
    uvicorn_port : int
        The port for the Uvicorn server.
    uvicorn_reload : bool
        Whether to enable Uvicorn's auto-reload feature.
    voice_sync_interval : int
        The interval for syncing voice channels, in seconds.
    voice_sync_jitter : float
        The jitter for voice channel sync intervals, as a fraction of the interval.
    guild_sync_interval : int
        The interval for syncing guilds, in seconds.
    guild_sync_jitter : float
        The jitter for guild sync intervals, as a fraction of the interval.
    """

    log_level: str = "WARNING"

    database_url: str = "postgresql+asyncpg://bot:secret@db/bot"
    redis_url: str = "redis://localhost:6379/0"
    redis_channel_base: str = "voice"
    redis_guild_base: str = "guild"

    uvicorn_host: str = "0.0.0.0"
    uvicorn_port: int = 8080
    uvicorn_reload: bool = False

    voice_sync_interval: int = 60
    voice_sync_jitter: float = 0.1
    guild_sync_interval: int = 86400
    guild_sync_jitter: float = 0.01

    class Config:
        env_file = ".env"


settings = Settings()
