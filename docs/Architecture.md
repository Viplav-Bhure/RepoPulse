# RepoPulse — Architecture

| | |
|---|---|
| **Author** | Viplav |
| **Status** | Finalized v1.0 — pre-implementation |
| **Companion document** | `PRD.md` |
| **Purpose** | Describe how RepoPulse is structured, how data flows through the system, the technology stack, folder structure, security boundaries, and implementation decisions. |

> **Source of truth:** `PRD.md` defines product requirements and scope. This document translates those requirements into a practical architecture. Decisions already confirmed in the PRD are marked **[Decided]**. Implementation suggestions are marked **[Proposed]**. Remaining choices are marked **[Open]**.

---

## 1. Purpose and Scope

RepoPulse is a full-stack software-engineering intelligence platform that analyzes **public GitHub repositories owned by the authenticated user**.

The system combines:

- GitHub OAuth authentication
- GitHub repository listing and ownership enforcement
- temporary Git cloning
- source-code parsing
- code metrics
- deterministic static analysis
- basic security checks
- existing test-coverage report reading
- Git-history analysis
- dependency extraction
- a static dependency graph
- one Random Forest defect-proneness model
- evidence-grounded OpenAI explanations
- a Next.js dashboard
- PostgreSQL persistence
- automated testing, Docker, and GitHub Actions CI/CD

The architecture deliberately excludes microservices, Redis/Celery, vector databases, RAG, repository-wide chat, PR intelligence, interactive dependency graphs, advanced security scanning, and separate ML infrastructure.

---

# 2. Architectural Goals

| Goal | Architectural consequence |
|---|---|
| Keep the project manageable | One FastAPI backend, one PostgreSQL database, one Next.js frontend. |
| Demonstrate full-stack + AI/ML engineering | Clear boundaries between UI, API, analysis, ML, and LLM explanation. |
| Protect repository access | Backend authorization on every repository-scoped operation. |
| Never execute user repository code | Analysis is read-only; tests/builds/install scripts are never run. |
| Support meaningful Git analysis | Use a temporary full Git clone and local Git history commands. |
| Keep ML defensible | Training and inference share a compatible feature definition. |
| Keep AI grounded | LLM receives structured evidence and a relevant code snippet, not an unrestricted repository dump. |
| Work on low-cost hosting | Hard repository limits, bounded analysis time, limited concurrency, no extra infrastructure. |
| Degrade gracefully | Individual non-essential stages can fail without destroying the complete report. |
| Keep facts separate from generated output | Deterministic findings, ML predictions, and LLM explanations are stored and displayed separately. |

---

# 3. System Context

```text
                         ┌───────────────────┐
                         │       User        │
                         │     Browser       │
                         └─────────┬─────────┘
                                   │ HTTPS
                                   ▼
                    ┌────────────────────────────┐
                    │       RepoPulse App        │
                    │                            │
                    │  Next.js + FastAPI + DB    │
                    └──────┬──────────┬──────────┘
                           │          │
                  OAuth/API│          │ HTTPS API
                           │          │
                           ▼          ▼
                     ┌─────────┐  ┌────────────┐
                     │ GitHub  │  │  OpenAI    │
                     │         │  │    API     │
                     └─────────┘  └────────────┘
                           │
                           │ Git clone
                           ▼
                    Temporary repo
                    analysis workspace
```

## External systems

| System | Purpose |
|---|---|
| GitHub | OAuth authentication, repository listing, repository metadata, public Git repositories |
| OpenAI API | "Explain with AI" for selected findings |
| PostgreSQL host | Persistent application and analysis data in production |

**[Decided]** Only public repositories are supported in v1.

**[Decided]** The application never accepts an arbitrary GitHub repository URL from the user.

---

# 4. High-Level Architecture

RepoPulse follows a **modular monolith** architecture.

```text
┌────────────────────────────────────────────────────────────────┐
│                         Browser                                │
│                                                                │
│  Next.js + TypeScript + Tailwind CSS                           │
│  Dashboard / Repositories / Files / Git / Dependencies        │
└───────────────────────────────┬────────────────────────────────┘
                                │ HTTPS
                                ▼
┌────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                            │
│                                                                │
│  API → Services → Domain/Analysis → External Integrations      │
│                                                                │
│  Auth | GitHub | Analyzer | Git | Dependencies | Security      │
│  ML | AI | Database                                            │
│                                                                │
│  FastAPI BackgroundTasks                                       │
└───────────────┬────────────────┬─────────────────┬─────────────┘
                │                │                 │
                ▼                ▼                 ▼
         ┌────────────┐   ┌─────────────┐   ┌─────────────┐
         │ PostgreSQL │   │ GitHub      │   │ OpenAI API  │
         └────────────┘   └─────────────┘   └─────────────┘
```

### Why a modular monolith?

**[Decided]**

RepoPulse needs several logically distinct subsystems, but they do not need to be separately deployed services.

A modular monolith gives:

- simple local development
- simple Docker Compose setup
- simpler deployment
- direct calls between analysis modules
- fewer networking and authentication boundaries
- easier debugging
- enough architectural separation for testing and future extraction if ever required

There is intentionally **no microservice architecture** in v1.

---

# 5. Container / Deployment View

## 5.1 Local development

**[Decided]**

```text
┌───────────────────────────────────────────────────────┐
│                  Docker Compose                       │
│                                                       │
│  ┌──────────────┐   ┌──────────────┐                 │
│  │   frontend   │   │    backend   │                 │
│  │   Next.js    │   │   FastAPI    │                 │
│  └──────────────┘   └──────┬───────┘                 │
│                             │                         │
│                      ┌──────▼───────┐                 │
│                      │  PostgreSQL  │                 │
│                      └──────────────┘                 │
└───────────────────────────────────────────────────────┘
```

## 5.2 Production

**[Decided]** Production uses a live free/low-cost deployment with the frontend and backend on different hosts. The exact providers remain **[Open]**.

Decided topology:

```text
Browser
   │
   ├──────────────► Frontend host
   │                 Next.js
   │
   │ HTTPS API
   ▼
Backend host
   FastAPI
      │
      ├──────────► PostgreSQL
      ├──────────► GitHub
      └──────────► OpenAI API
```

The production deployment should keep secrets and privileged integrations on the backend.

---

# 6. Technology Stack

| Layer | Technology | Status |
|---|---|---|
| Frontend | Next.js + TypeScript | **[Decided]** |
| Frontend styling | Tailwind CSS + shadcn/ui | **[Decided]** |
| Frontend routing | Next.js App Router | **[Proposed]** |
| Backend | FastAPI + Python | **[Decided]** |
| API validation | Pydantic / FastAPI validation | **[Decided]** |
| Database | PostgreSQL | **[Decided]** |
| ORM | SQLAlchemy | **[Decided]** |
| Migrations | Alembic | **[Decided]** |
| Authentication | GitHub OAuth App | **[Decided]** |
| Session mechanism | Secure HTTP-only cookie | **[Decided]** |
| Session storage format | PostgreSQL-backed opaque server-side session | **[Decided]** |
| Repository retrieval | Temporary full `git clone` | **[Decided]** |
| Git history | Local Git commands / GitPython or subprocess wrapper | **[Proposed]** |
| Parser | Tree-sitter | **[Decided]** |
| Supported source languages | Python, JavaScript, TypeScript | **[Decided]** |
| Static analysis | RepoPulse deterministic rules | **[Decided]** |
| Dependency graph | Graph data + static SVG | **[Decided]** |
| ML model | Random Forest Classifier | **[Decided]** |
| ML framework | scikit-learn | **[Proposed]** |
| ML artifact | Serialized model packaged with backend | **[Decided]** |
| ML training data | JM1; final compatible feature subset is fixed by the cross-language compatibility check | **[Decided]** |
| LLM | OpenAI API | **[Decided]** |
| LLM model | Environment-configurable | **[Decided]** |
| Background execution | FastAPI `BackgroundTasks` | **[Decided]** |
| Local infrastructure | Docker + Docker Compose | **[Decided]** |
| CI/CD | GitHub Actions | **[Decided]** |
| Backend tests | pytest | **[Proposed]** |
| Frontend tests | Vitest + Testing Library | **[Decided]** |
| E2E tests | Playwright | **[Decided]** |
| Charts | Recharts | **[Decided]** |
| Graph layout | Frontend static SVG; exact layout algorithm remains open | **[Decided]** |

