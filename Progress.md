# RepoPulse - Progress

> **Living status file.** The AI builder updates this file **after every task and at the end of every session**. It is the one file the AI edits on its own. `PRD.md`, `Architecture.md`, `Phases.md`, and `AGENTS.md` stay stable.

| | |
| --- | --- |
| **Last updated** | 2026-10-13 |
| **Updated by** | AI builder (task 0.5) |
| **Placement** | Repository root, next to `AGENTS.md` |

---

## 1. Snapshot

| | |
| --- | --- |
| **Overall status** | **In progress.** Phase 0 started. Tasks 0.1, 0.2, 0.3, 0.4, and 0.5 complete. |
| **Current phase** | Phase 0 - Foundations (**in progress**) |
| **Next task** | **0.6** - Database: SQLAlchemy session/models and Alembic baseline migration (see `Phases.md`, Phase 0) |
| **Blocked?** | Yes. Decide the PostgreSQL driver before task 0.6; see section 5.2. |
| **Last human approval** | Planning documents reviewed on 2026-10-09 |

---

## 2. Phase Tracker

**Status values:** `Not started` / `In progress` / `Blocked` / `Awaiting approval` / `Done`.
A phase is `Done` only after the human approves its exit criteria (see `AGENTS.md` section 3.2).

| Phase | Name | Status | Started | Finished | Tag |
| --- | --- | --- | --- | --- | --- |
| 0 | Foundations (includes **Gate G0**: ML feasibility) | In progress | 2026-10-10 | - | - |
| 1 | Identity and Repositories | Not started | - | - | `v0.1` |
| 2 | Analysis Core | Not started | - | - | `v0.2` |
| 3 | Repository Context | Not started | - | - | `v0.3` |
| 4 | ML | Not started | - | - | `v0.4` |
| 5 | AI Explanation | Not started | - | - | `v0.5` |
| 6 | Frontend | Not started | - | - | `v0.6` |
| 7 | Hardening and Release | Not started | - | - | `v1.0` |

**Gate G0** (end of Phase 0): `Not passed`. Phase 2 metric work and all of Phase 4 must not start until it is passed.

---

## 3. Current Task

| | |
| --- | --- |
| **Task ID** | 0.6 |
| **Title** | Database: SQLAlchemy session/models and Alembic baseline migration |
| **Status** | Not started |
| **Plan** | *(AI writes plan before starting)* |
| **Notes / problems** | PostgreSQL driver decision required before starting; see section 5.2. |

---

## 4. Completed Tasks

Record each finished task by **ID only** (the task text lives in `Phases.md`; do not copy it here).

