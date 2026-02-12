"""Local HuggingFace embedding service with pointer-aware disk reading.

Loads ``sentence-transformers`` locally (Singleton) and generates
384-dimensional vectors from code snippets resolved via Module 1's
file pointers (``filepath``, ``start_line``, ``end_line``).
"""

from __future__ import annotations

import pathlib
import threading
from typing import Optional

import structlog
from sentence_transformers import SentenceTransformer

from synaptic.core.content_reader import read_lines
from synaptic.models.graph import NodeRecord, NodeType

logger = structlog.get_logger(__name__)

# Default model — 384-dim vectors, fast and lightweight.
DEFAULT_MODEL: str = "all-MiniLM-L6-v2"
EMBEDDING_DIM: int = 384


class Embedder:
    """Singleton wrapper around a local ``SentenceTransformer`` model.

    The model is loaded **once** on first use and reused across all
    subsequent calls, keeping GPU/CPU memory stable.

    Usage::

        embedder = Embedder.get_instance()
        vec = embedder.embed_text("def hello(): pass")
        vecs = embedder.embed_nodes(nodes, repo_root)

    Attributes:
        model_name: HuggingFace model identifier.
        dimension: Expected output vector dimension.
    """

    _instance: Optional[Embedder] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self.dimension = EMBEDDING_DIM
        self._model: Optional[SentenceTransformer] = None

    @classmethod
    def get_instance(cls, model_name: str = DEFAULT_MODEL) -> Embedder:
        """Return the singleton Embedder, creating it on first call.

        Args:
            model_name: HuggingFace model identifier.

        Returns:
            The shared :class:`Embedder` instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(model_name)
        return cls._instance

    def _load_model(self) -> SentenceTransformer:
        """Lazy-load the transformer model."""
        if self._model is None:
            logger.info("loading_embedding_model", model=self.model_name)
            self._model = SentenceTransformer(self.model_name)
            logger.info("embedding_model_loaded", model=self.model_name, dim=self.dimension)
        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text string.

        Args:
            text: The input text (code snippet, query, etc.).

        Returns:
            A list of floats with length ``self.dimension``.
        """
        model = self._load_model()
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Generate embeddings for multiple texts in a single batch.

        Args:
            texts: List of input strings.
            batch_size: Encode batch size (controls memory usage).

        Returns:
            List of float vectors, one per input text.
        """
        model = self._load_model()
        vecs = model.encode(texts, batch_size=batch_size, normalize_embeddings=True)
        return [v.tolist() for v in vecs]

    def embed_node(
        self,
        node: NodeRecord,
        repo_root: pathlib.Path,
    ) -> Optional[list[float]]:
        """Read a node's source from disk and embed it.

        Only ``Function`` and ``Class`` nodes are embedded (``File``
        nodes are typically too large for a single vector).

        Args:
            node: The node record with file pointers.
            repo_root: Absolute path to the repository root.

        Returns:
            The embedding vector, or ``None`` if the node type is
            skipped or the file cannot be read.
        """
        if node.type not in (NodeType.FUNCTION, NodeType.CLASS):
            return None

        try:
            abs_path = (repo_root / node.filepath).resolve()
            snippet = read_lines(abs_path, node.start_line, node.end_line)
        except (FileNotFoundError, ValueError) as exc:
            logger.warning(
                "embed_node_read_failed",
                node_id=node.id,
                error=str(exc),
            )
            return None

        # Prepend metadata for richer semantic signal.
        text = f"{node.type.value} {node.name}\n{snippet}"
        return self.embed_text(text)

    def embed_nodes(
        self,
        nodes: list[NodeRecord],
        repo_root: pathlib.Path,
        batch_size: int = 32,
    ) -> list[dict]:
        """Batch-embed eligible nodes by reading their source from disk.

        Reads each node's snippet, batches them through the model, and
        returns a list of ``{"id": ..., "embedding": [...]}`` dicts
        ready for :meth:`GraphService.batch_update_embeddings`.

        Args:
            nodes: All nodes from the code graph.
            repo_root: Absolute path to the repository root.
            batch_size: Encode batch size.

        Returns:
            List of dicts with ``id`` and ``embedding`` keys.
            Only includes nodes that were successfully embedded.
        """
        eligible: list[tuple[str, str]] = []  # (node_id, text)

        for node in nodes:
            if node.type not in (NodeType.FUNCTION, NodeType.CLASS):
                continue
            try:
                abs_path = (repo_root / node.filepath).resolve()
                snippet = read_lines(abs_path, node.start_line, node.end_line)
            except (FileNotFoundError, ValueError) as exc:
                logger.warning(
                    "embed_node_read_failed",
                    node_id=node.id,
                    error=str(exc),
                )
                continue

            text = f"{node.type.value} {node.name}\n{snippet}"
            eligible.append((node.id, text))

        if not eligible:
            return []

        ids, texts = zip(*eligible)
        vectors = self.embed_texts(list(texts), batch_size=batch_size)

        logger.info("nodes_embedded", count=len(vectors))

        return [
            {"id": nid, "embedding": vec}
            for nid, vec in zip(ids, vectors)
        ]
