"""Print deterministic facts about the supplied JM1 CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import math
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

METRIC_COLUMNS = (
    "loc",
    "v(g)",
    "ev(g)",
    "iv(g)",
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
    "branchCount",
)
LABEL_COLUMN = "defects"
DEFAULT_CSV = Path(__file__).parent / "data" / "jm1.csv"


def load_rows(csv_path: Path) -> tuple[list[dict[str, str]], str]:
    content = csv_path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        expected = {"id", *METRIC_COLUMNS, LABEL_COLUMN}
        if reader.fieldnames is None or set(reader.fieldnames) != expected:
            raise ValueError("JM1 CSV columns do not match the expected schema")
        rows = list(reader)
    return rows, digest


def row_sort_key(row_id: str) -> tuple[int, str]:
    try:
        return int(row_id), row_id
    except ValueError:
        return 0, row_id


def rounded_interval(value: str, quantum: float) -> tuple[float, float]:
    center = float(value)
    return max(0.0, center - quantum / 2), center + quantum / 2


def formula_interval(
    row: dict[str, str],
    columns: tuple[str, ...],
    quanta: dict[str, float],
    formula,
) -> tuple[float, float]:
    intervals = [rounded_interval(row[column], quanta[column]) for column in columns]
    results = [
        formula(*values)
        for values in itertools.product(*[(low, high) for low, high in intervals])
    ]
    if not all(math.isfinite(value) for value in results):
        raise ValueError("formula is undefined")
    return min(results), max(results)


def report_formula(
    name: str,
    target: str,
    inputs: tuple[str, ...],
    rows: list[dict[str, str]],
    quanta: dict[str, float],
    formula,
) -> None:
    matches = 0
    mismatches = 0
    noncomputable = 0
    mismatch_ids = []
    for row in rows:
        try:
            expected_low, expected_high = formula_interval(row, inputs, quanta, formula)
            target_low, target_high = rounded_interval(row[target], quanta[target])
            matched = (
                expected_low <= target_high + 1e-12
                and target_low <= expected_high + 1e-12
            )
        except (ValueError, ZeroDivisionError):
            matched = False
            noncomputable += 1
        if matched:
            matches += 1
        else:
            mismatches += 1
            if len(mismatch_ids) < 3:
                mismatch_ids.append(row["id"])
    print(
        f"{name}: matches={matches}; mismatches={mismatches}; "
        f"noncomputable={noncomputable}; ids={','.join(mismatch_ids) or 'none'}"
    )


def report_formula_counts(
    name: str,
    target: str,
    inputs: tuple[str, ...],
    rows: list[dict[str, str]],
    quanta: dict[str, float],
    formula,
) -> None:
    matches = 0
    noncomputable = 0
    for row in rows:
        try:
            expected_low, expected_high = formula_interval(row, inputs, quanta, formula)
            target_low, target_high = rounded_interval(row[target], quanta[target])
            matched = (
                expected_low <= target_high + 1e-12
                and target_low <= expected_high + 1e-12
            )
        except (ValueError, ZeroDivisionError):
            matched = False
            noncomputable += 1
        matches += matched
    mismatches = len(rows) - matches
    print(
        f"{name}: matches={matches}; mismatches={mismatches}; "
        f"noncomputable={noncomputable}"
    )


def report_zero_count_values(name: str, rows: list[dict[str, str]]) -> None:
    print(f"{name}: rows={len(rows)}")
    for column in ("v", "d", "l", "i"):
        value_counts: dict[Decimal, int] = defaultdict(int)
        for row in rows:
            value_counts[Decimal(row[column])] += 1
        values = ",".join(
            f"{format(value.normalize(), 'f')}={count}"
            for value, count in sorted(value_counts.items())
        )
        print(f"{column}: {values or 'none'}")


def report_predicate(name: str, rows: list[dict[str, str]], predicate) -> None:
    mismatch_ids = [row["id"] for row in rows if not predicate(row)][:3]
    mismatches = sum(not predicate(row) for row in rows)
    print(
        f"{name}: matches={len(rows) - mismatches}; mismatches={mismatches}; "
        f"noncomputable=0; ids={','.join(mismatch_ids) or 'none'}"
    )


def report_definition_checks(
    rows_after_missing: list[dict[str, str]],
    final_retained_groups: list[list[dict[str, str]]],
) -> None:
    final_rows = [group[0] for group in final_retained_groups]
    decimal_places = {column: 0 for column in METRIC_COLUMNS}
    for row in rows_after_missing:
        for column in METRIC_COLUMNS:
            places = max(0, -Decimal(row[column]).as_tuple().exponent)
            decimal_places[column] = max(decimal_places[column], places)
    quanta = {column: 10.0**-places for column, places in decimal_places.items()}

    print(
        "rounding: per-column quantum=10^-maximum visible decimal places; "
        "inclusive value intervals extend half a quantum; formula matches when "
        "the target interval overlaps the RHS interval"
    )
    print("noncomputable rows are included in mismatches")
    print(
        "quantum: "
        + ", ".join(f"{column}={quanta[column]:g}" for column in METRIC_COLUMNS)
    )
    formulas = (
        (
            "n(column)=total_Op+total_Opnd",
            "n",
            ("total_Op", "total_Opnd"),
            lambda total_op, total_opnd: total_op + total_opnd,
        ),
        (
            "v=N*log2(n)",
            "v",
            ("total_Op", "total_Opnd", "uniq_Op", "uniq_Opnd"),
            lambda total_op, total_opnd, uniq_op, uniq_opnd: (
                (total_op + total_opnd) * math.log2(uniq_op + uniq_opnd)
            ),
        ),
        (
            "d=(uniq_Op/2)*(total_Opnd/uniq_Opnd)",
            "d",
            ("uniq_Op", "total_Opnd", "uniq_Opnd"),
            lambda uniq_op, total_opnd, uniq_opnd: (
                (uniq_op / 2) * (total_opnd / uniq_opnd)
            ),
        ),
        ("l=1/d", "l", ("d",), lambda d: 1 / d),
        ("i=v/d", "i", ("v", "d"), lambda v, d: v / d),
        ("e=d*v", "e", ("d", "v"), lambda d, v: d * v),
        ("b=v/3000", "b", ("v",), lambda v: v / 3000),
        ("b=e^(2/3)/3000", "b", ("e",), lambda e: e ** (2 / 3) / 3000),
        ("t=e/18", "t", ("e",), lambda e: e / 18),
        (
            "loc=lOCode+lOComment+lOBlank+locCodeAndComment",
            "loc",
            ("lOCode", "lOComment", "lOBlank", "locCodeAndComment"),
            lambda code, comment, blank, code_comment: (
                code + comment + blank + code_comment
            ),
        ),
        ("branchCount=v(g)-1", "branchCount", ("v(g)",), lambda vg: vg - 1),
    )
    predicates = (
        ("v(g)>=1", lambda row: Decimal(row["v(g)"]) >= 1),
        ("ev(g)<=v(g)", lambda row: Decimal(row["ev(g)"]) <= Decimal(row["v(g)"])),
        ("iv(g)<=v(g)", lambda row: Decimal(row["iv(g)"]) <= Decimal(row["v(g)"])),
    )
    for cohort_name, cohort in (
        ("after_question_rows", rows_after_missing),
        ("final_rows", final_rows),
    ):
        print(f"cohort={cohort_name}; rows={len(cohort)}")
        line_formulas = (
            (
                "line-fit-A",
                ("lOCode", "lOComment", "lOBlank", "locCodeAndComment"),
                lambda code, comment, blank, code_comment: (
                    code + comment + blank + code_comment
                ),
            ),
            (
                "line-fit-B",
                ("lOCode", "lOComment", "lOBlank"),
                lambda code, comment, blank: code + comment + blank,
            ),
            (
                "line-fit-C",
                ("lOCode", "lOComment", "lOBlank", "locCodeAndComment"),
                lambda code, comment, blank, code_comment: (
                    code + comment + blank - code_comment
                ),
            ),
            (
                "line-fit-D",
                ("lOCode", "lOBlank", "locCodeAndComment"),
                lambda code, blank, code_comment: code + blank + code_comment,
            ),
        )
        for name, inputs, formula in line_formulas:
            report_formula_counts(name, "loc", inputs, cohort, quanta, formula)
        print(
            "vocabulary=uniq_Op+uniq_Opnd (derived, no column): "
            f"computed={len(cohort)}; noncomputable=0"
        )
        for name, target, inputs, formula in formulas:
            report_formula(name, target, inputs, cohort, quanta, formula)
        for name, predicate in predicates:
            report_predicate(name, cohort, predicate)
        ratios = [
            float(row["branchCount"]) / (float(row["v(g)"]) - 1)
            for row in cohort
            if float(row["v(g)"]) != 1
        ]
        exact_branch_formula = sum(
            Decimal(row["branchCount"]) == Decimal(row["v(g)"]) - 1 for row in cohort
        )
        loc_differences = [
            sum(
                Decimal(row[column])
                for column in ("lOCode", "lOComment", "lOBlank", "locCodeAndComment")
            )
            - Decimal(row["loc"])
            for row in cohort
        ]
        print(
            "branchCount/(v(g)-1): "
            f"min={min(ratios):.6g}; max={max(ratios):.6g}; "
            f"defined={len(ratios)}; exact_branchCount=v(g)-1={exact_branch_formula}"
        )
        print(
            "line_count_sum-loc: "
            f"min={min(loc_differences)}; max={max(loc_differences)}"
        )
        if cohort_name == "final_rows":
            zero_operands = [row for row in cohort if Decimal(row["uniq_Opnd"]) == 0]
            zero_vocabulary = [
                row
                for row in cohort
                if Decimal(row["uniq_Op"]) + Decimal(row["uniq_Opnd"]) == 0
            ]
            report_zero_count_values("uniq_Opnd=0", zero_operands)
            report_zero_count_values("vocabulary=0", zero_vocabulary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", nargs="?", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--list",
        action="store_true",
        help="print IDs for zero-operator rows and conflicting metric vectors",
    )
    parser.add_argument(
        "--anomaly-evidence",
        action="store_true",
        help="print descriptive evidence for the JM1 anomalous rows",
    )
    parser.add_argument(
        "--final-set",
        action="store_true",
        help="print the preprocessing row-count funnel and final labels",
    )
    parser.add_argument(
        "--definitions-check",
        action="store_true",
        help="check JM1 metric-definition hypotheses against the dataset",
    )
    args = parser.parse_args()

    rows, digest = load_rows(args.csv_path)
    missing_rows = [
        row for row in rows if any(row[column] == "?" for column in METRIC_COLUMNS)
    ]
    clean_rows = [row for row in rows if row not in missing_rows]
    labels = defaultdict(int)
    for row in rows:
        labels[row[LABEL_COLUMN].lower()] += 1

    ids = [row["id"] for row in rows]
    metric_groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    metric_label_groups: dict[tuple[tuple[str, ...], str], int] = defaultdict(int)
    for row in clean_rows:
        metric_key = tuple(row[column] for column in METRIC_COLUMNS)
        label = row[LABEL_COLUMN].lower()
        metric_groups[metric_key].append(row)
        metric_label_groups[(metric_key, label)] += 1

    duplicate_metric_label_rows = len(clean_rows) - len(metric_label_groups)
    duplicate_metric_rows = len(clean_rows) - len(metric_groups)
    conflicting_groups = {
        key: group
        for key, group in metric_groups.items()
        if len({row[LABEL_COLUMN].lower() for row in group}) > 1
    }
    retained_groups = [
        group
        for group in metric_groups.values()
        if len({row[LABEL_COLUMN].lower() for row in group}) == 1
    ]
    retained_defective = sum(
        group[0][LABEL_COLUMN].lower() == "true" for group in retained_groups
    )
    retained_count = len(retained_groups)

    row_one = next((row for row in rows if row["id"] == "1"), None)
    fractional_columns = []
    if row_one is not None:
        fractional_columns = [
            column
            for column in METRIC_COLUMNS
            if Decimal(row_one[column]) != Decimal(row_one[column]).to_integral_value()
        ]
    code_gt_loc = [row for row in rows if Decimal(row["lOCode"]) > Decimal(row["loc"])]
    zero_operator_rows = [
        row
        for row in rows
        if row["total_Op"] != "?"
        and Decimal(row["total_Op"]) == 0
        and Decimal(row["loc"]) >= 1
    ]
    zero_operator_ids = {row["id"] for row in zero_operator_rows}
    rows_after_id_one = [row for row in clean_rows if row["id"] != "1"]
    rows_after_zero_operator = [
        row for row in rows_after_id_one if row["id"] not in zero_operator_ids
    ]
    final_metric_groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows_after_zero_operator:
        metric_key = tuple(row[column] for column in METRIC_COLUMNS)
        final_metric_groups[metric_key].append(row)
    final_retained_groups = [
        group
        for group in final_metric_groups.values()
        if len({row[LABEL_COLUMN].lower() for row in group}) == 1
    ]
    final_label_counts = defaultdict(int)
    for group in final_retained_groups:
        final_label_counts[group[0][LABEL_COLUMN].lower()] += 1
    code_gt_loc_ids = sorted((row["id"] for row in code_gt_loc), key=row_sort_key)
    missing_columns = [
        column for column in METRIC_COLUMNS if any(row[column] == "?" for row in rows)
    ]

    csv_label = (
        "ml/data/jm1.csv"
        if args.csv_path.resolve() == DEFAULT_CSV.resolve()
        else str(args.csv_path)
    )
    if args.definitions_check:
        report_definition_checks(clean_rows, final_retained_groups)
        return
    print(f"CSV: {csv_label}")
    print(f"SHA-256: {digest}")
    print(f"Rows: {len(rows)}")
    print(f"Metric inputs: {len(METRIC_COLUMNS)}")
    print("Identifier column: id (excluded from model features)")
    print(f"Unique IDs: {len(set(ids))}")
    print(f"Labels: defects=false {labels['false']}; defects=true {labels['true']}")
    print(f"Rows containing '?': {len(missing_rows)}")
    print(f"Columns containing '?': {', '.join(missing_columns)}")
    print(
        "Duplicate rows on metrics and label after '?'-row removal: "
        f"{duplicate_metric_label_rows}"
    )
    print(
        "Duplicate rows on metrics alone after '?'-row removal: "
        f"{duplicate_metric_rows}"
    )
    print(
        f"Conflicting metric vectors after '?'-row removal: {len(conflicting_groups)}"
    )
    print(
        "Rows after dropping conflicting vectors and deduplicating: "
        f"{retained_count} ({retained_defective / retained_count:.1%} defective)"
    )
    print(
        "id=1 fractional metric values: "
        f"{len(fractional_columns)} ({', '.join(fractional_columns)})"
    )
    print(f"Rows with lOCode > loc: {len(code_gt_loc)}")
    print(f"IDs with lOCode > loc: {', '.join(code_gt_loc_ids) or 'none'}")
    print(f"Rows with total_Op = 0 and loc >= 1: {len(zero_operator_rows)}")

    if args.final_set:
        print("Final-set row-count funnel:")
        print(f"Start: {len(rows)}")
        print(f"After dropping the five '?' rows: {len(clean_rows)}")
        print(f"After dropping id=1: {len(rows_after_id_one)}")
        print(
            "After dropping the total_Op = 0 and loc >= 1 group: "
            f"{len(rows_after_zero_operator)}"
        )
        print(
            "After removing conflicting metric vectors and deduplicating: "
            f"{len(final_retained_groups)}"
        )
        print(
            "Final labels: "
            f"defects=false {final_label_counts['false']}; "
            f"defects=true {final_label_counts['true']}"
        )
        print(
            "Final defect rate: "
            f"{final_label_counts['true'] / len(final_retained_groups):.2%}"
        )

    if args.anomaly_evidence:
        zero_operator_ids = {row["id"] for row in zero_operator_rows}
        zero_operator_keys = {
            tuple(row[column] for column in METRIC_COLUMNS)
            for row in zero_operator_rows
        }
        zero_operator_labels = defaultdict(int)
        for row in zero_operator_rows:
            zero_operator_labels[row[LABEL_COLUMN].lower()] += 1

        zero_operator_loc = sorted(Decimal(row["loc"]) for row in zero_operator_rows)
        middle = len(zero_operator_loc) // 2
        if len(zero_operator_loc) % 2:
            loc_median = zero_operator_loc[middle]
        else:
            loc_median = (zero_operator_loc[middle - 1] + zero_operator_loc[middle]) / 2

        zero_operator_rows_with_question = zero_operator_ids & {
            row["id"] for row in missing_rows
        }
        zero_operator_conflict_rows = [
            row
            for row in zero_operator_rows
            if tuple(row[column] for column in METRIC_COLUMNS) in conflicting_groups
        ]
        zero_operator_conflict_keys = {
            tuple(row[column] for column in METRIC_COLUMNS)
            for row in zero_operator_conflict_rows
        }
        reference_zero_operator_groups = [
            group
            for group in retained_groups
            if tuple(group[0][column] for column in METRIC_COLUMNS)
            in zero_operator_keys
        ]
        reference_zero_operator_defective = sum(
            group[0][LABEL_COLUMN].lower() == "true"
            for group in reference_zero_operator_groups
        )
        reference_without_zero_defective = retained_defective - (
            reference_zero_operator_defective
        )
        reference_without_zero_count = retained_count - len(
            reference_zero_operator_groups
        )
        reference_zero_rate = reference_zero_operator_defective / len(
            reference_zero_operator_groups
        )
        reference_without_zero_rate = (
            reference_without_zero_defective / reference_without_zero_count
        )

        print("Anomaly evidence:")
        if row_one is not None:
            print(
                "id=1 full row: "
                + ", ".join(f"{column}={value}" for column, value in row_one.items())
            )
        print(
            "Zero-operator group labels: "
            f"defects=false {zero_operator_labels['false']}; "
            f"defects=true {zero_operator_labels['true']}"
        )
        print(
            "Zero-operator group defect rate: "
            f"{zero_operator_labels['true'] / len(zero_operator_rows):.2%}"
        )
        print(
            f"All-row defect rate ({len(rows)} rows): {labels['true'] / len(rows):.2%}"
        )
        print(
            "Reference-set defect rate "
            f"({retained_count} rows): {retained_defective / retained_count:.2%}"
        )
        for column in ("total_Opnd", "n", "v", "e"):
            count = sum(Decimal(row[column]) == 0 for row in zero_operator_rows)
            print(f"Zero-operator rows with {column} = 0: {count}")
        print(
            "Zero-operator group loc min/median/max: "
            f"{zero_operator_loc[0]} / {loc_median} / {zero_operator_loc[-1]}"
        )
        loc_buckets = (
            ("1", lambda value: value == 1),
            ("2", lambda value: value == 2),
            ("3-5", lambda value: 3 <= value <= 5),
            ("6-10", lambda value: 6 <= value <= 10),
            ("11+", lambda value: value >= 11),
        )
        print(
            "Zero-operator group loc counts: "
            + "; ".join(
                f"{label} {sum(predicate(value) for value in zero_operator_loc)}"
                for label, predicate in loc_buckets
            )
        )
        print(
            "Zero-operator rows overlapping '?'-rows: "
            f"{len(zero_operator_rows_with_question)}"
        )
        print(
            "Zero-operator rows in conflicting vectors: "
            f"{len(zero_operator_conflict_rows)} rows, "
            f"{len(zero_operator_conflict_keys)} vectors"
        )
        print(
            "Reference rows from zero-operator group: "
            f"{len(reference_zero_operator_groups)} "
            f"({len(reference_zero_operator_groups) / retained_count:.1%})"
        )
        print(
            "Reference subgroup defect rates: "
            f"with zero-operator group ({len(reference_zero_operator_groups)} rows) "
            f"{reference_zero_rate:.2%}; "
            f"without ({reference_without_zero_count} rows) "
            f"{reference_without_zero_rate:.2%}"
        )

    if args.list:
        print("IDs with total_Op = 0 and loc >= 1:")
        print(
            ", ".join(
                sorted((row["id"] for row in zero_operator_rows), key=row_sort_key)
            )
            or "none"
        )
        print(
            "Conflicting metric vectors (SHA-256 prefix: "
            "defects=false IDs | defects=true IDs):"
        )
        for metric_key, group in sorted(conflicting_groups.items()):
            fingerprint = hashlib.sha256("\0".join(metric_key).encode()).hexdigest()[
                :12
            ]
            ids_by_label = {
                label: sorted(
                    (row["id"] for row in group if row[LABEL_COLUMN].lower() == label),
                    key=row_sort_key,
                )
                for label in ("false", "true")
            }
            print(
                f"{fingerprint}: {','.join(ids_by_label['false'])} | "
                f"{','.join(ids_by_label['true'])}"
            )


if __name__ == "__main__":
    main()
