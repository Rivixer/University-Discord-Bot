from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for the bot gateway.

    Attributes
    ----------
    log_level : str
        The logging level for the service.
        Can be 'DEBUG', 'INFO', 'WARNING', 'ERROR', or 'CRITICAL'.
    environment : str
        The environment in which the application is running.
    discord_bot_token : str
        The token for the Discord bot. This should be set in the environment.
    test_guild_id : int | None
        The ID of the test guild. This can be set to None if not applicable.
    redis_url : str
        The URL for the Redis instance.
    redis_guild_base : str
        The base key for guild-related data in Redis.
    redis_voice_channel_base : str
        The base key for voice channel-related data in Redis.
    grpc_port : int
        The port for the gRPC server.
    """

    log_level: str = "WARNING"
    environment: str = "development"

    discord_bot_token: str = ""
    test_guild_id: int | None = None

    redis_url: str = "redis://localhost:6379/0"
    redis_guild_base: str = "guild"
    redis_voice_channel_base: str = "voice"

    grpc_port: int = 50051

    class Config:
        env_file = ".env"


settings = Settings()
