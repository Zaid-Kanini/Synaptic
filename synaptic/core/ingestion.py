"""Ingestion orchestrator that ties the crawler and parsers together.

This is the main entry point for scanning a repository: it crawls the
file tree, dispatches each file to the appropriate language parser, and
merges the results into a single :class:`CodeGraph`.
"""

from __future__ import annotations

import pathlib

import structlog

from synaptic.core.crawler import FileCrawler, get_language_for_file
from synaptic.models.graph import CodeGraph
from synaptic.parsers.base import BaseLanguageParser
from synaptic.parsers.factory import ParserFactory
from synaptic.parsers.javascript_parser import JavaScriptParser
from synaptic.parsers.python_parser import PythonParser

logger = structlog.get_logger(__name__)


def _build_factory(repo_root: pathlib.Path) -> ParserFactory:
    """Create a :class:`ParserFactory` pre-loaded with all built-in parsers.

    Args:
        repo_root: Repository root directory.

    Returns:
        A ready-to-use factory instance.
    """
    factory = ParserFactory(repo_root)
    factory.register("python", PythonParser)
    factory.register("javascript", JavaScriptParser)
    return factory


async def ingest_repository(
    repo_path: str | pathlib.Path,
    blacklist: list[str] | None = None,
) -> CodeGraph:
    """Scan a local repository and produce its knowledge graph.

    This is an **async** function so it can be called directly from
    FastAPI route handlers.  The heavy lifting (file I/O and parsing) is
    CPU-bound and runs synchronously within the function; wrapping in
    ``asyncio.to_thread`` is recommended for very large repos.

    Args:
        repo_path: Path to the repository root directory.
        blacklist: Optional override for the default directory blacklist.

    Returns:
        A merged :class:`CodeGraph` containing every node and edge
        discovered across all files.

    Raises:
        FileNotFoundError: If *repo_path* does not exist.
        NotADirectoryError: If *repo_path* is not a directory.
    """
    root = pathlib.Path(repo_path).resolve()

    if not root.exists():
        raise FileNotFoundError(f"Repository path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")

    logger.info("ingestion_started", repo=str(root))

    crawler = FileCrawler(root, blacklist=blacklist)
    factory = _build_factory(root)

    merged = CodeGraph()
    files_parsed = 0
    files_failed = 0

    for file_path in crawler.crawl():
        language = get_language_for_file(file_path)
        if language is None:
            continue

        parser: BaseLanguageParser | None = factory.get(language)
        if parser is None:
            logger.warning("no_parser_for_language", language=language, file=str(file_path))
            continue

        try:
            source = file_path.read_bytes()
            graph = parser.parse_file(file_path, source)
            merged.nodes.extend(graph.nodes)
            merged.edges.extend(graph.edges)
            files_parsed += 1
        except Exception:
            files_failed += 1
            logger.exception(
                "parse_failed",
                file=str(file_path),
                language=language,
            )

    logger.info(
        "ingestion_finished",
        repo=str(root),
        files_parsed=files_parsed,
        files_failed=files_failed,
        total_nodes=len(merged.nodes),
        total_edges=len(merged.edges),
    )

    return merged
