# RepoPulse - Progress

> **Living status file.** The AI builder updates this file **after every task and at the end of every session**. It is the one file the AI edits on its own. `PRD.md`, `Architecture.md`, `Phases.md`, and `AGENTS.md` stay stable.

| | |
| --- | --- |
| **Last updated** | 2026-10-19 |
| **Updated by** | AI builder (task 1.3 implemented and verified; awaiting commit and CI) |
| **Placement** | Repository root, next to `AGENTS.md` |

---

## 1. Snapshot

| | |
| --- | --- |
| **Overall status** | **Phase 0 done; Phase 1 in progress.** Task 1.1 is committed as `f4b78dc` with all four CI jobs passed; task 1.3 awaits human commit and CI. |
| **Current phase** | Phase 1 - Identity and Repositories (in progress) |
| **Next task** | Phase 1 task 1.4 (not started) |
| **Blocked?** | No |
| **Last human approval** | 2026-10-18, Phase 0 exit review |

---

## 2. Phase Tracker

**Status values:** `Not started` / `In progress` / `Blocked` / `Awaiting approval` / `Done`.
A phase is `Done` only after the human approves its exit criteria (see `AGENTS.md` section 3.2).

| Phase | Name | Status | Started | Finished | Tag |
| --- | --- | --- | --- | --- | --- |
| 0 | Foundations (includes **Gate G0**: ML feasibility) | Done | 2026-10-10 | 2026-10-18 | - |
| 1 | Identity and Repositories | In progress | 2026-10-19 | - | `v0.1` |
| 2 | Analysis Core | Not started | - | - | `v0.2` |
| 3 | Repository Context | Not started | - | - | `v0.3` |
| 4 | ML | Not started | - | - | `v0.4` |
| 5 | AI Explanation | Not started | - | - | `v0.5` |
| 6 | Frontend | Not started | - | - | `v0.6` |
| 7 | Hardening and Release | Not started | - | - | `v1.0` |

**Gate G0** (end of Phase 0): `Passed`. Phase 2 metric work and all of Phase 4 must not start until the human approves the gate.

---

## 3. Current Task

| | |
| --- | --- |
| **Task ID** | Phase 1 task 1.4 |
| **Title** | Auth routes and callback orchestration |
| **Status** | Not started |
| **Plan** | Implement the auth routes and callback orchestration. Keep task 1.2 real OAuth App registration deferred to Stage 4. |
| **Notes / problems** | Phase 0 Done, Gate G0 passed. Task 1.1 is committed and CI-green. Task 1.3 is implemented and verified, awaiting human commit and CI. |

---

## 4. Completed Tasks

Record each finished task by **ID only** (the task text lives in `Phases.md`; do not copy it here).

