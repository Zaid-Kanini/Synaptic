"""Hybrid retriever — vector search + graph traversal + lazy code loading.

Implements the "Search & Expand" strategy:

1. **Semantic Retrieval** — vectorize the user question with the same
   local HuggingFace model used during ingestion, then query the Neo4j
   vector index for the top-*k* entry-point nodes.
2. **Structural Expansion** — for each entry point, traverse 1st and
   2nd-degree graph neighbours (callers, callees, parent class/file,
   imports) via Cypher.
3. **Context Assembly** — lazy-load actual source snippets from disk
   using the node file-pointers, and build a structured context bundle
   with code + relationship metadata for the LLM.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any

import structlog

from synaptic.core.content_reader import read_lines
from synaptic.graph.database import GraphService
from synaptic.graph.embedder import Embedder
from synaptic.graph.search import VECTOR_INDEX_NAME

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------


@dataclass
class RetrievedNode:
    """A single node retrieved from the graph with optional source code."""

    node_id: str
    name: str
    type: str | None = None
    filepath: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    docstring: str | None = None
    score: float | None = None
    relationship: str | None = None
    source_code: str | None = None


@dataclass
class ContextBundle:
    """The assembled context package sent to the LLM.

    Attributes:
        entry_points: Nodes found by vector similarity (with code).
        neighbours: Expanded graph neighbours (with code).
        relationships: Human-readable relationship descriptions.
        total_chars: Running character count for context-window budgeting.
    """

    entry_points: list[RetrievedNode] = field(default_factory=list)
    neighbours: list[RetrievedNode] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    total_chars: int = 0

    @property
    def is_empty(self) -> bool:
        return len(self.entry_points) == 0


# ------------------------------------------------------------------
# Retriever
# ------------------------------------------------------------------


class Retriever:
    """Hybrid vector + graph retriever with lazy code loading.

    All methods are **synchronous** — FastAPI endpoints dispatch them
    via ``asyncio.to_thread``.

    Args:
        graph_service: An already-connected :class:`GraphService`.
        repo_root: Absolute path to the repository on disk.
        top_k: Number of vector-search results.
        expand_depth: Graph traversal depth (1 or 2 hops).
        max_nodes: Hard cap on total nodes to prevent context blowout.
        max_context_chars: Character budget for assembled source code.
    """

    def __init__(
        self,
        graph_service: GraphService,
        repo_root: str | pathlib.Path,
        *,
        top_k: int = 5,
        expand_depth: int = 2,
        max_nodes: int = 15,
        max_context_chars: int = 12_000,
    ) -> None:
        self._svc = graph_service
        self._root = pathlib.Path(repo_root).resolve()
        self.top_k = top_k
        self.expand_depth = expand_depth
        self.max_nodes = max_nodes
        self.max_context_chars = max_context_chars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(self, question: str) -> ContextBundle:
        """Run the full Search → Expand → Assemble pipeline.

        Args:
            question: Natural-language developer question.

        Returns:
            A :class:`ContextBundle` ready for LLM consumption.
        """
        # Step 1: Semantic retrieval
        entry_points = self._vector_search(question)

        if not entry_points:
            logger.info("retriever_no_matches", question=question[:80])
            return ContextBundle()

        # Step 2: Structural expansion
        entry_ids = [ep["node_id"] for ep in entry_points]
        neighbours, relationships = self._expand_graph(entry_ids)

        # Step 3: Assemble context with lazy code loading
        bundle = self._assemble_context(entry_points, neighbours, relationships)

        logger.info(
            "retriever_complete",
            entry_points=len(bundle.entry_points),
            neighbours=len(bundle.neighbours),
            relationships=len(bundle.relationships),
            total_chars=bundle.total_chars,
        )
        return bundle

    # ------------------------------------------------------------------
    # Step 1: Vector search
    # ------------------------------------------------------------------

    def _vector_search(self, question: str) -> list[dict[str, Any]]:
        """Vectorize the question and query the Neo4j vector index."""
        embedder = Embedder.get_instance()
        query_vec = embedder.embed_text(question)

        cypher = """
        CALL db.index.vector.queryNodes($index_name, $k, $query_vec)
        YIELD node, score
        RETURN node.id         AS node_id,
               node.name       AS name,
               node.type       AS type,
               node.filepath   AS filepath,
               node.start_line AS start_line,
               node.end_line   AS end_line,
               node.docstring  AS docstring,
               score
        ORDER BY score DESC
        """

        results = self._svc.run_cypher(
            cypher,
            {
                "index_name": VECTOR_INDEX_NAME,
                "k": self.top_k,
                "query_vec": query_vec,
            },
        )

        logger.info("vector_search_done", count=len(results))
        return results

    # ------------------------------------------------------------------
    # Step 2: Graph expansion
    # ------------------------------------------------------------------

    def _expand_graph(
        self, entry_ids: list[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Traverse 1st/2nd-degree neighbours and collect relationship metadata."""
        cypher = f"""
        UNWIND $ids AS nid
        MATCH (n {{id: nid}})-[r]-(neighbour)
        WHERE NOT neighbour.id IN $ids
        WITH DISTINCT neighbour, n, type(r) AS rel_type
        RETURN neighbour.id         AS node_id,
               neighbour.name       AS name,
               neighbour.type       AS type,
               neighbour.filepath   AS filepath,
               neighbour.start_line AS start_line,
               neighbour.end_line   AS end_line,
               neighbour.docstring  AS docstring,
               n.id                 AS source_node_id,
               n.name               AS source_name,
               rel_type             AS relationship
        LIMIT {self.max_nodes * 3}
        """

        raw = self._svc.run_cypher(cypher, {"ids": entry_ids})

        # Deduplicate neighbours and collect relationship descriptions.
        seen: set[str] = set()
        neighbours: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []

        for row in raw:
            rel_desc = {
                "source": row.get("source_name", "?"),
                "relationship": row.get("relationship", "RELATED_TO"),
                "target": row.get("name", "?"),
            }
            relationships.append(rel_desc)

            nid = row["node_id"]
            if nid not in seen:
                seen.add(nid)
                neighbours.append(row)

        # If expand_depth >= 2, do a second hop from the first-hop neighbours.
        if self.expand_depth >= 2 and neighbours:
            hop1_ids = [n["node_id"] for n in neighbours[: self.max_nodes]]
            all_known = set(entry_ids) | seen

            cypher_hop2 = f"""
            UNWIND $ids AS nid
            MATCH (n {{id: nid}})-[r]-(neighbour)
            WHERE NOT neighbour.id IN $exclude
            WITH DISTINCT neighbour, n, type(r) AS rel_type
            RETURN neighbour.id         AS node_id,
                   neighbour.name       AS name,
                   neighbour.type       AS type,
                   neighbour.filepath   AS filepath,
                   neighbour.start_line AS start_line,
                   neighbour.end_line   AS end_line,
                   neighbour.docstring  AS docstring,
                   n.id                 AS source_node_id,
                   n.name               AS source_name,
                   rel_type             AS relationship
            LIMIT {self.max_nodes * 2}
            """

            raw2 = self._svc.run_cypher(
                cypher_hop2,
                {"ids": hop1_ids, "exclude": list(all_known)},
            )

            for row in raw2:
                rel_desc = {
                    "source": row.get("source_name", "?"),
                    "relationship": row.get("relationship", "RELATED_TO"),
                    "target": row.get("name", "?"),
                }
                relationships.append(rel_desc)

                nid = row["node_id"]
                if nid not in seen:
                    seen.add(nid)
                    neighbours.append(row)

        logger.info(
            "graph_expansion_done",
            neighbours=len(neighbours),
            relationships=len(relationships),
        )
        return neighbours, relationships

    # ------------------------------------------------------------------
    # Step 3: Context assembly
    # ------------------------------------------------------------------

    def _assemble_context(
        self,
        entry_points: list[dict[str, Any]],
        neighbours: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> ContextBundle:
        """Load source code and build the final context bundle."""
        bundle = ContextBundle()
        budget = self.max_context_chars
        node_count = 0

        # Entry points get priority for code loading.
        for ep in entry_points:
            if node_count >= self.max_nodes:
                break
            node = self._to_retrieved_node(ep)
            code = self._load_source(node)
            if code:
                if budget - len(code) < 0:
                    code = code[: budget] + "\n... (truncated)"
                    budget = 0
                else:
                    budget -= len(code)
                node.source_code = code
            bundle.entry_points.append(node)
            node_count += 1

        # Then neighbours.
        for nb in neighbours:
            if node_count >= self.max_nodes or budget <= 0:
                break
            node = self._to_retrieved_node(nb)
            code = self._load_source(node)
            if code:
                if budget - len(code) < 0:
                    code = code[: budget] + "\n... (truncated)"
                    budget = 0
                else:
                    budget -= len(code)
                node.source_code = code
            bundle.neighbours.append(node)
            node_count += 1

        # Relationship descriptions.
        for rel in relationships:
            desc = f"{rel['source']} --[{rel['relationship']}]--> {rel['target']}"
            bundle.relationships.append(desc)

        bundle.total_chars = self.max_context_chars - budget
        return bundle

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_retrieved_node(record: dict[str, Any]) -> RetrievedNode:
        """Convert a Cypher result dict to a RetrievedNode."""
        return RetrievedNode(
            node_id=record.get("node_id", ""),
            name=record.get("name", ""),
            type=record.get("type"),
            filepath=record.get("filepath"),
            start_line=record.get("start_line"),
            end_line=record.get("end_line"),
            docstring=record.get("docstring"),
            score=record.get("score"),
            relationship=record.get("relationship"),
        )

    def _load_source(self, node: RetrievedNode) -> str | None:
        """Lazy-load source code from disk using the node's file pointers."""
        if not node.filepath or not node.start_line or not node.end_line:
            return None
        try:
            abs_path = (self._root / node.filepath).resolve()
            return read_lines(abs_path, node.start_line, node.end_line)
        except (FileNotFoundError, ValueError) as exc:
            logger.warning(
                "source_load_failed",
                node_id=node.node_id,
                error=str(exc),
            )
            return None
