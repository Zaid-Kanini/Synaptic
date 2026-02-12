"""FastAPI application factory and lifespan management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from synaptic import __version__
from synaptic.api.routes import router
from synaptic.config import settings
from synaptic.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler — runs setup on startup.

    Args:
        app: The FastAPI application instance.
    """
    setup_logging(settings.log_level)
    yield


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Returns:
        A fully wired :class:`FastAPI` instance.
    """
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Synaptic Ingestion & Parsing Engine — scans a local repository, "
            "extracts its structural DNA via tree-sitter, and returns a "
            "knowledge graph ready for Neo4j."
        ),
        lifespan=lifespan,
    )
    app.include_router(router, tags=["Ingestion"])
    return app


app = create_app()