| Task ID | Date | PR / commit | Tests run and result | Notes |
|---|---|---|---|---|
| 0.1 | 2026-10-10 | awaiting human commit | None required (infrastructure only) | Done; `.gitignore`, `.env.example`, `README.md`, `frontend/`, `backend/`, `ml/` `.gitkeep` files created. Ignore rules verified with `git check-ignore`. |
| 0.2 | 2026-10-10 | awaiting human commit | `GET /health` -> `{"status":"ok"}` verified via `Invoke-WebRequest` (200 OK) | `backend/requirements.txt`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/.env` created. `.env.example` SESSION_SECRET_KEY -> SESSION_SECRET corrected. `.venv` created with `py -3.12`. |
| 0.3 | 2026-10-11 | awaiting human commit | ruff check (0 errors), ruff format (0 changes), pytest -v (2 passed, 0 warnings: test_health.py smoke test 200 OK + test_config.py missing required env var fail-fast ValidationError) | Done; created `backend/requirements-dev.txt` (pytest==9.1.1, ruff==0.17.0, httpx2==2.13.1), `backend/pyproject.toml`, `backend/tests/conftest.py`, `backend/tests/test_health.py`, `backend/tests/test_config.py`. Decision: replaced httpx with httpx2==2.13.1 to eliminate StarletteDeprecationWarning from starlette.testclient. Correcting note: tasks 0.1 and 0.2 are committed (0.1 = dab2b9b, 0.2 = de48014); .env lives at repo root, not backend/.env. |
| 0.4 | 2026-10-12 | awaiting human commit | Frontend landing page returned HTTP 200; direct dependency pins match package-lock.json; Recharts 3.10.1 installed. No lint/build/tests run (task 0.5). | Done; created the frontend skeleton, shadcn configuration, `frontend/lib/api.ts`, and local frontend env file. Removed generated button component and frontend AGENTS.md. Correcting note: 0.3 committed as b0bf50d. |
| 0.5 | 2026-10-13 | awaiting human commit | `npm run lint`, `npm run type-check`, and `npm run build` with and without `.env.local` all passed (exit 0). | Done; added `type-check`: `tsc --noEmit`. Correcting note: 0.4 committed as 6c8eba6. |

---

## 5. What the Human Must Provide

### 5.1 Setup checklist (before or during Phase 0)

| Item | Needed by | Done? |
| --- | --- | --- |
| GitHub repository created for the monorepo | Phase 0 (task 0.1) | [x] https://github.com/Viplav-Bhure/RepoPulse |
| Docker and Docker Compose installed and working | Phase 0 (task 0.7) | [x] Docker 29.8.1, Compose v5.5.1 |
| Python and Node.js toolchains installed | Phase 0 (tasks 0.2-0.5) | [x] Python 3.12 (via py launcher) + 3.13.14, Node.js 24.21.0 |
| `git` available locally | Phase 0 | [x] git 2.49.0.windows.1 |
| JM1 dataset file `jm1.csv` available (from the supplied `NASA_dataset.zip`); SHA-256 `1ec66eb3568ae8bb4e2709cf0bd28b11db41c7c0ae771325c0952997e35e4dff` | Phase 0 (Gate G0, task 0.9) | [ ] |
| GitHub OAuth App registered for local development | Phase 1 (task 1.2) | [ ] |
| OpenAI API key | Phase 5 | [ ] |
| A domain you own, with DNS access, and hosts that allow custom domains | Start of Phase 6 (latest Phase 7) | [ ] |

### 5.2 Decisions due (all currently **Open**)

The full schedule is in `Phases.md` section 3. The AI must **ask** for each decision before work that depends on it.

| Decision | Due | Status | Human's answer |
| --- | --- | --- | --- |
| Final JM1 feature subset | End of Phase 0 (G0) | Open | |
| Exact metrics library, if any | End of Phase 0 (G0) | Open | |
| Rules for anomalous JM1 rows (`id=1`, `lOCode` > `loc`, `total_Op` = 0) | End of Phase 0 (G0) | Open | |
| Prediction-unit rules (what counts as a function/method; qualifying top-level code) | End of Phase 0 (G0) | Open | |
| **Python runtime and Docker base image** | Phase 0 (task 0.2) | **Decided** | Python 3.12; Docker base image `python:3.12-slim-bookworm`; local `.venv` created with `py -3.12`. Wheels verified 2026-10-10. Recorded in Architecture decision log. |
| PostgreSQL driver (psycopg2-binary vs psycopg[binary]) | Task 0.6 | Open - ask before 0.6 | |
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
| Watch 2 | `unrs-resolver@1.12.2` postinstall was blocked via `eslint-config-next` -> `eslint-import-resolver-typescript`. | `npm run lint` passed (exit 0, no lint diagnostics) despite the blocked postinstall. | Verified |
| Watch 3 | `next dev` regenerates `frontend/AGENTS.md` and `node_modules/next/AGENTS.md` on every run. Do not commit; delete before commits. Notice says read `node_modules/next/dist/docs/` before writing Next code. | Ask the human how to handle before Phase 6. | Open |

**Watch items from the start:**

- Gate G0 may show that JM1 features cannot be computed consistently across Python, JavaScript, and TypeScript. If so, stop and report (see `AGENTS.md` section 3.3).
- The cookie/domain strategy requires an owned domain, which is not in place yet.
- **(Phase 2 - Tree-sitter smoke test)** Immediately after installing the Tree-sitter language packages in Phase 2, run a smoke test that loads each grammar and parses a small sample for Python, JavaScript, TypeScript, and TSX. Grammar versions and the core `tree-sitter` version must be compatible; a mismatch surfaces as a silent parse failure or a C-extension load error, not a pip error.
- **(Task 0.6 - PostgreSQL driver)** The PostgreSQL driver is not yet decided. Ask before starting task 0.6. Options are `psycopg2-binary` (sync, mature) and `psycopg[binary]` (psycopg3, sync + async, newer). A prebuilt binary wheel for Python 3.12 exists for psycopg[binary] (confirmed 2026-10-10).

---

## 7. Document Status and Known Doc Items

| Document | Status |
| --- | --- |
| `PRD.md` | Complete, reviewed 2026-10-09 |
| `Architecture.md` | Complete, reviewed 2026-10-09 |
| `Phases.md` | Complete, reviewed 2026-10-09 |
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