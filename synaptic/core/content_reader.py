"""On-demand content reader that resolves node pointers to source code.

Instead of storing raw source inline in every node, the ingestion
pipeline records ``filepath``, ``start_line``, and ``end_line`` as
*pointers*.  This module provides :func:`get_node_content` which reads
only the requested line range from disk using a buffered reader with
graceful encoding fallback.
"""

from __future__ import annotations

import pathlib
from typing import Optional

import structlog

from synaptic.models.graph import CodeGraph, NodeRecord

logger = structlog.get_logger(__name__)

# Encodings to attempt in order when reading source files.
_ENCODING_CHAIN: tuple[str, ...] = ("utf-8", "latin-1", "cp1252")


def read_lines(
    file_path: pathlib.Path,
    start_line: int,
    end_line: int,
) -> str:
    """Read a specific line range from *file_path* with encoding fallback.

    Uses a buffered reader and tries multiple encodings so that files
    saved in non-UTF-8 charsets are handled gracefully.

    Args:
        file_path: Absolute path to the source file.
        start_line: 1-indexed first line to include.
        end_line: 1-indexed last line to include.

    Returns:
        The extracted source text (lines joined by ``\\n``).

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        ValueError: If the line range is invalid.
    """
    if start_line < 1 or end_line < start_line:
        raise ValueError(
            f"Invalid line range: start_line={start_line}, end_line={end_line}"
        )

    if not file_path.exists():
        raise FileNotFoundError(f"Source file not found: {file_path}")

    content: Optional[str] = None
    used_encoding: str = _ENCODING_CHAIN[0]

    for encoding in _ENCODING_CHAIN:
        try:
            with file_path.open("r", encoding=encoding, buffering=8192) as fh:
                content = fh.read()
            used_encoding = encoding
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        # Last resort: read as bytes and decode with replacement chars.
        logger.warning(
            "encoding_fallback",
            file=str(file_path),
            tried=_ENCODING_CHAIN,
        )
        raw = file_path.read_bytes()
        content = raw.decode("utf-8", errors="replace")
        used_encoding = "utf-8(replace)"

    lines = content.splitlines()
    # Clamp end_line to actual file length.
    actual_end = min(end_line, len(lines))
    selected = lines[start_line - 1 : actual_end]

    logger.debug(
        "lines_read",
        file=str(file_path),
        start=start_line,
        end=actual_end,
        encoding=used_encoding,
    )

    return "\n".join(selected)


def get_node_content(
    node_id: str,
    graph: CodeGraph,
    repo_root: pathlib.Path,
) -> str:
    """Look up a node by ID and read its source from disk.

    This is the primary on-demand reader.  It resolves the node's
    ``filepath``, ``start_line``, and ``end_line`` pointers and returns
    only those lines.

    Args:
        node_id: The deterministic node ID to look up.
        graph: The :class:`CodeGraph` containing the node index.
        repo_root: Absolute path to the repository root so that
            repo-relative ``filepath`` values can be resolved.

    Returns:
        The raw source code for the requested node.

    Raises:
        KeyError: If *node_id* is not found in the graph.
        FileNotFoundError: If the underlying source file is missing.
    """
    node: Optional[NodeRecord] = _find_node(node_id, graph)
    if node is None:
        raise KeyError(f"Node not found: {node_id}")

    abs_path = (repo_root / node.filepath).resolve()

    return read_lines(abs_path, node.start_line, node.end_line)


def _find_node(node_id: str, graph: CodeGraph) -> Optional[NodeRecord]:
    """Linear scan for a node by ID.

    For production use with very large graphs, replace with a
    ``dict``-based index built once after ingestion.

    Args:
        node_id: Node ID to search for.
        graph: The code graph.

    Returns:
        The matching :class:`NodeRecord`, or ``None``.
    """
    for node in graph.nodes:
        if node.id == node_id:
            return node
    return None
