"""Print deterministic facts about the supplied JM1 CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
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
