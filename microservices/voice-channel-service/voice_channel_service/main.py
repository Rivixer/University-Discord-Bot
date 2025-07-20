"""
Entry-point for the Voice Channel Service.
Sets up logging, Redis, background tasks, and starts the FastAPI/Uvicorn server.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from shared.redis_client import RedisManager, RedisSubscriber

from .settings import settings
from .sync import periodic_full_guild_sync, periodic_full_voice_channel_sync

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for the FastAPI application.

    On startup:
    - Initializes the Redis client.
    - Launches the Redis subscriber to listen for events.
    - Waits briefly to allow event subscribers to settle.
    - Launches periodic sync tasks for guild and voice channel states.

    On shutdown:
    - Closes the Redis client connection.

    Yields
    -------
    None
        Control is yielded to the FastAPI application.
        The application will run until it is shut down.
    """
    RedisManager.initialize(settings.redis_url)

    asyncio.create_task(
        RedisSubscriber.listen(),
        name="redis-subscriber",
    )

    await asyncio.sleep(4)

    asyncio.create_task(
        periodic_full_guild_sync(),
        name="periodic-full-guild-sync",
    )

    asyncio.create_task(
        periodic_full_voice_channel_sync(),
        name="periodic-full-voice-channel-sync",
    )

    yield

    await RedisManager.close()


app = FastAPI(lifespan=lifespan)


def main() -> None:
    """Main entry point for the voice channel service.

    Initializes the FastAPI application.
    Starts the application using Uvicorn.
    """

    uvicorn.run(
        "voice_channel_service.main:app",
        host=settings.uvicorn_host,
        port=settings.uvicorn_port,
        reload=settings.uvicorn_reload,
    )


if __name__ == "__main__":
    main()