| Task ID | Date | PR / commit | Tests run and result | Notes |
|---|---|---|---|---|
| 1.3 | 2026-10-19 | awaiting human commit and CI | Ruff check and format check passed; focused OAuth pytest: 32 passed; backend pytest: 48 passed | Implemented and verified; no real credentials or network used. |
| 1.1 | 2026-10-19 | `f4b78dc` | Ruff check and format check passed; backend pytest: 16 passed; human verified Compose migration upgrade and `alembic current` reports `0002_identity (head)`; all four CI jobs passed | Committed and CI-green. |
| 0.1 | 2026-10-10 | awaiting human commit | None required (infrastructure only) | Done; `.gitignore`, `.env.example`, `README.md`, `frontend/`, `backend/`, `ml/` `.gitkeep` files created. Ignore rules verified with `git check-ignore`. |
| 0.2 | 2026-10-10 | awaiting human commit | `GET /health` -> `{"status":"ok"}` verified via `Invoke-WebRequest` (200 OK) | `backend/requirements.txt`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/.env` created. `.env.example` SESSION_SECRET_KEY -> SESSION_SECRET corrected. `.venv` created with `py -3.12`. |
| 0.3 | 2026-10-11 | awaiting human commit | ruff check (0 errors), ruff format (0 changes), pytest -v (2 passed, 0 warnings: test_health.py smoke test 200 OK + test_config.py missing required env var fail-fast ValidationError) | Done; created `backend/requirements-dev.txt` (pytest==9.1.1, ruff==0.17.0, httpx2==2.13.1), `backend/pyproject.toml`, `backend/tests/conftest.py`, `backend/tests/test_health.py`, `backend/tests/test_config.py`. Decision: replaced httpx with httpx2==2.13.1 to eliminate StarletteDeprecationWarning from starlette.testclient. Correcting note: tasks 0.1 and 0.2 are committed (0.1 = dab2b9b, 0.2 = de48014); .env lives at repo root, not backend/.env. |
| 0.4 | 2026-10-12 | awaiting human commit | Frontend landing page returned HTTP 200; direct dependency pins match package-lock.json; Recharts 3.10.1 installed. No lint/build/tests run (task 0.5). | Done; created the frontend skeleton, shadcn configuration, `frontend/lib/api.ts`, and local frontend env file. Removed generated button component and frontend AGENTS.md. Correcting note: 0.3 committed as b0bf50d. |
| 0.5 | 2026-10-13 | awaiting human commit | `npm run lint`, `npm run type-check`, and `npm run build` with and without `.env.local` all passed (exit 0). | Done; added `type-check`: `tsc --noEmit`. Correcting note: 0.4 committed as 6c8eba6. |
| 0.6 | 2026-10-13 | awaiting human commit | `ruff check .` passed; `ruff format --check .` passed; `pytest -v` passed (2 passed); Alembic upgrade/current verified on PostgreSQL 17.11; engine import checked out 0 connections. | Done; added SQLAlchemy, Alembic, psycopg 3, required `DATABASE_URL`, and an empty baseline migration. PostgreSQL 17 (development); production host to match. Correcting note: 0.5 committed as e583809. |
| 0.7 | 2026-10-13 | awaiting human commit | Compose build passed; all services healthy; frontend and `/health` returned 200; Alembic current is `0001_baseline (head)`; hostname `postgres`; backend UID 10001; Git 2.39.5; image app trees clean; containers removed and volume retained. | Done; corrected frontend builder permissions. Correcting note: 0.6 committed as 27b107b. |
| 0.8 | 2026-10-13 | f1a366b, 6aca054 | GitHub Actions: backend, frontend, migrations, and Docker jobs all passed | Workflow added; first CI run failed at frontend type-check (LayoutProps missing on fresh checkout); fixed by running Next typegen in the type-check script. Correcting note: 0.7 committed as a6edb6f. Alembic job approved. CI verified green on 6aca054. |
| 0.9 | 2026-10-14 | awaiting human commit | `backend\.venv\Scripts\python.exe ml\jm1_facts.py`; Ruff check and format check passed | Done; provenance, checksum, and Kaggle-reported unknown license status recorded in `ml/README.md`. |
| 0.9.1 | 2026-10-14 | awaiting human commit | Candidate predictor and target columns recorded; `id` excluded | Done; `ml/jm1_facts.py` and `ml/README.md` are evidence. |
| 0.9.2 | 2026-10-14 | awaiting human commit | Facts report matched documented row, label, duplicate, conflict, and checksum values | Done; `ml/jm1_facts.py` and `ml/README.md` are evidence. |
| 0.9.3 | 2026-10-14 | awaiting human commit | Facts report identified five `?` rows and all five affected metric columns | Done; record dropping these rows before training, without coercion or imputation. |
| 0.9.3a | 2026-10-14 | awaiting human commit | `--anomaly-evidence` reported the id=1 and zero-operator evidence | Decisions A and B recorded in `ml/README.md`; evidence in `ml/jm1_facts.py`. |
| 0.9.3b | 2026-10-14 | awaiting human commit | `--final-set` reported 7,837 rows, 6,184 non-defective, 1,653 defective (21.09%) | Preprocessing order and final-set funnel recorded in `ml/README.md`; evidence in `ml/jm1_facts.py`. |
| 0.9.4 | 2026-10-17 | b670a63 | Compatibility matrix recorded; no automated tests (G0 decision record) | Final use/drop classifications recorded in 0.9.10. Correcting note: matrix committed as b670a63. |
| 0.9.5 | 2026-10-17 | awaiting human commit | Prediction-unit decision recorded; no automated tests (G0 decision record) | Decision recorded in `ml/README.md`. |
| 0.9.6 | 2026-10-17 | awaiting human commit | Metric-method decision recorded; no automated tests (G0 decision record) | Decision recorded in `ml/README.md`; prototype dependency plan is under 0.9.9. |
| 0.9.7 | 2026-10-17 | awaiting human commit | Compatibility rule recorded; no automated tests (G0 decision record) | Evidence in `ml/README.md` and `ml/jm1_facts.py`. |
| 0.9.8 | 2026-10-17 | awaiting human commit | `pytest ml\tests`: 29 passed, including 13 G0 fixtures and the schema contract test. | Evidence: `ml/README.md`, fixtures, and extractor scripts. Awaiting human commit. |
| 0.9.9 | 2026-10-17 | awaiting human commit | Five-set per-language aggregates recorded; three full runs had identical stdout; median-ratio command output recorded. | Evidence: `ml/README.md` and range-check scripts. Correcting note: Stage 3b was committed as e401f11. Awaiting human commit for final G0 decision/report changes. |
| 0.9.10 | 2026-10-17 | awaiting human commit | Schema contract covered by `pytest ml\tests`: 29 passed. | Evidence: `ml/README.md`, `backend/app/ml/artifacts/feature_schema.json`, fixtures, and extractor scripts. Awaiting human commit. |
| 0.9.11 | 2026-10-17 | awaiting human commit | G0 report completed; median ratios computed from the aggregate table values. | Evidence: `ml/README.md`, fixtures, scripts, and draft schema. Awaiting human commit. |

---

## 5. What the Human Must Provide

### 5.1 Setup checklist (before or during Phase 0)

| Item | Needed by | Done? |
| --- | --- | --- |
| GitHub repository created for the monorepo | Phase 0 (task 0.1) | [x] https://github.com/Viplav-Bhure/RepoPulse |
| Docker and Docker Compose installed and working | Phase 0 (task 0.7) | [x] Docker 29.8.2, Compose v5.5.1 |
| Python and Node.js toolchains installed | Phase 0 (tasks 0.2-0.5) | [x] Python 3.12 (via py launcher) + 3.13.14, Node.js 24.21.0 |
| `git` available locally | Phase 0 | [x] git 2.49.0.windows.1 |
| JM1 dataset file `jm1.csv` available (from the supplied `NASA_dataset.zip`); SHA-256 `1ec66eb3568ae8bb4e2709cf0bd28b11db41c7c0ae771325c0952997e35e4dff` | Phase 0 (Gate G0, task 0.9) | [x] |
| GitHub OAuth App registered for local development | Stage 4 (deferred from task 1.2) | [ ] |
| OpenAI API key | Phase 5 | [ ] |
| A domain you own, with DNS access, and hosts that allow custom domains | Start of Phase 6 (latest Phase 7) | [ ] |

### 5.2 Decisions due (remaining items are **Open**)

The full schedule is in `Phases.md` section 3. The AI must **ask** for each decision before work that depends on it.

| Decision | Due | Status | Human's answer |
| --- | --- | --- | --- |
| Final JM1 feature subset | End of Phase 0 (G0) | Decided | Use `loc`, `v(g)`, `uniq_Op`, `uniq_Opnd`, `total_Op`, `total_Opnd`, `n`, `v`, `l`, `d`, `i`, `b`. Drop `ev(g)`, `iv(g)`, and `branchCount` as not verifiable/language-neutral; drop `e` and `t` by the median range rule; drop the four line-class fields for simplicity because individual definitions are unverified, aggregate fit is about 80%, and they are style-dependent. Recorded in `ml/README.md` 0.9.10. |
| Exact metrics library, if any | End of Phase 0 (G0) | Decided | No metrics library in production. RepoPulse owns one Tree-sitter extractor for Python, JavaScript, and TypeScript. Radon, Lizard, and typhonjs-escomplex are G0 cross-checks only; revisit only if the 0.9.9 prototype cannot meet the compatibility rule (0.9.7). |
| Rules for anomalous JM1 rows (`id=1`, `lOCode` > `loc`, `total_Op` = 0) | End of Phase 0 (G0) | Decided | Drop `id=1` (the only row with `lOCode` > `loc`) and all 1,332 rows with `total_Op` = 0 and `loc` >= 1. Order: drop the five `?` rows, drop `id=1`, drop the group, remove conflicting-label metric vectors and deduplicate, then split. |
| Prediction-unit rules (what counts as a function/method; qualifying top-level code) | End of Phase 0 (G0) | Decided | Same rules for all three languages: outermost function-like nodes with block/statement bodies are units; nested functions, closures, and callbacks belong to the outer unit; qualifying module-level code follows the recorded 0.9.8 rule. Full rules and fixture cases are in `ml/README.md`. |
| **Python runtime and Docker base image** | Phase 0 (task 0.2) | **Decided** | Python 3.12; Docker base image `python:3.12-slim-bookworm`; local `.venv` created with `py -3.12`. Wheels verified 2026-10-10. Recorded in Architecture decision log. |
| PostgreSQL driver and major version | Task 0.6 | Decided | psycopg[binary] (psycopg 3); SQLAlchemy URL scheme `postgresql+psycopg://`; PostgreSQL 17 (development), production host to match. |
| GitHub API access after login (proposed: list at callback plus a server-side public-data credential) | Start of Phase 1 | Open (proposal awaiting confirmation) | |
| Test-file handling in summaries and ML | Phase 2 / Phase 4 | Open (proposal awaiting confirmation) | |
| Failed-run retention | Phase 2 | Open (proposal awaiting confirmation) | |

