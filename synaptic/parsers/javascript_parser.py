"""Tree-sitter based parser for JavaScript source files.

Extracts functions, classes, call-site relationships, and import
statements from the JavaScript AST.
"""

from __future__ import annotations

import pathlib
from typing import Optional

import structlog
import tree_sitter_javascript as tsjavascript
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

JS_LANGUAGE = Language(tsjavascript.language())


class JavaScriptParser(BaseLanguageParser):
    """Extracts code entities and relationships from JavaScript files.

    Handles:

    - Function declarations and arrow-function variable declarations.
    - Class declarations with method definitions.
    - ``import`` / ``require`` statements.
    - Call-site edges.

    Args:
        repo_root: Repository root for relative path computation.
    """

    def __init__(self, repo_root: pathlib.Path) -> None:
        super().__init__(repo_root)
        self._parser = Parser(JS_LANGUAGE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_file(self, file_path: pathlib.Path, source: bytes) -> CodeGraph:
        """Parse a JavaScript file and return its code graph.

        Args:
            file_path: Absolute path to the ``.js`` file.
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
                docstring=None,
            )
        )

        self._extract_definitions(root, source, rel_path, file_id, nodes, edges)
        self._extract_imports(root, file_id, edges)

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
        """Walk the tree and extract function/class definitions.

        Args:
            node: Current tree-sitter node.
            source: Full file source bytes.
            rel_path: Repo-relative file path.
            parent_id: Enclosing node ID.
            nodes: Node accumulator.
            edges: Edge accumulator.
            scope_prefix: Dot-separated scope for nested entities.
        """
        for child in node.children:
            if child.type == "function_declaration":
                self._handle_function(child, source, rel_path, parent_id, nodes, edges, scope_prefix)
            elif child.type == "class_declaration":
                self._handle_class(child, source, rel_path, parent_id, nodes, edges, scope_prefix)
            elif child.type in ("lexical_declaration", "variable_declaration"):
                self._handle_variable_declaration(child, source, rel_path, parent_id, nodes, edges, scope_prefix)
            elif child.type == "export_statement":
                # Recurse into export wrappers
                self._extract_definitions(child, source, rel_path, parent_id, nodes, edges, scope_prefix)

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
        """Process a ``function_declaration`` node.

        Args:
            node: The tree-sitter node.
            source: Full file bytes.
            rel_path: Repo-relative path.
            parent_id: Enclosing node ID.
            nodes: Node accumulator.
            edges: Edge accumulator.
            scope_prefix: Current scope.
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
                docstring=self._extract_jsdoc(node),
            )
        )
        edges.append(EdgeRecord(source_id=parent_id, target_id=func_id, type=EdgeType.DEFINES))

        body = node.child_by_field_name("body")
        if body is not None:
            self._extract_calls(body, func_id, rel_path, edges)

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
        """Process a ``class_declaration`` node.

        Args:
            node: The tree-sitter node.
            source: Full file bytes.
            rel_path: Repo-relative path.
            parent_id: Enclosing node ID.
            nodes: Node accumulator.
            edges: Edge accumulator.
            scope_prefix: Current scope.
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
                docstring=self._extract_jsdoc(node),
            )
        )
        edges.append(EdgeRecord(source_id=parent_id, target_id=class_id, type=EdgeType.DEFINES))

        # Extract methods from class body
        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                if child.type == "method_definition":
                    self._handle_method(child, source, rel_path, class_id, nodes, edges, f"{qualified}.")

    def _handle_method(
        self,
        node: Node,
        source: bytes,
        rel_path: str,
        parent_id: str,
        nodes: list[NodeRecord],
        edges: list[EdgeRecord],
        scope_prefix: str,
    ) -> None:
        """Process a ``method_definition`` inside a class body.

        Args:
            node: The tree-sitter node.
            source: Full file bytes.
            rel_path: Repo-relative path.
            parent_id: Enclosing class ID.
            nodes: Node accumulator.
            edges: Edge accumulator.
            scope_prefix: Current scope.
        """
        name = self._child_text_by_field(node, "name")
        if not name:
            return

        qualified = f"{scope_prefix}{name}" if scope_prefix else name
        method_id = f"{rel_path}::{qualified}"

        nodes.append(
            NodeRecord(
                id=method_id,
                type=NodeType.FUNCTION,
                name=qualified,
                filepath=rel_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                docstring=self._extract_jsdoc(node),
            )
        )
        edges.append(EdgeRecord(source_id=parent_id, target_id=method_id, type=EdgeType.DEFINES))

        body = node.child_by_field_name("body")
        if body is not None:
            self._extract_calls(body, method_id, rel_path, edges)

    def _handle_variable_declaration(
        self,
        node: Node,
        source: bytes,
        rel_path: str,
        parent_id: str,
        nodes: list[NodeRecord],
        edges: list[EdgeRecord],
        scope_prefix: str,
    ) -> None:
        """Detect arrow functions assigned to ``const``/``let``/``var``.

        Args:
            node: A ``lexical_declaration`` or ``variable_declaration`` node.
            source: Full file bytes.
            rel_path: Repo-relative path.
            parent_id: Enclosing node ID.
            nodes: Node accumulator.
            edges: Edge accumulator.
            scope_prefix: Current scope.
        """
        for child in node.children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node is None or value_node is None:
                continue
            if value_node.type not in ("arrow_function", "function_expression"):
                continue

            name = self._node_text(name_node)
            qualified = f"{scope_prefix}{name}" if scope_prefix else name
            func_id = f"{rel_path}::{qualified}"

            nodes.append(
                NodeRecord(
                    id=func_id,
                    type=NodeType.FUNCTION,
                    name=qualified,
                    filepath=rel_path,
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    docstring=self._extract_jsdoc(node),
                )
            )
            edges.append(EdgeRecord(source_id=parent_id, target_id=func_id, type=EdgeType.DEFINES))

            body = value_node.child_by_field_name("body")
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
        """Recursively find ``call_expression`` nodes and record edges.

        Args:
            node: Subtree to search.
            caller_id: ID of the calling function.
            rel_path: Repo-relative file path.
            edges: Edge accumulator.
        """
        if node.type == "call_expression":
            callee = self._resolve_call_name(node)
            if callee:
                target_id = f"{rel_path}::{callee}"
                edges.append(EdgeRecord(source_id=caller_id, target_id=target_id, type=EdgeType.CALLS))

        for child in node.children:
            self._extract_calls(child, caller_id, rel_path, edges)

    def _resolve_call_name(self, call_node: Node) -> Optional[str]:
        """Extract the callee name from a ``call_expression``.

        Args:
            call_node: A ``call_expression`` tree-sitter node.

        Returns:
            Callee name string or ``None``.
        """
        func = call_node.child_by_field_name("function")
        if func is None:
            return None
        if func.type == "identifier":
            return self._node_text(func)
        elif func.type == "member_expression":
            return self._node_text(func)
        return None

    # ------------------------------------------------------------------
    # Import extraction
    # ------------------------------------------------------------------

    def _extract_imports(
        self,
        root: Node,
        file_id: str,
        edges: list[EdgeRecord],
    ) -> None:
        """Extract ES6 ``import`` and CommonJS ``require`` statements.

        Args:
            root: Root node of the syntax tree.
            file_id: File node ID.
            edges: Edge accumulator.
        """
        for child in root.children:
            if child.type == "import_statement":
                source_node = child.child_by_field_name("source")
                if source_node is not None:
                    module = self._strip_quotes(self._node_text(source_node))
                    if module:
                        edges.append(
                            EdgeRecord(source_id=file_id, target_id=module, type=EdgeType.IMPORTS)
                        )
            elif child.type == "export_statement":
                # ``export { x } from 'module'``
                source_node = child.child_by_field_name("source")
                if source_node is not None:
                    module = self._strip_quotes(self._node_text(source_node))
                    if module:
                        edges.append(
                            EdgeRecord(source_id=file_id, target_id=module, type=EdgeType.IMPORTS)
                        )

        # Also scan for top-level require() calls
        self._extract_require_calls(root, file_id, edges)

    def _extract_require_calls(
        self,
        node: Node,
        file_id: str,
        edges: list[EdgeRecord],
    ) -> None:
        """Find ``require('module')`` calls at the top level.

        Args:
            node: Node to search.
            file_id: File node ID.
            edges: Edge accumulator.
        """
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func is not None and self._node_text(func) == "require":
                args = node.child_by_field_name("arguments")
                if args is not None and args.child_count > 0:
                    for arg_child in args.children:
                        if arg_child.type == "string":
                            module = self._strip_quotes(self._node_text(arg_child))
                            if module:
                                edges.append(
                                    EdgeRecord(source_id=file_id, target_id=module, type=EdgeType.IMPORTS)
                                )
                            break
        for child in node.children:
            self._extract_require_calls(child, file_id, edges)

    # ------------------------------------------------------------------
    # JSDoc helper
    # ------------------------------------------------------------------

    def _extract_jsdoc(self, node: Node) -> Optional[str]:
        """Extract a JSDoc comment immediately preceding *node*.

        Args:
            node: A definition node.

        Returns:
            JSDoc text or ``None``.
        """
        prev = node.prev_named_sibling
        if prev is not None and prev.type == "comment":
            text = self._node_text(prev)
            if text.startswith("/**"):
                return text
        return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_quotes(text: str) -> str:
        """Remove surrounding quotes from a string literal.

        Args:
            text: Raw string literal.

        Returns:
            Inner content.
        """
        for q in ('"""', "'''", '"', "'", "`"):
            if text.startswith(q) and text.endswith(q):
                return text[len(q) : -len(q)]
        return text

    @staticmethod
    def _child_text_by_field(node: Node, field: str) -> Optional[str]:
        """Return decoded text of a named field child.

        Args:
            node: Parent node.
            field: Field name.

        Returns:
            Text or ``None``.
        """
        child = node.child_by_field_name(field)
        if child is None:
            return None
        text: bytes | None = child.text
        if text is None:
            return None
        return text.decode("utf-8", errors="replace")
