"""FastAPI route definitions for Module 2: Knowledge Graph & Semantic Memory.

Provides endpoints for:

- ``POST /graph/ingest`` — Push Module 1 JSON into Neo4j Aura + embed.
- ``POST /graph/search`` — Hybrid vector similarity search.
- ``POST /graph/setup`` — One-time index and constraint setup.
- ``DELETE /graph/clear`` — Wipe all graph data (dangerous).

All Neo4j calls use the **synchronous** driver and are dispatched to a
thread via ``asyncio.to_thread`` so the FastAPI event loop stays free.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, status

from synaptic.config import settings
from synaptic.core.ingestion import ingest_repository
from synaptic.graph.database import GraphService
from synaptic.graph.ingestor import ingest_to_neo4j
from synaptic.graph.search import similarity_search, hybrid_search
from synaptic.graph.setup_index import create_vector_index, create_uniqueness_constraints

graph_router = APIRouter(prefix="/graph")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_graph_service() -> GraphService:
    """Build a GraphService from application settings.

    Raises:
        HTTPException: If Neo4j credentials are not configured.
    """
    if not settings.neo4j_uri or not settings.neo4j_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Neo4j Aura credentials not configured. "
                "Set SYNAPTIC_NEO4J_URI and SYNAPTIC_NEO4J_PASSWORD "
                "in your .env file."
            ),
        )
    return GraphService(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class GraphIngestRequest(BaseModel):
    """Payload for ``POST /graph/ingest``.

    Attributes:
        path: Absolute local path to the repository to scan.
        blacklist: Optional glob patterns to exclude.
        embed: Whether to generate and store embeddings.
        clear_existing: Wipe existing graph data before ingesting.
    """

    path: str = Field(..., description="Absolute local path to the repository.")
    blacklist: list[str] | None = Field(None, description="Optional glob patterns to exclude.")
    embed: bool = Field(True, description="Generate and store embeddings.")
    clear_existing: bool = Field(False, description="Wipe existing data first.")


class GraphIngestResponse(BaseModel):
    """Response from ``POST /graph/ingest``."""

    status: str = Field("success")
    nodes_merged: int = Field(..., description="Nodes created/updated in Neo4j.")
    edges_merged: int = Field(..., description="Edges created/updated in Neo4j.")
    nodes_embedded: int = Field(..., description="Nodes with embeddings stored.")


class SearchRequest(BaseModel):
    """Payload for ``POST /graph/search``."""

    query: str = Field(..., description="Natural-language search query.")
    k: int = Field(5, ge=1, le=50, description="Number of results to return.")
    expand: bool = Field(False, description="Include graph neighbourhood context.")
    expand_depth: int = Field(1, ge=1, le=3, description="Hops for neighbourhood expansion.")


class SearchResult(BaseModel):
    """A single search result."""

    node_id: str
    name: str
    type: str | None = None
    filepath: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    docstring: str | None = None
    score: float | None = None
    relationship: str | None = None


class SearchResponse(BaseModel):
    """Response from ``POST /graph/search``."""

    query: str
    matches: list[SearchResult] = Field(default_factory=list)
    context: list[SearchResult] = Field(default_factory=list)


class SetupResponse(BaseModel):
    """Response from ``POST /graph/setup``."""

    status: str = Field("success")
    message: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@graph_router.post(
    "/ingest",
    response_model=GraphIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest repository into Neo4j Aura",
    description=(
        "Run Module 1 parsing, then push nodes and edges into Neo4j Aura "
        "Cloud using batched UNWIND writes. Optionally generates local "
        "HuggingFace embeddings and stores them on the graph nodes."
    ),
)
async def graph_ingest(request: GraphIngestRequest) -> GraphIngestResponse:
    """Parse a repo and push its knowledge graph into Neo4j Aura."""
    # Phase 0: Run Module 1 ingestion.
    try:
        graph = await ingest_repository(
            repo_path=request.path,
            blacklist=request.blacklist,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Module 1 ingestion failed: {exc}",
        )

    # Phase 1-3: Push to Neo4j + embed (sync → thread).
    def _do_ingest() -> dict:
        svc = _get_graph_service()
        with svc:
            return ingest_to_neo4j(
                graph=graph,
                repo_root=request.path,
                graph_service=svc,
                embed=request.embed,
                clear_existing=request.clear_existing,
                batch_size=settings.embedding_batch_size,
            )

    try:
        summary = await asyncio.to_thread(_do_ingest)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Neo4j ingestion failed: {exc}",
        )

    return GraphIngestResponse(
        status="success",
        nodes_merged=summary["nodes_merged"],
        edges_merged=summary["edges_merged"],
        nodes_embedded=summary["nodes_embedded"],
    )


@graph_router.post(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Semantic code search",
    description=(
        "Vectorize a natural-language query locally and find the most "
        "similar code entities in Neo4j Aura via vector index."
    ),
)
async def graph_search(request: SearchRequest) -> SearchResponse:
    """Perform hybrid vector + graph search."""
    def _do_search() -> tuple[list, list]:
        svc = _get_graph_service()
        with svc:
            if request.expand:
                raw = hybrid_search(
                    query_text=request.query,
                    graph_service=svc,
                    k=request.k,
                    expand_depth=request.expand_depth,
                )
                return raw["matches"], raw["context"]
            else:
                raw_matches = similarity_search(
                    query_text=request.query,
                    graph_service=svc,
                    k=request.k,
                )
                return raw_matches, []

    try:
        raw_matches, raw_context = await asyncio.to_thread(_do_search)
        matches = [SearchResult(**m) for m in raw_matches]
        context = [SearchResult(**c) for c in raw_context]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {exc}",
        )

    return SearchResponse(query=request.query, matches=matches, context=context)


@graph_router.post(
    "/setup",
    response_model=SetupResponse,
    status_code=status.HTTP_200_OK,
    summary="Set up Neo4j indexes and constraints",
    description="Create vector index and uniqueness constraints in Neo4j Aura.",
)
async def graph_setup() -> SetupResponse:
    """One-time setup of Neo4j vector index and constraints."""
    def _do_setup() -> None:
        svc = _get_graph_service()
        with svc:
            create_uniqueness_constraints(svc)
            create_vector_index(svc)

    try:
        await asyncio.to_thread(_do_setup)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Setup failed: {exc}",
        )

    return SetupResponse(status="success", message="Vector index and constraints created.")


@graph_router.delete(
    "/clear",
    response_model=SetupResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear all graph data",
    description="Delete all nodes and relationships from Neo4j. Use with caution.",
)
async def graph_clear() -> SetupResponse:
    """Wipe all data from the Neo4j database."""
    def _do_clear() -> None:
        svc = _get_graph_service()
        with svc:
            svc.clear_all()

    try:
        await asyncio.to_thread(_do_clear)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Clear failed: {exc}",
        )

    return SetupResponse(status="success", message="All graph data deleted.")
