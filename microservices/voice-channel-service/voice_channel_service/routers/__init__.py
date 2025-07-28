"""
Voice Channel Service Routers Initialization

This module initializes the routers for the voice channel service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .config import router as config_router
from .voice_channel import router as voice_channel_router

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    """Registers the voice channel service routers with the FastAPI application.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance to register the routers with.
    """
    app.include_router(config_router)
    app.include_router(voice_channel_router)
