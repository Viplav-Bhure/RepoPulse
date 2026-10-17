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

- Drop `id=1`. Rationale: 17 of its 21 metric values are fractional (loc 1.1, v(g) 1.4), which is not a valid count; it is also the only row with lOCode > loc.
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

Provisional compatibility matrix. All Python, JavaScript, and TypeScript cells
give expected Tree-sitter node types and remain **unverified until Phase 2
fixtures**. Use/drop classifications remain provisional until 0.9.9 and 0.9.10.
The prediction-unit rules are recorded in 0.9.8; expected node mappings still
need fixture verification.

The fit intervals use half of each column's visible rounding quantum. A
noncomputable row is included in the mismatch count. "After ?" is the 10,880-row
set; "final" is the 7,837-row set after the recorded anomaly and deduplication
rules. Counts below are matches / mismatches; noncomputable counts are shown
where nonzero.

| JM1 column | Definition and data-check fit | Python (unverified until Phase 2 fixtures) | JavaScript (unverified until Phase 2 fixtures) | TypeScript (unverified until Phase 2 fixtures) | Implementation method | Provisional use/drop | Justification |
|---|---|---|---|---|---|---|---|
| `loc` | Total physical lines in the unit span, including signature. A is best-fitting: after ? A 7,825/10,880; B 417/10,880; C 418/10,880; D 275/10,880. Final: A 6,267/7,837; B 392/7,837; C 393/7,837; D 250/7,837. | `def f():\n    x = 1`; count both physical lines; expected `function_definition`, `assignment`. | `function f() {\n  x = 1;\n}`; count all 3 physical lines; expected `function_declaration`, `lexical_declaration`. | `function f(): number {\n  return 1;\n}`; count all 3 physical lines; expected `function_declaration`, `return_statement`. | Count source lines over the selected unit span; span selection follows 0.9.8. | USE (provisional) | Keep relation A; it fits best, though the approximation differs from `loc` in 1,570 final rows (20.03%). |
| `v(g)` | Cyclomatic complexity: 1 + decision points. Dataset invariant: >=1 in 10,880/10,880 after ? and 7,837/7,837 final. | `if x and y:`; count `if` and short-circuit operator; expected `if_statement`, `boolean_operator`. | `if (x && y) {}`; expected `if_statement`, `binary_expression`; not applicable (no comprehension syntax). | `if (x && y) {}`; expected `if_statement`, `binary_expression`; not applicable (no comprehension syntax). | Tree-sitter decision-node/token walk per approved rules below. | USE (provisional) | Human-confirmed decision-point definition; expected node mappings require fixtures. |
| `ev(g)` | Dataset check `ev(g) <= v(g)`: 10,880/10,880 after ?; 7,837/7,837 final. | `if (x) { a(); }`; expected `if_statement`, `call`; reduction not implemented. | `if (x) a()`; expected `if_statement`, `call_expression`; reduction not implemented. | `if (x) a()`; expected `if_statement`, `call_expression`; reduction not implemented. | No implementation; control-flow-graph reduction is excluded. | DROP | Requires control-flow-graph reduction and call-graph rules that are not language-neutral. |
| `iv(g)` | Dataset check `iv(g) <= v(g)`: 10,880/10,880 after ?; 7,837/7,837 final. | `if (x) { a(); }`; expected `if_statement`, `call`; reduction not implemented. | `if (x) a()`; expected `if_statement`, `call_expression`; reduction not implemented. | `if (x) a()`; expected `if_statement`, `call_expression`; reduction not implemented. | No implementation; control-flow-graph reduction is excluded. | DROP | Requires control-flow-graph reduction and call-graph rules that are not language-neutral. |
| `n` | Stored column equals `total_Op + total_Opnd`: after ? 10,739/141; final 7,697/140. Vocabulary is separately derived as `uniq_Op + uniq_Opnd` (no JM1 column). | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | Derived from the two total-count base features. | USE (provisional; derived) | Stored `n` matches the total-count sum in the measured data; vocabulary is a separate intermediate for `v`. |
| `v` | `N * log2(vocabulary)`, where `N = total_Op + total_Opnd` and `vocabulary = uniq_Op + uniq_Opnd`. Fit: after ? 9,408/1,472 (1,332 noncomputable); final 7,698/139. | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | Derived formula; `v` column quantum is 0.01. | USE (provisional; derived) | The derived formula fits the final data within visible rounding intervals. |
| `l` | `1 / d`. Fit: after ? 9,511/1,369 (1,368 noncomputable); final 7,818/19 (19 noncomputable). | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | Derived formula. | USE (provisional; derived) | Deterministic function of the base counts; final data fit is 7,818 rows. |
| `d` | `(uniq_Op / 2) * (total_Opnd / uniq_Opnd)`. Fit: after ? 9,451/1,429 (1,368 noncomputable); final 7,758/79 (19 noncomputable). | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | Derived formula. | USE (provisional; derived) | Deterministic function of the base counts; final data fit is 7,758 rows. |
| `i` | `v / d`. Fit: after ? 9,468/1,412 (1,368 noncomputable); final 7,775/62 (19 noncomputable). | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | Derived formula. | USE (provisional; derived) | Deterministic function of the base counts; final data fit is 7,775 rows. |
| `e` | `d * v`. Fit: after ? 10,842/38; final 7,801/36. | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | Derived formula. | USE (provisional; derived) | Deterministic function of the base counts; final data fit is 7,801 rows. |
| `b` | Use `v / 3000`: after ? 10,872/8; final 7,830/7. Alternative `e^(2/3)/3000`: after ? 3,030/7,850; final 972/6,865. | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | Derived formula; select the better-fitting tested relation provisionally. | USE (provisional; derived) | `v / 3000` fits far more rows than the tested alternative. |
| `t` | `e / 18`. Fit: after ? 10,789/91; final 7,756/81. | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | derived from the base counts; no language-specific extraction | Derived formula. | USE (provisional; derived) | Deterministic function of the base counts; final data fit is 7,756 rows. |
| `lOCode` | Code-only physical lines. Part of relation A; final aggregate fit 6,267/7,837. Individual component fit not separately tested. | `x = 1`; expected `assignment`, `expression_statement`; exclude comment-only lines. | `x = 1;`; expected `lexical_declaration`, `variable_declarator`; exclude comment-only lines. | `const x: number = 1;`; expected `lexical_declaration`, `variable_declarator`; exclude comment-only lines. | Classify physical lines by code/comment node spans. | USE (provisional) | Human-confirmed line class; use best-fitting aggregate relation A. |
| `lOComment` | Comment-only physical lines; Python docstring lines count here. Part of relation A; final aggregate fit 6,267/7,837. Individual component fit not separately tested. | `# note` or a docstring; expected `comment`, or `expression_statement` containing `string`. | `// note`; expected `comment`. | `// note`; expected `comment`. | Classify physical lines by comment node spans; include Python docstring spans. | USE (provisional) | Human-confirmed line class; use best-fitting aggregate relation A. |
| `lOBlank` | Blank physical lines. Part of relation A; final aggregate fit 6,267/7,837. Individual component fit not separately tested. | A blank line; no syntax node, identified from source text between nodes. | A blank line; no syntax node, identified from source text between nodes. | A blank line; no syntax node, identified from source text between nodes. | Count empty physical lines within the unit span. | USE (provisional) | Human-confirmed line class; use best-fitting aggregate relation A. |
| `locCodeAndComment` | Physical lines containing code and a comment. Part of relation A; final aggregate fit 6,267/7,837. Individual component fit not separately tested. | `x = 1  # note`; expected `assignment`/`expression_statement` and `comment`. | `const x = 1; // note`; expected `lexical_declaration` and `comment`. | `const x: number = 1; // note`; expected `lexical_declaration` and `comment`. | Count lines with overlapping code and comment spans. | USE (provisional) | Human-confirmed line class; use best-fitting aggregate relation A. |
| `uniq_Op` | Number of distinct operator tokens under the approved token convention. No independent JM1 target check. | `a + a`; `+` once; expected `binary_operator` and operator token. | `a + a`; `+` once; expected `binary_expression` and operator token. | `a + a`; `+` once; expected `binary_expression` and operator token; exclude type-only syntax. | Tree-sitter token walk; distinct operator lexemes. | USE (provisional) | One of the four approved Halstead base counts. |
| `uniq_Opnd` | Number of distinct non-keyword identifiers and literals. No independent JM1 target check; derived vocabulary is used in `v`. | `a + a`; operand `a` once; expected `identifier`. | `obj.value`; operands `obj`, `value`; expected `identifier`, `property_identifier`. | `obj.value`; operands `obj`, `value`; expected `identifier`, `property_identifier`; exclude type-only syntax. | Tree-sitter token walk; distinct operand lexemes. | USE (provisional) | One of the four approved Halstead base counts. |
| `total_Op` | Operator-token occurrences. Joint `n(column)` fit: after ? 10,739/141; final 7,697/140. | `a + b`; count each operator occurrence; expected `binary_operator` and operator token. | `a + b`; count each operator occurrence; expected `binary_expression` and operator token. | `a + b`; count each operator occurrence; expected `binary_expression` and operator token; exclude type-only syntax. | Tree-sitter token walk; count occurrences, including keywords. | USE (provisional) | One of the four approved Halstead base counts. |
| `total_Opnd` | Non-keyword identifier and literal occurrences. Joint `n(column)` fit: after ? 10,739/141; final 7,697/140. | `a + a`; count both identifier occurrences; expected `identifier`. | `obj.value`; count both identifier occurrences; expected `identifier`, `property_identifier`. | `obj.value`; count both identifier occurrences; expected `identifier`, `property_identifier`; exclude type-only syntax. | Tree-sitter token walk; count occurrences. | USE (provisional) | One of the four approved Halstead base counts. |
| `branchCount` | Tested `branchCount = v(g)-1`: 0 matches in both cohorts. Final `branchCount/(v(g)-1)` min/max 1.00496/5; exact matches 0. | `if x:`; no branch-count implementation; expected `if_statement`. | `if (x) {}`; no branch-count implementation; expected `if_statement`. | `if (x) {}`; no branch-count implementation; expected `if_statement`. | No implementation. | DROP | Data does not define it: ratio ranges 1.005 to 5 and is never equal to 1. |

