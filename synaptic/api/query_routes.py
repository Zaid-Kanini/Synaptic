"""FastAPI route definitions for Module 3: GraphRAG Query Pipeline.

Provides the ``POST /query`` endpoint that accepts a developer question,
runs hybrid retrieval + LLM synthesis, and returns a structured answer
with source citations.

All heavy lifting (Neo4j queries, OpenAI calls) is synchronous and
dispatched via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status

from synaptic.config import settings
from synaptic.rag.pipeline import GraphRAGPipeline

query_router = APIRouter(prefix="/rag", tags=["GraphRAG"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class QueryRequest(BaseModel):
    """Payload for ``POST /rag/query``."""

    question: str = Field(
        ...,
        description="Natural-language developer question about the codebase.",
        min_length=3,
        max_length=1000,
    )
    repo_path: str = Field(
        ...,
        description="Absolute local path to the repository (for lazy code loading).",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of vector-search results.",
    )
    expand_depth: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Graph traversal depth (1-3 hops).",
    )


class SourceNodeResponse(BaseModel):
    """A code entity referenced in the answer."""

    node_id: str
    name: str
    type: str | None = None
    filepath: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    score: float | None = None
    relationship: str | None = None


class QueryResponse(BaseModel):
    """Response from ``POST /rag/query``."""

    answer: str = Field(..., description="Markdown-formatted LLM answer.")
    source_nodes: list[SourceNodeResponse] = Field(
        default_factory=list,
        description="Code entities used as context for the answer.",
    )
    relationships: list[str] = Field(
        default_factory=list,
        description="Graph relationship descriptions.",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Timing and usage metadata.",
    )


# ------------------------------------------------------------------
# Endpoint
# ------------------------------------------------------------------


@query_router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question about the codebase",
    description=(
        "Takes a natural-language developer question, performs hybrid "
        "vector + graph retrieval over the Neo4j knowledge graph, "
        "lazy-loads source code from disk, and synthesizes a structured "
        "Markdown answer using OpenAI GPT."
    ),
)
async def rag_query(request: QueryRequest) -> QueryResponse:
    """Run the full GraphRAG pipeline for a developer question."""
    if not settings.neo4j_uri or not settings.neo4j_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Neo4j credentials not configured. "
                "Set SYNAPTIC_NEO4J_URI and SYNAPTIC_NEO4J_PASSWORD."
            ),
        )

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "OpenAI API key not configured. "
                "Set SYNAPTIC_OPENAI_API_KEY in your .env file."
            ),
        )

    def _run_pipeline() -> dict:
        pipeline = GraphRAGPipeline(
            repo_root=request.repo_path,
            top_k=request.top_k,
            expand_depth=request.expand_depth,
        )
        result = pipeline.query(request.question)
        return {
            "answer": result.answer,
            "source_nodes": [
                {
                    "node_id": sn.node_id,
                    "name": sn.name,
                    "type": sn.type,
                    "filepath": sn.filepath,
                    "start_line": sn.start_line,
                    "end_line": sn.end_line,
                    "score": sn.score,
                    "relationship": sn.relationship,
                }
                for sn in result.source_nodes
            ],
            "relationships": result.relationships,
            "metadata": result.metadata,
        }

    try:
        data = await asyncio.to_thread(_run_pipeline)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"GraphRAG pipeline failed: {exc}",
        )

    return QueryResponse(**data)
