"""Entry point for running the Synaptic API server via ``python main.py``."""

import uvicorn

from synaptic.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "synaptic.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