USE (provisional): 18 columns; DROP: ev(g), iv(g), branchCount.

Approved provisional definitions:

- Line classes are counted over the unit span from first to last line, including
  the signature. `loc` counts all physical lines. Python docstring lines count
  as comment lines.
- `v(g) = 1 + decision points`. Python: `if`/`elif`, `for`/`while`, each
  non-default `case_clause` of `match`, `except`, `conditional_expression`,
  `boolean_operator` (`and`/`or`), and comprehension `for_in_clause` and
  `if_clause`. JavaScript and TypeScript: `if`, `for`/`for-in`/`for-of`,
  `while`/`do-while`, each non-default case, `catch`, ternary, and short-circuit
  operators `&&`, `||`, `??`, `&&=`, `||=`, `??=`. Optional chaining `?.` is
  not a decision point. Callbacks passed to `.map`/`.filter` are separate
  functions; their unit boundaries are decided in 0.9.8. Expected node names
  are all unverified until Phase 2 fixtures: Python `if_statement`,
  `elif_clause`, `for_statement`, `while_statement`, `case_clause`,
  `except_clause`, `conditional_expression`, `boolean_operator`,
  `for_in_clause`, `if_clause`; JavaScript/TypeScript `if_statement`,
  `for_statement`, `for_in_statement`, `while_statement`, `do_statement`,
  `switch_case`, `catch_clause`, `ternary_expression`, `binary_expression`,
  `augmented_assignment_expression`.
