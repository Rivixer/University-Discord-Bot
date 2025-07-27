"""
Voice Channel Service Main Module

Sets up logging, Redis, background tasks, and starts the FastAPI/Uvicorn server.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.models.error_response import ErrorResponse
from shared.redis_client import RedisManager, RedisSubscriber

from .exceptions import DomainException
from .rename_scheduler import initialize_cooldowns
from .routers import register_routes
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

    await initialize_cooldowns()

    yield

    await RedisManager.close()


app = FastAPI(lifespan=lifespan)
register_routes(app)


@app.exception_handler(DomainException)
async def handle_domain_exc(request: Request, exc: DomainException):
    response_cls = ErrorResponse.for_error_code(exc.error_code)
    payload = response_cls(
        error_code=exc.error_code,
        message=exc.message or "An error occurred",
        **{k: getattr(exc, k) for k in vars(exc) if k not in ("error_code", "message")},
    ).model_dump(mode="json")
    return JSONResponse(status_code=exc.status_code, content=payload)


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