> **Confirmed frontend stack:** Tailwind CSS + shadcn/ui are selected for styling and UI components; Recharts is selected for charts.

---

# 7. End-to-End Product Flow

```text
User
  │
  ▼
Landing Page
  │
  ▼
GitHub OAuth
  │
  ▼
Authenticated User
  │
  ▼
Fetch GitHub repositories
  │
  ▼
Filter:
repository.owner == authenticated_user.github_username
  │
  ▼
Repository List
  │
  ▼
Select "Analyze"
  │
  ▼
Create analysis_run
  │
  ▼
FastAPI BackgroundTasks
  │
  ├── Clone repository
  ├── Validate size/file limits
  ├── Discover source files
  ├── Parse source
  ├── Extract metrics
  ├── Static analysis
  ├── Security checks
  ├── Dependency extraction
  ├── Git history analysis
  ├── Read existing coverage report
  ├── Prepare ML features
  ├── Random Forest prediction
  ├── Build risk factors
  └── Persist analysis
  │
  ▼
Completed Analysis
  │
  ▼
Repository Dashboard
  │
  ├── Code metrics
  ├── Defect-proneness
  ├── Security findings
  ├── Coverage
  ├── Git activity
  ├── Top findings
  └── Dependency graph
       │
       ▼
Selected Finding
       │
       ▼
"Explain with AI"
       │
       ▼
Evidence Package
       │
       ▼
OpenAI API
       │
       ▼
Stored Explanation
       │
       ▼
Displayed to User
```

---

# 8. Authentication Flow

**[Decided]** GitHub OAuth App.

```text
Browser
  │
  │ Get Started
  ▼
Next.js
  │
  │ redirect to backend OAuth endpoint
  ▼
FastAPI
  │
  ├── create OAuth state
  └── redirect to GitHub
       │
       ▼
GitHub authorization
       │
       ▼
GitHub callback
       │
       ▼
FastAPI
  │
  ├── validate state
  ├── exchange authorization code
  ├── fetch GitHub user
  ├── create/update local user
  └── establish session
       │
       ▼
HTTP-only session cookie
       │
       ▼
Next.js repository page
```

### Authentication rules

- GitHub OAuth is the only login method.
- No email/password authentication.
- Public repository access only.
- The frontend never receives the GitHub client secret.
- OAuth credentials stay on the backend.
- Tokens/secrets are never written to logs.
- The user's GitHub access token is **not persisted [Decided]**. **[Proposed]** It is held in memory only during the OAuth callback, used to fetch the user's repository list, and then discarded.
- Session cookies are HTTP-only.
- Production cookies should be `Secure`.
- CSRF/origin protection must be implemented for cookie-authenticated state-changing requests.

---

# 9. Repository Ownership Flow

- **Default branch only [Decided].**

The most important authorization rule is:

```text
Authenticated RepoPulse User
            │
            ▼
       GitHub username
            │
            ▼
       GitHub repository
            │
            ▼
repository.owner == authenticated_user.github_username
            │
       ┌────┴────┐
       │         │
      YES        NO
       │         │
       ▼         ▼
   allow       reject
```

The rule is enforced **on the backend**, not merely by filtering the UI.

### Example

If the authenticated GitHub username is:

```text
viplav
```

Allowed:

```text
viplav/project-a
viplav/project-b
viplav/project-b-fork
```

Rejected:

```text
friend/project-c
organization/project-d
other-user/project-e
```

User-owned forks are included because the owner is still the authenticated user.

### Repository list refresh [Proposed]

Because the user's token is not stored, the repository list is fetched and upserted into `repositories` during the OAuth callback. Later refreshes and the pre-analysis size check use a server-side public-data credential (`GITHUB_PUBLIC_API_TOKEN`), so they do not depend on a per-user token and do not share a low unauthenticated rate limit across all users. Only public data is requested, and ownership is still verified against the stored `repositories.user_id`.

Every resource must also follow the ownership chain:

```text
finding
   ↓
file
   ↓
analysis_run
   ↓
repository
   ↓
user
```

A request is allowed only if the final user matches the authenticated user.

---

# 10. Repository Retrieval Architecture

## 10.1 Retrieval strategy

**[Decided]**

Use a temporary full Git clone.

```text
GitHub repository
       │
       ▼
Temporary directory
       │
       ├── source files
       ├── .git history
       └── repository metadata
       │
       ▼
Analysis
       │
       ▼
Results persisted
       │
       ▼
Temporary directory deleted
```

A full clone is used because RepoPulse needs both:

1. source code
2. Git history

The application does not depend entirely on GitHub API calls for historical statistics.

## 10.2 Repository limits

**[Decided]**

Default v1 limits:

- approximately 50 MB
- approximately 1,000 supported source files
- maximum analysis duration: 5 minutes

All limits should be configurable.

## 10.3 Ignored content

By default ignore:

```text
node_modules/
.git objects not needed by analysis
binary files
build output
generated files
large generated assets
```

Do not recurse into Git submodules in v1.

Do not execute:

- repository code
- test suites
- build scripts
- package installation scripts
- GitHub Actions
- repository-provided shell scripts

---

# 11. Analysis Pipeline

## 11.1 Pipeline overview

```text
1. Clone
   ↓
2. Validate limits
   ↓
3. File discovery
   ↓
4. Language identification
   ↓
5. Tree-sitter parsing
   ↓
6. Metric extraction
   ↓
7. Static analysis
   ↓
8. Security analysis
   ↓
9. Dependency extraction
   ↓
10. Git history analysis
   ↓
11. Coverage report reading
   ↓
12. ML feature preparation
   ↓
13. Random Forest inference
   ↓
14. Risk summary
   ↓
15. Persist results
   ↓
16. Cleanup
```

AI explanation is intentionally **not part of the mandatory analysis pipeline**.

It is triggered later for a selected finding.

## 11.2 Why AI is separate

The core report must remain available even if:

- OpenAI is unavailable
- the user does not request an explanation
- the LLM request fails
- an explanation exceeds a provider limit

This implements the product's evidence-first and graceful-degradation principles.

---

# 12. Analysis Stage Architecture