- Halstead counting is token-based on Tree-sitter with classic conventions
  adapted per language. Operands are non-keyword identifiers and literals;
  operators are keywords and operator tokens; comments are excluded. TypeScript
  type-only syntax is excluded. Unique counts count distinct lexemes; total
  counts count occurrences.
- `n(column) = total_Op + total_Opnd`; vocabulary is the derived
  `uniq_Op + uniq_Opnd` and has no JM1 column. `v = N * log2(vocabulary)`, where
  `N = total_Op + total_Opnd`; `d = (uniq_Op / 2) * (total_Opnd / uniq_Opnd)`;
  `l = 1/d`; `i = v/d`; `e = d*v`; `b = v/3000`; `t = e/18`.
- Unit boundaries and nested functions follow the rules recorded in 0.9.8.

Zero-operand convention: when `uniq_Opnd = 0`, set `d = l = i = 0`; this
matches the stored values in all 19/19 final rows. Use `v = N * log2(vocabulary)`;
the relation fits all 19/19 final rows. If `vocabulary = 0`, set `v = 0`; this
case is untested by the data. These conventions were recorded before any model
results.

Reproduce the data check from the repository root in PowerShell:

```powershell
backend\.venv\Scripts\python.exe ml\jm1_facts.py --definitions-check
```

