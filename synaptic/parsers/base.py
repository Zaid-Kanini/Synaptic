"""Abstract base class for all language-specific tree-sitter parsers.

Every new language grammar must subclass :class:`BaseLanguageParser` and
implement the abstract extraction methods.
"""

from __future__ import annotations

import abc
import pathlib

from synaptic.models.graph import CodeGraph


class BaseLanguageParser(abc.ABC):
    """Contract that every language parser must fulfil.

    Subclasses are responsible for:

    1. Initialising the appropriate ``tree-sitter`` ``Language`` and ``Parser``.
    2. Extracting nodes (files, classes, functions) and edges (defines,
       calls, imports) from the concrete syntax tree.

    Args:
        repo_root: The root of the repository being scanned, used to
            compute repo-relative file paths for node IDs.
    """

    def __init__(self, repo_root: pathlib.Path) -> None:
        self.repo_root = repo_root.resolve()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def parse_file(self, file_path: pathlib.Path, source: bytes) -> CodeGraph:
        """Parse *source* and return extracted nodes and edges.

        Args:
            file_path: Absolute path to the source file.
            source: Raw bytes of the source file.

        Returns:
            A :class:`CodeGraph` containing all nodes and edges found in
            the file.
        """

    # ------------------------------------------------------------------
    # Helpers available to all subclasses
    # ------------------------------------------------------------------

    def _relative_path(self, file_path: pathlib.Path) -> str:
        """Return a POSIX-style repo-relative path string.

        Args:
            file_path: Absolute path to convert.

        Returns:
            Forward-slash separated relative path.
        """
        try:
            return file_path.resolve().relative_to(self.repo_root).as_posix()
        except ValueError:
            return file_path.as_posix()

    @staticmethod
    def _node_text(node: object) -> str:
        """Decode the UTF-8 text of a tree-sitter node.

        Args:
            node: A ``tree_sitter.Node`` instance.

        Returns:
            The decoded text content.
        """
        # tree_sitter.Node exposes ``text`` as ``bytes | None``.
        text: bytes | None = getattr(node, "text", None)
        if text is None:
            return ""
        return text.decode("utf-8", errors="replace")