| Stage | Input | Output | Failure behavior |
|---|---|---|---|
| Clone | GitHub repository | Temporary working tree | Run fails |
| Discovery | Working tree | Supported source-file list | Limit exceeded → run fails |
| Parsing | Source files | Syntax trees | Minor parse errors tolerated; unusable files skipped with a warning **[Decided]** |
| Metrics | Syntax trees | Numeric metrics | Affected file may be skipped if parsing fails |
| Static analysis | Metrics + syntax | Deterministic findings | Continue where possible |
| Security | Source + syntax | Security findings | Continue where possible |
| Dependencies | Imports/references | Nodes + edges | Continue with partial graph where possible |
| Git history | Git repository | File/repository history metrics | Non-essential: run completes without history signals; stage shown as failed **[Decided]** |
| Coverage | Existing report | Coverage values | Missing report → unavailable |
| ML | Per-function compatible feature vectors | Function probabilities aggregated to one file score + class | Non-essential: run completes without ML scores; the stage must validate feature compatibility first **[Decided]** |
| Risk | All available signals | Contributing factors | No single combined health score |
| Persistence | Stage results | PostgreSQL rows | Analysis cannot be considered complete until required data is persisted |
| AI | Evidence package | Explanation text | Optional; report remains usable |

**Essential-stage policy [Decided]:** clone, discovery, parsing, metrics, static analysis, security, and persistence are essential. Dependencies, Git history, coverage, ML, risk, and AI explanation are non-essential enrichment stages: their failure is recorded and shown, and the run still completes.

---

# 13. Source-Code Parsing

## 13.1 Parser

**[Decided]** Tree-sitter is the parser architecture for:

- Python
- JavaScript
- TypeScript

The parser should expose enough structure to identify:

- functions
- classes
- imports
- conditionals
- loops
- calls
- nesting
- relevant expressions

## 13.2 Parser boundary

```text
Raw source file
      │
      ▼
Tree-sitter parser
      │
      ▼
Syntax tree
      │
      ├──► Metrics
      ├──► Static rules
      ├──► Dependencies
      └──► ML feature extraction
```

Analysis modules should not depend on HTTP or database access.

This keeps the core analysis logic deterministic and unit-testable.

---

# 14. Code Metrics Architecture

Required metrics include:

- LOC
- functions
- classes
- imports
- cyclomatic complexity

Additional metrics are computed only when required by the selected ML dataset.

Because JM1 module rows correspond to functions/methods, the JM1-compatible features are computed **per function/method** and kept in memory for the ML stage. Code outside any function/method qualifies only if it contains control flow (`if`, `for`, `while`, `try`, `switch`) or a call expression outside imports, decorators, and exports. Constant assignments, type declarations, and docstrings alone do not qualify; qualifying top-level code is a module-level unit. These per-unit vectors are not stored as a function-level table.

### Default static-analysis thresholds

**[Decided]**

| Metric | Default finding threshold |
|---|---:|
| Cyclomatic complexity | > 10 |
| Function length | > 50 LOC |
| File size | > 500 LOC |
| Imports | > 20 |

Thresholds should be configurable.

The exact implementation of additional ML metrics remains dependent on the dataset compatibility check.

---

# 15. Static Analysis Architecture

Static analysis is deterministic.

```text
Syntax tree + metrics
        │
        ▼
┌──────────────────────────┐
│ RepoPulse Rule Engine    │
├──────────────────────────┤
│ Long function            │
│ High complexity          │
│ Large file               │
│ Duplicate code           │
│ Suspicious patterns      │
│ Poor/unused structure    │
└────────────┬─────────────┘
             ▼
          Findings
```

Each finding should contain at least:

```text
type
severity
file
line
message
measured_value (when applicable)
threshold (when applicable)
```

The LLM does not create these findings.

---

# 16. Security Analysis

Security analysis is intentionally small.

### In scope

- obvious hard-coded secrets
- selected unsafe patterns appropriate to Python/JavaScript/TypeScript

Example:

```text
HIGH
Hardcoded Secret

payments.py:42
API_KEY = "..."
```

### Out of scope

- dependency CVE scanning
- full SAST platform
- penetration testing
- dynamic security testing
- package vulnerability database
- runtime security monitoring

---

# 17. Test Coverage Architecture

RepoPulse **does not execute repository tests**.

```text
Repository
   │
   ├── source files
   ├── test files
   └── existing coverage report?
             │
       ┌─────┴─────┐
      YES           NO
       │             │
       ▼             ▼
Parse report      coverage =
       │           unavailable
       ▼
coverage metrics
```

Coverage should be treated as a normal optional signal.

The architecture should support the initially selected standard formats during implementation. Exact report formats remain an implementation choice.

---

# 18. Git History Architecture

The cloned repository provides local Git history.

```text
Temporary Git clone
       │
       ▼
Git history extractor
       │
       ├── commit count
       ├── recent commits
       ├── lines added
       ├── lines removed
       ├── contributors
       └── modification frequency
       │
       ▼
File-level + repository-level Git metrics
```

### File-level examples

```text
payments.py
  commits: 31
  recent_commits: 12
  lines_added: 702
  lines_removed: 211
  contributors: 4
  modification_frequency: high
```

### Repository-level examples

```text
commits
contributors
files_changed
commits_over_time
```

Git history is a risk/context signal, not proof that a file contains a defect.

---

# 19. Dependency Architecture

## 19.1 Graph model

```text
G = (V, E)

V = source files/modules
E = dependency relationships
```

Example:

```text
main.py
 ├── auth.py
 ├── users.py
 └── orders.py
       └── database.py
```

## 19.2 Extraction

Python:

```text
import x
from x import y
from .module import z
```

JavaScript/TypeScript:

```text
import x from "./x"
import { y } from "../shared/y"
require("./module")
```

Only repository-internal modules are represented as graph nodes.

Third-party packages are not graph nodes in v1.

## 19.3 Output

The backend returns graph data:

```json
{
  "nodes": [
    {"id": "main.py"},
    {"id": "auth.py"}
  ],
  "edges": [
    {"source": "main.py", "target": "auth.py"}
  ]
}
```

The frontend renders a **static, non-interactive** graph.

No:

- pan/zoom
- drag
- interactive graph filtering
- graph database
- advanced graph algorithms

A dependency-count table is also displayed so large graphs remain useful.

---

# 20. Machine Learning Architecture

## 20.1 Model

**[Decided]**

One model:

```text
Random Forest Classifier
```

Target:

```text
defect-prone
vs.
not defect-prone
```

A JM1 *module row* corresponds to a function/method. In user-facing product terminology, use **file** for the repository code container. The file is the aggregate container: the system predicts **per function/method** and **aggregates to one stored file-level score [Decided]**. If a file has qualifying executable top-level code outside functions/methods, that code is treated as a module-level ML unit and its probability participates in the same file-level aggregation. The model estimates defect-proneness from a compatible subset of software metrics; it does not guarantee that a bug exists or will occur.

## 20.2 Offline training

```text
JM1 dataset
      │
      ▼
Data cleaning (drop `?` rows, deduplicate on metrics, resolve conflicting labels)
      │
      ▼
Cross-language feature compatibility mapping
      │
      ▼
Final compatible feature subset
      │
      ▼
Stratified train/test split
      │
      ▼
Random Forest
      │
      ▼
Evaluation
      │
      ├── F1
      ├── ROC-AUC
      ├── precision / recall
      ├── confusion matrix
      └── feature importance
      │
      ▼
Model artifact + feature schema
      │
      ▼
backend/app/ml/artifacts/
```

The supplied JM1 file contains 10,885 rows, 21 metric inputs, an `id` identifier, and the binary `defects` label. A second dataset (`cm1.csv`) was available but is not part of v1 training.

The supplied JM1 file has five rows containing `?` in `uniq_Op`, `uniq_Opnd`, `total_Op`, `total_Opnd`, and `branchCount`. The training pipeline must explicitly resolve this before the final model is trained; it must never silently convert `?` to zero.