Later decisions (aggregation rule, risk thresholds, ML targets, graph layout, OpenAI model and snippet cap, hosting, indexes, and others) are tracked in `Phases.md` section 3. Move them into this table when their phase approaches.

---

## 6. Blockers and Active Risks

| # | Item | Impact | Status |
|---|---|---|---|
| - | No blockers yet | - | - |
| Watch 1 | `npm audit`: 9 high (7 with `--omit=dev`), all via `shadcn@4.21.4` (`ts-morph` and `@shadcn/registry`) -> `fast-glob` -> `micromatch` -> `braces`. `shadcn` is a dependency but only needed at build time (`globals.css` imports `shadcn/tailwind.css`). | Decide in task 0.7 / Phase 7 whether it moves to `devDependencies`; never run `npm audit fix --force`. | Open |
| Watch 2 | npm reports an `allowScripts` warning for `unrs-resolver@1.12.2` via `eslint-config-next` -> `eslint-import-resolver-typescript`. | Review in Phase 7; `npm run lint` passed (exit 0, no lint diagnostics). | Open |
| Watch 3 | `next dev` regenerates `frontend/AGENTS.md` and `node_modules/next/AGENTS.md` on every run. Do not commit; delete before commits. Notice says read `node_modules/next/dist/docs/` before writing Next code. | Ask the human how to handle before Phase 6. | Open |
| Watch 4 | PowerShell may wrap normal Docker Compose stderr progress as `NativeCommandError`, including when a command succeeds. | Check the saved command log and native exit code before treating the wrapper as a failure. | Observed |
| Watch 5 | npm flags `eslint@9.39.5` as deprecated in CI ("no longer supported"). | Review in Phase 7. | Open |
| Watch 6 | Tree-sitter core/grammar compatibility: the Phase 2 smoke test must parse a LARGE file and walk every node, not a tiny sample. | Verify core and grammar wheel compatibility on a large fixture before Phase 2 metric work. | Open |

