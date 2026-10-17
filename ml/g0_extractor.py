"""G0 Tree-sitter extractor for Python, JavaScript, and TypeScript."""

from __future__ import annotations

import argparse
import json
import keyword
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from math import log2
from pathlib import Path

import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

SOURCE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}
SKIP_DIRECTORIES = frozenset(
    {".git", "node_modules", "dist", "build", ".next", "__pycache__", "venv", ".venv"}
)
MINIFIED_SUFFIXES = (
    ".min.js",
    ".min.jsx",
    ".min.mjs",
    ".min.cjs",
    ".min.ts",
    ".min.tsx",
)

_KEYWORD_OPERATORS = set(keyword.kwlist + keyword.softkwlist) - {
    "False",
    "None",
    "True",
}
_OPERATOR_TOKENS = {
    "!=",
    "%",
    "%=",
    "&",
    "&=",
    "*",
    "**",
    "**=",
    "*=",
    "+",
    "+=",
    "-",
    "->",
    "-=",
    ".",
    "/",
    "//",
    "//=",
    "/=",
    ":=",
    "<",
    "<<",
    "<<=",
    "<=",
    "=",
    "==",
    ">",
    ">=",
    ">>",
    ">>=",
    "@",
    "@=",
    "^",
    "^=",
    "|",
    "|=",
    "~",
}
_LITERAL_NODE_TYPES = {
    "ellipsis",
    "false",
    "float",
    "integer",
    "none",
    "string",
    "true",
}
_DOCSTRING_CONTAINERS = {"block", "module"}
_CONTROL_FLOW_NODES = {
    "for_statement",
    "if_statement",
    "match_statement",
    "try_statement",
    "while_statement",
}
_DECISION_NODES = {
    "conditional_expression",
    "elif_clause",
    "except_clause",
    "for_in_clause",
    "for_statement",
    "if_clause",
    "if_statement",
    "while_statement",
}
_JS_FUNCTION_NODES = {
    "function_declaration",
    "function_expression",
    "generator_function",
    "generator_function_declaration",
    "arrow_function",
    "method_definition",
}
_JS_MODULE_EXCLUDED_NODES = {
    "decorator",
    "export_statement",
    "import_statement",
}
_JS_CONTROL_FLOW_NODES = {
    "do_statement",
    "for_in_statement",
    "for_statement",
    "if_statement",
    "switch_statement",
    "try_statement",
    "while_statement",
}
_JS_DECISION_NODES = {
    "catch_clause",
    "do_statement",
    "for_in_statement",
    "for_statement",
    "if_statement",
    "switch_case",
    "ternary_expression",
    "while_statement",
}
_JS_LOGICAL_DECISIONS = {"&&", "||", "??", "&&=", "||=", "??="}
_JS_DELIMITERS = {"(", ")", "[", "]", "{", "}", ",", ";", ":"}
_JS_IDENTIFIER_NODES = {
    "identifier",
    "private_property_identifier",
    "property_identifier",
    "shorthand_property_identifier",
    "shorthand_property_identifier_pattern",
    "type_identifier",
}
_JS_LITERAL_NODES = {
    "false",
    "null",
    "number",
    "regex",
    "string",
    "true",
}
_TS_TYPE_ONLY_NODES = {
    "abstract_method_signature",
    "ambient_declaration",
    "call_signature",
    "construct_signature",
    "function_signature",
    "interface_body",
    "interface_declaration",
    "implements_clause",
    "method_signature",
    "type_alias_declaration",
    "type_annotation",
    "type_arguments",
    "type_parameters",
}
_JSX_TAG_NODES = {
    "jsx_attribute",
    "jsx_closing_element",
    "jsx_opening_element",
    "jsx_self_closing_element",
}

NodeRange = tuple[int, int, int, int]


@dataclass(frozen=True)
class Unit:
    name: str
    kind: str
    start_line: int
    end_line: int
    node: Node = field(repr=False, compare=False)
    language: str = "python"
    external_name_node: Node | None = field(default=None, repr=False, compare=False)
    excluded_ranges: tuple[NodeRange, ...] = field(
        default=(), repr=False, compare=False
    )


def _parse_python(source: str) -> Node:
    language = Language(tree_sitter_python.language())
    parser = Parser(language)
    return parser.parse(source.encode("utf-8")).root_node


def _parse_javascript(source: str, language: str) -> Node:
    if language == "javascript":
        grammar = Language(tree_sitter_javascript.language())
    elif language == "typescript":
        grammar = Language(tree_sitter_typescript.language_typescript())
    else:
        grammar = Language(tree_sitter_typescript.language_tsx())
    return Parser(grammar).parse(source.encode("utf-8")).root_node