Excluding the `id` column, the file also contains duplicated and conflicting instances (after removing the five `?` rows: 1,973 rows duplicate another row on metrics and label, and 88 metric vectors appear with both labels). The pipeline deduplicates on the metric columns and removes conflicting-label vectors **before** the train/test split, leaving 8,731 rows (21.9% defective). A few anomalous rows (row `id=1` with fractional counts, one row with `lOCode` > `loc`, and 1,332 rows with `total_Op` = 0) are handled by explicit, recorded rules during the Phase 0 check.

## 20.3 Dataset and feature-compatibility rule

**JM1 is selected and locked as the v1 training dataset.** JM1 is a C software-module dataset, while RepoPulse analyzes Python, JavaScript, and TypeScript. This language/domain mismatch is an explicit product limitation. The repository includes the supplied `jm1.csv` under `ml/data/` (SHA-256 `1ec66eb3568ae8bb4e2709cf0bd28b11db41c7c0ae771325c0952997e35e4dff`). The dataset's Kaggle listing reports the license as **unknown**, so the project does not represent the dataset as freely redistributable; provenance and this licensing uncertainty must be documented alongside the file.

The serving schema is therefore a subset of JM1 metrics whose definitions can be reproduced consistently enough across Python, JavaScript, and TypeScript. For every candidate metric, the compatibility record must contain the JM1 definition, the implementation method, language-specific rules, and a final `use` or `drop` decision. Unsupported approximations are not silently accepted.

## 20.4 ML granularity and metric implementation

- **Prediction unit [Decided]:** JM1 rows correspond to functions/methods, so serving features are computed **per function/method** and predictions remain in memory. Code outside any function/method is excluded unless it contains qualifying top-level control flow (`if`, `for`, `while`, `try`, `switch`) or a call expression outside imports, decorators, and exports. Constant assignments, type declarations, and docstrings alone do not qualify. No function-level table is stored.
- **File score [Decided approach, rule Open]:** Function/method and qualifying top-level-unit probabilities are aggregated into one file-level score, stored in `predictions`. Candidate rules: mean, top-3 mean, maximum; chosen in Phase 4. The prediction record stores nullable `riskiest_function_name`, `riskiest_function_start_line`, and `riskiest_function_end_line`. Riskiest-function metadata is selected from functions/methods only, regardless of whether a qualifying top-level unit has a higher probability. Among functions/methods, highest probability wins; ties use earliest source start line, then lexicographically smallest qualified function name. The three function metadata fields are null only when the file contains no predicted function/method. This does not create a function-level table. Every analyzed file has a prediction row with status `scored`, `no_ml_unit`, or `ml_failed`. For `no_ml_unit` and `ml_failed`, `model_version`, probability, and class are null and the UI shows **Not scored** with the corresponding reason; no risk label is assigned.
- **Metric implementation [Decided]:** hybrid. RepoPulse owns the semantic definition and uses Tree-sitter for AST-dependent extraction; a metrics library may supplement this only where its output is verified against the JM1 definition and all three supported languages.
- **Exact library [Open]:** select it during Phase 0 only after compatibility testing demonstrates that it produces the required definition accurately. The five JM1 rows containing `?` are **dropped before training**; they are not coerced to zero or imputed.
- **Training/serving invariant:** `feature_schema.json` defines feature names, order, units, definitions, source-dataset columns, and language compatibility notes for both training and inference.

## 20.5 Online inference

```text
Parsed source
     │
     ▼
Per-function compatible feature vectors + qualifying top-level unit (in memory)
     │
     ▼
Packaged Random Forest
     │
     ▼
unit-level defect-proneness probabilities (functions/methods plus any qualifying top-level unit)
     │
     ▼
aggregation rule → one file-level score (if any unit exists)
     │
     ├── score exists → risk label
     └── no unit → status=no_ml_unit; ML failure → status=ml_failed
         (both Not scored; null model_version, probability, and class)
     │
     ▼
PostgreSQL (one prediction/status row per analyzed file)
```

The model is loaded once when the backend starts rather than loaded for every file/request. Each file prediction row stores `status` (`scored`, `no_ml_unit`, or `ml_failed`). `model_version`, probability, and class are nullable and must be null unless status is `scored`. The UI shows **Not scored** with the status-specific reason and assigns no risk label. Riskiest-function metadata always selects the highest-probability function/method among functions/methods only; a higher-probability top-level unit does not hide it.

## 20.6 Model limitations

JM1 is C/module data, not Python/JavaScript/TypeScript data. Evaluation metrics describe performance on JM1's held-out data and must not be presented as proof that the model is calibrated for arbitrary supported-language repositories. The UI and documentation must use defect-proneness language rather than promising future bug detection.

# 21. Risk Architecture

RepoPulse does not create a single opaque health score.

Instead, it exposes independent dimensions.

```text
                     Repository
                         │
       ┌─────────────────┼──────────────────┐
       ▼                 ▼                  ▼
 Code quality        Security          Test coverage
       │                 │                  │
       └────────────┬────┴───────┬──────────┘
                    ▼            ▼
               Git history   Dependencies
                    │            │
                    └─────┬──────┘
                          ▼
                 ML defect-proneness
                          │
                          ▼
                  Risk factors
```

Example contributing factors:

```text
payments.py

Risk factors:
- Complexity = 19 (>10)
- Function length = 83 LOC (>50)
- Coverage = 42%
- Recent commits = 11
- High-severity security finding
- Defect probability = 0.81
```

The UI should show these factors rather than hiding them behind a single score.

---

# 22. AI Explanation Architecture

## 22.1 Evidence-first flow

```text
Deterministic analysis
        │
        ├── metrics
        ├── findings
        ├── coverage
        ├── Git history
        └── ML probability
                │
                ▼
        Evidence package
                │
                ├── structured facts
                └── relevant code snippet
                │
                ▼
           OpenAI API
                │
                ▼
        Explanation text
                │
                ▼
            PostgreSQL
                │
                ▼
              UI
```

## 22.2 Example evidence package

```json
{
  "file": "payments.py",
  "loc": 421,
  "complexity": 19,
  "coverage": 42,
  "recent_commits": 11,
  "defect_probability": 0.81,
  "findings": [
    "high complexity",
    "long function"
  ],
  "code_snippet": "..."
}
```

## 22.3 AI boundaries

The LLM:

- explains supplied evidence
- explains why a finding matters
- suggests practical next steps

The LLM does **not**:

- scan the entire repository
- create authoritative findings
- determine security severity independently
- replace the static analyzer
- act as a repository chatbot
- use RAG
- use a vector database

The exact OpenAI model is configured through environment variables.

---

# 23. Background Analysis Architecture

**Execution constraint:** the analysis pipeline must not perform blocking clone/parsing work directly inside an `async def` request handler. Use a synchronous `BackgroundTasks` callable so blocking work is executed off the event loop, with explicit limits on concurrent analyses. A separate worker/process-pool architecture is not part of the current design.

**[Decided]** FastAPI `BackgroundTasks` + frontend polling.

```text
POST /repositories/{id}/analyze
             │
             ▼
     create analysis_run
             │
             ▼
      status = queued
             │
             ▼
     schedule background task
             │
             ▼
        return run_id
             │
             │
             └──────────────► Frontend polls
                                  │
                                  ▼
                          GET analysis/status
```

### Important limitation

This is intentionally **not** a distributed job system.

There is no:

- Redis
- Celery
- Kafka
- dedicated worker service

Because the project targets bounded repositories and low-cost hosting.

### Concurrency

**[Proposed]**

Use a small concurrency limit to prevent multiple large analyses from exhausting CPU, RAM, and disk.

Example:

```text
1 analysis per user
2–3 analyses globally
```