**Watch items from the start:**

- The cookie/domain strategy requires an owned domain, which is not in place yet.

---

## 7. Document Status and Known Doc Items

| Document | Status |
| --- | --- |
| `PRD.md` | Complete, revised during Phase 0 |
| `Architecture.md` | Complete, revised during Phase 0 |
| `Phases.md` | Complete, revised during Phase 0 |
| `AGENTS.md` | Complete |
| `Progress.md` | This file |

**Known minor items (non-blocking, not yet applied):**

1. `Phases.md` (4.16, 4.18, exit criteria) report one combined **Not scored** count; splitting it into "no code to score" and "ML unavailable" is optional.
2. `Phases.md` section 2.1 describes a pull-request workflow marked [Proposed]; `AGENTS.md` section 9.1 now says the human commits directly to `main`. Update `Phases.md` section 2.1 when convenient.

---

## 8. Session Log

Newest first. One entry per session. Keep entries short.

| Date | Session summary | Tasks touched | Open questions raised |
|---|---|---|---|
| 2026-10-19 | Task 1.3 OAuth helpers implemented and verified; awaiting human commit and CI. Real OAuth App registration remains deferred to Stage 4. | 1.3; 1.2 deferred; next 1.4 | None |
| 2026-10-19 | Recorded task 1.1 implementation and human-verified migration head; awaiting human commit and CI. Task 1.2 planning is next and has not started. | 1.1; 1.2 planning pointer | Human commit and CI for task 1.1. |
| 2026-10-18 | Phase 0 is Done and Gate G0 passed on the human's approval. All section 4 rows for 0.1-0.9.11 marked "awaiting human commit" are now committed; the last two commits are c4645a3 and 9c125fa. | Phase 0 exit review; Phase 1 planning | None |
| 2026-10-17 | Final JM1 feature subset recorded; draft schema and G0 report added; Phase 0 set to Awaiting approval. Schema tests pass; awaiting human exit review and commit. | 0.9.8-0.9.11 | Human re-verification of the four Phase 0 exit criteria. |
| 2026-10-17 | G0 stage 3b aggregates added for five labeled sets, including per-language flags, counts, skipped files, parse errors, and elapsed time; three stdout runs matched. Feature subset remains a proposal; awaiting review. | 0.9.9 | Final JM1 feature use/drop decision before 0.9.10. |
| 2026-10-17 | G0 stage 3a results recorded for three labeled repositories plus combined units. Core 0.26.0 crashed 10/10 baseline runs; 0.25.2 passed 10/10, pip check and 27 ML tests passed, and three full aggregate outputs matched. | 0.9.9 | Final JM1 feature use/drop decision before 0.9.10; update Architecture section 46 verified-wheel row. |
| 2026-10-17 | Started G0 stage 3a; final-set output remained byte-identical, 27 ML tests and Ruff checks passed, but RepoPulse range extraction hit a native Tree-sitter failure. No aggregate results recorded. | 0.9.9 | Continue extractor investigation; use/drop decisions remain pending. |
| 2026-10-17 | G0 stage 2 JavaScript, JSX, TypeScript, and TSX extraction implemented; pytest 27 passed and Ruff checks passed on maintained ML Python files. JM1 checksum unchanged; awaiting review. | 0.9.8 stage 2 | Stage 2 review. |
| 2026-10-17 | G0 stage 1 extractor and fixtures implemented; pytest 17 passed, Ruff checks passed; awaiting review. Tree-sitter pins installed in backend/.venv; JM1 checksum unchanged. | 0.9.8 stage 1 | Approve stage 1 before continuing. |
| 2026-10-17 | Corrected G0 compatibility-rule references and 0.9.6 decision wording; drafted a plan for remaining G0 work without implementation or installs. | 0.9.6; 0.9.8-0.9.11 planning | Final JM1 feature subset; token-count conventions; additional repositories for the range check. |
| 2026-10-17 | Recorded human-confirmed G0 decisions for the matrix, prediction unit, metric method, compatibility rule, and unit boundaries. Gate G0 remains not passed. | 0.9.4-0.9.8 | Final JM1 feature subset; complete 0.9.9 and 0.9.10 validation. |
| 2026-10-14 | Verified Stage A-B commit b670a63; zero-operand v formula fits 19/19 rows; Tree-sitter wheel dry run passed with no installs. Gate G0 remains not passed. | 0.9.4 Stage A-B | 0.9.5-0.9.9 G0 choices: metric method, compatibility rule, unit boundaries, and prototype setup. |
| 2026-10-14 | Revised the provisional JM1 compatibility matrix with the approved decision-point rules, measured line relations, and zero-operand evidence. | 0.9.4 | Confirm zero-operand `v` and zero-vocabulary conventions. |
| 2026-10-14 | Completed the JM1 definitions check and drafted the provisional compatibility matrix; awaiting human approval. No Tree-sitter packages installed. | 0.9.4 Stage A-B | Approve or revise the provisional compatibility matrix. |
| 2026-10-14 | Confirmed tasks 0.9 through 0.9.3b committed as 78aafc3 and decision docs committed as 30251f9; corrected the anomalous-row decision log and started the JM1 definitions check. | 0.9.4 | Compatibility decisions for operator/operand counts, line counting, and branches/decision points. |
| 2026-10-14 | Recorded the confirmed JM1 anomalous-row rules and preprocessing order; added the measured final-set funnel. Gate G0 remains not passed. | 0.9.3a, 0.9.3b | Final JM1 feature subset, metrics library, and prediction-unit rules. |
| 2026-10-14 | Added the read-only JM1 facts reporter and G0 dataset record; confirmed the lOCode anomaly is id=1 and preserved pending anomaly decisions. Gate G0 remains not passed. | 0.9, 0.9.1, 0.9.2, 0.9.3 | Human keep/drop rules for anomalous JM1 rows. |
| 2026-10-14 | Verified task 0.8 CI green on 6aca054; confirmed the JM1 SHA-256 and computed stage-1 dataset facts with Python csv; prepared a G0 plan without applying anomaly decisions. | 0.8, 0.9 planning | JM1 anomaly keep/drop decisions remain open. |
| 2026-10-14 | Reproduced the fresh-checkout `LayoutProps` type-check failure, added `next typegen` before `tsc`, then passed type-check, lint, and build from cleaned frontend outputs. The build emitted Google font assets. | 0.8 | First CI run after the fix must be green before verification. |
| 2026-10-13 | Added the GitHub Actions workflow for backend, frontend, Docker builds, and approved Alembic migrations. Local checks only; first CI run pending. | 0.8 | First CI run must be green before verification. |
| 2026-10-13 | Task 0.7 complete. Built both images; Compose health, HTTP, migration, hostname, backend UID, Git, and image-content checks passed. Containers removed; `repopulse_postgres_data` retained. Correcting note: 0.6 committed as 27b107b. | 0.7 | None |
| 2026-10-13 | Task 0.6 complete. Added exact SQLAlchemy/Alembic/psycopg pins, required `DATABASE_URL`, lazy SQLAlchemy engine/session factory, declarative base, and empty Alembic baseline. PostgreSQL 17 tag resolved to 17.11; migration applied/current at head and only `alembic_version` exists. Container removed; lint, format check, and tests passed. Correcting note: 0.5 committed as e583809. | 0.6 | None |
| 2026-10-13 | Task 0.5 complete. Added the frontend `type-check` script. Lint, type-check, and production builds with and without `.env.local` passed. The local env file was restored and verified; build made no tracked changes beyond `package.json`, and no frontend AGENTS.md appeared. Correcting note: 0.4 committed as 6c8eba6. | 0.5 | PostgreSQL driver decision required before task 0.6. |
| 2026-10-11 | Task 0.3 complete (awaiting human commit). Created backend/requirements-dev.txt, pyproject.toml, tests/conftest.py, tests/test_health.py, tests/test_config.py. Installed pinned pytest==9.1.1, ruff==0.17.0, httpx2==2.13.1 in backend/.venv (httpx replaced with httpx2 to resolve StarletteDeprecationWarning). Verified ruff check, ruff format, and pytest -v (2 passed, 0 warnings). Noted commits for 0.1 (dab2b9b) and 0.2 (de48014), and root .env location. | 0.3 | None |
| 2026-10-12 | Task 0.4 complete. Created the frontend skeleton with exact direct dependency pins, shadcn defaults, Recharts, API base helper, and placeholder page. HTTP 200 verified; dev server stopped and port 3000 confirmed free. No lint/build/tests run (task 0.5). Removed generated frontend AGENTS.md and shadcn button component. Correcting note: 0.3 committed as b0bf50d. | 0.4 | None |
| 2026-10-10 | Housekeeping by reviewer: `Progress.md` re-encoded as ASCII (UTF-8 without BOM, LF line endings) to remove garbled characters. `AGENTS.md` gained section 7.6 (environment and file handling) and a rewritten section 9.1 (the human makes every commit). No code changed. | None | None |
| 2026-10-10 | Task 0.2 complete. Python 3.12 decision recorded in Architecture and Progress.md. Created `backend/requirements.txt`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/.env`. Fixed `SESSION_SECRET_KEY` -> `SESSION_SECRET` in `.env.example`. Venv created with `py -3.12`. `/health` verified 200 OK. | 0.2 | Doc issue: `.env.example` had `SESSION_SECRET_KEY`; corrected to `SESSION_SECRET` (Architecture section 41). PostgreSQL driver still open (ask before task 0.6). |
| 2026-10-10 | Task 0.1 complete (awaiting human commit). Created `.gitignore`, `.env.example`, `README.md` stub, `frontend/`, `backend/`, `ml/` `.gitkeep` files. Verified ignore rules with `git check-ignore`. docs/ confirmed untouched. | 0.1 | None |
| 2026-10-09 | Planning complete: `PRD.md`, `Architecture.md`, `Phases.md`, `AGENTS.md`, and this file created and reviewed. **No code written. Nothing started.** | None | See section 5.2 |

---

## 9. How to Update This File (rules for the AI)

1. **After every task:** add a row to section 4, update section 3 to the next task, and update section 1 if the phase or status changed.
2. **At phase boundaries:** set the phase to `Awaiting approval` and list the exit-criteria evidence. Change it to `Done` (and fill the dates and tag) only after the human approves.
3. **When a decision is made:** record the human's answer in section 5.2, then follow `AGENTS.md` section 9.4 to update the decision logs in the documents.
4. **At the end of every session:** add a session-log row and make sure the snapshot is true.
5. **Never delete history.** Add rows; do not rewrite old ones. Fix mistakes by adding a correcting note.
6. **Keep it short.** Reference task IDs and requirement IDs; do not copy text from the other documents.
7. **If this file disagrees with the code or repository, the code wins.** Correct this file and mention it in your report.
8. **Never mark something done that you did not run and verify.**
