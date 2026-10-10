# RepoPulse - Progress

> **Living status file.** The AI builder updates this file **after every task and at the end of every session**. It is the one file the AI edits on its own. `PRD.md`, `Architecture.md`, `Phases.md`, and `AGENTS.md` stay stable.

| | |
| --- | --- |
| **Last updated** | 2026-10-10 |
| **Updated by** | AI builder â€” task 0.2 complete |
| **Placement** | Repository root, next to `AGENTS.md` |

---

## 1. Snapshot

| | |
| --- | --- |
| **Overall status** | **In progress.** Phase 0 started. Tasks 0.1 and 0.2 complete. |
| **Current phase** | Phase 0 â€” Foundations (**in progress**) |
| **Next task** | **0.3** â€” Ruff linter/formatter, pytest, one passing smoke test for GET /health (see `Phases.md`, Phase 0) |
| **Blocked?** | No. See section 5 for decisions and setup the human must provide first. |
| **Last human approval** | Planning documents reviewed on 2026-10-09 |

---

## 2. Phase Tracker

**Status values:** `Not started` Â· `In progress` Â· `Blocked` Â· `Awaiting approval` Â· `Done`.
A phase is `Done` only after the human approves its exit criteria (see `AGENTS.md` Â§3.2).

| Phase | Name | Status | Started | Finished | Tag |
| --- | --- | --- | --- | --- | --- |
| 0 | Foundations (includes **Gate G0**: ML feasibility) | In progress | 2026-10-10 | â€” | â€” |
| 1 | Identity and Repositories | Not started | â€” | â€” | `v0.1` |
| 2 | Analysis Core | Not started | â€” | â€” | `v0.2` |
| 3 | Repository Context | Not started | â€” | â€” | `v0.3` |
| 4 | ML | Not started | â€” | â€” | `v0.4` |
| 5 | AI Explanation | Not started | â€” | â€” | `v0.5` |
| 6 | Frontend | Not started | â€” | â€” | `v0.6` |
| 7 | Hardening and Release | Not started | â€” | â€” | `v1.0` |

**Gate G0** (end of Phase 0): `Not passed`. Phase 2 metric work and all of Phase 4 must not start until it is passed.

---

## 3. Current Task

| | |
| --- | --- |
| **Task ID** | 0.3 |
| **Title** | Ruff linter/formatter, pytest, one passing smoke test for GET /health |
| **Status** | Not started |
| **Plan** | *(AI writes plan before starting)* |
| **Notes / problems** | â€” |

---

## 4. Completed Tasks

Record each finished task by **ID only** (the task text lives in `Phases.md`; do not copy it here).

