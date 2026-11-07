"""Pure Tree-sitter parsing and syntax-tree fact extraction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Tree, TreeCursor

_EXTENSION_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}

_FUNCTION_TYPES: Mapping[str, frozenset[str]] = {
    "python": frozenset({"function_definition", "lambda"}),
    "javascript": frozenset(
        {
            "arrow_function",
            "function_declaration",
            "function_expression",
            "generator_function",
            "generator_function_declaration",
            "method_definition",
        }
    ),
    "typescript": frozenset(
        {
            "abstract_method_signature",
            "arrow_function",
            "function_declaration",
            "function_expression",
            "function_signature",
            "function_type",
            "generator_function",
            "generator_function_declaration",
            "method_definition",
            "method_signature",
        }
    ),
    "tsx": frozenset(
        {
            "abstract_method_signature",
            "arrow_function",
            "function_declaration",
            "function_expression",
            "function_signature",
            "function_type",
            "generator_function",
            "generator_function_declaration",
            "method_definition",
            "method_signature",
        }
    ),
}

_CLASS_TYPES: Mapping[str, frozenset[str]] = {
    "python": frozenset({"class_definition"}),
    "javascript": frozenset({"class", "class_declaration"}),
    "typescript": frozenset(
        {"abstract_class_declaration", "class", "class_declaration"}
    ),
    "tsx": frozenset({"abstract_class_declaration", "class", "class_declaration"}),
}

_IMPORT_TYPES: Mapping[str, frozenset[str]] = {
    "python": frozenset({"import_from_statement", "import_statement"}),
    "javascript": frozenset({"import_statement"}),
    "typescript": frozenset({"import_statement"}),
    "tsx": frozenset({"import_statement"}),
}

_BRANCH_TYPES: Mapping[str, frozenset[str]] = {
    "python": frozenset(
        {
            "case_clause",
            "conditional_expression",
            "elif_clause",
            "else_clause",
            "except_clause",
            "if_statement",
        }
    ),
    "javascript": frozenset(
        {
            "catch_clause",
            "else_clause",
            "if_statement",
            "switch_case",
            "ternary_expression",
        }
    ),
    "typescript": frozenset(
        {
            "catch_clause",
            "else_clause",
            "if_statement",
            "switch_case",
            "ternary_expression",
        }
    ),
    "tsx": frozenset(
        {
            "catch_clause",
            "else_clause",
            "if_statement",
            "switch_case",
            "ternary_expression",
        }
    ),
}

_LOOP_TYPES: Mapping[str, frozenset[str]] = {
    "python": frozenset({"for_statement", "while_statement"}),
    "javascript": frozenset(
        {"do_statement", "for_in_statement", "for_statement", "while_statement"}
    ),
    "typescript": frozenset(
        {"do_statement", "for_in_statement", "for_statement", "while_statement"}
    ),
    "tsx": frozenset(
        {"do_statement", "for_in_statement", "for_statement", "while_statement"}
    ),
}

_CALL_TYPES: Mapping[str, frozenset[str]] = {
    "python": frozenset({"call"}),
    "javascript": frozenset({"call_expression"}),
    "typescript": frozenset({"call_expression"}),
    "tsx": frozenset({"call_expression"}),
}

_BLOCK_TYPES = frozenset({"block", "statement_block"})


@dataclass(frozen=True)
class NodeFact:
    """Source range and tree depth for one extracted syntax node."""

    node_type: str
    start_line: int
    end_line: int
    depth: int


@dataclass(frozen=True)
class FunctionFact:
    """Function-like node; only outermost nodes with block bodies are G0 units."""

    node_type: str
    name: str | None
    start_line: int
    end_line: int
    body_range: tuple[int, int] | None
    outermost: bool
    parent_index: int | None
    is_unit: bool
    nesting_depth: int


@dataclass(frozen=True)
class TraversalFacts:
    """Structured syntax facts collected in one iterative tree walk."""

    nodes_visited: int
    functions: tuple[FunctionFact, ...]
    classes: tuple[NodeFact, ...]
    imports: tuple[NodeFact, ...]
    branches: tuple[NodeFact, ...]
    loops: tuple[NodeFact, ...]
    calls: tuple[NodeFact, ...]
    max_node_depth: int
    max_function_nesting: int


@dataclass(frozen=True)
class ParseResult:
    """Tree and syntax facts for one supported source file."""

    language: str
    tree: Tree
    node_count: int
    error_count: int
    missing_count: int
    error_ratio: float
    usable: bool
    status_code: str | None
    facts: TraversalFacts


def _language_for_name(file_name: str | Path) -> tuple[str, Language]:
    extension = Path(file_name).suffix.lower()
    language_name = _EXTENSION_LANGUAGES.get(extension)
    if language_name is None:
        raise ValueError(f"Unsupported source extension: {extension or '(none)'}")

    if language_name == "python":
        language = Language(tree_sitter_python.language())
    elif language_name == "javascript":
        language = Language(tree_sitter_javascript.language())
    elif language_name == "typescript":
        language = Language(tree_sitter_typescript.language_typescript())
    else:
        language = Language(tree_sitter_typescript.language_tsx())

    return language_name, language


def _node_name(node: Node, field_name: str) -> str | None:
    name_node = node.child_by_field_name(field_name)
    if name_node is None or name_node.text is None:
        return None
    return name_node.text.decode("utf-8", errors="replace")


def _function_name(node: Node, parent: Node | None) -> str | None:
    name = _node_name(node, "name")
    if name is not None:
        return name
    if parent is not None and parent.type == "variable_declarator":
        return _node_name(parent, "name")
    return None


def _node_fact(node: Node, depth: int) -> NodeFact:
    return NodeFact(
        node_type=node.type,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        depth=depth,
    )


def _walk_tree(root: Node, language: str) -> tuple[TraversalFacts, int, int]:
    functions: list[FunctionFact] = []
    classes: list[NodeFact] = []
    imports: list[NodeFact] = []
    branches: list[NodeFact] = []
    loops: list[NodeFact] = []
    calls: list[NodeFact] = []
    function_stack: list[tuple[int, int]] = []
    node_count = 0
    error_count = 0
    missing_count = 0
    max_node_depth = 0
    max_function_nesting = 0
    cursor: TreeCursor = root.walk()

    while True:
        node = cursor.node
        if node is None:
            break
        depth = cursor.depth
        node_count += 1
        error_count += node.type == "ERROR"
        missing_count += node.is_missing
        max_node_depth = max(max_node_depth, depth)

        while function_stack and function_stack[-1][0] >= depth:
            function_stack.pop()

        node_types = _FUNCTION_TYPES[language]
        if node.type in node_types:
            parent_index = function_stack[-1][1] if function_stack else None
            body = node.child_by_field_name("body")
            has_block_body = body is not None and body.type in _BLOCK_TYPES
            function_index = len(functions)
            nesting_depth = len(function_stack) + 1
            functions.append(
                FunctionFact(
                    node_type=node.type,
                    name=_function_name(node, node.parent),
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                    body_range=(body.start_byte, body.end_byte)
                    if body is not None
                    else None,
                    outermost=parent_index is None,
                    parent_index=parent_index,
                    is_unit=parent_index is None and has_block_body,
                    nesting_depth=nesting_depth,
                )
            )
            function_stack.append((depth, function_index))
            max_function_nesting = max(max_function_nesting, nesting_depth)

        if node.type in _CLASS_TYPES[language] and node.is_named:
            classes.append(_node_fact(node, depth))
        if node.type in _IMPORT_TYPES[language]:
            imports.append(_node_fact(node, depth))
        if node.type in _BRANCH_TYPES[language]:
            branches.append(_node_fact(node, depth))
        if node.type in _LOOP_TYPES[language]:
            loops.append(_node_fact(node, depth))
        if node.type in _CALL_TYPES[language]:
            calls.append(_node_fact(node, depth))

        if cursor.goto_first_child():
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent():
                facts = TraversalFacts(
                    nodes_visited=node_count,
                    functions=tuple(functions),
                    classes=tuple(classes),
                    imports=tuple(imports),
                    branches=tuple(branches),
                    loops=tuple(loops),
                    calls=tuple(calls),
                    max_node_depth=max_node_depth,
                    max_function_nesting=max_function_nesting,
                )
                return facts, error_count, missing_count

    facts = TraversalFacts(
        nodes_visited=node_count,
        functions=tuple(functions),
        classes=tuple(classes),
        imports=tuple(imports),
        branches=tuple(branches),
        loops=tuple(loops),
        calls=tuple(calls),
        max_node_depth=max_node_depth,
        max_function_nesting=max_function_nesting,
    )
    return facts, error_count, missing_count


def parse_source(source: bytes, file_name: str | Path) -> ParseResult:
    """Parse bytes and return tree/traversal facts without decoding repository code."""
    language_name, language = _language_for_name(file_name)
    tree = Parser(language).parse(source)
    if tree is None:
        raise RuntimeError("Tree-sitter returned no syntax tree.")

    facts, error_count, missing_count = _walk_tree(tree.root_node, language_name)
    node_count = facts.nodes_visited
    total_errors = error_count + missing_count
    usable = total_errors <= 1
    status_code = (
        None
        if total_errors == 0
        else "syntax_errors_tolerated"
        if usable
        else "file_unusable"
    )
    return ParseResult(
        language=language_name,
        tree=tree,
        node_count=node_count,
        error_count=error_count,
        missing_count=missing_count,
        error_ratio=total_errors / node_count if node_count else 0.0,
        usable=usable,
        status_code=status_code,
        facts=facts,
    )