## 0.9.5 Prediction unit

JM1 module rows correspond to functions/methods, so features are computed per
function/method, predicted in memory, and aggregated into one stored file-level
score. Do not add a function-level table; per-function features live in memory
for the duration of the run. A file is the aggregate container, not the JM1
prediction unit.

## 0.9.6 Metric implementation

No metrics library is used in production. RepoPulse owns one Tree-sitter
extractor for Python, JavaScript, and TypeScript. Radon, Lizard, and
typhonjs-escomplex may be used only as cross-checks in G0, never as production
sources. Revisit this decision only if the 0.9.9 prototype extractor cannot
meet the compatibility rule (0.9.7).

## 0.9.7 Compatibility rule

A JM1 feature enters the serving schema only if:

1. Its definition is verified by the data check or fixed by an approved
  convention.
2. It can be implemented consistently across Python, JavaScript, and
  TypeScript, with every approximation justified in the matrix. Consistently
  does not mean identically.
3. Its serving range stays within a stable range of the JM1 range, checked in
  0.9.9.

Derived fields use only admitted features. The zero-operand conventions are
recorded in 0.9.4. This rule was recorded before any model results.

## 0.9.8 Prediction-unit rules

The same rules apply to Python, JavaScript, and TypeScript. A unit is an
OUTERMOST function-like node that has a block/statement body and is not inside
another unit:

- Python `def` and `async def`.
- JavaScript/TypeScript function declarations, function expressions, arrow
  functions with block bodies, methods, constructors, getters/setters, and
  object-literal methods. Class methods are units.
- Anything nested inside a unit (inner defs, closures, callbacks) belongs to
  that unit and is not a separate unit.
- Python lambdas and expression-bodied arrow functions never form units.
- TypeScript overload signatures and abstract/declare functions without
  bodies are not units.
- Module-level code is everything outside units (class bodies included, minus
  their methods). It forms one module-level unit only if it qualifies by the
  0.9.8 rule: control flow (`if`, `for`, `while`, `try`, `switch`) or a call
  expression outside imports, decorators, and exports. Imports, constant
  assignments, type declarations, and docstrings alone do not qualify. Unit
  subtrees are excluded from module-level counts.

Stage 1 Python fixtures created: `python_main_guard`, `api_key_assignment`,
`import_only`, `declaration_only`, `docstring_only`, `python_nested_def`,
`python_if_and`, and `python_line_classes`. Stage 2 JavaScript, JSX, TypeScript,
and TSX fixtures created: `javascript_app_listen`,
`javascript_block_vs_expression_arrow`, `type_only_typescript`,
`typescript_overload_impl`, and `jsx_component`.

### Token counting conventions

- Delimiters are excluded; member access and optional chaining count as operators.
- Function/method names and parameter identifiers count as operands; decorators
  are excluded.
- Python docstring lines count as comment lines, and the docstring string is not
  an operand.
- Each literal counts as one operand; JSX tag and attribute names are operands,
  while JSX text is ignored.
- Zero vocabulary gives `v = 0`.

### Known approximations

Delimiters are excluded, so call parentheses do not count as operators in any
language. The 0.9.9 range check shows whether this matters.

## 0.9.9 Feature-range sanity check

Not yet done. The stage-one extractor lives in `ml/`; its pins
(`tree-sitter==0.26.0`, `tree-sitter-python==0.25.0`,
`tree-sitter-javascript==0.25.0`, `tree-sitter-typescript==0.23.2`) are in
`ml/requirements.txt` and installed into `backend/.venv` for this prototype.
The backend requirements remain unchanged; the backend gets Tree-sitter in
Phase 2.

## 0.9.10 Feature schema

Not yet done.

## 0.9.11 G0 report

Not yet done.
