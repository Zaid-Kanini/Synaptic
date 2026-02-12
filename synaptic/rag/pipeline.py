"""GraphRAG pipeline — the main orchestrator connecting retrieval to synthesis.

Takes a developer question, runs the hybrid retriever to gather
graph context, then feeds the context to the LLM for a structured
Markdown answer.  All methods are **synchronous**; FastAPI endpoints
dispatch via ``asyncio.to_thread``.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any

import structlog

from synaptic.config import settings
from synaptic.graph.database import GraphService
from synaptic.rag.retriever import Retriever, ContextBundle, RetrievedNode
from synaptic.rag.llm_service import LLMService

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Response model
# ------------------------------------------------------------------


@dataclass
class SourceNode:
    """Lightweight reference to a code entity for the UI."""

    node_id: str
    name: str
    type: str | None = None
    filepath: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    score: float | None = None
    relationship: str | None = None


@dataclass
class QueryResult:
    """The final response from the GraphRAG pipeline.

    Attributes:
        answer: Markdown-formatted LLM response.
        source_nodes: List of code entities used as context.
        relationships: Graph relationship descriptions.
        metadata: Timing and token usage info.
    """

    answer: str
    source_nodes: list[SourceNode] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------
# Pipeline
# ------------------------------------------------------------------


class GraphRAGPipeline:
    """End-to-end GraphRAG pipeline: Question → Retrieval → LLM → Answer.

    Usage::

        pipeline = GraphRAGPipeline(repo_root="/path/to/repo")
        result = pipeline.query("How is user data validated?")
        print(result.answer)

    Args:
        repo_root: Absolute path to the repository on disk.
        top_k: Number of vector-search results.
        expand_depth: Graph traversal depth.
        max_nodes: Hard cap on total context nodes.
        max_context_chars: Character budget for source code.
        openai_model: OpenAI model identifier override.
    """

    def __init__(
        self,
        repo_root: str | pathlib.Path,
        *,
        top_k: int | None = None,
        expand_depth: int | None = None,
        max_nodes: int | None = None,
        max_context_chars: int | None = None,
        openai_model: str | None = None,
    ) -> None:
        self._repo_root = pathlib.Path(repo_root).resolve()
        self._top_k = top_k or settings.rag_top_k
        self._expand_depth = expand_depth or settings.rag_expand_depth
        self._max_nodes = max_nodes or settings.rag_max_nodes
        self._max_context_chars = max_context_chars or settings.rag_max_context_chars
        self._openai_model = openai_model or settings.openai_model

    def query(self, question: str) -> QueryResult:
        """Run the full pipeline for a developer question.

        1. Connect to Neo4j.
        2. Retrieve context via hybrid search + graph expansion.
        3. Synthesize an answer via OpenAI.
        4. Return structured result with sources.

        Args:
            question: Natural-language developer question.

        Returns:
            A :class:`QueryResult` with the answer, sources, and metadata.

        Raises:
            RuntimeError: If OpenAI API key is not configured.
        """
        import time

        if not settings.openai_api_key:
            raise RuntimeError(
                "OpenAI API key not configured. "
                "Set SYNAPTIC_OPENAI_API_KEY in your .env file."
            )

        t_start = time.perf_counter()

        # Step 1: Retrieve
        svc = GraphService(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )

        with svc:
            retriever = Retriever(
                graph_service=svc,
                repo_root=self._repo_root,
                top_k=self._top_k,
                expand_depth=self._expand_depth,
                max_nodes=self._max_nodes,
                max_context_chars=self._max_context_chars,
            )
            context = retriever.retrieve(question)

        t_retrieve = time.perf_counter()

        # Step 2: Synthesize
        llm = LLMService(
            api_key=settings.openai_api_key,
            azure_endpoint=settings.azure_endpoint,
            deployment=self._openai_model,
        )
        answer = llm.synthesize(question, context)

        t_synthesize = time.perf_counter()

        # Step 3: Build response
        source_nodes = self._extract_source_nodes(context)

        result = QueryResult(
            answer=answer,
            source_nodes=source_nodes,
            relationships=context.relationships,
            metadata={
                "retrieval_time_ms": round((t_retrieve - t_start) * 1000),
                "synthesis_time_ms": round((t_synthesize - t_retrieve) * 1000),
                "total_time_ms": round((t_synthesize - t_start) * 1000),
                "entry_points": len(context.entry_points),
                "neighbours": len(context.neighbours),
                "context_chars": context.total_chars,
                "model": self._openai_model,
            },
        )

        logger.info(
            "pipeline_complete",
            question=question[:80],
            **result.metadata,
        )

        return result

    @staticmethod
    def _extract_source_nodes(context: ContextBundle) -> list[SourceNode]:
        """Flatten entry points + neighbours into a single source list."""
        nodes: list[SourceNode] = []

        for ep in context.entry_points:
            nodes.append(_to_source_node(ep))

        for nb in context.neighbours:
            nodes.append(_to_source_node(nb))

        return nodes


def _to_source_node(node: RetrievedNode) -> SourceNode:
    """Convert a RetrievedNode to a lightweight SourceNode."""
    return SourceNode(
        node_id=node.node_id,
        name=node.name,
        type=node.type,
        filepath=node.filepath,
        start_line=node.start_line,
        end_line=node.end_line,
        score=node.score,
        relationship=node.relationship,
    )