def _node_range(node: Node) -> NodeRange:
    return (
        node.start_byte,
        node.end_byte,
        node.start_point.row + 1,
        node.end_point.row + 1,
    )


def _walk(
    node: Node, excluded_ranges: frozenset[tuple[int, int]] = frozenset()
) -> Iterable[Node]:
    if (node.start_byte, node.end_byte) in excluded_ranges:
        return
    yield node
    for child in node.children:
        yield from _walk(child, excluded_ranges)


def _module_level_qualifies(root: Node) -> bool:
    def contains_qualifying_node(node: Node) -> bool:
        if node.type in {"decorator", "function_definition"}:
            return False
        if node.type in _CONTROL_FLOW_NODES or node.type == "call":
            return True
        return any(contains_qualifying_node(child) for child in node.children)

    return contains_qualifying_node(root)


def _js_function_name(node: Node, parent: Node | None) -> tuple[str, Node | None]:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return name_node.text.decode("utf-8"), None
    if node.type == "method_definition":
        return "<anonymous>", None
    if parent is not None and parent.type == "variable_declarator":
        binding = parent.child_by_field_name("name")
        if binding is not None and binding.type in _JS_IDENTIFIER_NODES:
            return binding.text.decode("utf-8"), binding
    return "<anonymous>", None


def _js_module_level_qualifies(root: Node) -> bool:
    def contains_qualifying_node(node: Node) -> bool:
        if node.type in _JS_MODULE_EXCLUDED_NODES:
            return False
        if node.type in _JS_FUNCTION_NODES:
            body = node.child_by_field_name("body")
            if body is not None and body.type == "statement_block":
                return False
        if node.type in _JS_CONTROL_FLOW_NODES or node.type == "call_expression":
            return True
        return any(contains_qualifying_node(child) for child in node.children)

    return contains_qualifying_node(root)


def module_level_qualifies(source: str, file_path: str | Path = "source.py") -> bool:
    """Return whether code outside prediction units qualifies as a unit."""
    language = SOURCE_EXTENSIONS.get(Path(file_path).suffix.lower())
    if language == "python":
        return _module_level_qualifies(_parse_python(source))
    if language in {"javascript", "typescript", "tsx"}:
        return _js_module_level_qualifies(_parse_javascript(source, language))
    suffix = Path(file_path).suffix or "(none)"
    raise ValueError(f"Unsupported source extension: {suffix}")


def find_units(source: str, file_path: str | Path = "source.py") -> list[Unit]:
    """Find outermost function-like nodes and an optional qualifying module unit."""
    path = Path(file_path)
    language = SOURCE_EXTENSIONS.get(path.suffix.lower())
    if language not in {"python", "javascript", "typescript", "tsx"}:
        raise ValueError(f"Unsupported source extension: {path.suffix or '(none)'}")

    if language != "python":
        root = _parse_javascript(source, language)
        function_nodes: list[tuple[Node, Node | None]] = []

        def collect_outermost(node: Node, parent: Node | None = None) -> None:
            if node.type in _JS_FUNCTION_NODES:
                body = node.child_by_field_name("body")
                if body is not None and body.type == "statement_block":
                    function_nodes.append((node, parent))
                    return
            for child in node.children:
                collect_outermost(child, node)

        collect_outermost(root)
        units = []
        for node, parent in function_nodes:
            name, external_name_node = _js_function_name(node, parent)
            units.append(
                Unit(
                    name=name,
                    kind="method" if node.type == "method_definition" else "function",
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                    node=node,
                    language=language,
                    external_name_node=external_name_node,
                )
            )

        if _js_module_level_qualifies(root):
            excluded = tuple(_node_range(node) for node, _ in function_nodes)
            units.append(
                Unit(
                    name="<module>",
                    kind="module",
                    start_line=1,
                    end_line=len(source.splitlines()),
                    node=root,
                    language=language,
                    excluded_ranges=excluded,
                )
            )
        return units

    root = _parse_python(source)
    function_nodes: list[Node] = []

    def collect_outermost(node: Node) -> None:
        if node.type == "function_definition":
            function_nodes.append(node)
            return
        for child in node.children:
            collect_outermost(child)

    collect_outermost(root)
    units = [
        Unit(
            name=(node.child_by_field_name("name").text or b"").decode("utf-8"),
            kind="function",
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            node=node,
        )
        for node in function_nodes
    ]

    if _module_level_qualifies(root):
        excluded = tuple(
            _node_range(node)
            for node in _walk(root)
            if node.type in {"decorator", "function_definition"}
        )
        line_count = len(source.splitlines())
        units.append(
            Unit(
                name="<module>",
                kind="module",
                start_line=1,
                end_line=line_count,
                node=root,
                excluded_ranges=excluded,
            )
        )
    return units