The exact limit can be configured after deployment testing.

### Timeout

**[Decided]**

Default maximum:

```text
300 seconds / 5 minutes
```

The value remains configurable.

---

# 24. Backend Layering

```text
┌───────────────────────────────┐
│ API / Routers                 │
│ HTTP, validation, auth        │
└───────────────┬───────────────┘
                ▼
┌───────────────────────────────┐
│ Application Services          │
│ Use-case orchestration        │
└───────────────┬───────────────┘
                ▼
┌─────────────────────────────────────────────┐
│ Domain / Analysis Modules                   │
│ analyzer | git | dependencies | security    │
│ ml                                          │
└───────────────┬─────────────────────────────┘
                │
        ┌───────┴────────┐
        ▼                ▼
 External I/O       PostgreSQL
 GitHub / OpenAI
```

### Principle

Core analysis logic should ideally be pure:

```text
input data → deterministic computation → result
```

rather than:

```text
analysis function → database + HTTP + filesystem + model + UI
```

This improves testability and makes the system easier to reason about.

---

# 25. Backend Modules

| Module | Responsibility |
|---|---|
| `auth/` | GitHub OAuth, sessions, current-user authentication |
| `github/` | GitHub API integration and repository retrieval |
| `repositories/` | Repository records and ownership authorization |
| `analyzer/` | Pipeline orchestration, file discovery, parsing, metrics, static analysis, coverage |
| `git/` | Git history extraction |
| `dependencies/` | Import resolution and graph construction |
| `security/` | Secret and unsafe-pattern detection |
| `ml/` | Feature preparation, model loading, inference |
| `ai/` | Evidence package, OpenAI client, prompt |
| `database/` | SQLAlchemy models, database sessions, Alembic |
| `api/` | HTTP routers and schemas |

---

# 26. Authorization Architecture

Every repository-scoped resource follows an ownership chain.

```text
Current authenticated user
          │
          ▼
Repository ownership
          │
          ▼
Analysis ownership
          │
          ▼
File ownership
          │
          ▼
Finding / Prediction / Explanation ownership
```

Example:

```text
GET /files/123
       │
       ▼
file 123
       │
       ▼
analysis_run
       │
       ▼
repository
       │
       ▼
repository.user_id == current_user.id ?
       │
    ┌──┴──┐
   YES    NO
    │      │
 allow   reject
```

This prevents ID-tampering attacks such as:

```text
User A:
GET /repositories/17

User A changes:
GET /repositories/18
```

if repository 18 belongs to User B.

---

# 27. Data Architecture

## 27.1 Main relationship

```text
User
 │
 └──< Repository
        │
        └──< AnalysisRun
               │
               ├──< File
               │     ├──< Finding
               │     └──< Prediction
               │
               ├──< DependencyEdge
               │
               ├──< GitFileStats
               │
               └──< AIExplanation
```

## 27.2 Starting relational schema

```text
users
- id
- github_user_id
- username
- email
- created_at

repositories
- id
- user_id
- github_repo_id
- name
- owner
- default_branch
- created_at

analysis_runs
- id
- repository_id
- commit_sha
- status
- current_stage
- started_at
- completed_at
- error_message

files
- id
- analysis_id
- path
- language
- loc
- functions
- classes
- imports
- complexity
- coverage

findings
- id
- file_id
- type
- severity
- line
- message
- measured_value
- threshold

predictions
- id
- file_id
- status (`scored` | `no_ml_unit` | `ml_failed`)
- model_version (nullable; null unless status=`scored`)
- probability (nullable)
- class (nullable)
- riskiest_function_name (nullable)
- riskiest_function_start_line (nullable)
- riskiest_function_end_line (nullable)
```

Additional tables/entities required by the product:

```text
git_file_stats
dependency_edges
ai_explanations
sessions (if server-side session storage is chosen)
```

The exact final schema and indexes are **[Open]** until implementation.

### Retention [Decided policy; details Proposed]

The latest 10 completed analysis runs per repository are kept. After a run completes, older completed runs are deleted together with their dependent rows (files, findings, predictions, dependency edges, Git stats, explanations), using cascading foreign keys or one transactional delete. Failed runs do not count toward the 10; their retention is **[Open]** (proposal: keep only the most recent failed run per repository).

---

# 28. Analysis Run State Machine

A run should have an explicit lifecycle.

```text
QUEUED
  │
  ▼
RUNNING
  │
  ├──────────────► FAILED
  │
  ▼
COMPLETED
```

The running state also exposes a current stage:

```text
cloning
discovery
parsing
metrics
static_analysis
security
dependencies
git_history
coverage
ml
risk
persisting
cleanup
completed
```

Example API response:

```json
{
  "run_id": 42,
  "status": "running",
  "stage": "git_history",
  "progress": null
}
```

Exact numeric progress percentages are optional because stages have very different execution costs.

---

# 29. Frontend Architecture

The frontend is a thin client.

It is responsible for:

- rendering pages
- calling the backend
- polling analysis status
- displaying charts
- displaying findings
- displaying the static dependency graph
- displaying AI explanations

It is **not** responsible for:

- GitHub API access
- OpenAI API access
- repository authorization
- storing API secrets
- determining whether a repository belongs to the user

## Suggested routes

```text
/
├── /repositories
├── /repositories/[id]
├── /repositories/[id]/files/[fileId]
├── /repositories/[id]/git
├── /repositories/[id]/dependencies
└── /repositories/[id]/history
```

### Main pages

| Page | Purpose |
|---|---|
| `/` | Landing / Get Started |
| `/repositories` | Own public repositories |
| `/repositories/[id]` | Repository dashboard |
| `/repositories/[id]/files/[fileId]` | File-level analysis |
| `/repositories/[id]/git` | Git history |
| `/repositories/[id]/dependencies` | Static dependency graph |
| `/repositories/[id]/history` | Analysis comparison |

---

# 30. Dashboard Data Flow

```text
FastAPI
  │
  ├── repository metadata
  ├── latest analysis
  ├── findings
  ├── predictions
  ├── coverage
  ├── Git statistics
  └── dependency graph
        │
        ▼
Next.js dashboard
        │
        ├── Risk
        ├── Security
        ├── Coverage
        ├── Code metrics
        ├── Top findings
        ├── Git activity
        └── Dependency preview
```

No combined "health score" is displayed.

---

# 31. API Architecture

Exact endpoint names can evolve during implementation, but the API should follow this shape:

```text
GET   /auth/github/login
GET   /auth/github/callback
POST  /auth/logout
GET   /auth/me

GET   /repositories
POST  /repositories/{id}/analyze

GET   /repositories/{id}/analysis
GET   /repositories/{id}/analysis/{run_id}
GET   /repositories/{id}/files

GET   /files/{id}
GET   /files/{id}/findings

POST  /findings/{id}/explain

GET   /repositories/{id}/git
GET   /repositories/{id}/dependencies
GET   /repositories/{id}/history
```

Every repository-scoped route must enforce ownership.

---

# 32. Security Architecture

## 32.1 Core controls

| Control | Implementation |
|---|---|
| Authentication | GitHub OAuth |
| Authorization | Backend ownership checks |
| OAuth secrets | Backend environment variables |
| Session | HTTP-only cookie |
| Repository execution | Never execute repository code |
| Tests | Never execute repository tests |
| Input validation | FastAPI/Pydantic |
| Logs | Never contain credentials/tokens/source dumps |
| Temporary files | Delete after analysis |
| Git operations | Timeouts + non-interactive mode |
| Symlinks | Do not follow outside analysis directory |
| Submodules | Do not recurse |
| OpenAI key | Backend only |
| AI input | Bounded evidence package |
| AI output | Render as text/sanitized content |

