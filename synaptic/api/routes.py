"""FastAPI route definitions for the Synaptic ingestion API.

Provides two main endpoints:

- ``POST /ingest`` — scan a repository and return (or stream) its lean
  knowledge graph metadata.
- ``GET /node/{node_id}/content`` — on-demand reader that resolves a
  node's pointers and returns only the relevant source lines.
"""

from __future__ import annotations

import json
import pathlib
from typing import AsyncIterator

from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from synaptic.core.content_reader import get_node_content
from synaptic.core.ingestion import ingest_repository
from synaptic.models.graph import CodeGraph

router = APIRouter()


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class IngestRequest(BaseModel):
    """Payload for the ``/ingest`` endpoint.

    Attributes:
        path: Absolute local path to the repository to scan.
        blacklist: Optional list of glob patterns to exclude.
        stream: If ``True``, return an NDJSON streaming response.
    """

    path: str = Field(..., description="Absolute local path to the repository.")
    blacklist: list[str] | None = Field(
        None, description="Optional glob patterns to exclude."
    )
    stream: bool = Field(
        False, description="If true, return NDJSON streaming response."
    )


class IngestResponse(BaseModel):
    """Response from the ``/ingest`` endpoint (non-streaming mode).

    Attributes:
        status: Human-readable status message.
        total_nodes: Number of nodes extracted.
        total_edges: Number of edges extracted.
        graph: The complete lean code knowledge graph (no content field).
    """

    status: str = Field("success", description="Status message.")
    total_nodes: int = Field(..., description="Number of nodes extracted.")
    total_edges: int = Field(..., description="Number of edges extracted.")
    graph: CodeGraph = Field(..., description="The extracted code knowledge graph.")


class NodeContentResponse(BaseModel):
    """Response from the ``/node/{node_id}/content`` endpoint.

    Attributes:
        node_id: The requested node ID.
        filepath: Repo-relative file path.
        start_line: Starting line of the snippet.
        end_line: Ending line of the snippet.
        content: The raw source code read from disk.
    """

    node_id: str = Field(..., description="Requested node ID.")
    filepath: str = Field(..., description="Repo-relative file path.")
    start_line: int = Field(..., description="Starting line.")
    end_line: int = Field(..., description="Ending line.")
    content: str = Field(..., description="Raw source code read on demand.")


# ------------------------------------------------------------------
# Streaming helper
# ------------------------------------------------------------------


async def _stream_ndjson(graph: CodeGraph) -> AsyncIterator[str]:
    """Yield the graph as newline-delimited JSON (NDJSON).

    Each line is a self-contained JSON object with a ``_type`` discriminator
    (``"node"`` or ``"edge"``), making it easy for consumers to process
    records incrementally without buffering the entire payload.

    Args:
        graph: The code graph to stream.

    Yields:
        One JSON-encoded line per node or edge, terminated by ``\\n``.
    """
    for node in graph.nodes:
        record = {"_type": "node", **node.model_dump(mode="json")}
        yield json.dumps(record, ensure_ascii=False) + "\n"

    for edge in graph.edges:
        record = {"_type": "edge", **edge.model_dump(mode="json")}
        yield json.dumps(record, ensure_ascii=False) + "\n"


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post(
    "/ingest",
    status_code=status.HTTP_200_OK,
    summary="Ingest a local repository",
    description=(
        "Recursively scan a local directory, parse all supported source "
        "files using tree-sitter, and return a lean JSON knowledge graph "
        "(no inline content — use /node/{id}/content for on-demand reads). "
        "Set ``stream: true`` to receive NDJSON for memory-efficient consumption."
    ),
)
async def ingest(request: IngestRequest):
    """Ingest a local repository and return its knowledge graph.

    When ``request.stream`` is ``True`` the response is an NDJSON stream
    (``application/x-ndjson``) so the client can process records
    incrementally.  Otherwise a standard JSON payload is returned.

    Args:
        request: Contains the local path, optional blacklist, and stream flag.

    Returns:
        :class:`IngestResponse` **or** a :class:`StreamingResponse`.

    Raises:
        HTTPException: 400 if the path is invalid, 500 on unexpected errors.
    """
    try:
        graph: CodeGraph = await ingest_repository(
            repo_path=request.path,
            blacklist=request.blacklist,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        )

    # --- Streaming mode ---
    if request.stream:
        return StreamingResponse(
            _stream_ndjson(graph),
            media_type="application/x-ndjson",
            headers={
                "X-Total-Nodes": str(len(graph.nodes)),
                "X-Total-Edges": str(len(graph.edges)),
            },
        )

    # --- Standard JSON mode ---
    return IngestResponse(
        status="success",
        total_nodes=len(graph.nodes),
        total_edges=len(graph.edges),
        graph=graph,
    )


@router.get(
    "/node/{node_id:path}/content",
    response_model=NodeContentResponse,
    status_code=status.HTTP_200_OK,
    summary="Read node source on demand",
    description=(
        "Resolve a node's file-pointer (filepath + line range) and return "
        "only the relevant source lines from disk.  This avoids storing "
        "content inline in the graph metadata."
    ),
)
async def node_content(
    node_id: str,
    repo_root: str = Query(
        ..., description="Absolute path to the repository root."
    ),
) -> NodeContentResponse:
    """Read the source code for a single node by its ID.

    Args:
        node_id: Deterministic node ID (from the ingested graph).
        repo_root: Absolute path to the repo root so relative paths
            can be resolved.

    Returns:
        :class:`NodeContentResponse` with the on-demand source snippet.

    Raises:
        HTTPException: 400 on bad input, 404 if node or file not found.
    """
    root = pathlib.Path(repo_root).resolve()
    if not root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"repo_root is not a valid directory: {repo_root}",
        )

    # Re-ingest to get the graph index (in production this would be
    # cached or stored in a database — kept simple for Module 1).
    try:
        graph: CodeGraph = await ingest_repository(repo_path=root)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build graph index: {exc}",
        )

    try:
        content = get_node_content(node_id, graph, root)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node not found: {node_id}",
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    # Look up the node for response metadata.
    node = next(n for n in graph.nodes if n.id == node_id)

    return NodeContentResponse(
        node_id=node_id,
        filepath=node.filepath,
        start_line=node.start_line,
        end_line=node.end_line,
        content=content,
    )
