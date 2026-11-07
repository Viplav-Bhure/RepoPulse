"""Tests for pure Tree-sitter parsing and syntax facts."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language

from app.analyzer import parser as parser_module
from app.analyzer.parser import ParseResult, parse_source

FIXTURES = Path(__file__).parent / "fixtures"
_GRAMMARS = {
    "python": Language(tree_sitter_python.language()),
    "javascript": Language(tree_sitter_javascript.language()),
    "typescript": Language(tree_sitter_typescript.language_typescript()),
    "tsx": Language(tree_sitter_typescript.language_tsx()),
}


def _parse_fixture(relative_path: str) -> ParseResult:
    path = FIXTURES / relative_path
    return parse_source(path.read_bytes(), path.name)


@pytest.mark.parametrize(
    (
        "relative_path",
        "language",
        "functions",
        "classes",
        "imports",
        "branches",
        "loops",
        "calls",
    ),
    [
        ("py_basic/source.py", "python", 2, 1, 1, 1, 0, 1),
        ("js_basic/source.js", "javascript", 2, 1, 1, 2, 0, 1),
        ("ts_basic/source.ts", "typescript", 2, 1, 1, 2, 0, 1),
        ("ts_basic/component.tsx", "tsx", 1, 0, 1, 0, 0, 0),
    ],
)
def test_basic_fixtures_have_hand_checked_facts(
    relative_path: str,
    language: str,
    functions: int,
    classes: int,
    imports: int,
    branches: int,
    loops: int,
    calls: int,
) -> None:
    result = _parse_fixture(relative_path)

    assert result.language == language
    assert result.usable
    assert result.status_code is None
    assert result.error_count == 0
    assert result.missing_count == 0
    assert result.node_count == result.facts.nodes_visited
    assert len(result.facts.functions) == functions
    assert len(result.facts.classes) == classes
    assert len(result.facts.imports) == imports
    assert len(result.facts.branches) == branches
    assert len(result.facts.loops) == loops
    assert len(result.facts.calls) == calls
    assert result.error_ratio == 0.0
    assert result.facts.max_node_depth > 0


def test_python_fixture_has_hand_checked_function_ranges_and_units() -> None:
    result = _parse_fixture("py_basic/source.py")

    assert [
        (function.name, function.start_line, function.end_line, function.is_unit)
        for function in result.facts.functions
    ] == [("greet", 5, 7, True), ("helper", 10, 11, True)]
    assert all(function.outermost for function in result.facts.functions)
    assert all(function.parent_index is None for function in result.facts.functions)
    assert result.facts.functions[0].body_range is not None


def test_javascript_fixture_tracks_method_and_variable_function_names() -> None:
    result = _parse_fixture("js_basic/source.js")

    assert [
        (function.name, function.outermost, function.parent_index, function.is_unit)
        for function in result.facts.functions
    ] == [("greet", True, None, True), ("helper", True, None, True)]


def test_nested_javascript_function_records_parent_index() -> None:
    source = (
        b"const outer = () => { const inner = () => { return 1; }; return inner(); };\n"
    )
    result = parse_source(source, "nested.js")

    assert [
        (function.name, function.outermost, function.parent_index, function.is_unit)
        for function in result.facts.functions
    ] == [("outer", True, None, True), ("inner", False, 0, False)]


def test_expression_bodied_tsx_arrow_is_not_a_g0_unit() -> None:
    result = _parse_fixture("ts_basic/component.tsx")
    function = result.facts.functions[0]

    assert function.node_type == "arrow_function"
    assert function.name == "Greeter"
    assert function.outermost
    assert not function.is_unit
    assert function.body_range is not None


def test_nested_function_records_outermost_and_parent_index() -> None:
    result = parse_source(
        b"def outer():\n    def inner():\n        return 1\n    return inner()\n",
        "nested.py",
    )

    assert [
        (function.name, function.outermost, function.parent_index, function.is_unit)
        for function in result.facts.functions
    ] == [("outer", True, None, True), ("inner", False, 0, False)]
    assert result.facts.max_function_nesting == 2


def test_typescript_overload_signature_is_not_a_unit() -> None:
    result = parse_source(
        b"class Handler { handle(value: string): string; "
        b"handle(value: string) { return value; } }\n",
        "overload.ts",
    )

    assert [
        (function.node_type, function.is_unit) for function in result.facts.functions
    ] == [("method_signature", False), ("method_definition", True)]


@pytest.mark.parametrize(
    (
        "source",
        "file_name",
        "error_count",
        "missing_count",
        "usable",
        "status_code",
    ),
    [
        (
            b"def f()\n    return 1\n",
            "broken.py",
            1,
            0,
            True,
            "syntax_errors_tolerated",
        ),
        (
            b"def f()\n    return 1\n???\n???\n",
            "broken.py",
            2,
            0,
            False,
            "file_unusable",
        ),
        (
            b"function f() { return 1;",
            "broken.js",
            0,
            1,
            True,
            "syntax_errors_tolerated",
        ),
    ],
)
def test_syntax_error_cutoff_uses_error_and_missing_node_count(
    source: bytes,
    file_name: str,
    error_count: int,
    missing_count: int,
    usable: bool,
    status_code: str,
) -> None:
    result = parse_source(source, file_name)

    assert result.error_count == error_count
    assert result.missing_count == missing_count
    assert result.usable is usable
    assert result.status_code == status_code
    assert result.error_ratio == (error_count + missing_count) / result.node_count


def test_empty_source_is_usable() -> None:
    result = parse_source(b"", "empty.py")

    assert result.node_count == 1
    assert result.usable
    assert result.status_code is None
    assert result.error_ratio == 0.0


def test_bom_and_invalid_utf8_are_parsed_as_bytes() -> None:
    bom_result = parse_source(b"\xef\xbb\xbfvalue = 1\n", "bom.py")
    invalid_result = parse_source(b"value = 1\n\xff", "invalid.py")

    assert bom_result.usable
    assert bom_result.error_count == 0
    assert invalid_result.node_count > 0
    assert invalid_result.error_count + invalid_result.missing_count > 0


@pytest.mark.parametrize(
    ("file_name", "language"),
    [
        ("a.py", "python"),
        ("a.js", "javascript"),
        ("a.jsx", "javascript"),
        ("a.mjs", "javascript"),
        ("a.cjs", "javascript"),
        ("a.ts", "typescript"),
        ("a.tsx", "tsx"),
    ],
)
def test_supported_extensions_select_their_grammar(
    file_name: str, language: str
) -> None:
    result = parse_source(b"", file_name)

    assert result.language == language


def test_unsupported_extension_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported source extension"):
        parse_source(b"", "source.java")


def test_traversal_node_and_field_names_match_installed_grammars() -> None:
    for grammar_name, language in _GRAMMARS.items():
        expected_nodes = (
            parser_module._FUNCTION_TYPES[grammar_name]
            | parser_module._CLASS_TYPES[grammar_name]
            | parser_module._IMPORT_TYPES[grammar_name]
            | parser_module._BRANCH_TYPES[grammar_name]
            | parser_module._LOOP_TYPES[grammar_name]
            | parser_module._CALL_TYPES[grammar_name]
            | ({"block"} if grammar_name == "python" else {"statement_block"})
        )
        if grammar_name != "python":
            expected_nodes |= {"variable_declarator"}
        node_names = {
            language.node_kind_for_id(node_id)
            for node_id in range(language.node_kind_count)
        }
        assert expected_nodes <= node_names
        for node_name in expected_nodes:
            node_id = language.id_for_node_kind(node_name, True)
            if node_id is None:
                node_id = language.id_for_node_kind(node_name, False)
            assert node_id is not None
            assert language.node_kind_for_id(node_id) == node_name

        field_names = {
            language.field_name_for_id(field_id)
            for field_id in range(1, language.field_count + 1)
        }
        assert {"name", "body"} <= field_names
        for field_name in ("name", "body"):
            field_id = language.field_id_for_name(field_name)
            assert field_id > 0
            assert language.field_name_for_id(field_id) == field_name


def _large_source(language: str) -> tuple[str, bytes]:
    snippets = {
        "python": b"def value():\n    return 1\n",
        "javascript": b"function value() { return 1; }\n",
        "typescript": b"function value(): number { return 1; }\n",
        "tsx": b'const value = () => <div data-id="1">x</div>;\n',
    }
    snippet = snippets[language]
    source = snippet * (1_048_576 // len(snippet))
    extension = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "tsx": "tsx",
    }[language]
    return f"large.{extension}", source


@pytest.mark.parametrize("language", ["python", "javascript", "typescript", "tsx"])
def test_large_sources_parse_and_walk_every_node(language: str) -> None:
    file_name, source = _large_source(language)
    started = time.perf_counter()
    last_result: ParseResult | None = None

    for _ in range(10):
        last_result = parse_source(source, file_name)
        assert last_result.usable
        assert last_result.node_count == last_result.facts.nodes_visited

    elapsed = time.perf_counter() - started
    assert last_result is not None
    print(
        f"Tree-sitter smoke language={language} bytes={len(source)} "
        f"nodes={last_result.node_count} "
        f"errors={last_result.error_count + last_result.missing_count} "
        f"runs=10 elapsed_seconds={elapsed:.3f}"
    )


def test_deep_nesting_is_walked_iteratively() -> None:
    depth = 3000
    source = b"value = " + b"(" * depth + b"1" + b")" * depth + b"\n"
    result = parse_source(source, "deep.py")

    assert result.node_count == result.facts.nodes_visited
    assert result.facts.max_node_depth >= depth


def test_many_syntax_errors_mark_file_unusable() -> None:
    source = b"".join(b"def f(:\n    pass\n" for _ in range(100))
    result = parse_source(source, "many_errors.py")

    assert result.error_count + result.missing_count >= 2
    assert not result.usable
    assert result.status_code == "file_unusable"
