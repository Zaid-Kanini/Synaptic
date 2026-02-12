"""Graph data models for nodes, edges, and the complete code graph.

These Pydantic v2 models define the strict JSON schema that is output
by the ingestion pipeline and consumed by the Neo4j graph database.
"""

from __future__ import annotations

import enum
from typing import Optional

from pydantic import BaseModel, Field


class NodeType(str, enum.Enum):
    """Enumeration of supported node types in the knowledge graph."""

    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"


class EdgeType(str, enum.Enum):
    """Enumeration of supported edge/relationship types."""

    DEFINES = "defines"
    CALLS = "calls"
    IMPORTS = "imports"


class NodeRecord(BaseModel):
    """A single node in the code knowledge graph.

    Content is **not** stored inline.  Instead, each node retains
    ``filepath``, ``start_line``, and ``end_line`` as *pointers* so that
    the raw source can be read on demand via
    :func:`synaptic.core.content_reader.get_node_content`.

    Attributes:
        id: Deterministic unique identifier (e.g. ``filepath::class::function``).
        type: The kind of code entity this node represents.
        name: Human-readable name of the entity.
        filepath: Absolute or repo-relative path to the source file.
        start_line: 1-indexed starting line number in the source file.
        end_line: 1-indexed ending line number in the source file.
        docstring: Extracted docstring, if present.
    """

    id: str = Field(..., description="Deterministic unique identifier.")
    type: NodeType = Field(..., description="Kind of code entity.")
    name: str = Field(..., description="Human-readable entity name.")
    filepath: str = Field(..., description="Path to the source file (repo-relative pointer).")
    start_line: int = Field(..., ge=1, description="Starting line number (1-indexed pointer).")
    end_line: int = Field(..., ge=1, description="Ending line number (1-indexed pointer).")
    docstring: Optional[str] = Field(None, description="Extracted docstring.")


class EdgeRecord(BaseModel):
    """A directed edge (relationship) between two nodes.

    Attributes:
        source_id: The ``id`` of the originating node.
        target_id: The ``id`` of the destination node (or unresolved name).
        type: The kind of relationship this edge represents.
    """

    source_id: str = Field(..., description="Originating node id.")
    target_id: str = Field(..., description="Destination node id or unresolved name.")
    type: EdgeType = Field(..., description="Relationship type.")


class CodeGraph(BaseModel):
    """Complete knowledge graph produced by the ingestion pipeline.

    Attributes:
        nodes: All extracted code entities.
        edges: All relationships between entities.
    """

    nodes: list[NodeRecord] = Field(default_factory=list, description="Extracted code entities.")
    edges: list[EdgeRecord] = Field(default_factory=list, description="Relationships between entities.")