| Task ID | Date | PR / commit | Tests run and result | Notes |
|---|---|---|---|---|
| 0.1 | 2026-10-10 | awaiting human commit | None required (infrastructure only) | Done; `.gitignore`, `.env.example`, `README.md`, `frontend/`, `backend/`, `ml/` `.gitkeep` files created. Ignore rules verified with `git check-ignore`. |
| 0.2 | 2026-10-10 | awaiting human commit | `GET /health` â†’ `{"status":"ok"}` verified via `Invoke-WebRequest` (200 OK) | `backend/requirements.txt`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/.env` created. `.env.example` SESSION_SECRET_KEY â†’ SESSION_SECRET corrected. `.venv` created with `py -3.12`. |

---

## 5. What the Human Must Provide

### 5.1 Setup checklist (before or during Phase 0)

| Item | Needed by | Done? |
| --- | --- | --- |
| GitHub repository created for the monorepo | Phase 0 (task 0.1) | âœ… https://github.com/Viplav-Bhure/RepoPulse |
| Docker and Docker Compose installed and working | Phase 0 (task 0.7) | âœ… Docker 29.8.1, Compose v5.5.1 |
| Python and Node.js toolchains installed | Phase 0 (tasks 0.2â€“0.5) | âœ… Python 3.12 (via py launcher) + 3.13.14, Node.js 24.21.0 |
| `git` available locally | Phase 0 | âœ… git 2.49.0.windows.1 |
| JM1 dataset file `jm1.csv` available (from the supplied `NASA_dataset.zip`); SHA-256 `1ec66eb3568ae8bb4e2709cf0bd28b11db41c7c0ae771325c0952997e35e4dff` | Phase 0 (Gate G0, task 0.9) | â˜ |
| GitHub OAuth App registered for local development | Phase 1 (task 1.2) | â˜ |
| OpenAI API key | Phase 5 | â˜ |
| A domain you own, with DNS access, and hosts that allow custom domains | Start of Phase 6 (latest Phase 7) | â˜ |

### 5.2 Decisions due (all currently **Open**)

The full schedule is in `Phases.md` Â§3. The AI must **ask** for each decision before work that depends on it.

| Decision | Due | Status | Human's answer |
| --- | --- | --- | --- |
| Final JM1 feature subset | End of Phase 0 (G0) | Open | |
| Exact metrics library, if any | End of Phase 0 (G0) | Open | |
| Rules for anomalous JM1 rows (`id=1`, `lOCode` > `loc`, `total_Op` = 0) | End of Phase 0 (G0) | Open | |
| Prediction-unit rules (what counts as a function/method; qualifying top-level code) | End of Phase 0 (G0) | Open | |
| **Python runtime and Docker base image** | Phase 0 (task 0.2) | **Decided** | Python 3.12; Docker base image `python:3.12-slim-bookworm`; local `.venv` created with `py -3.12`. Wheels verified 2026-10-10. Recorded in Architecture decision log. |
| PostgreSQL driver (psycopg2-binary vs psycopg[binary]) | Task 0.6 | Open â€” ask before 0.6 | |
| GitHub API access after login (proposed: list at callback plus a server-side public-data credential) | Start of Phase 1 | Open (proposal awaiting confirmation) | |
| Test-file handling in summaries and ML | Phase 2 / Phase 4 | Open (proposal awaiting confirmation) | |
| Failed-run retention | Phase 2 | Open (proposal awaiting confirmation) | |

Later decisions (aggregation rule, risk thresholds, ML targets, graph layout, OpenAI model and snippet cap, hosting, indexes, and others) are tracked in `Phases.md` Â§3. Move them into this table when their phase approaches.

---

## 6. Blockers and Active Risks

| # | Item | Impact | Status |
|---|---|---|---|
| â€” | No blockers yet | â€” | â€” |

**Watch items from the start:**

- Gate G0 may show that JM1 features cannot be computed consistently across Python, JavaScript, and TypeScript. If so, stop and report (see `AGENTS.md` Â§3.3).
- The cookie/domain strategy requires an owned domain, which is not in place yet.
- **(Phase 2 â€” Tree-sitter smoke test)** Immediately after installing the Tree-sitter language packages in Phase 2, run a smoke test that loads each grammar and parses a small sample for Python, JavaScript, TypeScript, and TSX. Grammar versions and the core `tree-sitter` version must be compatible; a mismatch surfaces as a silent parse failure or a C-extension load error, not a pip error.
- **(Task 0.6 â€” PostgreSQL driver)** The PostgreSQL driver is not yet decided. Ask before starting task 0.6. Options are `psycopg2-binary` (sync, mature) and `psycopg[binary]` (psycopg3, sync + async, newer). A prebuilt binary wheel for Python 3.12 exists for psycopg[binary] (confirmed 2026-10-10).

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

1. `PRD.md` FR-UI-2 says "Not scored when no ML unit exists" but should also cover ML failure ("Not scored with its status-specific reason").
2. `Phases.md` (4.16, 4.18, exit criteria) report one combined **Not scored** count; splitting it into "no code to score" and "ML unavailable" is optional.

---

## 8. Session Log

Newest first. One entry per session. Keep entries short.

| Date | Session summary | Tasks touched | Open questions raised |
|---|---|---|---|
| 2026-10-10 | Task 0.2 complete. Python 3.12 decision recorded in Architecture and Progress.md. Created `backend/requirements.txt`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/.env`. Fixed `SESSION_SECRET_KEY` â†’ `SESSION_SECRET` in `.env.example`. Venv created with `py -3.12`. `/health` verified 200 OK. | 0.2 | Doc issue: `.env.example` had `SESSION_SECRET_KEY`; corrected to `SESSION_SECRET` (Architecture Â§41). PostgreSQL driver still open (ask before task 0.6). |
| 2026-10-10 | Task 0.1 complete (awaiting human commit). Created `.gitignore`, `.env.example`, `README.md` stub, `frontend/`, `backend/`, `ml/` `.gitkeep` files. Verified ignore rules with `git check-ignore`. docs/ confirmed untouched. | 0.1 | None |
| 2026-10-09 | Planning complete: `PRD.md`, `Architecture.md`, `Phases.md`, `AGENTS.md`, and this file created and reviewed. **No code written. Nothing started.** | None | See section 5.2 |

---

## 9. How to Update This File (rules for the AI)

1. **After every task:** add a row to section 4, update section 3 to the next task, and update section 1 if the phase or status changed.
2. **At phase boundaries:** set the phase to `Awaiting approval` and list the exit-criteria evidence. Change it to `Done` (and fill the dates and tag) only after the human approves.
3. **When a decision is made:** record the human's answer in section 5.2, then follow `AGENTS.md` Â§9.4 to update the decision logs in the documents.
4. **At the end of every session:** add a session-log row and make sure the snapshot is true.
5. **Never delete history.** Add rows; do not rewrite old ones. Fix mistakes by adding a correcting note.
6. **Keep it short.** Reference task IDs and requirement IDs; do not copy text from the other documents.
7. **If this file disagrees with the code or repository, the code wins.** Correct this file and mention it in your report.
8. **Never mark something done that you did not run and verify.**
