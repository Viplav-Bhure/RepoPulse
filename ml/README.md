# JM1 and Gate G0

## 0.9 Dataset provenance

The training source is the supplied PROMISE/NASA JM1 CSV at `ml/data/jm1.csv`.
License: unknown (Kaggle-reported); no redistribution rights are claimed.

SHA-256: `1ec66eb3568ae8bb4e2709cf0bd28b11db41c7c0ae771325c0952997e35e4dff`

Reproduce the deterministic facts report from the repository root in PowerShell:

```powershell
backend\.venv\Scripts\python.exe ml\jm1_facts.py
```

The script uses only the Python standard library, reads the CSV, and writes no
files. Pass a CSV path to inspect another copy, or add `--list` to print the long
ID lists for zero-operator rows and conflicting metric vectors.

## 0.9.1 Candidate predictors

Predictors: `loc`, `v(g)`, `ev(g)`, `iv(g)`, `n`, `v`, `l`, `d`, `i`, `e`, `b`,
`t`, `lOCode`, `lOComment`, `lOBlank`, `locCodeAndComment`, `uniq_Op`,
`uniq_Opnd`, `total_Op`, `total_Opnd`, `branchCount`.

Target: `defects`. The `id` identifier is excluded from the model feature vector.

## 0.9.2 Dataset facts

Measured by `jm1_facts.py`:

- 10,885 rows and 21 metric inputs; all 10,885 IDs are unique.
- Labels: 8,779 `false` and 2,106 `true`.
- Five rows contain `?`, in `uniq_Op`, `uniq_Opnd`, `total_Op`, `total_Opnd`,
  and `branchCount`.
- After removing those rows, 1,973 rows duplicate another row on metrics and
  label; 2,061 rows duplicate on metrics alone; 88 metric vectors carry both
  labels.
- Dropping conflicting metric vectors and deduplicating produces 8,731 rows,
  with 21.9% defective.

## 0.9.3 Missing values

The five rows containing `?` are dropped before training. They are not coerced to
zero or imputed. The affected columns are `uniq_Op`, `uniq_Opnd`, `total_Op`,
`total_Opnd`, and `branchCount`.

## 0.9.3a Anomalous rows

Decisions:

- Drop `id=1`. Rationale: it is also the only row with `lOCode` > `loc`.
- Drop all 1,332 rows with `total_Op` = 0 and `loc` >= 1. Rationale: every row
  also has `total_Opnd` = 0, `n` = 0, `v` = 0, and `e` = 0; median `loc` is 30;
  the group accounts for 893 of the 8,731 reference rows.

Preprocessing order: drop the five `?` rows, drop `id=1`, drop the zero-operator
group, remove conflicting-label metric vectors and deduplicate, then split.

- `id=1` has 17 fractional metric values, including `loc` 1.1.
- One row has `lOCode` greater than `loc`; it is `id=1`.
- 1,332 rows have `total_Op` = 0 while `loc` >= 1.

### Evidence

Reproduce with `backend\.venv\Scripts\python.exe ml\jm1_facts.py --anomaly-evidence`.

The full `id=1` row is:

```text
id=1, loc=1.1, v(g)=1.4, ev(g)=1.4, iv(g)=1.4, n=1.3, v=1.3, l=1.3, d=1.3, i=1.3, e=1.3, b=1.3, t=1.3, lOCode=2, lOComment=2, lOBlank=2, locCodeAndComment=2, uniq_Op=1.2, uniq_Opnd=1.2, total_Op=1.2, total_Opnd=1.2, branchCount=1.4, defects=false
```

The 1,332-row `total_Op` = 0 and `loc` >= 1 group has 1,007 non-defective
and 325 defective rows (24.40% defective). The full dataset rate is 19.35%
(2,106 / 10,885); the 8,731-row reference-set rate is 21.94%.

All 1,332 group rows also have `total_Opnd` = 0, `n` = 0, `v` = 0, and `e` = 0.
Group `loc` minimum, median, and maximum are 4, 30, and 1,129. Counts by `loc`
are: 1 = 0; 2 = 0; 3-5 = 45; 6-10 = 110; 11+ = 1,177.

The group overlaps zero of the five `?` rows and includes 204 rows from 39 of
the 88 conflicting metric vectors. Of the reference set, 893 rows (10.2%) come
from this group. The reference defect rates are 29.45% with the group (893 rows)
and 21.09% without it (7,838 rows).

### Final-set funnel

Reproduce with `backend\.venv\Scripts\python.exe ml\jm1_facts.py --final-set`.

- Start: 10,885 rows.
- After dropping the five `?` rows: 10,880.
- After dropping `id=1`: 10,879.
- After dropping the `total_Op` = 0 and `loc` >= 1 group: 9,547.
- After removing conflicting metric vectors and deduplicating: 7,837.
- Final labels: 6,184 non-defective and 1,653 defective (21.09% defective).

## 0.9.3b Duplicate and conflicting vectors

Removing metric vectors whose duplicates carry conflicting labels is confirmed
by PRD decision 29. Deduplication uses the 21 metric columns, excluding `id`,
and occurs before splitting. The detailed deduplication pipeline remains for
Phase 4, task 4.2. The measured 8,731-row, 21.9%-defective result above is the
reference before applying anomaly rules.

## 0.9.4 Compatibility matrix

Not yet done.

## 0.9.5 Prediction unit

Not yet done.

## 0.9.6 Metric implementation

Not yet done.

## 0.9.7 Compatibility rule

Not yet done.

## 0.9.8 Prediction-unit rules

Not yet done.

## 0.9.9 Feature-range sanity check

Not yet done.

## 0.9.10 Feature schema

Not yet done.

## 0.9.11 G0 report

Not yet done.