## 32.2 Repository ingestion threat boundary

Repository content is **untrusted input**.

```text
UNTRUSTED
GitHub repository
      │
      ▼
Read-only analysis boundary
      │
      ├── parser
      ├── metrics
      ├── rules
      └── dependency extraction
      │
      ▼
Trusted structured facts
```

Never cross the boundary by executing repository-provided code.

---

# 33. AI Security Boundary

Repository code can contain strings that resemble instructions.

Therefore:

```text
Code snippet
   │
   ▼
Treat as DATA
   │
   ▼
Clearly delimit in prompt
   │
   ▼
Tell model not to follow instructions contained in code
   │
   ▼
OpenAI
```

The model has no tools or ability to execute repository content.

The explanation should be rendered as text rather than executable markup.

---

# 34. Split-Host Web Security

If frontend and backend are deployed separately, authentication must account for browser cookie rules.

Required considerations:

1. HTTPS in production.
2. Correct `SameSite` and `Secure` cookie settings.
3. Exact CORS origin configuration.
4. Credentialed requests only where necessary.
5. CSRF/origin protection for state-changing requests.
6. OAuth callback URL must match the production topology.

**[Decided cookie/domain strategy; hosting providers remain Open]** The frontend and backend production hosts use the same registrable/parent domain. The exact hosting providers remain open and must be selected before production authentication is configured.

The production domain shape is therefore expected to be, for example:

```text
app.example.com
api.example.com
```

The proxy approach is not the selected v1 strategy; use same-parent-domain hosts.

**Prerequisite:** this strategy requires a domain you own, DNS control for it, and hosting providers that allow custom domains on the chosen plans. The default domains that providers assign to free projects do not share a parent domain. The session cookie's `Domain` attribute and the GitHub OAuth callback URL must use the same parent domain. Local development is unaffected because `localhost` ports are the same site.

---

# 35. Temporary Repository Workspace

Each analysis should use an isolated temporary directory.

```text
/tmp/repopulse/
    run-abc123/
        repository/
            source...
            .git...
```

Lifecycle:

```text
create
  ↓
clone
  ↓
analyze
  ↓
persist results
  ↓
finally:
delete directory
```

Cleanup must happen even if analysis fails.

No repository source should be permanently stored unless explicitly required by a persisted feature.

---

# 36. Error and Degradation Strategy

| Failure | Result |
|---|---|
| GitHub API unavailable | Clear repository retrieval error |
| Clone fails | Analysis fails |
| Repository too large | Analysis stops |
| Unsupported files | Supported files still analyzed |
| Corrupt file | Handle according to parser failure policy |
| Coverage missing | "Unavailable" |
| Git history issue | Stage failure policy |
| ML unavailable/incompatible | Prediction unavailable; other report data remains |
| OpenAI unavailable | AI explanation unavailable; report remains |
| Backend restart during run | Mark stale in-process run failed on startup |
| Unexpected exception | Run marked failed and useful error logged |

The UI should expose stage status so users know what succeeded.

---

# 37. Observability

Use structured application logging.

Important events:

```text
user_authenticated
analysis_started
analysis_stage_started
analysis_stage_completed
analysis_completed
analysis_failed
ml_prediction_generated
ai_explanation_requested
ai_explanation_failed
```

Include:

```text
timestamp
log level
run ID
user ID (non-sensitive internal identifier)
repository ID
stage
duration
```

Do not log:

- GitHub OAuth tokens
- session cookies
- OpenAI API keys
- full source code
- sensitive request headers

A lightweight health endpoint is **[Proposed]**.

---

# 38. Testing Architecture

## 38.1 Unit tests

Test pure analysis logic:

```text
test_complexity_calculation
test_loc_calculation
test_static_rule_thresholds
test_dependency_extraction
test_git_metric_extraction
test_feature_vector_order
test_risk_prediction
```

## 38.2 Backend/API tests

```text
test_github_oauth_callback
test_repository_listing
test_repository_ownership
test_tampered_repository_id
test_tampered_file_id
test_analysis_endpoint
test_analysis_status
test_explain_finding
```

## 38.3 Integration tests

```text
FastAPI
   ↕
PostgreSQL
```

Verify:

- analysis runs persist
- files persist
- findings persist
- predictions persist
- history comparisons work

## 38.4 AI tests

Mock OpenAI.

Test:

```text
OpenAI success
OpenAI timeout
OpenAI error
malformed response
```

The report must remain usable when the AI service fails.

## 38.5 E2E

Recommended flow:

```text
Login
  ↓
Repository list
  ↓
Select repository
  ↓
Analyze
  ↓
Poll status
  ↓
Dashboard
  ↓
File detail
  ↓
Explain with AI
```

Playwright is a **[Proposed]** candidate.

---

# 39. CI/CD Architecture

```text
Developer
   │
   ▼
git push
   │
   ▼
GitHub Actions
   │
   ├── install frontend dependencies
   ├── install backend dependencies
   ├── lint
   ├── unit tests
   ├── integration tests
   ├── frontend build
   ├── backend checks
   └── Docker build
          │
          ▼
       pass/fail
```

Deployment automation depends on the final hosting providers.

---

# 40. Folder Structure

The repository uses a monorepo.

```text
repopulse/
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── repositories/
│   │   │   ├── page.tsx
│   │   │   └── [id]/
│   │   │       ├── page.tsx
│   │   │       ├── files/
│   │   │       ├── git/
│   │   │       ├── dependencies/
│   │   │       └── history/
│   │   └── ...
│   ├── components/
│   │   ├── dashboard/
│   │   ├── findings/
│   │   ├── dependencies/
│   │   ├── git/
│   │   └── ui/
│   ├── lib/
│   │   ├── api.ts
│   │   ├── auth.ts
│   │   ├── polling.ts
│   │   └── types.ts
│   ├── public/
│   ├── Dockerfile
│   ├── package.json
│   └── tsconfig.json
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── auth/
│   │   │   ├── routes.py
│   │   │   ├── oauth.py
│   │   │   └── session.py
│   │   ├── github/
│   │   │   ├── client.py
│   │   │   └── clone.py
│   │   ├── repositories/
│   │   │   ├── service.py
│   │   │   └── authorization.py
│   │   ├── analyzer/
│   │   │   ├── pipeline.py
│   │   │   ├── discovery.py
│   │   │   ├── parser.py
│   │   │   ├── metrics.py
│   │   │   ├── static_rules.py
│   │   │   └── coverage.py
│   │   ├── git/
│   │   │   └── history.py
│   │   ├── dependencies/
│   │   │   ├── extractor.py
│   │   │   └── graph.py
│   │   ├── security/
│   │   │   ├── secrets.py
│   │   │   └── unsafe_patterns.py
│   │   ├── ml/
│   │   │   ├── features.py
│   │   │   ├── model.py
│   │   │   └── artifacts/
│   │   │       ├── model.pkl
│   │   │       └── feature_schema.json
│   │   ├── ai/
│   │   │   ├── client.py
│   │   │   ├── evidence.py
│   │   │   └── prompts.py
│   │   ├── database/
│   │   │   ├── models.py
│   │   │   ├── session.py
│   │   │   └── migrations/
│   │   └── api/
│   │       ├── repositories.py
│   │       ├── analyses.py
│   │       ├── files.py
│   │       ├── findings.py
│   │       └── schemas.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── ml/
│   ├── data/
│   │   └── dataset.csv
│   ├── preprocess.py
│   ├── train.py
│   ├── evaluate.py
│   ├── feature_schema.py
│   └── README.md
│
├── docs/
│   ├── PRD.md
│   └── Architecture.md
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

This is intentionally a **rough structure**. File-level organization can change during implementation without changing the architecture.

---

# 41. Configuration

Example environment variables:

```text
DATABASE_URL=
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_PUBLIC_API_TOKEN=

