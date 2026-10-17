import json
from pathlib import Path

import pytest

from ml.g0_extractor import (
    SKIP_DIRECTORIES,
    derive_halstead_features,
    discover_files,
    extract_file,
    features_for_unit,
    find_units,
    module_level_qualifies,
)
from ml.g0_range_check import _serving_values

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "g0"


@pytest.mark.parametrize(
    "case_dir", sorted(FIXTURE_ROOT.iterdir()), ids=lambda path: path.name
)
def test_fixture_unit_names_and_module_qualification(case_dir: Path) -> None:
    source_path = next(case_dir.glob("source.*"))
    source = source_path.read_text(encoding="utf-8")
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    units = find_units(source, source_path)

    assert module_level_qualifies(source, source_path) is expected["module_qualifies"]
    assert [unit.name for unit in units] == expected["unit_names"]


@pytest.mark.parametrize(
    "case_name,unit_name",
    [
        ("python_main_guard", "<module>"),
        ("python_if_and", "decide"),
        ("python_line_classes", "sample"),
        ("python_nested_def", "outer"),
    ],
)
def test_hand_computed_fixture_features(case_name: str, unit_name: str) -> None:
    case_dir = FIXTURE_ROOT / case_name
    source = (case_dir / "source.py").read_text(encoding="utf-8")
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    unit = next(unit for unit in find_units(source) if unit.name == unit_name)

    assert features_for_unit(source, unit) == pytest.approx(
        expected["features"][unit_name]
    )


def test_decorator_is_excluded_from_function_unit() -> None:
    source = "@decorate(flag)\ndef sample(arg):\n    return arg\n"
    unit = find_units(source)[0]
    features = features_for_unit(source, unit)

    assert unit.name == "sample"
    assert features["loc"] == 2
    assert features["total_Op"] == 2
    assert features["total_Opnd"] == 3


def test_nested_decorator_is_excluded_from_outer_unit_tokens() -> None:
    source = (
        "def outer():\n    @mark(flag)\n    def inner(value):\n        return value\n"
    )
    unit = find_units(source)[0]
    features = features_for_unit(source, unit)

    assert unit.name == "outer"
    assert features["total_Op"] == 3
    assert features["total_Opnd"] == 4


def test_member_access_counts_as_an_operator() -> None:
    source = "def get(obj):\n    return obj.value\n"
    unit = find_units(source)[0]
    features = features_for_unit(source, unit)

    assert features["total_Op"] == 3
    assert features["total_Opnd"] == 4


@pytest.mark.parametrize(
    "case_name,unit_name",
    [
        ("javascript_block_vs_expression_arrow", "choose"),
        ("type_only_typescript", "render"),
    ],
)
def test_hand_computed_javascript_and_typescript_counts(
    case_name: str, unit_name: str
) -> None:
    case_dir = FIXTURE_ROOT / case_name
    source_path = next(case_dir.glob("source.*"))
    source = source_path.read_text(encoding="utf-8")
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    unit = next(
        unit for unit in find_units(source, source_path) if unit.name == unit_name
    )
    features = features_for_unit(source, unit)

    for feature_name, expected_value in expected["hand_computed_counts"][
        unit_name
    ].items():
        assert features[feature_name] == pytest.approx(expected_value)


def test_javascript_function_like_unit_names_and_nested_boundaries() -> None:
    source = """function declared() {}
    function* declaredGenerator() {}
const namedExpression = function named() {};
const generated = function* generator() {};
    async function* declaredAsyncGenerator() {}
const asynchronous = async function asyncNamed() {};
const arrow = () => {};
const expressionArrow = () => 1;
class Box {
    constructor() {}
    get value() {}
    set value(next) {}
    method() {}
}
const object = {
    run() {},
    get value() {},
    set value(next) {},
};
const outer = () => {
    const callback = () => {};
    function nested() {}
    return callback;
};
"""

    units = find_units(source, "source.js")

    assert [unit.name for unit in units] == [
        "declared",
        "declaredGenerator",
        "named",
        "generator",
        "declaredAsyncGenerator",
        "asyncNamed",
        "arrow",
        "constructor",
        "value",
        "value",
        "method",
        "run",
        "value",
        "value",
        "outer",
    ]


def test_tsx_file_extraction_uses_tsx_grammar(tmp_path: Path) -> None:
    source_path = tmp_path / "component.tsx"
    source_path.write_text(
        "function View(props: { label: string }) { "
        "return <button>{props.label}</button>; }",
        encoding="utf-8",
    )

    result = extract_file(source_path)

    assert [unit["name"] for unit in result["units"]] == ["View"]


def test_typescript_module_counts_runtime_class_name() -> None:
    source = "class Model {}\nactivate(new Model());\n"
    unit = next(
        unit for unit in find_units(source, "source.ts") if unit.name == "<module>"
    )

    features = features_for_unit(source, unit)

    assert features["uniq_Opnd"] == 2
    assert features["total_Opnd"] == 3


def test_discovery_uses_extensions_skip_list_and_binary_detection(
    tmp_path: Path,
) -> None:
    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "source.js").write_text("app.listen(1)\n", encoding="utf-8")
    (tmp_path / "types.d.ts").write_text(
        "declare interface Shape {}\n", encoding="utf-8"
    )
    (tmp_path / "ignored.min.js").write_text("minified()\n", encoding="utf-8")
    (tmp_path / "binary.py").write_bytes(b"\0not source")
    ignored = tmp_path / next(iter(SKIP_DIRECTORIES))
    ignored.mkdir()
    (ignored / "hidden.py").write_text("hidden = True\n", encoding="utf-8")

    assert [path.name for path in discover_files(tmp_path)] == [
        "source.js",
        "source.py",
    ]


def test_range_check_groups_typescript_and_counts_skips_and_parse_errors(
    tmp_path: Path,
) -> None:
    (tmp_path / "source.py").write_text(
        "def python_unit():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "broken.py").write_text(
        "def broken(:\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "source.js").write_text(
        "function javascriptUnit() { return 1; }\n", encoding="utf-8"
    )
    (tmp_path / "view.tsx").write_text(
        "function View() { return <div />; }\n", encoding="utf-8"
    )
    (tmp_path / "ignored.min.js").write_text("minified()\n", encoding="utf-8")
    (tmp_path / "types.d.ts").write_text(
        "declare interface Shape {}\n", encoding="utf-8"
    )
    (tmp_path / "binary.py").write_bytes(b"\0not source")
    ignored = tmp_path / next(iter(SKIP_DIRECTORIES))
    ignored.mkdir()
    (ignored / "hidden.py").write_text("hidden = True\n", encoding="utf-8")

    values, languages, _, files, language_values = _serving_values(tmp_path, ())

    assert len(values["loc"]) >= 3
    assert languages["python"] >= 1
    assert languages["javascript"] == 1
    assert languages["typescript"] == 1
    assert len(language_values["typescript"]["loc"]) == 1
    assert files["discovered"] == 4
    assert files["skipped"] == 3
    assert files["parse_error_files"] == 1
    assert files["parse_error_nodes"] > 0


def test_zero_vocabulary_uses_zero_volume_and_zero_derived_ratios() -> None:
    features = derive_halstead_features(0, 0, 0, 0)

    assert features == {
        "n": 0,
        "v": 0.0,
        "l": 0.0,
        "d": 0.0,
        "i": 0.0,
        "e": 0.0,
        "b": 0.0,
        "t": 0.0,
    }
