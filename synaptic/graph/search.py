"""Hybrid vector + graph search over the Neo4j knowledge graph.

Vectorizes a query locally using the same HuggingFace model used for
node embeddings, then executes ``db.index.vector.queryNodes()`` against
Neo4j Aura to find the most semantically similar code entities.
"""

from __future__ import annotations

from typing import Any

import structlog

from synaptic.graph.database import GraphService
from synaptic.graph.embedder import Embedder, EMBEDDING_DIM

logger = structlog.get_logger(__name__)

# Name of the Neo4j vector index (must match setup_index.py).
VECTOR_INDEX_NAME: str = "code_embedding_index"


def similarity_search(
    query_text: str,
    graph_service: GraphService,
    k: int = 5,
) -> list[dict[str, Any]]:
    """Find the *k* most similar code nodes for a natural-language query.

    1. Vectorize ``query_text`` locally via the Embedder singleton.
    2. Execute a vector similarity query against Neo4j Aura.
    3. Return the top-*k* results with metadata and similarity scores.

    Args:
        query_text: Natural-language search query (e.g.
            ``"function that validates user input"``).
        graph_service: An already-connected :class:`GraphService`.
        k: Number of nearest neighbours to return.

    Returns:
        A list of dicts, each containing::

            {
                "node_id": str,
                "name": str,
                "type": str,
                "filepath": str,
                "start_line": int,
                "end_line": int,
                "score": float,       # cosine similarity
                "docstring": str | None,
            }

        Ordered by descending similarity score.
    """
    embedder = Embedder.get_instance()
    query_vec = embedder.embed_text(query_text)

    logger.info("similarity_search", query=query_text[:80], k=k)

    cypher = """
    CALL db.index.vector.queryNodes($index_name, $k, $query_vec)
    YIELD node, score
    RETURN node.id        AS node_id,
           node.name      AS name,
           node.type      AS type,
           node.filepath  AS filepath,
           node.start_line AS start_line,
           node.end_line  AS end_line,
           node.docstring AS docstring,
           score
    ORDER BY score DESC
    """

    results = graph_service.run_cypher(
        cypher,
        {
            "index_name": VECTOR_INDEX_NAME,
            "k": k,
            "query_vec": query_vec,
        },
    )

    logger.info("similarity_search_results", count=len(results))
    return results


def hybrid_search(
    query_text: str,
    graph_service: GraphService,
    k: int = 5,
    expand_depth: int = 1,
) -> dict[str, Any]:
    """Vector search + graph neighbourhood expansion.

    First performs a vector similarity search, then expands each result
    by traversing its immediate graph neighbourhood (callers, callees,
    parent class/file) up to ``expand_depth`` hops.

    This gives the consumer both *semantic relevance* and *structural
    context* — ideal for RAG pipelines.

    Args:
        query_text: Natural-language search query.
        graph_service: An already-connected :class:`GraphService`.
        k: Number of nearest neighbours from vector search.
        expand_depth: Number of relationship hops to expand.

    Returns:
        A dict with::

            {
                "matches": [<similarity_search results>],
                "context": [<expanded neighbour nodes>],
            }
    """
    matches = similarity_search(query_text, graph_service, k=k)

    if not matches:
        return {"matches": [], "context": []}

    # Collect matched node IDs for neighbourhood expansion.
    match_ids = [m["node_id"] for m in matches]

    cypher = f"""
    UNWIND $ids AS nid
    MATCH (n {{id: nid}})-[r*1..{expand_depth}]-(neighbour)
    WHERE NOT neighbour.id IN $ids
    RETURN DISTINCT
           neighbour.id        AS node_id,
           neighbour.name      AS name,
           neighbour.type      AS type,
           neighbour.filepath  AS filepath,
           neighbour.start_line AS start_line,
           neighbour.end_line  AS end_line,
           neighbour.docstring AS docstring,
           type(r[0])          AS relationship
    LIMIT 50
    """

    context = graph_service.run_cypher(
        cypher, {"ids": match_ids}
    )

    logger.info(
        "hybrid_search_complete",
        matches=len(matches),
        context_nodes=len(context),
    )

    return {"matches": matches, "context": context}