SESSION_SECRET=

OPENAI_API_KEY=
OPENAI_MODEL=

FRONTEND_URL=
API_BASE_URL=                 # Backend callback base URL
NEXT_PUBLIC_API_BASE_URL=     # Frontend API base URL; read by frontend/lib/api.ts

MAX_REPO_SIZE_MB=50
MAX_SOURCE_FILES=1000
ANALYSIS_TIMEOUT_SECONDS=300

TEMP_CLONE_DIR=
```

Rules:

- `.env` is never committed.
- `.env.example` contains placeholders only.
- Secrets exist only on the backend.
- Production secrets are supplied through the deployment platform.
- `GITHUB_PUBLIC_API_TOKEN` **[Proposed]** is a backend-owned credential with no user scopes, used only for public-data GitHub calls. It is not a per-user token.

---

# 42. Design Decisions and Rationale

| Decision | Reason | Trade-off |
|---|---|---|
| Modular monolith | Keeps deployment manageable | Less independently scalable |
| FastAPI | Strong Python ecosystem for analysis + ML | Backend is Python-specific |
| Next.js | Full-featured React framework | More frontend structure than plain React |
| Tailwind CSS + shadcn/ui | Consistent styling plus reusable UI components | Adds a component layer to maintain |
| PostgreSQL | Relational analysis data | Requires schema/migration management |
| Full Git clone | Reliable Git-history access | Uses temporary disk |
| Tree-sitter | Structural parsing across supported languages | Metric implementation requires care |
| BackgroundTasks | Simple asynchronous UX | Jobs can be lost on process restart |
| Random Forest only | Demonstrates meaningful ML integration without model-comparison scope | Limited by training dataset |
| Evidence-first LLM | Reduces hallucinated findings | Explanation quality depends on supplied evidence |
| Frontend-rendered static graph | Keeps graph generation simple while avoiding server-side image generation | Less exploration for very large repos |
| Public repos only | Smaller permission/security surface | Cannot analyze private repos |
| No code execution | Strong security boundary | Cannot dynamically measure runtime behavior |
| No combined health score | Transparent dimensions | More values for the user to interpret |

---

# 43. Important Open Decisions

These are the remaining implementation choices. Confirmed product decisions are intentionally excluded.

| # | Decision | Why it matters |
|---|---|---|
| 1 | Final JM1 feature subset | Determines which metrics are actually shared by Python/JavaScript/TypeScript inference |
| 3 | Coverage report precedence | Multiple supported formats may exist in one repository |
| 4 | Risk-label thresholds | Must be justified using validation results |
| 5 | ML success targets | Pre-committed F1 and ROC-AUC targets |
| 6 | Dependency-graph layout algorithm | Determines readability of the frontend static SVG |
| 7 | Large-graph grouping threshold | Determines when to switch to directory-level graph view |
| 8 | OpenAI model name | Cost/quality trade-off |
| 9 | Maximum AI snippet size | Cost/latency and prompt size |
| 10 | Hosting providers | Exact frontend/backend providers remain open |
| 11 | Final database indexes | Based on real query patterns |
| 12 | Deployment migration strategy | Manual vs automatic migrations |
| 13 | Own-code test coverage target | Final quality bar for the project itself |
| 14 | Function-to-file aggregation rule | Mean, top-3 mean, or maximum; determines the stored file score |
| 15 | GitHub API access after login | Proposed: list at the OAuth callback plus a server-side public-data credential |
| 16 | Failed-run retention | Completes the retention policy |
| 17 | Test-file treatment | Default summaries and ML scores for test files |

Confirmed and therefore closed: JM1 dataset, per-function prediction aggregated to a file-level score, essential-stage policy, RepoPulse-owned Tree-sitter metric extraction without a production metrics library, PostgreSQL-backed opaque sessions, no GitHub token persistence, same-parent-domain production hosts, unparseable-file policy, concurrency policy, coverage formats, deterministic alias resolution policy, four static thresholds plus lightweight duplicate detection, Vitest + Testing Library + Playwright, archived/empty repository display policy, source/test distinction, latest-10 retention, and Phase 7 portfolio deliverables.

# 44. Implementation Order

The architecture should be implemented in dependency order.

## Phase 0 — Repository foundations

```text
monorepo
Docker Compose
FastAPI skeleton
Next.js skeleton
PostgreSQL
Alembic
GitHub Actions
environment configuration
```

## Phase 1 — Authentication and repositories

```text
GitHub OAuth
session
user persistence
repository listing
ownership enforcement
authorization tests
```

## Phase 2 — Analysis core

```text
temporary clone
limits
file discovery
Tree-sitter
metrics
static analysis
security checks
analysis_run lifecycle
```

## Phase 3 — Repository context

```text
Git history
dependencies
static dependency graph
coverage reader
```

## Phase 4 — ML

```text
dataset compatibility
feature schema
training
evaluation
Random Forest artifact
backend inference
risk labels
```

## Phase 5 — AI

```text
evidence package
OpenAI client
prompt
explanation storage
failure handling
```

## Phase 6 — Frontend

```text
repository page
analysis status
dashboard
file detail
Git history
dependencies
history comparison
AI explanation UI
```

## Phase 7 — Hardening

```text
security review
error handling
logging
test coverage
CI
Docker builds
deployment
documentation
```

---

# 45. Architecture Invariants

The following rules should remain true throughout implementation.

### Invariant 1 — Backend owns authorization

The frontend may hide things, but it is never the security boundary.

### Invariant 2 — Repository code is never executed

No test execution, package installation, builds, or repository scripts.

### Invariant 3 — LLM does not create findings

Findings come from deterministic analysis and measured signals.

### Invariant 4 — ML output is probabilistic

The UI must say the model **estimates defect-proneness**, not that a bug definitely exists.

### Invariant 5 — No single opaque health score

Risk dimensions remain separate.

### Invariant 6 — AI is optional

A failed OpenAI request must not invalidate an otherwise successful repository analysis.

### Invariant 7 — Analysis is bounded

Repository size, source-file count, duration, temporary disk usage, and concurrency must be controlled.

### Invariant 8 — Training and inference features must match

The model must never receive a feature vector whose meaning/order differs from training.

### Invariant 9 — Temporary repository data is cleaned up

Clone directories are deleted after analysis, including failure paths.

### Invariant 10 — Scope remains deliberately small

Do not reintroduce:

```text
PR intelligence
webhooks
RAG
vector DB
repository chatbot
technical debt engine
multi-role RBAC
separate ML server
MLflow
CVE platform
interactive graph
```

---

# 46. Summary Architecture Diagram

```text
                               USER
                                │
                                ▼
                    ┌──────────────────────┐
                    │ Next.js + TypeScript │
                    │   Tailwind CSS       │
                    └──────────┬───────────┘
                               │ HTTPS
                               ▼
                    ┌──────────────────────┐
                    │       FastAPI        │
                    │   Modular Monolith   │
                    ├──────────────────────┤
                    │ Auth / Authorization │
                    │ GitHub Integration   │
                    │ Analysis Pipeline    │
                    │ Git History          │
                    │ Dependencies         │
                    │ Security             │
                    │ ML                   │
                    │ AI                   │
                    └───────┬─────┬────────┘
                            │     │
              ┌─────────────┘     └──────────────┐
              ▼                                  ▼
       ┌─────────────┐                    ┌──────────────┐
       │ PostgreSQL  │                    │ External APIs│
       │             │                    │              │
       │ Users       │                    │ GitHub       │
       │ Repositories│                    │ OpenAI       │
       │ Runs        │                    └──────────────┘
       │ Files       │
       │ Findings    │
       │ Predictions │
       │ Graph data  │
       │ Explanations│
       └─────────────┘

                       ANALYSIS PIPELINE