def derive_halstead_features(
    uniq_op: int,
    uniq_opnd: int,
    total_op: int,
    total_opnd: int,
) -> dict[str, int | float]:
    """Calculate the retained Halstead fields using the recorded zero rules."""
    vocabulary = uniq_op + uniq_opnd
    length = total_op + total_opnd
    volume = length * log2(vocabulary) if vocabulary else 0.0
    if uniq_opnd == 0:
        difficulty = level = intelligence = 0.0
    else:
        difficulty = (uniq_op / 2) * (total_opnd / uniq_opnd)
        level = 1 / difficulty if difficulty else 0.0
        intelligence = volume / difficulty if difficulty else 0.0
    effort = difficulty * volume
    return {
        "n": length,
        "v": volume,
        "l": level,
        "d": difficulty,
        "i": intelligence,
        "e": effort,
        "b": volume / 3000,
        "t": effort / 18,
    }


def _docstring_ranges(root: Node) -> frozenset[tuple[int, int]]:
    ranges: set[tuple[int, int]] = set()
    for node in _walk(root):
        if node.type not in _DOCSTRING_CONTAINERS:
            continue
        statements = [child for child in node.named_children if child.type != "comment"]
        if not statements or statements[0].type != "expression_statement":
            continue
        literal = next(
            (child for child in statements[0].named_children if child.type == "string"),
            None,
        )
        if literal is not None:
            ranges.add((literal.start_byte, literal.end_byte))
    return frozenset(ranges)


def _operator_and_operand_counts(
    unit: Unit, source_bytes: bytes, docstrings: frozenset[tuple[int, int]]
) -> tuple[set[str], set[str], int, int]:
    excluded_ranges = frozenset((item[0], item[1]) for item in unit.excluded_ranges)
    operators: set[str] = set()
    operands: set[str] = set()
    total_op = 0
    total_opnd = 0

    def visit(node: Node, parent_type: str = "") -> None:
        nonlocal total_op, total_opnd
        node_key = (node.start_byte, node.end_byte)
        if (
            node_key in excluded_ranges
            or node_key in docstrings
            or node.type in {"comment", "decorator"}
        ):
            return
        text = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
        if unit.language != "python":
            if node.type in _TS_TYPE_ONLY_NODES or node.type == "jsx_text":
                return
            if node.type in {"as_expression", "satisfies_expression"}:
                expression = node.named_children[0] if node.named_children else None
                if expression is not None:
                    visit(expression, node.type)
                return
            if node.type == "non_null_expression":
                for child in node.named_children:
                    visit(child, node.type)
                return
            if node.type == "template_string":
                operands.add(text)
                total_opnd += 1
                for child in node.named_children:
                    if child.type == "template_substitution":
                        visit(child, node.type)
                return
            if node.type in _JS_IDENTIFIER_NODES or node.type in _JS_LITERAL_NODES:
                operands.add(text)
                total_opnd += 1
                return
            if node.type == "optional_chain":
                operators.add("?.")
                total_op += 1
                return
            if (
                not node.is_named
                and node.child_count == 0
                and text not in _JS_DELIMITERS
                and not (parent_type in _JSX_TAG_NODES and text in {"<", ">", "/", "="})
                and not (parent_type == "optional_parameter" and text == "?")
            ):
                operators.add(text)
                total_op += 1
            for child in node.children:
                visit(child, node.type)
            return
        if node.type in _LITERAL_NODE_TYPES or node.type == "identifier":
            operands.add(text)
            total_opnd += 1
            return
        if not node.is_named and (
            node.type in _OPERATOR_TOKENS or node.type in _KEYWORD_OPERATORS
        ):
            operators.add(text)
            total_op += 1
        for child in node.children:
            visit(child, node.type)

    visit(unit.node)
    if unit.external_name_node is not None:
        name = unit.external_name_node.text.decode("utf-8")
        operands.add(name)
        total_opnd += 1
    return operators, operands, total_op, total_opnd


