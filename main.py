"""Entry point for running the Synaptic API server via ``python main.py``."""

import os

import uvicorn

from synaptic.config import settings

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "synaptic.api.app:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
