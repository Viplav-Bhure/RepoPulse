# RepoPulse — Product Requirements Document

| | |
|---|---|
| **Author** | Viplav |
| **Status** | Finalized v1.0 — pre-implementation |
| **Project stage** | Idea; nothing built yet |
| **Audience** | Students, the author (as builder), and development teams |

> **How to read this document.** Every requirement here comes from the RepoPulse specification or from a decision explicitly confirmed by the author (see [Decision Log](#17-decision-log)). Anything not yet decided is listed in [Open Decisions](#16-open-decisions) instead of being assumed.

> **Revision note.** The implementation decisions confirmed after review have been incorporated below, while deliberately leaving only true implementation-level choices open.

---

## 1. Overview

### 1.1 Summary

RepoPulse is an AI-powered software engineering intelligence platform that analyzes a developer's GitHub repositories using source-code analysis, Git history, dependency analysis, machine learning, and evidence-grounded AI explanations.

### 1.2 The question it answers

> "How healthy is my codebase, where are its risky areas, what does its structure look like, and why should I care about those areas?"

### 1.3 How it works, at a glance

A user signs in with GitHub. RepoPulse lists only the **public repositories owned by that user**. The user selects one and starts an analysis. RepoPulse then examines the source code, code structure, metrics, dependencies, basic code-quality and security issues, test coverage (when a report is available), Git history, and historical file activity. A **Random Forest** model estimates defect-proneness at the function/method level and aggregates those predictions into a file-level score; an **LLM** explains important findings in plain language. Results appear on a dashboard.

```
Repository Health → Code Metrics → Issues / Findings → ML Defect Risk
      → Dependency Structure → Git History → AI Explanations
```

### 1.4 Resume-ready description

> Built an AI-powered repository intelligence platform that analyzes code quality, dependencies, Git history and defect-proneness using static analysis, Random Forest ML, and LLM-based explanations.

---

## 2. Goals and Non-Goals

### 2.1 Goals

1. Give a developer a clear, evidence-based picture of the health and risk of a repository they own.
2. Combine multiple independent signals (metrics, Git history, static findings, security findings, test coverage, dependencies, ML probability) rather than relying on any single one.
3. Keep deterministic facts (rules, measurements) separate from probabilistic output (ML) and generated text (LLM), and make that separation visible to the user.
4. Demonstrate, as a portfolio project, competence across CS fundamentals (parsing, graphs, databases, networking, auth), AI/ML (supervised learning, LLM integration), full-stack development, and software engineering practice (testing, CI/CD, containerization).
5. Stay deliberately scoped so every retained feature serves the central purpose of **understanding and evaluating a repository**.

### 2.2 Non-Goals — what RepoPulse is NOT

- A general-purpose coding chatbot
- A GitHub replacement
- An enterprise security platform
- A full CI/CD platform
- A pull-request review system
- A complete SonarQube clone
- An automated code-fixing system
- A generic "paste code into ChatGPT" application

### 2.3 Explicitly removed from scope

PR Intelligence · Pull Request page · GitHub webhooks · Vector database · RAG · Repository-wide AI chatbot · Technical Debt engine · Multi-role RBAC · Separate ML server · MLflow · Model registry · Advanced security platform · Dependency CVE platform · Interactive dependency graph

---

## 3. Target Users

**Primary user: a developer who owns public GitHub repositories** and wants to understand the quality, risk, and structure of their own code. RepoPulse is built so that students and small teams can use it on their personal and academic projects.

There is **one application role: `USER`**. There is no Admin, Developer, Manager, Viewer, or Owner role. A user owns their own RepoPulse account and the repositories/analyses associated with it.

---

## 4. Product Principles

| Principle | Meaning |
|---|---|
| **Evidence first** | Findings come from rules and measurements. The LLM only explains supplied evidence; it never originates findings. |
| **Honest uncertainty** | ML output is a probability estimate of *defect-proneness*, never a statement that a bug exists. |
| **Transparency over a single score** | Separate dimensions are shown. No combined "health score" is produced. |
| **Backend-enforced security** | Authorization is checked on the server for every request; hiding UI elements is never relied upon. |
| **Graceful degradation** | If one subsystem fails (e.g., the LLM or coverage data), the rest of the report still works. |
| **Scope discipline** | Support a few languages properly rather than many partially. |

---

## 5. Scope Summary

### 5.1 Core
1. User authentication
2. GitHub integration
3. Own-repository restriction
4. Repository retrieval
5. Source-code parsing
6. Code metrics
7. Basic static analysis
8. Git history analysis
9. Dependency analysis
10. Static dependency graph
11. Random Forest defect prediction
12. Risk summary
13. AI explanation
14. PostgreSQL database
15. Next.js frontend
16. FastAPI backend

### 5.2 Supporting engineering
17. Basic security checks
18. Test coverage analysis (from existing reports only)
19. Analysis history
20. Docker
21. Automated testing
22. CI/CD
23. Input validation
24. Basic logging and error handling

### 5.3 Supported languages (v1)
**Python** and **JavaScript/TypeScript**. Files in other languages are not analyzed (see FR-REPO-6).

---

## 6. User Journey

1. **Landing.** The user sees the product pitch and a **Get Started** button.
2. **Sign in with GitHub.** Authentication and repository access are one step via GitHub OAuth (public-repository scope only).
3. **Repository list.** RepoPulse shows the user's own public repositories (name, primary language, last-updated time) each with an **Analyze** button. There is **no field for entering an arbitrary repository URL**.
4. **Start analysis.** The backend creates an analysis run and executes it as a background task. The frontend polls a status endpoint and shows progress.
5. **Dashboard.** When complete, the user lands on the repository dashboard.
6. **Drill down.** The user opens file-level detail, the Git history page, and the dependencies page.
7. **Explain with AI.** For a selected finding, the user clicks **Explain with AI** and receives a concise explanation.
8. **Re-analyze and compare.** The user runs the analysis again later and sees how metrics changed since the previous run.

---

## 7. Functional Requirements

### 7.1 Authentication and Authorization

| ID | Requirement |
|---|---|
| FR-AUTH-1 | The system SHALL authenticate users exclusively via **GitHub OAuth**; there are no separate email/password accounts. |
| FR-AUTH-2 | The system SHALL request the **minimal OAuth scope** needed to read public repositories. Private repositories are not supported. |
| FR-AUTH-3 | The system SHALL maintain an authenticated session using a PostgreSQL-backed opaque server-side session referenced by a secure HTTP-only cookie. |
| FR-AUTH-4 | The system SHALL have a single role, `USER`. |
| FR-AUTH-5 | Every repository-scoped endpoint (repositories, analyses, files, findings, predictions, explanations) SHALL verify on the backend that the requested resource belongs to the authenticated user, including when a client manually changes an ID in the URL (e.g., `repository_id=17`). |
| FR-AUTH-6 | Unauthorized or non-owned resource requests SHALL be rejected. |
| FR-AUTH-7 | OAuth tokens and other credentials SHALL NOT be written to logs. |

### 7.2 GitHub Integration and Ownership Rule

| ID | Requirement |
|---|---|
| FR-GH-1 | After login, the system SHALL retrieve the user's repositories from the GitHub API. |
| FR-GH-2 | The system SHALL make available for analysis **only** repositories where `repository.owner == authenticated_user.github_username`. |
| FR-GH-3 | Repositories owned by other users or by organizations (e.g., `friend/project3`, `organization/project4` when the user is `viplav`) SHALL NOT be listed and SHALL be rejected if requested directly through the API. |
| FR-GH-4 | The repository list SHALL display repository name, primary language, and last-updated time, with an **Analyze** action. |
| FR-GH-5 | The UI SHALL NOT provide any input for arbitrary repository URLs. |
| FR-GH-6 | GitHub API failures SHALL produce a clear error ("Unable to retrieve repository") without crashing the application. |
| FR-GH-7 | The system SHALL NOT persist the user's GitHub access token. **Proposed mechanism:** the token is held in memory only during the OAuth callback to fetch and store the user's repository list; later GitHub API calls for public data (repository refresh, size pre-check) use a server-side credential that is not tied to any user. |

### 7.3 Repository Retrieval and File Handling

| ID | Requirement |
|---|---|
| FR-REPO-1 | On **Analyze**, the backend SHALL fetch the repository contents and Git information from GitHub. |
| FR-REPO-2 | The system SHALL enforce a **maximum repository size of ~50 MB** and a **maximum of ~1,000 source files** in v1; limits SHALL be configurable. |
| FR-REPO-3 | The system SHALL enforce a maximum analysis duration of 5 minutes; the limit is configurable. |
| FR-REPO-4 | When a limit is exceeded, the system SHALL stop and show: "Repository too large for current analysis limits." |
| FR-REPO-5 | The system SHALL ignore by default: `node_modules/`, `.git` objects, binary files, build artifacts, and large generated files. |
| FR-REPO-6 | The system SHALL analyze only supported-language files (Python, JavaScript, TypeScript). If unsupported files exist, supported files SHALL still be analyzed and the user SHALL be told: "This repository contains unsupported files. Supported files were analyzed." |
| FR-REPO-7 | A corrupted or unreadable repository SHALL fail the run with: "Repository analysis failed." |

### 7.4 Analysis Pipeline

The pipeline is the core of RepoPulse. It executes as a **FastAPI `BackgroundTasks` task**; the frontend **polls a status endpoint**. v1 does **not** use Redis, Celery, Kafka, or a separate worker service.

```
Repository
   ↓  File discovery
   ↓  Language identification
   ↓  Source parsing
   ↓  Metric extraction
   ↓  Static analysis
   ↓  Dependency extraction
   ↓  Git history analysis
   ↓  Test analysis (existing coverage report only)
   ↓  Feature preparation
   ↓  ML prediction
   ↓  Risk aggregation
   ↓  AI explanation (on demand)
   ↓  Dashboard
```

| ID | Requirement |
|---|---|
| FR-PIPE-1 | Starting an analysis SHALL create an `analysis_run` record with status and timestamps and return immediately; execution continues in the background. |
| FR-PIPE-2 | The system SHALL expose a status endpoint reporting at least: queued/running/completed/failed, and the current stage. |
| FR-PIPE-3 | Source parsing, metrics, static analysis, security checks, and persistence are essential stages. Failure of a non-essential stage (Git history, dependency analysis, coverage reading, ML/risk, AI explanation) SHALL NOT fail the whole run; the failure is recorded and shown. |
| FR-PIPE-4 | The system SHALL record the `commit_sha` analyzed in each run. |
| FR-PIPE-5 | The entire repository SHALL NOT be sent to an LLM. Structured information is built first. |

### 7.5 Source-Code Parsing

| ID | Requirement |
|---|---|
| FR-PARSE-1 | The system SHALL parse source code into a syntax structure (AST) rather than treating it as plain text. |
| FR-PARSE-2 | From parsing, the system SHALL identify: functions, classes, imports, conditionals, loops, function calls, and nested structures. |
| FR-PARSE-3 | Parsing SHALL work for Python and JavaScript/TypeScript. **Tree-sitter** is the selected parser. |

*Why it matters:* a naive text view treats `def add(a, b): return a + b` and a deeply nested branching function as equivalent. Structural parsing lets RepoPulse distinguish low from high complexity.

### 7.6 Code Metrics

| ID | Requirement |
|---|---|
| FR-MET-1 | The system SHALL compute, per file: lines of code (LOC), number of functions, number of classes, number of imports, and **cyclomatic complexity**. |
| FR-MET-2 | The system SHALL compute any additional metrics required as ML features (e.g., operator/operand counts, branch-related metrics), subject to the feature-compatibility check in §9. |
| FR-MET-3 | Metrics SHALL be reported as numbers (e.g., `Cyclomatic Complexity = 18`), not vague descriptions. |

### 7.7 Static Analysis (deterministic)

| ID | Requirement |
|---|---|
| FR-STAT-1 | The system SHALL detect via rules/measurable properties: long functions, high complexity, very large files, potential duplicate code, suspicious coding patterns, and unused/poorly structured code. |
| FR-STAT-2 | Each finding SHALL record: type, severity, file, line, and message, and where applicable the measured value and threshold (e.g., `Complexity: 21, Threshold: 10`). |
| FR-STAT-3 | Findings SHALL NOT be generated by the LLM. |
| FR-STAT-4 | Thresholds SHALL be documented and configurable. The defaults are cyclomatic complexity > 10, function length > 50 LOC, file size > 500 LOC, and imports > 20. |

### 7.8 Basic Security Analysis

Deliberately small; **not** a replacement for a security scanner.

| ID | Requirement |
|---|---|
| FR-SEC-1 | The system SHALL detect obvious hard-coded secrets (e.g., assignments such as `API_KEY = "..."`, `PASSWORD = "..."`, `TOKEN = "..."`). |
| FR-SEC-2 | The system SHALL detect selected unsafe patterns, depending on supported languages. |
| FR-SEC-3 | Security findings SHALL be shown with severity (e.g., HIGH Hardcoded Secret, MEDIUM Unsafe Function Usage). |
| FR-SEC-4 | Dependency CVE scanning is out of scope. |

### 7.9 Test Coverage

| ID | Requirement |
|---|---|
| FR-COV-1 | The system SHALL read coverage information **only from an existing standard coverage report** present in the repository. |
| FR-COV-2 | The system SHALL **never execute repository tests** or any repository code. |
| FR-COV-3 | When no report is available, coverage SHALL be displayed as **"unavailable"** and SHALL NOT prevent the rest of the analysis. |
| FR-COV-4 | When available, the system SHALL show repository-level and per-module coverage (e.g., `payments.py — 41%`) and source-file vs. test-file counts. |
| FR-COV-5 | Coverage SHALL be treated as a signal alongside complexity (a complex file with high coverage differs from one with almost none). |

### 7.10 Git History Analysis

| ID | Requirement |
|---|---|
| FR-GIT-1 | For each file the system SHALL compute: commit count, recent commits, lines added, lines removed, number of contributors, and modification frequency. |
| FR-GIT-2 | The system SHALL provide repository-level totals: commits, contributors, files changed. |
| FR-GIT-3 | History SHALL be used as a risk signal (e.g., two files with equal complexity and coverage but 4 vs. 27 commits are not equally risky). |

### 7.11 Dependency Analysis and Static Graph

| ID | Requirement |
|---|---|
| FR-DEP-1 | The system SHALL extract dependencies between files/modules from imports/references. |
| FR-DEP-2 | The system SHALL model dependencies as a directed graph **G = (V, E)**, where V = modules/files and E = dependency relationships. |
| FR-DEP-3 | The system SHALL be able to answer: which files a module imports, which files depend on it, and which modules are common dependency points. |
| FR-DEP-4 | The system SHALL render a **static (non-interactive)** dependency diagram. |
| FR-DEP-5 | The Dependencies page SHALL show totals (modules, links) and a table of modules with dependency counts, so large repositories remain usable even if a single diagram is unreadable. |
| FR-DEP-6 | Advanced graph algorithms are not required for v1; graph construction itself is in scope. |

### 7.12 ML Defect Prediction

| ID | Requirement |
|---|---|
| FR-ML-1 | The system SHALL use **one** model: a **Random Forest Classifier** (binary: defect-prone vs. not). |
| FR-ML-2 | The model SHALL be trained offline on a **single public software-defect dataset** (NASA MDP/PROMISE family), separately from normal user analysis. |
| FR-ML-3 | The trained model SHALL be packaged with the backend (no separate ML server, no model registry, no MLflow). |
| FR-ML-4 | At analysis time, the system SHALL produce features equivalent to the training features (feature compatibility, see §9) and output a defect probability **per function**, aggregated into one stored file-level score. |
| FR-ML-5 | Probability → risk label (e.g., HIGH) thresholds SHALL be chosen, justified, and documented during implementation, not asserted arbitrarily. |
| FR-ML-6 | Wording SHALL be probabilistic: "The model estimates this file as highly defect-prone based on the available software metrics." The UI SHALL NOT say a file "will" contain a bug. When available, show the file-level aggregate score and separately identify the highest-risk function and its lines; do not imply the function probability equals the aggregate file score. |
| FR-ML-7 | The system SHALL store `model_version` for scored predictions; it SHALL be null when `status` is `no_ml_unit` or `ml_failed`. |
| FR-ML-7a | The system SHALL store nullable `riskiest_function_name`, `riskiest_function_start_line`, and `riskiest_function_end_line` fields on each file prediction. These fields identify the highest-probability function/method **among functions/methods only**, regardless of whether a qualifying top-level unit has a higher probability. If there are no functions/methods, the fields are null. If function/method probabilities tie for highest, choose the earliest source start line; if still tied, choose the lexicographically smallest qualified function name. This metadata is explanatory only and SHALL NOT create a function-level persistence table. The UI SHALL label this as the riskiest function, distinct from the aggregate file score. |
| FR-ML-7b | Each file prediction SHALL have a `status` of `scored`, `no_ml_unit`, or `ml_failed`. For `no_ml_unit` and `ml_failed`, `model_version`, `probability`, and `class` SHALL be null and no risk label SHALL be assigned. For `scored`, `model_version`, `probability`, and `class` SHALL be non-null. |
| FR-ML-8 | The rule that aggregates function-level probabilities into the stored file-level score SHALL be chosen, justified, and documented during Phase 4 validation. |

### 7.13 Risk Summary

| ID | Requirement |
|---|---|
| FR-RISK-1 | The system SHALL combine signals into a per-file risk picture: code metrics, Git history, static findings, security findings, test coverage, dependency data, and aggregated ML defect probability. |
| FR-RISK-2 | The system SHALL show *why* a file is risky as a list of contributing factors (e.g., high complexity, low coverage, frequent modification, large size, many dependencies). |
| FR-RISK-3 | The system SHALL NOT produce a single combined health/"everything" score. Dimensions are displayed separately. |

### 7.14 AI Explanation

| ID | Requirement |
|---|---|
| FR-AI-1 | For a selected finding, the user SHALL be able to click **Explain with AI**. |
| FR-AI-2 | The system SHALL send the LLM an **evidence package**: structured facts (file, LOC, complexity, coverage, recent commits, ML probability, findings) **plus the relevant code snippet** for the selected finding. |
| FR-AI-3 | The LLM provider is the **OpenAI API**. The exact model is configurable via environment variables and is not locked by this PRD. |
| FR-AI-4 | The prompt SHALL instruct the model to explain only the supplied evidence and not to invent findings. |
| FR-AI-5 | The explanation SHALL be concise, describe what the facts mean, and suggest practical next steps (e.g., add tests around complex paths, split large functions). |
| FR-AI-6 | The explanation SHALL be stored with the analysis in PostgreSQL. |
| FR-AI-7 | If the OpenAI API fails, the rest of the report SHALL continue to work and the UI SHALL show the explanation as temporarily unavailable. |
| FR-AI-8 | No vector database, embeddings, RAG, or reranking SHALL be used. |

### 7.15 Dashboard and Pages

**Repository dashboard** — repository name, last-analyzed time, and independent scorecards:

| Dimension | Source |
|---|---|
| Defect risk | ML output and associated risk signals; scored-file risk counts plus a separate **Not scored** count |
| Security findings | Count/severity summary |
| Test coverage | Direct measurement from an existing report, or "unavailable" |
| Complexity / code-quality measures | Selected metrics (shown separately, not merged into one score) |

Also on the dashboard: **Top Findings** (e.g., payments.py — High Complexity) and a **Dependency Structure** preview.

| ID | Requirement |
|---|---|
| FR-UI-1 | The dashboard SHALL display the dimensions above independently. ML summaries SHALL exclude null probabilities from scored-file and risk-label counts and show a separate **Not scored** count. |
| FR-UI-2 | **File-level page:** the user SHALL be able to drill from the repository to a file and see LOC, functions, classes, complexity, coverage, dependency count, recent commits, defect probability or **Not scored** with its status specific reason, the risk label or **Not scored**, and findings grouped by severity. When a function/method prediction exists, show the riskiest function name and line range separately from the aggregate file score; label both clearly so a high function probability is not mistaken for the file score. Include an **Explain with AI** action. |
| FR-UI-3 | **Git history page:** commits, contributors, files changed, and a commits-over-time chart. |
| FR-UI-4 | **Dependencies page:** totals, static graph, and a module/dependency-count table. |
| FR-UI-5 | The UI SHALL show per-stage status when some stages fail (e.g., Code analysis ✓, Git analysis ✓, ML analysis ✓, AI explanation ✗ temporarily unavailable). |

### 7.16 Analysis History

| ID | Requirement |
|---|---|
| FR-HIST-1 | A repository SHALL be analyzable multiple times; every run is stored (not only the latest). |
| FR-HIST-2 | The user SHALL be able to compare the current run with the previous one, e.g., coverage `58% → 64%`, high findings `12 → 8`, average complexity `11.4 → 10.1`. |
| FR-HIST-3 | The system SHALL keep the latest 10 completed analysis runs per repository and delete older completed runs together with their dependent data. Failed runs do not count toward the 10; their retention is an open decision. |

### 7.17 Input Validation, Logging, and Error Handling

| ID | Requirement |
|---|---|
| FR-ENG-1 | The backend SHALL validate all request inputs (FastAPI request validation). |
| FR-ENG-2 | The backend SHALL log meaningful events: user authenticated, analysis started/completed/failed, ML prediction generated, AI explanation requested. |
| FR-ENG-3 | Logs SHALL NOT contain sensitive credentials or tokens. |
| FR-ENG-4 | Expected failures (GitHub failure, unsupported language, corrupted repo, AI API failure, size limit exceeded) SHALL produce clear user-facing messages and SHALL NOT crash the application. |

---

## 8. Architecture

### 8.1 Components

- **Frontend:** Next.js + TypeScript + Tailwind CSS + shadcn/ui + Recharts
- **Backend:** FastAPI — a single application, modularized (not microservices), including the analysis and ML layers; lightweight FastAPI `BackgroundTasks` are used for analysis execution
- **Database:** PostgreSQL
- **External services:** GitHub (OAuth + API), OpenAI API

### 8.2 Suggested backend module layout

```
backend/
├── auth/
├── github/
├── repositories/
├── analyzer/
├── git/
├── dependencies/
├── security/
├── ml/
├── ai/
├── database/
└── api/
```

### 8.3 Environments

**Development — Docker Compose**
```
┌──────────────────────────────┐
│       Docker Compose         │
│                              │
│  Next.js                     │
│  FastAPI                     │
│  PostgreSQL                  │
└──────────────────────────────┘
```

**Production — live on a free/low-cost cloud host**
```
                 GitHub
                    │
                    ↓
            RepoPulse Web App
                    │
             ┌──────┴──────┐
             ↓             ↓
          Next.js        FastAPI
                           │
                ┌──────────┼──────────┐
                ↓          ↓          ↓
           PostgreSQL   GitHub API   OpenAI API
```

Docker Compose remains the local development environment so deployment does not dictate how the project is built. The LLM is an external API, not a container. v1 intentionally avoids Redis, Celery, Kafka, separate worker services, vector databases, and other infrastructure not required by the core product.

### 8.4 End-to-end data flow

```
GitHub → Authentication → Next.js UI → HTTPS → FastAPI
FastAPI → PostgreSQL / Repository Analyzer / Git Analyzer
Repository Analyzer → Parser → Metrics → Dependencies → Static Graph
Parser + Metrics → Static Analysis → Security + Testing
→ Feature Set → Random Forest → Defect Probability → Risk Summary
→ Evidence Package → OpenAI API → AI Explanation
→ PostgreSQL storage → Dashboard
```

### 8.5 Six-layer mental model

| Layer | Question | Components |
|---|---|---|
| 1. Identity | Who is the user? | GitHub OAuth, session |
| 2. Repository | What code does the user own? | GitHub integration, ownership rule |
| 3. Understanding | What is inside that code? | Parser, metrics, dependencies, Git history, tests, security |
| 4. Intelligence | What looks risky? | Random Forest |
| 5. Explanation | Why does it look risky? | LLM |
| 6. Presentation | What does the developer see? | Dashboard, graphs, findings, history |

---

## 9. Machine Learning Specification

### 9.1 Problem definition
Binary classification: estimate **defect-proneness** from a compatible subset of software metrics. In the JM1 training dataset, each **module row corresponds to a function/method**. In RepoPulse, a repository **file** is the aggregate container: RepoPulse computes compatible features **per function/method**, predicts each function/method in memory, and **aggregates those function probabilities into one stored file-level score**. The aggregation rule (candidates: mean, top-3 mean, maximum) is chosen during Phase 4 validation. Code outside any function/method is excluded from function-level ML unless it contains qualifying top-level control flow (`if`, `for`, `while`, `try`, `switch`) or a call expression outside imports, decorators, and exports; in that case it is treated as a module-level unit and predicted separately, with its probability included in the file aggregation. Constant assignments, type declarations, and docstrings alone do not qualify. No function-level model data is stored. It does not predict arbitrary future failures.

### 9.2 Training data
- A **single** public defect dataset from the NASA MDP/PROMISE family.
- **JM1 is the selected training dataset for v1.** The supplied PROMISE/NASA JM1 CSV contains 10,885 module instances, 21 metric inputs plus the `defects` label, and is used as the single offline training dataset. Because JM1 is a C dataset while RepoPulse analyzes Python, JavaScript, and TypeScript, only features whose definitions can be reproduced consistently enough across all three supported languages will be retained for serving. The final compatible feature subset is recorded in `feature_schema.json`. The project copy is `ml/data/jm1.csv` (SHA-256 `1ec66eb3568ae8bb4e2709cf0bd28b11db41c7c0ae771325c0952997e35e4dff`). Inspection of the supplied file found 10,885 rows, with 8,779 non-defective and 2,106 defective instances; five rows contain `?` in five metric columns and are dropped before training. Row IDs are unique, but excluding `id` the file contains duplicated and conflicting instances (counts after removing the five `?` rows): 1,973 rows duplicate another row on metrics and label, 2,061 duplicate on metrics alone, and 88 metric vectors appear with both labels. The preprocessing pipeline deduplicates on the 21 metric columns and removes metric vectors with conflicting labels **before** the train/test split, leaving 8,731 rows (21.9% defective, versus 19.3% in the raw file). A few anomalous rows (row `id=1` has fractional counts, one row has `lOCode` greater than `loc`, and 1,332 rows have `total_Op` = 0) are handled by explicit rules recorded during the Phase 0 check. The dataset's Kaggle listing reports its license as **unknown**; RepoPulse therefore makes no claim that the dataset is freely redistributable and preserves that provenance/licensing limitation in project documentation.

### 9.3 Training pipeline (offline, separate from user analysis)

```
Dataset → Cleaning → Feature selection → Train/Test split
        → Random Forest → Evaluation → Save trained model
```

Suggested layout:
```
training_data/dataset.csv
ml/preprocess.py
ml/train.py
ml/model.pkl
```

### 9.4 Feature compatibility (critical)
The features RepoPulse computes from a user's repository must be equivalent to the features the model was trained on. Training on one column set and feeding unrelated metrics in production is invalid. The compatibility check (per language) is a prerequisite task before model training is finalized.

### 9.5 Evaluation requirements
- Report **F1, ROC-AUC, and PR-AUC** (with precision and recall for the defect class), not accuracy alone. Preliminary experiments on deduplicated JM1 gave ROC-AUC near 0.72 and PR-AUC near 0.45 (baseline 0.22) for Random Forest, gradient boosting, and logistic regression alike, so targets should be set realistically.
- Document how **class imbalance** is handled.
- Document the train/test split.
- Present feature importance (a reason Random Forest was chosen).
- Document the chosen probability thresholds for risk labels and their justification.

### 9.6 Why a single model
The goal is to integrate an ML model into a real software system and use its output meaningfully — not to run an algorithm comparison (no Logistic Regression vs. KNN vs. SVM vs. XGBoost bake-off).

### 9.7 Known limitation (must be stated honestly)
The model is trained on a public dataset while user repositories can be very different from it. Its probability is an estimate based on relationships learned from that data; it is **not** a universally calibrated probability of a future bug. The product claim is deliberately limited to **defect-proneness based on software metrics**.

---

## 10. Data Model

The following relational schema is taken from the specification and is intended as a starting point; the final schema is decided during implementation.

```
users            id, github_user_id, username, email, created_at
repositories     id, user_id, github_repo_id, name, owner, default_branch, created_at
analysis_runs    id, repository_id, commit_sha, status, started_at, completed_at
files            id, analysis_id, path, language, loc, complexity, coverage
findings         id, file_id, type, severity, line, message
predictions      id, file_id, status, model_version NULL, probability NULL, class NULL, riskiest_function_name NULL, riskiest_function_start_line NULL, riskiest_function_end_line NULL
```

A prediction row exists for each analyzed file. `status` is `scored`, `no_ml_unit`, or `ml_failed`, distinguishing a file with no qualifying ML unit from an ML-stage failure. For `no_ml_unit` and `ml_failed`, `model_version`, `probability`, and `class` are null; the UI displays **Not scored** with the reason available from `status`, and no risk label is assigned. For `scored`, `model_version` and `probability` are non-null. The riskiest-function fields are independently nullable and identify the highest-probability function/method among functions/methods only, even when a top-level unit has a higher probability.

**Entities required by this PRD that are not yet in the schema above** (to be designed): per-file Git history metrics, dependency edges between files, stored AI explanations, and fields for functions/classes/imports counts and other ML features.

**Relationship chain:** User → Repository → Analysis → File → Finding / Prediction. PostgreSQL is used because the data is naturally relational (e.g., "show all high-risk files from the latest analysis of repository X"). Indexes to be chosen during implementation.

---

## 11. API (illustrative)

Final API design follows the implementation. Examples from the spec:

```
GET   /repositories
POST  /repositories/{id}/analyze
GET   /repositories/{id}/analysis
GET   /repositories/{id}/files
GET   /files/{id}/findings
POST  /findings/{id}/explain
```

Notes:
- Authentication is via **GitHub OAuth**, so the spec's example `POST /auth/login` is replaced by an OAuth login/callback flow (endpoint design pending).
- A **status endpoint** for polling analysis progress is required (FR-PIPE-2).
- Every endpoint above enforces the ownership check from FR-AUTH-5.

---

## 12. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Security** | Backend-enforced authorization; minimal OAuth scope; no credentials in logs; no execution of repository code or tests; input validation. |
| **Reliability** | Graceful degradation when GitHub, coverage data, or the OpenAI API fail; clear error messages. |
| **Performance** | Bounded by repository limits (~50 MB, ~1,000 source files) and a maximum analysis duration of 5 minutes (configurable); analysis runs in the background and never blocks the request. |
| **Maintainability** | Modular backend; automated tests for core logic; CI on every push. |
| **Portability** | Docker Compose for local development; same codebase deployed to a live host. |
| **Observability** | Structured logging of key lifecycle events. |
| **Honesty of output** | ML outputs worded probabilistically; ML, deterministic findings, and AI text are visibly distinct. |

---

## 13. Testing and CI/CD

### 13.1 Test types
| Type | Examples |
|---|---|
| Unit | `test_complexity_calculation`, `test_dependency_extraction`, `test_git_metric_extraction`, `test_risk_prediction` |
| Backend | `test_login`, `test_repository_access`, `test_analysis_endpoint` |
| Integration | FastAPI ↔ PostgreSQL |
| Frontend / E2E | Login → select repository → analyze → view dashboard |

Volume need not be large; the goal is that important logic is not untested. Security-critical tests should include: a user attempting to access another user's repository/analysis by changing IDs, and a non-owned repository being rejected.

### 13.2 CI/CD pipeline (GitHub Actions)
```
Push → Install dependencies → Lint → Unit tests → Integration tests → Build → Docker image
```

---

## 14. Success Criteria

**Functional (v1 is done when):**
1. A user can sign in with GitHub and see only their own public repositories.
2. Requests for non-owned repositories are rejected by the backend.
3. A user can analyze a supported repository within the size limits and see the dashboard, file-level pages, Git history page, and dependency page.
4. Coverage appears when a standard report exists and shows "unavailable" otherwise, without breaking the analysis.
5. Defect probabilities are produced by the trained Random Forest using compatible features.
6. **Explain with AI** returns an explanation grounded in supplied evidence; if OpenAI fails, the rest of the report is unaffected.
7. Repeated analyses are stored and a previous-vs-current comparison is shown.
8. The app runs locally via Docker Compose and is deployed live.
9. CI runs lint, tests, and build on every push.

**ML (targets TBD):** F1 and ROC-AUC reported with documented split and imbalance handling. Numeric targets are an Open Decision.

---

## 15. Risks and Considerations

| Risk | Note |
|---|---|
| Feature mismatch between training data and extracted features | Mitigated by the per-language feature-compatibility check before locking the dataset (§9.2, §9.4). |
| Model generalization to real-world repositories | Acknowledged limitation (§9.7); claims are constrained. |
| Unit mismatch: JM1 rows are functions, files are much larger | Mitigated by per-function prediction aggregated to a file score (§9.1) and a feature-range sanity check on real repositories. |
| Duplicated and conflicting JM1 instances inflate evaluation scores | Mitigated by deduplicating on metrics and removing conflicting vectors before the split (§9.2). |
| Same-parent-domain hosting needs an owned domain | Requires a domain, DNS control, and hosting providers that allow custom domains on the chosen plans; settle before Phase 6. |
| Free/low-cost hosting limits (memory, CPU, request/idle behavior) | Background analysis runs inside the FastAPI process; host limits could constrain analysis duration or reliability. Confirm against the chosen host. |
| Large repositories | Mitigated by hard size/file/duration limits. |
| Scope creep | Mitigated by the explicit non-goals and removed-scope lists. |
| Coverage unavailable for many repos | Many repositories may not commit a coverage report; the UI must make "unavailable" a normal, non-error state. |
| LLM hallucination | Mitigated by evidence-only input and prompt instructions; the LLM never creates findings. |

---

## 16. Open Decisions

Only implementation details that were not resolved by the current decisions remain open. Architecture §43 is the authoritative implementation-level list.

| Area | Remaining decision |
|---|---|
| Final JM1 feature subset | Which JM1 metrics survive the cross-language compatibility rule for Python, JavaScript, and TypeScript |
| Coverage report precedence | Which report wins if multiple supported coverage formats are present |
| Risk-label thresholds | Exact LOW/MEDIUM/HIGH thresholds after model evaluation |
| ML success targets | Pre-committed F1 and ROC-AUC targets |
| Dependency-graph layout | Exact coordinate/layout library or algorithm for the frontend static SVG |
| Large-graph grouping threshold | Node count above which the graph is grouped by directory |
| OpenAI model | Exact model name in production configuration |
| AI snippet cap | Maximum code-snippet size sent to OpenAI |
| Hosting providers | Exact frontend and backend providers |
| Final database indexes | Additional indexes based on observed query patterns |
| Deployment migration strategy | Manual vs automatic database migrations during deployment |
| Own-code test coverage target | Final coverage target for RepoPulse itself |
| Function-to-file aggregation rule | Mean, top-3 mean, or maximum of function probabilities; chosen in Phase 4 validation |
| GitHub API access after login | Proposed: list repositories during the OAuth callback and use a server-side public-data credential for later calls; to be confirmed |
| Failed-run retention | Whether and how failed runs are pruned (proposal: keep only the most recent failed run per repository) |
| Test-file treatment | Whether default summaries exclude test files (proposed) and whether ML scores are shown for them |

Decisions already confirmed—JM1, per-function prediction aggregated to a file-level score, essential-stage policy, RepoPulse-owned Tree-sitter metric extraction without a production metrics library, PostgreSQL-backed sessions, no OAuth-token persistence, same-parent-domain production hosts, unparseable-file policy, concurrency policy, coverage formats, alias policy, static-analysis scope, frontend/E2E tooling, repository display policy, test-file handling, retention, and Phase 7 portfolio output—are not open decisions.

## 17. Decision Log

Decisions confirmed by the author while preparing this PRD:

| Topic | Decision |
|---|---|
| PRD audience | Students, the author, and dev teams |
| PRD depth | Between Standard and Full spec (suited to a resume project) |
| Project stage | Just an idea; nothing built |
| Login | **GitHub OAuth App only** (login and public-repository access in one step) |
| Languages (v1) | **Python + JavaScript/TypeScript** |
| Test coverage | Read an existing standard coverage report if present; **never execute repository tests**; show "unavailable" otherwise and continue |
| Analysis execution | **FastAPI background task**; frontend polls a status endpoint |
| LLM provider | **OpenAI API** |
| Training dataset | **JM1 selected**; final compatible feature subset determined by the Phase 0 compatibility check |
| Repository access | **Public repositories only** (minimal OAuth scope) |
| AI input | **Structured facts + the relevant code snippet** for the selected finding |
| Dashboard scoring | **Separate dimensions only**; no combined health score |
| Environments | Docker Compose for development; **live deployment on a free/low-cost cloud host** for production |
| Repository limits (v1) | **~50 MB and ~1,000 source files** |
| Timeline | **No fixed deadline**; phased plan without dates |

---

### 17.1 Confirmed implementation decisions

| # | Topic | Confirmed decision |
|---|---|---|
| 1 | GitHub authentication | GitHub OAuth App |
| 2 | Repository retrieval | Temporary Git clone |
| 3 | Analyzed branch | Default branch only |
| 4 | Forks | User-owned forks are included |
| 5 | Analysis duration | 5-minute maximum, configurable |
| 6 | Static-analysis defaults | Complexity > 10, function > 50 LOC, file > 500 LOC, imports > 20 |
| 7 | ML dataset | **JM1 selected**; retain only a compatible feature subset for Python/JavaScript/TypeScript |
| 8 | OpenAI model | Exact model remains configurable through environment variables |
| 9 | Frontend stack | Next.js + TypeScript + Tailwind CSS + shadcn/ui + Recharts |
| 10 | Analysis execution | FastAPI `BackgroundTasks` + polling; no Redis/Celery worker infrastructure |
| 11 | Dependency graph | Backend returns `{nodes, edges}`; frontend renders a static SVG; exact layout algorithm remains open |
| 12 | ML granularity | Function/method predictions computed in memory and aggregated into one stored file-level score; qualifying top-level executable code can contribute a module-level unit; no function-level table |
| 13 | Riskiest-function metadata | Store nullable function name and start/end lines on the file prediction; select the highest-probability function/method among functions/methods only, ties use earliest start line then lexicographically smallest qualified name; top-level code does not suppress function metadata |
| 14 | Unscored prediction status | Store status `scored`, `no_ml_unit`, or `ml_failed`; unscored rows have null model_version/probability/class and no risk label |
| 15 | Metric implementation | RepoPulse owns one Tree-sitter extractor for Python, JavaScript, and TypeScript; no production metrics library |
| 16 | Session mechanism | PostgreSQL-backed opaque server-side sessions with a secure HTTP-only cookie |
| 17 | OAuth token storage | Do not persist GitHub access tokens |
| 18 | Production cookie/domain strategy | Same parent/registrable domain for frontend and backend hosts; exact providers remain open |
| 19 | Unparseable files | Minor parse errors continue; unusable files are skipped and recorded as warnings |
| 20 | Analysis concurrency | One active analysis per repository plus a small global concurrency cap |
| 21 | Coverage | Cobertura XML + lcov + Istanbul JSON |
| 22 | JS/TS path aliases | Resolve aliases only when deterministic; otherwise treat unresolved imports as external |
| 23 | Static analysis extras | Four confirmed threshold rules plus lightweight duplicate-code detection |
| 24 | Frontend/E2E tooling | Vitest + Testing Library + Playwright |
| 25 | Archived/empty repositories | Show them with an explanatory status; disable Analyze when unsupported |
| 26 | Test files | Analyze and report them, while clearly distinguishing source vs test files |
| 27 | Analysis retention | Keep the latest 10 completed analyses per repository |
| 28 | Phase 7 portfolio output | Live deployment + 2–3 minute demo + self-analysis |
| 29 | JM1 preprocessing | Drop the five rows containing `?`; deduplicate on the metric columns (excluding `id`) and remove conflicting-label vectors before splitting; never coerce `?` to zero or impute |
| 30 | JM1 repository copy | Commit the supplied `jm1.csv` under `ml/data/`; record provenance, checksum, and the Kaggle-reported unknown license status; make no unrestricted redistribution claim |
| 31 | Essential stages | Source parsing, metrics, static analysis, security checks, and persistence are essential; Git history, dependencies, coverage, ML/risk, and AI explanation are non-essential enrichment stages |
| 32 | PostgreSQL driver and URL scheme | psycopg 3 (`psycopg[binary]`), SQLAlchemy URL scheme `postgresql+psycopg://`. PostgreSQL major version 17 (development); production host to match. |
| 33 | JM1 anomalous rows | Drop `id=1` (the only row with `lOCode` > `loc`) and all 1,332 rows with `total_Op` = 0 and `loc` >= 1; preprocessing order: drop the five `?` rows, drop `id=1`, drop the zero-operator group, remove conflicting-label metric vectors and deduplicate, then split. |
| 34 | JM1 metric method | No metrics library in production. RepoPulse owns one Tree-sitter extractor for Python, JavaScript, and TypeScript. Radon, Lizard, and typhonjs-escomplex may be used only as G0 cross-checks, never as production sources. Revisit only if the 0.9.9 prototype cannot meet the compatibility rule (0.9.7). |
| 35 | JM1 compatibility rule | A feature enters the serving schema only if its definition is verified by the data check or fixed by an approved convention; it can be implemented consistently across Python, JavaScript, and TypeScript with every approximation justified in the matrix (consistently, not identically); and its serving range stays within a stable range of JM1 (0.9.9). Derived fields use only admitted features. Record before model results. |
| 36 | Prediction-unit rules | The same rules apply to all three languages. Units are outermost function-like nodes with block/statement bodies; nested functions, closures, and callbacks belong to their containing unit. Python lambdas and expression-bodied arrows are not units; TypeScript overload signatures and bodyless abstract/declare functions are not units. Qualifying module-level code is defined by control flow or a call expression outside imports, decorators, and exports; unit subtrees are excluded. See `ml/README.md` 0.9.8 for the complete rules and fixture cases. |

## 18. Delivery Phases (no dates)

A suggested build order. Phases are sequential in dependency, not scheduled.

**Phase 0 — Foundations**
- Repository setup, Docker Compose (Next.js, FastAPI, PostgreSQL), CI skeleton.
- *ML prerequisite:* verify which JM1 metrics can be reproduced consistently across Python/JavaScript/TypeScript; finalize the compatible feature subset and feature definitions.

**Phase 1 — Identity and repositories**
- GitHub OAuth, session, user record.
- Public-repository listing with the ownership rule enforced on the backend (and tests for ID tampering).

**Phase 2 — Analysis core**
- Background-task analysis run with status polling; repository retrieval with size/file limits and ignore rules.
- Parsing, metrics, static analysis, basic security checks.

**Phase 3 — Context signals**
- Git history analysis, dependency extraction and static graph, coverage report reading.

**Phase 4 — ML**
- Training pipeline, evaluation (F1, ROC-AUC, imbalance handling), model packaged into the backend, prediction and risk summary.

**Phase 5 — AI explanation**
- Evidence package, OpenAI integration, graceful failure handling, stored explanations.

**Phase 6 — Dashboard and history**
- Dashboard, file-level, Git history, and dependencies pages; analysis history and comparison.

**Phase 7 — Hardening and release**
- Error-handling and logging pass, full test suite, CI/CD completion, live deployment, documentation (README, architecture diagram, ML limitations).

---

## 19. Interview-Readiness Notes

The scope is designed so each area can be defended in depth:

- **Frontend/Backend:** why Next.js and FastAPI; route structure; request validation.
- **Database:** why PostgreSQL; relationships; indexes.
- **Auth:** how repository access is protected; what happens if IDs are changed manually.
- **GitHub:** how repositories are retrieved; how the ownership rule is enforced.
- **Parsing:** what an AST is; why parse instead of regular expressions.
- **Graph:** nodes, edges, and how dependencies are generated.
- **ML:** why Random Forest; target variable; features; split; class imbalance; why F1/ROC-AUC over accuracy.
- **AI:** why an LLM after the ML model; how invention of findings is prevented.
- **DevOps/Testing:** why Docker; what CI does; what is unit-tested.

---

## 20. Glossary

| Term | Meaning |
|---|---|
| **AST** | Abstract Syntax Tree — a structural representation of parsed source code. |
| **Cyclomatic complexity** | Number of independent decision paths through code. |
| **Defect-proneness** | Model-estimated likelihood that a function/method resembles defective JM1 module rows; function probabilities are aggregated into a file-level score. It is not a guarantee of a bug. |
| **Not scored** | A file prediction with status `no_ml_unit` or `ml_failed`; probability, class, and model_version are null, no risk label is assigned, and the UI shows “Not scored” plus the status-specific reason. |
| **Evidence package** | Structured facts (and the relevant snippet) sent to the LLM for explanation. |
| **PROMISE / NASA MDP** | Public software-engineering datasets of module metrics with defect labels. |
| **Static analysis** | Rule-based inspection of code without running it. |
