"""Tree-sitter based parser for Python source files.

Extracts functions, classes, call-site relationships, and import
statements from the Python AST.
"""

from __future__ import annotations

import pathlib
from typing import Optional

import structlog
import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Node

from synaptic.models.graph import (
    CodeGraph,
    EdgeRecord,
    EdgeType,
    NodeRecord,
    NodeType,
)
from synaptic.parsers.base import BaseLanguageParser

logger = structlog.get_logger(__name__)

PY_LANGUAGE = Language(tspython.language())


class PythonParser(BaseLanguageParser):
    """Extracts code entities and relationships from Python source files.

    Uses the ``tree-sitter-python`` grammar to build a concrete syntax
    tree, then walks it to collect:

    - **Nodes**: files, classes, and functions (with metadata).
    - **Edges**: ``defines``, ``calls``, and ``imports``.

    Args:
        repo_root: Repository root used for relative path computation.
    """

    def __init__(self, repo_root: pathlib.Path) -> None:
        super().__init__(repo_root)
        self._parser = Parser(PY_LANGUAGE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_file(self, file_path: pathlib.Path, source: bytes) -> CodeGraph:
        """Parse a Python file and return its code graph.

        Args:
            file_path: Absolute path to the ``.py`` file.
            source: Raw bytes of the file.

        Returns:
            :class:`CodeGraph` with extracted nodes and edges.
        """
        rel_path = self._relative_path(file_path)
        tree = self._parser.parse(source)
        root = tree.root_node

        nodes: list[NodeRecord] = []
        edges: list[EdgeRecord] = []

        # File-level node
        file_id = rel_path
        nodes.append(
            NodeRecord(
                id=file_id,
                type=NodeType.FILE,
                name=file_path.name,
                filepath=rel_path,
                start_line=1,
                end_line=source.count(b"\n") + 1,
                docstring=self._extract_module_docstring(root),
            )
        )

        # Walk top-level definitions
        self._extract_definitions(
            node=root,
            source=source,
            rel_path=rel_path,
            parent_id=file_id,
            nodes=nodes,
            edges=edges,
        )

        # Imports
        self._extract_imports(root, file_id, rel_path, edges)

        return CodeGraph(nodes=nodes, edges=edges)

    # ------------------------------------------------------------------
    # Definition extraction
    # ------------------------------------------------------------------

    def _extract_definitions(
        self,
        node: Node,
        source: bytes,
        rel_path: str,
        parent_id: str,
        nodes: list[NodeRecord],
        edges: list[EdgeRecord],
        scope_prefix: str = "",
    ) -> None:
        """Recursively extract class and function definitions.

        Args:
            node: Current tree-sitter node to inspect.
            source: Full file source bytes.
            rel_path: Repo-relative file path.
            parent_id: ID of the enclosing node (file or class).
            nodes: Accumulator for discovered nodes.
            edges: Accumulator for discovered edges.
            scope_prefix: Dot-separated scope for nested entities.
        """
        for child in node.children:
            if child.type == "class_definition":
                self._handle_class(child, source, rel_path, parent_id, nodes, edges, scope_prefix)
            elif child.type == "function_definition":
                self._handle_function(child, source, rel_path, parent_id, nodes, edges, scope_prefix)
            elif child.type == "decorated_definition":
                # The actual definition is the last child of the decorator wrapper.
                inner = child.children[-1] if child.children else None
                if inner is not None:
                    if inner.type == "class_definition":
                        self._handle_class(inner, source, rel_path, parent_id, nodes, edges, scope_prefix)
                    elif inner.type == "function_definition":
                        self._handle_function(inner, source, rel_path, parent_id, nodes, edges, scope_prefix)

    def _handle_class(
        self,
        node: Node,
        source: bytes,
        rel_path: str,
        parent_id: str,
        nodes: list[NodeRecord],
        edges: list[EdgeRecord],
        scope_prefix: str,
    ) -> None:
        """Process a single class definition node.

        Args:
            node: The ``class_definition`` tree-sitter node.
            source: Full file source bytes.
            rel_path: Repo-relative file path.
            parent_id: Enclosing node ID.
            nodes: Node accumulator.
            edges: Edge accumulator.
            scope_prefix: Current scope prefix.
        """
        name = self._child_text_by_field(node, "name")
        if not name:
            return

        qualified = f"{scope_prefix}{name}" if scope_prefix else name
        class_id = f"{rel_path}::{qualified}"

        nodes.append(
            NodeRecord(
                id=class_id,
                type=NodeType.CLASS,
                name=qualified,
                filepath=rel_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                docstring=self._extract_body_docstring(node),
            )
        )
        edges.append(
            EdgeRecord(source_id=parent_id, target_id=class_id, type=EdgeType.DEFINES)
        )

        # Recurse into class body for methods and nested classes
        body = node.child_by_field_name("body")
        if body is not None:
            self._extract_definitions(
                body, source, rel_path, class_id, nodes, edges, scope_prefix=f"{qualified}."
            )

    def _handle_function(
        self,
        node: Node,
        source: bytes,
        rel_path: str,
        parent_id: str,
        nodes: list[NodeRecord],
        edges: list[EdgeRecord],
        scope_prefix: str,
    ) -> None:
        """Process a single function definition node.

        Args:
            node: The ``function_definition`` tree-sitter node.
            source: Full file source bytes.
            rel_path: Repo-relative file path.
            parent_id: Enclosing node ID.
            nodes: Node accumulator.
            edges: Edge accumulator.
            scope_prefix: Current scope prefix.
        """
        name = self._child_text_by_field(node, "name")
        if not name:
            return

        qualified = f"{scope_prefix}{name}" if scope_prefix else name
        func_id = f"{rel_path}::{qualified}"

        nodes.append(
            NodeRecord(
                id=func_id,
                type=NodeType.FUNCTION,
                name=qualified,
                filepath=rel_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                docstring=self._extract_body_docstring(node),
            )
        )
        edges.append(
            EdgeRecord(source_id=parent_id, target_id=func_id, type=EdgeType.DEFINES)
        )

        # Extract call-site edges from the function body
        body = node.child_by_field_name("body")
        if body is not None:
            self._extract_calls(body, func_id, rel_path, edges)

    # ------------------------------------------------------------------
    # Call-site extraction
    # ------------------------------------------------------------------

    def _extract_calls(
        self,
        node: Node,
        caller_id: str,
        rel_path: str,
        edges: list[EdgeRecord],
    ) -> None:
        """Walk *node* and record every function/method call as an edge.

        Args:
            node: Subtree to search for ``call`` nodes.
            caller_id: ID of the calling function.
            rel_path: Repo-relative file path (used for callee ID).
            edges: Edge accumulator.
        """
        if node.type == "call":
            callee_name = self._resolve_call_name(node)
            if callee_name:
                # Use an unresolved target ID; graph linking resolves later.
                target_id = f"{rel_path}::{callee_name}"
                edges.append(
                    EdgeRecord(source_id=caller_id, target_id=target_id, type=EdgeType.CALLS)
                )

        for child in node.children:
            self._extract_calls(child, caller_id, rel_path, edges)

    def _resolve_call_name(self, call_node: Node) -> Optional[str]:
        """Extract the callee name from a ``call`` node.

        Handles simple calls (``foo()``) and attribute calls
        (``obj.method()``).

        Args:
            call_node: A tree-sitter ``call`` node.

        Returns:
            Dotted callee name, or ``None`` if unresolvable.
        """
        func = call_node.child_by_field_name("function")
        if func is None:
            return None

        if func.type == "identifier":
            return self._node_text(func)
        elif func.type == "attribute":
            return self._node_text(func)
        return None

    # ------------------------------------------------------------------
    # Import extraction
    # ------------------------------------------------------------------

    def _extract_imports(
        self,
        root: Node,
        file_id: str,
        rel_path: str,
        edges: list[EdgeRecord],
    ) -> None:
        """Extract ``import`` and ``from ... import`` statements.

        Args:
            root: Root node of the syntax tree.
            file_id: ID of the file node.
            rel_path: Repo-relative file path.
            edges: Edge accumulator.
        """
        for child in root.children:
            if child.type == "import_statement":
                self._handle_import_statement(child, file_id, edges)
            elif child.type == "import_from_statement":
                self._handle_import_from_statement(child, file_id, edges)

    def _handle_import_statement(
        self, node: Node, file_id: str, edges: list[EdgeRecord]
    ) -> None:
        """Handle ``import foo, bar`` statements.

        Args:
            node: An ``import_statement`` tree-sitter node.
            file_id: File node ID.
            edges: Edge accumulator.
        """
        for child in node.children:
            if child.type in ("dotted_name", "aliased_import"):
                module_name = self._node_text(child).split(" as ")[0].strip()
                if module_name:
                    edges.append(
                        EdgeRecord(
                            source_id=file_id,
                            target_id=module_name,
                            type=EdgeType.IMPORTS,
                        )
                    )

    def _handle_import_from_statement(
        self, node: Node, file_id: str, edges: list[EdgeRecord]
    ) -> None:
        """Handle ``from module import name`` statements.

        Args:
            node: An ``import_from_statement`` tree-sitter node.
            file_id: File node ID.
            edges: Edge accumulator.
        """
        module_name: Optional[str] = None
        for child in node.children:
            if child.type in ("dotted_name", "relative_import"):
                module_name = self._node_text(child)
                break

        if module_name:
            edges.append(
                EdgeRecord(
                    source_id=file_id,
                    target_id=module_name,
                    type=EdgeType.IMPORTS,
                )
            )

    # ------------------------------------------------------------------
    # Docstring helpers
    # ------------------------------------------------------------------

    def _extract_module_docstring(self, root: Node) -> Optional[str]:
        """Extract the module-level docstring (first expression statement).

        Args:
            root: Root node of the syntax tree.

        Returns:
            The docstring text, or ``None``.
        """
        for child in root.children:
            if child.type == "expression_statement":
                expr = child.children[0] if child.children else None
                if expr is not None and expr.type == "string":
                    return self._strip_quotes(self._node_text(expr))
            elif child.type in ("comment",):
                continue
            else:
                break
        return None

    def _extract_body_docstring(self, def_node: Node) -> Optional[str]:
        """Extract the docstring from the body of a class or function.

        Args:
            def_node: A ``class_definition`` or ``function_definition`` node.

        Returns:
            The docstring text, or ``None``.
        """
        body = def_node.child_by_field_name("body")
        if body is None:
            return None
        for child in body.children:
            if child.type == "expression_statement":
                expr = child.children[0] if child.children else None
                if expr is not None and expr.type == "string":
                    return self._strip_quotes(self._node_text(expr))
            elif child.type in ("comment",):
                continue
            else:
                break
        return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_quotes(text: str) -> str:
        """Remove surrounding triple or single quotes from a string literal.

        Args:
            text: Raw string literal text.

        Returns:
            The inner content.
        """
        for q in ('"""', "'''", '"', "'"):
            if text.startswith(q) and text.endswith(q):
                return text[len(q) : -len(q)].strip()
        return text

    @staticmethod
    def _child_text_by_field(node: Node, field: str) -> Optional[str]:
        """Return the decoded text of a named field child.

        Args:
            node: Parent tree-sitter node.
            field: Field name (e.g. ``"name"``).

        Returns:
            Text content or ``None``.
        """
        child = node.child_by_field_name(field)
        if child is None:
            return None
        text: bytes | None = child.text
        if text is None:
            return None
        return text.decode("utf-8", errors="replace")
