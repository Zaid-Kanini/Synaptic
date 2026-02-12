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
        neo4j_uri: Neo4j Aura ``neo4j+s://`` connection string.
        neo4j_user: Neo4j database username.
        neo4j_password: Neo4j database password.
        neo4j_database: Neo4j target database name.
        embedding_model: HuggingFace sentence-transformers model name.
        embedding_batch_size: Batch size for UNWIND operations.
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

    # Module 2: Neo4j Aura Cloud
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # Module 2: Local HuggingFace Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_batch_size: int = 200

    # Module 3: GraphRAG Pipeline
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    azure_endpoint: str = ""
    rag_max_nodes: int = 15
    rag_max_context_chars: int = 12000
    rag_expand_depth: int = 2
    rag_top_k: int = 5

    model_config = {"env_prefix": "SYNAPTIC_", "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
