"""Graph ingestor — orchestrates Module 1 JSON → Neo4j Aura + embeddings.

Takes a :class:`CodeGraph` produced by Module 1, pushes nodes and edges
into Neo4j Aura Cloud using batched ``UNWIND`` writes, then generates
local HuggingFace embeddings for Function/Class nodes and stores the
vectors back on the graph nodes.
"""

from __future__ import annotations

import pathlib

import structlog

from synaptic.graph.database import GraphService
from synaptic.graph.embedder import Embedder
from synaptic.models.graph import CodeGraph

logger = structlog.get_logger(__name__)


def ingest_to_neo4j(
    graph: CodeGraph,
    repo_root: str | pathlib.Path,
    graph_service: GraphService,
    *,
    embed: bool = True,
    clear_existing: bool = False,
    batch_size: int = 200,
) -> dict:
    """Push a Module 1 code graph into Neo4j Aura and optionally embed.

    This is the main entry point for Module 2.  It performs three phases:

    1. **Nodes** — Batch-MERGE all code entities (File, Class, Function).
    2. **Edges** — Batch-MERGE all relationships (DEFINES, CALLS, IMPORTS)
       with automatic ``ExternalLibrary`` placeholder creation for
       unresolved targets.
    3. **Embeddings** (optional) — Read each Function/Class node's source
       from disk via pointers, generate a 384-dim vector locally, and
       store it on the Neo4j node.

    Args:
        graph: The lean code graph from Module 1.
        repo_root: Absolute path to the repository root (needed to
            resolve file pointers for embedding).
        graph_service: An already-connected :class:`GraphService`.
        embed: Whether to generate and store embeddings (default True).
        clear_existing: If True, wipe all existing data first.
        batch_size: Records per UNWIND transaction.

    Returns:
        A summary dict with counts::

            {
                "nodes_merged": int,
                "edges_merged": int,
                "nodes_embedded": int,
            }
    """
    root = pathlib.Path(repo_root).resolve()

    if clear_existing:
        logger.warning("clearing_existing_graph_data")
        graph_service.clear_all()

    # ------------------------------------------------------------------
    # Phase 1: Batch-create nodes
    # ------------------------------------------------------------------
    logger.info("phase1_nodes_start", total=len(graph.nodes))

    node_records = [
        {
            "id": n.id,
            "type": n.type.value,
            "name": n.name,
            "filepath": n.filepath,
            "start_line": n.start_line,
            "end_line": n.end_line,
            "docstring": n.docstring,
        }
        for n in graph.nodes
    ]

    nodes_merged = graph_service.batch_create_nodes(
        node_records, batch_size=batch_size
    )
    logger.info("phase1_nodes_done", merged=nodes_merged)

    # ------------------------------------------------------------------
    # Phase 2: Batch-create edges (with ExternalLibrary fallback)
    # ------------------------------------------------------------------
    logger.info("phase2_edges_start", total=len(graph.edges))

    edge_records = [
        {
            "source_id": e.source_id,
            "target_id": e.target_id,
            "type": e.type.value,
        }
        for e in graph.edges
    ]

    edges_merged = graph_service.batch_create_edges(
        edge_records, batch_size=batch_size
    )
    logger.info("phase2_edges_done", merged=edges_merged)

    # ------------------------------------------------------------------
    # Phase 3: Generate & store embeddings (optional)
    # ------------------------------------------------------------------
    nodes_embedded = 0

    if embed:
        logger.info("phase3_embeddings_start")

        embedder = Embedder.get_instance()
        embedding_records = embedder.embed_nodes(
            graph.nodes, root, batch_size=32
        )

        if embedding_records:
            nodes_embedded = graph_service.batch_update_embeddings(
                embedding_records, batch_size=batch_size
            )

        logger.info("phase3_embeddings_done", embedded=nodes_embedded)

    summary = {
        "nodes_merged": nodes_merged,
        "edges_merged": edges_merged,
        "nodes_embedded": nodes_embedded,
    }
    logger.info("ingest_to_neo4j_complete", **summary)
    return summary
