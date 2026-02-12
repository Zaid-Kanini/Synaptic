"""Neo4j Aura Cloud connection manager with batch Cypher execution.

Uses the **synchronous** ``GraphDatabase.driver`` and ``execute_query``
API as recommended by the official Neo4j Python driver docs.  FastAPI
endpoints call these methods via ``asyncio.to_thread`` so the event
loop is never blocked.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from neo4j import GraphDatabase, Driver

logger = structlog.get_logger(__name__)

# Default batch size for UNWIND operations — tuned for Aura latency.
DEFAULT_BATCH_SIZE: int = 200


class GraphService:
    """Synchronous connection manager for Neo4j Aura Cloud.

    Usage::

        svc = GraphService(uri, user, password)
        svc.connect()
        svc.batch_create_nodes(records)
        svc.close()

    Or as a context manager::

        with GraphService(uri, user, password) as svc:
            svc.batch_create_nodes(records)

    Attributes:
        uri: Neo4j Aura ``neo4j+s://`` connection string.
        user: Database username (typically ``neo4j``).
        database: Target database name (``neo4j`` for Aura free tier).
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
    ) -> None:
        self.uri = uri
        self.user = user
        self._password = password
        self.database = database
        self._driver: Optional[Driver] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish the driver connection to Aura."""
        if self._driver is not None:
            return
        self._driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self._password),
        )
        self._driver.verify_connectivity()
        logger.info("neo4j_connected", uri=self.uri, database=self.database)

    def close(self) -> None:
        """Gracefully close the driver connection."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("neo4j_disconnected")

    def __enter__(self) -> GraphService:
        self.connect()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _ensure_driver(self) -> Driver:
        """Return the driver, raising if not connected."""
        if self._driver is None:
            raise RuntimeError("GraphService is not connected. Call connect() first.")
        return self._driver

    # ------------------------------------------------------------------
    # Batch write helpers (UNWIND + MERGE for idempotency)
    # ------------------------------------------------------------------

    def batch_create_nodes(
        self,
        records: list[dict[str, Any]],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> int:
        """Create or update code-entity nodes in batches.

        Each record must contain at minimum::

            {
                "id": "...",
                "type": "file" | "class" | "function",
                "name": "...",
                "filepath": "...",
                "start_line": 1,
                "end_line": 10,
                "docstring": "..." | None,
            }

        Nodes are labeled ``CodeEntity`` with a secondary label
        (``File``, ``Class``, ``Function``) applied per type.
        ``MERGE`` ensures idempotency.  No APOC dependency.

        Args:
            records: List of node property dicts.
            batch_size: Number of records per UNWIND transaction.

        Returns:
            Total number of nodes merged.
        """
        driver = self._ensure_driver()
        total = 0
        # Group by type so we can apply the correct secondary label
        # without needing APOC's dynamic label support.
        by_type: dict[str, list[dict[str, Any]]] = {}
        for rec in records:
            by_type.setdefault(rec["type"], []).append(rec)

        for node_type, type_records in by_type.items():
            cypher = _merge_nodes_cypher_for_type(node_type)
            for chunk in _chunked(type_records, batch_size):
                cnt = self._execute_write(driver, cypher, {"batch": chunk})
                total += cnt
                logger.debug("batch_nodes_merged", type=node_type, count=cnt, batch_size=len(chunk))
        return total

    def batch_create_edges(
        self,
        records: list[dict[str, Any]],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> int:
        """Create or update relationships in batches.

        Each record must contain::

            {
                "source_id": "...",
                "target_id": "...",
                "type": "defines" | "calls" | "imports",
            }

        If the ``target_id`` does not match any existing node, an
        ``ExternalLibrary`` placeholder node is created to preserve
        graph connectivity.

        Args:
            records: List of edge property dicts.
            batch_size: Number of records per UNWIND transaction.

        Returns:
            Total number of relationships merged.
        """
        driver = self._ensure_driver()
        total = 0
        cypher = _merge_edges_cypher()
        for chunk in _chunked(records, batch_size):
            cnt = self._execute_write(driver, cypher, {"batch": chunk})
            total += cnt
            logger.debug("batch_edges_merged", count=cnt, batch_size=len(chunk))
        return total

    def update_node_embedding(
        self,
        node_id: str,
        embedding: list[float],
    ) -> None:
        """Store a vector embedding on an existing node.

        Args:
            node_id: The deterministic node ID.
            embedding: The float vector (e.g. 384-dim from MiniLM).
        """
        driver = self._ensure_driver()
        driver.execute_query(
            "MATCH (n {id: $node_id}) SET n.embedding = $embedding",
            node_id=node_id,
            embedding=embedding,
            database_=self.database,
        )

    def batch_update_embeddings(
        self,
        records: list[dict[str, Any]],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> int:
        """Batch-update embeddings on existing nodes.

        Each record: ``{"id": "...", "embedding": [float, ...]}``.

        Args:
            records: List of dicts with ``id`` and ``embedding``.
            batch_size: Number of records per UNWIND transaction.

        Returns:
            Total number of nodes updated.
        """
        driver = self._ensure_driver()
        total = 0
        cypher = """
        UNWIND $batch AS rec
        MATCH (n {id: rec.id})
        SET n.embedding = rec.embedding
        RETURN count(n) AS cnt
        """
        for chunk in _chunked(records, batch_size):
            cnt = self._execute_write(driver, cypher, {"batch": chunk})
            total += cnt
            logger.debug("batch_embeddings_updated", count=cnt)
        return total

    def run_cypher(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute an arbitrary read query and return result records.

        Args:
            cypher: The Cypher query string.
            parameters: Optional query parameters.

        Returns:
            List of record dicts.
        """
        driver = self._ensure_driver()
        records, _, _ = driver.execute_query(
            cypher,
            parameters_=parameters or {},
            database_=self.database,
        )
        return [record.data() for record in records]

    def clear_all(self) -> None:
        """Delete all nodes and relationships. **Use with caution.**"""
        driver = self._ensure_driver()
        driver.execute_query(
            "MATCH (n) DETACH DELETE n",
            database_=self.database,
        )
        logger.warning("neo4j_cleared_all")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _execute_write(
        driver: Driver,
        cypher: str,
        parameters: dict[str, Any],
    ) -> int:
        """Run a write query via execute_query and return the ``cnt`` scalar."""
        records, _, _ = driver.execute_query(
            cypher,
            parameters_=parameters,
            database_="neo4j",
        )
        if records:
            return records[0].get("cnt", 0)
        return 0


# ------------------------------------------------------------------
# Cypher templates
# ------------------------------------------------------------------


def _merge_nodes_cypher_for_type(node_type: str) -> str:
    """Return a Cypher MERGE query for a specific node type.

    Each type gets its own secondary label (``File``, ``Class``,
    ``Function``) alongside the base ``CodeEntity`` label.  This
    avoids any APOC dependency.

    Args:
        node_type: One of ``"file"``, ``"class"``, ``"function"``.

    Returns:
        A parameterized Cypher string expecting a ``$batch`` parameter.
    """
    label_map = {
        "file": "File",
        "class": "Class",
        "function": "Function",
    }
    secondary = label_map.get(node_type, "CodeEntity")

    return f"""
    UNWIND $batch AS rec
    MERGE (n:CodeEntity:{secondary} {{id: rec.id}})
    SET n.name       = rec.name,
        n.filepath   = rec.filepath,
        n.start_line = rec.start_line,
        n.end_line   = rec.end_line,
        n.docstring  = rec.docstring,
        n.type       = rec.type
    RETURN count(n) AS cnt
    """


def _merge_edges_cypher() -> str:
    """Return a Cypher query that MERGEs edges with ExternalLibrary fallback.

    No APOC dependency.  Uses ``FOREACH`` + ``CASE`` pattern for
    conditional relationship creation and missing-target handling.
    """
    return """
    UNWIND $batch AS rec

    MATCH (src:CodeEntity {id: rec.source_id})

    OPTIONAL MATCH (tgt:CodeEntity {id: rec.target_id})
    WITH src, rec,
         CASE WHEN tgt IS NOT NULL THEN tgt ELSE null END AS resolved

    FOREACH (_ IN CASE WHEN resolved IS NULL THEN [1] ELSE [] END |
        MERGE (ext:ExternalLibrary {id: rec.target_id})
        SET ext.name = rec.target_id
    )

    WITH src, rec
    MATCH (tgt {id: rec.target_id})

    FOREACH (_ IN CASE WHEN rec.type = 'defines' THEN [1] ELSE [] END |
        MERGE (src)-[:DEFINES]->(tgt)
    )
    FOREACH (_ IN CASE WHEN rec.type = 'calls' THEN [1] ELSE [] END |
        MERGE (src)-[:CALLS]->(tgt)
    )
    FOREACH (_ IN CASE WHEN rec.type = 'imports' THEN [1] ELSE [] END |
        MERGE (src)-[:IMPORTS]->(tgt)
    )

    RETURN count(tgt) AS cnt
    """


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    """Split *items* into sub-lists of at most *size* elements."""
    return [items[i : i + size] for i in range(0, len(items), size)]