def _line_features(
    unit: Unit, source: str, docstrings: frozenset[tuple[int, int]]
) -> tuple[int, int, int, int, int]:
    lines = source.splitlines()
    excluded_nodes = frozenset((item[0], item[1]) for item in unit.excluded_ranges)
    excluded_lines = {
        line_number
        for _, _, start_line, end_line in unit.excluded_ranges
        for line_number in range(start_line, end_line + 1)
    }
    if unit.kind != "module":
        active_lines = set(range(unit.start_line, unit.end_line + 1))
    else:
        active_lines = set(range(1, len(lines) + 1)) - excluded_lines

    code_lines: set[int] = set()
    comment_lines: set[int] = set()

    def collect_lines(node: Node) -> None:
        node_key = (node.start_byte, node.end_byte)
        if node_key in excluded_nodes:
            return
        if node.type == "comment":
            comment_lines.update(
                range(node.start_point.row + 1, node.end_point.row + 2)
            )
            return
        if node_key in docstrings:
            comment_lines.update(
                range(node.start_point.row + 1, node.end_point.row + 2)
            )
            return
        if node.child_count == 0:
            code_lines.update(range(node.start_point.row + 1, node.end_point.row + 2))
            return
        for child in node.children:
            collect_lines(child)

    collect_lines(unit.node)
    loc = len(active_lines)
    code_only = comment_only = blank = code_and_comment = 0
    for line_number in active_lines:
        if line_number < 1 or line_number > len(lines):
            continue
        has_code = line_number in code_lines
        has_comment = line_number in comment_lines
        if has_code and has_comment:
            code_and_comment += 1
        elif has_code:
            code_only += 1
        elif has_comment:
            comment_only += 1
        elif not lines[line_number - 1].strip():
            blank += 1
    return loc, code_only, comment_only, blank, code_and_comment


def features_for_unit(source: str, unit: Unit) -> dict[str, int | float]:
    """Compute the approved feature vector for one prediction unit."""
    source_bytes = source.encode("utf-8")
    docstrings = _docstring_ranges(unit.node)
    operators, operands, total_op, total_opnd = _operator_and_operand_counts(
        unit, source_bytes, docstrings
    )

    decisions = 0
    excluded_ranges = frozenset((item[0], item[1]) for item in unit.excluded_ranges)
    for node in _walk(unit.node, excluded_ranges):
        if unit.language == "python":
            if node.type in _DECISION_NODES:
                decisions += 1
            elif node.type == "case_clause":
                pattern = node.child_by_field_name("pattern")
                if pattern is None or pattern.type != "wildcard_pattern":
                    decisions += 1
            elif node.type in {"and", "or"}:
                decisions += 1
        else:
            if node.type in _JS_DECISION_NODES:
                decisions += 1
            elif node.type in {"binary_expression", "augmented_assignment_expression"}:
                decisions += sum(
                    child.type in _JS_LOGICAL_DECISIONS for child in node.children
                )

    loc, code_only, comment_only, blank, code_and_comment = _line_features(
        unit, source, docstrings
    )
    halstead = derive_halstead_features(
        len(operators), len(operands), total_op, total_opnd
    )
    return {
        "loc": loc,
        "v(g)": 1 + decisions,
        **halstead,
        "lOCode": code_only,
        "lOComment": comment_only,
        "lOBlank": blank,
        "locCodeAndComment": code_and_comment,
        "uniq_Op": len(operators),
        "uniq_Opnd": len(operands),
        "total_Op": total_op,
        "total_Opnd": total_opnd,
    }


def _language_for_path(path: Path) -> str | None:
    return SOURCE_EXTENSIONS.get(path.suffix.lower())


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as source_file:
            return b"\0" in source_file.read(8192)
    except OSError:
        return True


def discover_files(root: str | Path) -> list[Path]:
    """Discover supported, non-binary files without entering ignored directories."""
    root_path = Path(root)
    if root_path.is_file():
        candidates = [root_path]
    else:
        candidates = []
        for directory, directory_names, filenames in os.walk(
            root_path, followlinks=False
        ):
            current = Path(directory)
            directory_names[:] = [
                name
                for name in directory_names
                if name not in SKIP_DIRECTORIES and not (current / name).is_symlink()
            ]
            candidates.extend(current / name for name in filenames)

    return sorted(
        path
        for path in candidates
        if _language_for_path(path)
        and not path.name.lower().endswith(".d.ts")
        and not path.is_symlink()
        and not path.name.lower().endswith(MINIFIED_SUFFIXES)
        and not _is_binary(path)
    )


def extract_file(path: str | Path) -> dict[str, object]:
    """Extract feature vectors for one supported source file."""
    file_path = Path(path)
    language = _language_for_path(file_path)
    if language not in {"python", "javascript", "typescript", "tsx"}:
        raise ValueError(
            f"Unsupported source extension: {file_path.suffix or '(none)'}"
        )
    source = file_path.read_bytes().decode("utf-8", errors="replace")
    units = find_units(source, file_path)
    return {
        "path": str(file_path),
        "units": [
            {
                "name": unit.name,
                "kind": unit.kind,
                "start_line": unit.start_line,
                "end_line": unit.end_line,
                "features": features_for_unit(source, unit),
            }
            for unit in units
        ],
    }


def main() -> None:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("path", type=Path)
    root = argument_parser.parse_args().path
    paths = discover_files(root)
    if root.is_file() and not paths:
        paths = [root]
    for path in paths:
        try:
            result = extract_file(path)
        except ValueError as error:
            result = {"path": str(path), "error": str(error)}
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
