"""Compare serving-unit feature ranges with the final JM1 reference set."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

if __package__:
    from .g0_extractor import (
        SKIP_DIRECTORIES,
        SOURCE_EXTENSIONS,
        _parse_javascript,
        _parse_python,
        discover_files,
        features_for_unit,
        find_units,
    )
    from .jm1_facts import DEFAULT_CSV, final_set_rows, load_rows
else:
    from g0_extractor import (
        SKIP_DIRECTORIES,
        SOURCE_EXTENSIONS,
        _parse_javascript,
        _parse_python,
        discover_files,
        features_for_unit,
        find_units,
    )
    from jm1_facts import DEFAULT_CSV, final_set_rows, load_rows

USE_FEATURES = (
    "loc",
    "v(g)",
    "n",
    "v",
    "l",
    "d",
    "i",
    "e",
    "b",
    "t",
    "lOCode",
    "lOComment",
    "lOBlank",
    "locCodeAndComment",
    "uniq_Op",
    "uniq_Opnd",
    "total_Op",
    "total_Opnd",
)
LANGUAGES = ("python", "javascript", "typescript")
EXPECTED_FINAL_ROWS = 7837


def _values_for_reference() -> dict[str, list[float]]:
    rows, _ = load_rows(DEFAULT_CSV)
    reference_rows = final_set_rows(rows)
    if len(reference_rows) != EXPECTED_FINAL_ROWS:
        raise ValueError(
            "JM1 reference row count does not match the recorded final set"
        )
    return {
        feature: [float(row[feature]) for row in reference_rows]
        for feature in USE_FEATURES
    }


def _is_excluded(path: Path, prefixes: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(prefix) for prefix in prefixes)


def _empty_values() -> dict[str, list[float]]:
    return {feature: [] for feature in USE_FEATURES}


def _source_candidates(
    repository: Path, excluded_prefixes: tuple[Path, ...]
) -> set[Path]:
    if repository.is_file():
        candidates = [repository]
    else:
        candidates = []
        for directory, directory_names, filenames in os.walk(
            repository, followlinks=False
        ):
            current = Path(directory)
            directory_names[:] = [
                name
                for name in directory_names
                if name not in SKIP_DIRECTORIES and not (current / name).is_symlink()
            ]
            candidates.extend(current / name for name in filenames)
    return {
        path
        for path in candidates
        if path.suffix.lower() in SOURCE_EXTENSIONS
        and not _is_excluded(path, excluded_prefixes)
    }


def _parse_error_node_count(root: Any) -> int:
    count = 0
    nodes = [root]
    while nodes:
        node = nodes.pop()
        count += node.is_error or node.is_missing
        nodes.extend(node.children)
    return count


def _serving_values(
    repository: Path, excluded_prefixes: tuple[Path, ...]
) -> tuple[
    dict[str, list[float]],
    Counter[str],
    int,
    dict[str, int],
    dict[str, dict[str, list[float]]],
]:
    if not repository.is_dir():
        raise ValueError("Repository input is not a directory")

    values = _empty_values()
    values_by_language = {language: _empty_values() for language in LANGUAGES}
    languages: Counter[str] = Counter()
    zero_unique_operands = 0
    candidates = _source_candidates(repository, excluded_prefixes)
    source_paths = [
        path
        for path in discover_files(repository)
        if not _is_excluded(path, excluded_prefixes)
    ]
    file_counts = {
        "discovered": len(source_paths),
        "skipped": len(candidates - set(source_paths)),
        "parse_error_files": 0,
        "parse_error_nodes": 0,
    }
    for source_path in source_paths:
        source = source_path.read_bytes().decode("utf-8", errors="replace")
        source_language = SOURCE_EXTENSIONS[source_path.suffix.lower()]
        language = "typescript" if source_language == "tsx" else source_language
        root = (
            _parse_python(source)
            if language == "python"
            else _parse_javascript(source, source_language)
        )
        parse_error_nodes = _parse_error_node_count(root)
        file_counts["parse_error_files"] += parse_error_nodes > 0
        file_counts["parse_error_nodes"] += parse_error_nodes
        for unit in find_units(source, source_path):
            features = features_for_unit(source, unit)
            languages[language] += 1
            zero_unique_operands += features["uniq_Opnd"] == 0
            for feature in USE_FEATURES:
                value = float(features[feature])
                values[feature].append(value)
                values_by_language[language][feature].append(value)
    return values, languages, zero_unique_operands, file_counts, values_by_language


def _percentile95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "median": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "median": median(values),
        "p95": _percentile95(values),
        "max": max(values),
    }


def _flags(
    serving_median: float | None,
    above_max_percent: float | None,
    jm1_median: float,
) -> list[str]:
    result = []
    if above_max_percent is not None and above_max_percent > 5:
        result.append("range>5%")
    if serving_median is not None:
        if (serving_median == 0) != (jm1_median == 0):
            result.append("median>10x")
        elif serving_median != 0 and jm1_median != 0:
            if max(serving_median, jm1_median) / min(serving_median, jm1_median) > 10:
                result.append("median>10x")
    return result


def _feature_results(
    serving: dict[str, list[float]], reference: dict[str, list[float]]
) -> dict[str, dict[str, Any]]:
    results = {}
    for feature in USE_FEATURES:
        serving_values = serving[feature]
        reference_values = reference[feature]
        serving_summary = _summary(serving_values)
        reference_summary = _summary(reference_values)
        above_max_count = sum(
            value > reference_summary["max"] for value in serving_values
        )
        above_max_percent = (
            100 * above_max_count / len(serving_values) if serving_values else None
        )
        results[feature] = {
            "serving": serving_summary,
            "jm1": reference_summary,
            "above_jm1_max_percent": above_max_percent,
            "flags": _flags(
                serving_summary["median"],
                above_max_percent,
                reference_summary["median"],
            ),
        }
    return results


def _format(value: float | int | None) -> str:
    return "NA" if value is None else f"{value:.6g}"


def _print_set(label: str, report: dict[str, Any]) -> None:
    language_counts = " ".join(
        f"{language}={report['languages'].get(language, 0)}" for language in LANGUAGES
    )
    print(
        f"\n{label}: units={report['unit_count']}; {language_counts}; "
        f"uniq_Opnd=0={report['zero_unique_operands']}"
    )
    files = report["files"]
    print(
        "files: "
        f"discovered={files['discovered']} skipped={files['skipped']} "
        f"parse_error_files={files['parse_error_files']} "
        f"parse_error_nodes={files['parse_error_nodes']}"
    )
    print("feature | n | serving med/p95/max | JM1 med/p95/max | >JM1 max% | flags")
    for feature in USE_FEATURES:
        result = report["features"][feature]
        serving = result["serving"]
        reference = result["jm1"]
        flags = ",".join(result["flags"]) or "-"
        serving_range = "/".join(
            _format(serving[key]) for key in ("median", "p95", "max")
        )
        reference_range = "/".join(
            _format(reference[key]) for key in ("median", "p95", "max")
        )
        print(
            f"{feature} | {serving['count']} | {serving_range} | {reference_range} | "
            f"{_format(result['above_jm1_max_percent'])} | {flags}"
        )


def _print_language_results(
    values_by_language: dict[str, dict[str, list[float]]],
    reference: dict[str, list[float]],
) -> None:
    reports = {
        language: _feature_results(values_by_language[language], reference)
        for language in LANGUAGES
    }
    print("\nPer-language feature ranges (all sets combined)")
    print(
        "feature | language | n | serving med/p95/max | JM1 med/p95/max | "
        ">JM1 max% | flags"
    )
    for feature in USE_FEATURES:
        for language in LANGUAGES:
            result = reports[language][feature]
            serving = result["serving"]
            reference_summary = result["jm1"]
            serving_range = "/".join(
                _format(serving[key]) for key in ("median", "p95", "max")
            )
            reference_range = "/".join(
                _format(reference_summary[key]) for key in ("median", "p95", "max")
            )
            flags = ",".join(result["flags"]) or "-"
            print(
                f"{feature} | {language} | {serving['count']} | {serving_range} | "
                f"{reference_range} | {_format(result['above_jm1_max_percent'])} | "
                f"{flags}"
            )

    print("\nPer-language flags")
    print("feature | python | javascript | typescript")
    for feature in USE_FEATURES:
        flags = [
            ",".join(reports[language][feature]["flags"]) or "-"
            for language in LANGUAGES
        ]
        print(f"{feature} | {flags[0]} | {flags[1]} | {flags[2]}")
    counts = " ".join(
        f"{language}={len(values_by_language[language]['loc'])}"
        for language in LANGUAGES
    )
    print(f"Per-language units (all sets combined): {counts}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repositories", nargs="+", type=Path)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        type=Path,
        metavar="PATH_PREFIX",
        help="exclude this path prefix (may be supplied more than once)",
    )
    args = parser.parse_args()

    started = perf_counter()
    reference = _values_for_reference()
    excluded_prefixes = tuple(path.resolve() for path in args.exclude)
    reports: dict[str, dict[str, Any]] = {}
    combined_values = _empty_values()
    values_by_language = {language: _empty_values() for language in LANGUAGES}
    combined_languages: Counter[str] = Counter()
    combined_zero_unique_operands = 0
    combined_files = Counter()

    try:
        for index, repository in enumerate(args.repositories):
            label = "RepoPulse" if index == 0 else f"repo-{index}"
            values, languages, zero_unique_operands, files, language_values = (
                _serving_values(repository, excluded_prefixes)
            )
            unit_count = len(values["loc"])
            report = {
                "unit_count": unit_count,
                "languages": dict(languages),
                "zero_unique_operands": zero_unique_operands,
                "files": files,
                "features": _feature_results(values, reference),
            }
            reports[label] = report
            combined_languages.update(languages)
            combined_zero_unique_operands += zero_unique_operands
            combined_files.update(files)
            for feature in USE_FEATURES:
                combined_values[feature].extend(values[feature])
            for language in LANGUAGES:
                for feature in USE_FEATURES:
                    values_by_language[language][feature].extend(
                        language_values[language][feature]
                    )

        combined = {
            "unit_count": len(combined_values["loc"]),
            "languages": dict(combined_languages),
            "zero_unique_operands": combined_zero_unique_operands,
            "files": dict(combined_files),
            "features": _feature_results(combined_values, reference),
        }
    except (OSError, ValueError):
        print(
            "Repository range check failed; no paths or source were recorded.",
            file=sys.stderr,
        )
        return 1

    for label, report in reports.items():
        _print_set(label, report)
    _print_set("Combined", combined)
    _print_language_results(values_by_language, reference)

    elapsed_seconds = perf_counter() - started
    output = {
        "sets": reports | {"Combined": combined},
        "languages": {
            language: _feature_results(values_by_language[language], reference)
            for language in LANGUAGES
        },
        "elapsed_seconds": elapsed_seconds,
    }
    output_directory = Path(__file__).parent / ".g0-range"
    output_directory.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    output_path = output_directory / f"range-{timestamp}.json"
    output_path.write_text(
        json.dumps(output, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print("Aggregate-only report saved under ml/.g0-range/.")
    print(f"Elapsed: {elapsed_seconds:.3f} seconds", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
