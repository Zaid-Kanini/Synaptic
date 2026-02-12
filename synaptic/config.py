"""Application-wide configuration and settings.

Uses ``pydantic-settings`` so values can be overridden via environment
variables prefixed with ``SYNAPTIC_``.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global settings for the Synaptic ingestion engine.

    Attributes:
        app_name: Display name of the application.
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        default_blacklist: Directory/file patterns to skip during crawling.
        max_file_size_bytes: Skip files larger than this threshold.
    """

    app_name: str = "Synaptic"
    log_level: str = "INFO"
    default_blacklist: list[str] = [
        ".git",
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".env",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
        ".idea",
        ".vscode",
    ]
    max_file_size_bytes: int = 1_048_576  # 1 MB

    model_config = {"env_prefix": "SYNAPTIC_"}


settings = Settings()