GitHub
  │
  ▼
Temporary Git Clone
  │
  ▼
File Discovery
  │
  ▼
Tree-sitter
  │
  ├───────────────┬────────────────┬────────────────┐
  ▼               ▼                ▼                ▼
Metrics      Static Rules      Dependencies    Security
  │               │                │                │
  └───────────────┴────────┬───────┴────────────────┘
                           ▼
                     Git History
                           │
                           ▼
                     Coverage Data
                           │
                           ▼
                  Feature Preparation
                           │
                           ▼
                   Random Forest
                           │
                           ▼
                 Defect-Proneness
                           │
                           ▼
                     Risk Factors
                           │
                           ▼
                      PostgreSQL
                           │
                           ▼
                       Dashboard
                           │
                    "Explain with AI"
                           │
                           ▼
                     Evidence Package
                           │
                           ▼
                       OpenAI API
                           │
                           ▼
                  Stored Explanation
```

---

# Decision Log

| Decision | Final choice |
|---|---|
| GitHub integration | GitHub OAuth App |
| Repository scope | Public repositories personally owned by the authenticated user; user-owned forks included |
| Branch | Default branch only |
| Repository retrieval | Temporary full `git clone`; local Git history; cleanup after analysis |
| Supported languages | Python, JavaScript, TypeScript |
| Parser | Tree-sitter |
| Analysis duration | Maximum 5 minutes; configurable |
| Static-analysis defaults | Complexity > 10; function > 50 LOC; file > 500 LOC; imports > 20 |
| ML dataset | JM1 selected; final compatible feature subset determined by cross-language compatibility; supplied `jm1.csv` committed under `ml/data/`; Kaggle-reported license is unknown and must be documented without claiming unrestricted redistribution; deduplicated on metrics (excluding `id`) with conflicting-label vectors removed before splitting |
| ML granularity | Per-function/method predictions in memory; qualifying top-level executable units may contribute; aggregate to one file-level score; no function-level table |
| Riskiest-function metadata | Nullable function name/start/end lines; highest-probability function/method among functions/methods only; deterministic tie-break; null only when no function/method is predicted |
| Prediction status | `scored`, `no_ml_unit`, or `ml_failed`; unscored rows have null model_version/probability/class, show **Not scored** with reason, and have no risk label |
| Metric implementation | RepoPulse-owned Tree-sitter extraction; no production metrics library |
| Session mechanism | PostgreSQL-backed opaque server-side sessions with secure HTTP-only cookie |
| OAuth token storage | Do not persist GitHub access tokens |
| Production cookie/domain strategy | Frontend and backend hosts use the same parent/registrable domain; exact providers remain open |
| Coverage | Cobertura XML + lcov + Istanbul JSON |
| Unparseable files | Minor parse errors continue; unusable files are skipped and recorded as warnings |
| Essential stages | Source parsing/metrics/static analysis/security and persistence are essential; Git history, dependencies, coverage, ML, risk, and AI are non-essential enrichment stages |
| Analysis concurrency | One active analysis per repository plus a small global cap |
| Static-analysis extras | Four threshold rules plus lightweight duplicate-code detection |
| JM1 anomalous rows | Drop `id=1` (the only row with `lOCode` > `loc`) and all 1,332 rows with `total_Op` = 0 and `loc` >= 1; preprocessing order: drop the five `?` rows, drop `id=1`, drop the zero-operator group, remove conflicting-label metric vectors and deduplicate, then split. |
| Frontend stack | Next.js + TypeScript + Tailwind CSS + shadcn/ui + Recharts |
| Frontend/E2E tooling | Vitest + Testing Library + Playwright |
| Dependency graph | Backend returns `{nodes, edges}`; frontend renders a static non-interactive SVG |
| Test files | Analyze and report them while distinguishing source vs test |
| Repository display | Archived/empty repositories remain visible with explanatory status; Analyze disabled when unsupported |
| Analysis retention | Latest 10 completed analyses per repository |
| Production topology | Frontend and backend deployed on different hosts |
| Phase 7 portfolio output | Live deployment + 2–3 minute demo + self-analysis |
| Python runtime | Python 3.12; Docker base image `python:3.12-slim-bookworm`; local development uses a `py -3.12`-created virtual environment |
| PostgreSQL driver and URL scheme | psycopg 3 (`psycopg[binary]`), SQLAlchemy URL scheme `postgresql+psycopg://`. PostgreSQL major version 17 (development); production host to match. |
| Verified wheel packages (Python 3.12) | fastapi 0.143.0, uvicorn 0.54.0, pydantic 2.14.0, SQLAlchemy 2.1.4, alembic 1.20.0, tree-sitter 0.26.0, tree-sitter-python 0.25.0, tree-sitter-javascript 0.25.0, tree-sitter-typescript 0.23.2, scikit-learn 1.9.1, psycopg 3.3.6 (binary) — all have prebuilt wheels for Python 3.12 on PyPI; confirmed via `pip install --dry-run --only-binary=:all:` on 2026-10-10 |
| JM1 metric method | No metrics library in production. RepoPulse owns one Tree-sitter extractor for Python, JavaScript, and TypeScript. Radon, Lizard, and typhonjs-escomplex may be used only as G0 cross-checks, never as production sources. Revisit only if the 0.9.9 prototype cannot meet the compatibility rule. |
| JM1 compatibility rule | Admit a feature to the serving schema only if its definition is verified by the data check or fixed by an approved convention, it is implemented consistently across all three languages with each approximation justified in the matrix (consistently, not identically), and its serving range stays within a stable range of JM1 (0.9.9). Derived fields use only admitted features. Record before model results. |
| Prediction-unit rules | Apply the same rules to Python, JavaScript, and TypeScript. Units are outermost function-like nodes with block/statement bodies; nested functions, closures, and callbacks belong to their containing unit. Python lambdas and expression-bodied arrows are not units; TypeScript overload signatures and bodyless abstract/declare functions are not units. Qualifying module-level code is defined by control flow or a call expression outside imports, decorators, and exports; unit subtrees are excluded. See `ml/README.md` 0.9.8 for the complete rules and fixture cases. |

# 47. Final Architecture Statement

RepoPulse is intentionally designed as a **secure, evidence-first modular monolith**.

The browser provides the interface. FastAPI owns authentication, authorization, repository access, analysis orchestration, ML inference, and AI integration. PostgreSQL stores application and analysis state. GitHub provides identity and public repository data. OpenAI provides optional explanations.

The most important architectural boundary is:

```text
Untrusted repository
        │
        ▼
Read-only deterministic analysis
        │
        ▼
Structured evidence
        │
        ├──► Random Forest → defect-proneness estimate
        │
        └──► OpenAI → explanation
```

This keeps RepoPulse technically ambitious enough to demonstrate parsing, graphs, Git, databases, authentication, machine learning, LLM integration, full-stack development, testing, and DevOps — while avoiding infrastructure that does not materially improve the core product.

