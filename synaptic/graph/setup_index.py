"""One-time script to create the Neo4j Vector Index in Aura.

Run this once after setting up your Neo4j Aura instance to create
the vector index required for similarity search.  Safe to re-run —
it checks for existing indexes before creating.

Usage::

    python -m synaptic.graph.setup_index

Requires ``SYNAPTIC_NEO4J_URI``, ``SYNAPTIC_NEO4J_USER``, and
``SYNAPTIC_NEO4J_PASSWORD`` environment variables (or a ``.env`` file).
"""

from __future__ import annotations

import os
import sys

import structlog

# Allow running as a standalone script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from synaptic.graph.database import GraphService
from synaptic.graph.embedder import EMBEDDING_DIM
from synaptic.graph.search import VECTOR_INDEX_NAME
from synaptic.logging import setup_logging

logger = structlog.get_logger(__name__)

# The label on which the vector index is built.
INDEX_LABEL: str = "CodeEntity"
INDEX_PROPERTY: str = "embedding"


def create_vector_index(svc: GraphService) -> None:
    """Create the vector similarity index if it does not already exist.

    Uses cosine similarity and the dimension matching ``all-MiniLM-L6-v2``
    (384).

    Args:
        svc: An already-connected :class:`GraphService`.
    """
    # Check if the index already exists.
    existing = svc.run_cypher("SHOW INDEXES YIELD name RETURN name")
    existing_names = {r["name"] for r in existing}

    if VECTOR_INDEX_NAME in existing_names:
        logger.info("vector_index_exists", name=VECTOR_INDEX_NAME)
        print(f"[OK] Vector index '{VECTOR_INDEX_NAME}' already exists.")
        return

    cypher = f"""
    CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
    FOR (n:{INDEX_LABEL})
    ON (n.{INDEX_PROPERTY})
    OPTIONS {{
        indexConfig: {{
            `vector.dimensions`: {EMBEDDING_DIM},
            `vector.similarity_function`: 'cosine'
        }}
    }}
    """

    svc.run_cypher(cypher)

    logger.info(
        "vector_index_created",
        name=VECTOR_INDEX_NAME,
        label=INDEX_LABEL,
        property=INDEX_PROPERTY,
        dimensions=EMBEDDING_DIM,
    )
    print(
        f"[OK] Created vector index '{VECTOR_INDEX_NAME}' "
        f"(label={INDEX_LABEL}, property={INDEX_PROPERTY}, "
        f"dim={EMBEDDING_DIM}, similarity=cosine)"
    )


def create_uniqueness_constraints(svc: GraphService) -> None:
    """Create uniqueness constraints on node IDs for fast lookups.

    Args:
        svc: An already-connected :class:`GraphService`.
    """
    constraints = [
        ("code_entity_id_unique", "CodeEntity", "id"),
        ("external_lib_id_unique", "ExternalLibrary", "id"),
    ]

    for name, label, prop in constraints:
        cypher = f"""
        CREATE CONSTRAINT {name} IF NOT EXISTS
        FOR (n:{label})
        REQUIRE n.{prop} IS UNIQUE
        """
        try:
            svc.run_cypher(cypher)
            logger.info("constraint_created", name=name)
            print(f"[OK] Constraint '{name}' ensured.")
        except Exception as exc:
            # Some Aura tiers may not support certain constraint types.
            logger.warning("constraint_failed", name=name, error=str(exc))
            print(f"[WARN] Constraint '{name}' skipped: {exc}")


def main() -> None:
    """Entry point: load env vars, connect, and set up indexes."""
    setup_logging("INFO")

    # Load from environment (or .env via python-dotenv).
    from dotenv import load_dotenv
    load_dotenv()

    uri = os.environ.get("SYNAPTIC_NEO4J_URI", "")
    user = os.environ.get("SYNAPTIC_NEO4J_USER", "neo4j")
    password = os.environ.get("SYNAPTIC_NEO4J_PASSWORD", "")

    if not uri or not password:
        print(
            "[ERROR] Set SYNAPTIC_NEO4J_URI and SYNAPTIC_NEO4J_PASSWORD in your .env file.\n"
            "  Example:\n"
            "    SYNAPTIC_NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io\n"
            "    SYNAPTIC_NEO4J_USER=neo4j\n"
            "    SYNAPTIC_NEO4J_PASSWORD=your-password\n"
        )
        sys.exit(1)

    with GraphService(uri, user, password) as svc:
        print(f"Connected to {uri}")
        create_uniqueness_constraints(svc)
        create_vector_index(svc)
        print("\n[DONE] Neo4j Aura setup complete.")


if __name__ == "__main__":
    main()
