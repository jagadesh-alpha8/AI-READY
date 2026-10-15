# AIOS Discovery Sprint — Project Workflow & Technical Report

> **Scope.** Every statement below was traced through the actual repository at
> `D:\AI READY` (branch `main`, HEAD `1473056 "filters"` **plus the uncommitted
> working tree as of 13 Oct 2026** — the AI processing modes, AI usage tracking,
> and the whole benchmark backend (`apps.benchmarks`, `apps.assessments`) are not
> committed yet). Where a capability is commonly expected but genuinely absent,
> this report says **"Not found in the codebase"** rather than guessing. No secret
> values are reproduced.
>
> **Status legend:** `[IMPLEMENTED]` · `[PARTIAL]` · `[UI-ONLY / DEMO DATA]` ·
> `[PLANNED]` · `[DEAD/UNUSED]`
>
> ⚠️ **Read this before anything else.** The product now has **two halves**:
>
> * **The AI Readiness Audit** (the original platform) — documents → AI facts →
>   human review → 8-pillar CRI → baseline → recommendations → report. Every
>   screen of it, and every module around it (Evidence Intelligence, CRI &
>   Benchmark Intelligence, Transformation Plan, Goals & Tasks, AI Copilot,
>   Reminders, Compliance Mapping, UAT Readiness, Admin / Settings), now reads
>   **real API data**. The nine prototype screens that used to render hardcoded
>   sample content were rewired to the existing backend (§3.12).
> * **The Benchmark Intelligence library** (new, InGage-internal) — official
>   source documents → AI-drafted, human-approved requirements → benchmarks with
>   L3/L2/L1 levels, evidence rules and applicability rules → versioned, approved
>   releases → a daily watcher of official sites → **benchmark assessments of a
>   college against the published release** (§3.17–§3.19).
>
> The one place sample data is still on screen: three tabs of **Benchmark
> Studio** (Editor, Approvals, AI candidates) still render the prototype's twelve
> seed benchmarks, and the page says so. Its other seven tabs are real.
>
> ### What changed since this report was first written
>
> First written at `8742ea7`. Everything below has landed since, and every affected
> section has been updated rather than appended to:
>
> | Change | Effect on this report |
> |---|---|
> | **Navigation rebuilt** around the 12-module product plan | §2, §4.3, §4.8, §19 — the app is no longer a bare 10-screen wizard; those ten steps are now one module among several |
> | **Institution DNA** module built (3 new models, 3 nested sub-resources, new pages) | §1, §3, §4, §5, §6, §7, §8, §19, §23 |
> | **Project Status Dashboard** page added | §1, §4, §19, §25 |
> | **Sprint Setup narrowed** — no longer creates institutions, no sprint-mode picker | §2.3, §3.3, §7 |
> | **Institution delete became a hard delete**, and institution *creation* moved to the Institution DNA list page | §3.2, §5.3, §7.1 |
> | **`apps.vector_store` added** — a 12th Django app: Pinecone-backed semantic retrieval over college document text | §1, §3.11, §5, §6, §7, §9, §11, §12, §13, §17, §19, §21, §22, §24, §25, §27 |
> | **Status Dashboard left the sidebar** — now a standalone route outside the app shell, reached by URL | §4.2, §4.3, §19, §25 |
> | **Nine modules ported from the InGage prototype**, frontend-only, on demo data — including a **second, parallel CRI scoring model** | §1, §3.12, §4, §19, §25, §27 |
> | **Ported modules rewired to real data** (`44b57e9`, `398bd21`) — eight of the nine now derive everything from existing endpoints; the second CRI model is no longer rendered; AI Chatbot became **AI Copilot** (deterministic answers + vector evidence search, no LLM) | §1, §3.12, §4, §25, §27 |
> | **Admin / Settings built** — scoring rubric, account, **user administration** (`/api/v1/users`), AI usage & billing | §1, §3.16, §4, §5, §7, §8 |
> | **Drive import reworked** (`f7195dc`, `e35fdc4`) — parallel folder walk and downloads, imports **every** supported file (not one per checklist slot), live progress, and a **Stop** button | §3.4, §7, §10.4, §11 |
> | **OCR is real** (`e35fdc4`) — PyMuPDF text layer + **PaddleOCR** for scanned pages, plus header/footer cleanup; pdfplumber no longer used | §1, §9.2, §10, §13, §14, §21, §22, §25 |
> | **Extraction control** (`1473056`) — Stop / Process per document, Stop all, Process incomplete, process a ticked selection; JSON-tolerant parsing for OpenAI-compatible routers; confirming a fact closes its "unconfirmed" gap | §2.3, §3.6, §7, §9 |
> | **AI processing modes** — `AI_PROCESSING_MODE=single \| multi_router`; 4-router pool with Redis leases; worker count derived from the mode; health command | §3.14, §9.1, §11, §13, §24 |
> | **AI usage & cost tracking** — an `AIUsage` row per AI call, priced at call time; per-sprint and platform billing views | §3.15, §6, §7, §9.5 |
> | **`apps.benchmarks` added** — Source Library, requirement drafting, benchmark catalogue, levels, evidence rules, applicability, releases, and the **daily source watcher** (the first Celery Beat job) | §1, §2.4, §3.17, §3.18, §5, §6, §7, §11, §12, §13, §19, §23 |
> | **`apps.assessments` added** — benchmark assessments of a college: profile, cycles, evidence upload and review, four separate scores, finalize | §1, §2.4, §3.19, §5, §6, §7, §19 |
> | **Domain + HTTPS** — `https://ai.ingageedutech.com` (Let's Encrypt), the four routers on HTTPS too | §14 |
> | **Pending-work round (15 Oct)** — login rate limits, API docs off in production, admin login limit, health check + post-deploy check, Redis cache; **benchmark candidates** from watcher changes (stage 4b); **improvement plan** (stage 6: gaps, templates, initiatives, tasks); audit documents reusable as evidence; Word / Excel / CSV / image reading; Benchmark Studio seed tabs and prototype data removed | §1, §3.12, §3.18–§3.21, §7, §10, §14, §17, §25, §27 |
>
> Backend test count moved **481 → 498** (Institution DNA) **→ 578** (vector store)
> **→ 779 → 816** (now); migrations **20 → 21 → 22 → 39 → 42**; Django apps **11 → 12 → 14**.

---

## Table of contents

| # | Section |
|---|---|
| 1 | [Project overview](#1-project-overview) |
| 2 | [Complete project workflow](#2-complete-project-workflow) |
| 3 | [Every major feature](#3-every-major-feature) |
| 4 | [Frontend architecture](#4-frontend-architecture) |
| 5 | [Backend architecture](#5-backend-architecture) |
| 6 | [Database architecture](#6-database-architecture) |
| 7 | [API documentation](#7-api-documentation) |
| 8 | [Authentication & authorization](#8-authentication--authorization) |
| 9 | [AI / LLM workflow](#9-ai--llm-workflow) |
| 10 | [File upload & document processing](#10-file-upload--document-processing) |
| 11 | [Background jobs — Celery & Redis](#11-background-jobs--celery--redis) |
| 12 | [External services](#12-external-services) |
| 13 | [Configuration & environment variables](#13-configuration--environment-variables) |
| 14 | [Deployment architecture](#14-deployment-architecture) |
| 15 | [Complete user journeys](#15-complete-user-journeys) |
| 16 | [Error handling](#16-error-handling) |
| 17 | [Security analysis](#17-security-analysis) |
| 18 | [Performance analysis](#18-performance-analysis) |
| 19 | [Project folder structure](#19-project-folder-structure) |
| 20 | [Architecture diagrams](#20-architecture-diagrams) |
| 21 | [Technology stack](#21-technology-stack) |
| 22 | [Dependencies](#22-dependencies) |
| 23 | [Important files](#23-important-files) |
| 24 | [Project execution guide](#24-project-execution-guide) |
| 25 | [Dead / unused / scaffold code](#25-dead--unused--scaffold-code) |
| 26 | ["How the project works" — presentation script](#26-how-the-project-works--presentation-script) |
| 27 | [Final project summary](#27-final-project-summary) |

---

# 1. Project overview

## Project name

**AIOS AI Readiness Discovery Sprint Platform** — built by **InGage Technologies**.

- Frontend npm package: `aios-discovery-sprint-frontend` v1.0.0
- Celery app name: `aios_backend`
- OpenAPI title: `AIOS Discovery Sprint API` v1.0.0
- Container images: `ghcr.io/jagadesh-alpha8/ai-ready-backend`, `ghcr.io/jagadesh-alpha8/ai-ready-frontend`

The tagline shown on the login screen (`frontend/src/pages/auth/Login.tsx`):

> *"24-48 Hour Fast-Track Discovery Platform for Higher Education Institutions by InGage Technologies."*

## Project purpose — in plain language

A college or university wants to know **how ready it is to adopt AI** — in its
teaching, its labs, its faculty skills, its research, its placements, and its
governance. Answering that properly normally means a consultant spending weeks
reading through accreditation paperwork.

This platform compresses that into **24–48 hours**:

1. The institution uploads its existing paperwork — NAAC Self-Study Report, AQAR,
   AICTE approval, faculty lists, placement reports, lab inventories — either by
   dragging files in or by pasting one **Google Drive folder link**.
2. **AI reads every page** and pulls out specific facts ("Total faculty: 312",
   "AI-certified faculty: 18", "Placement rate: 84%"), always quoting the exact
   sentence it took each fact from and stating how confident it is.
3. Anything the AI is unsure about, or that contradicts another document, becomes
   a **gap** on a to-do list. The campus staff member who actually owns that data
   (the Registrar, the HR Officer, the Lab Admin…) confirms or corrects it.
4. Once the facts are confirmed, the platform computes a **Campus Readiness Index
   (CRI)** — a 0–100 score across **eight pillars**, plus a separate *confidence*
   number saying how much evidence backs that score.
5. An InGage consultant **approves the baseline**, the system generates
   **recommendations** with expected score improvements, and produces a
   downloadable **PDF/DOCX Discovery Report**.

**The second half — Benchmark Intelligence.** Alongside the audit, InGage is
building its own **benchmark library**: what "good" looks like for an Indian
college, traced to official sources. Staff register the official documents (UGC,
AICTE, NAAC, NBA, DGT, CERT-In, UNESCO, NIST…), the AI drafts candidate
requirements that must quote the source word for word, experts approve them,
link them to benchmarks, write the three maturity levels and the evidence each
level needs, say which colleges each benchmark applies to, and publish an
approved **release**. A daily watcher checks the official pages for changes. A
college is then **assessed against the published release** — it uploads
evidence, InGage reviews it, and four separate scores come out per benchmark.

## Business problem

| Problem | How it showed up before |
|---|---|
| AI-readiness assessment is slow and manual | A consultant reads hundreds of pages of accreditation documents by hand |
| Institutional data is scattered and inconsistent | The same number (faculty count, enrolment) appears differently in the SSR, the AQAR, and the HR list |
| No one can tell *why* a score is what it is | A consultant's spreadsheet score has no traceable evidence behind it |
| Data ownership is diffuse | The person who can confirm "how many AI-certified faculty" is not the person who uploaded the file |
| Reports are bespoke every time | Each engagement produces a hand-written deck with no reusable structure |

## Solution provided

| Capability | Implementation |
|---|---|
| Automated document ingestion | Direct upload **and** Google Drive folder import (`apps/documents`) |
| AI reading + structured extraction | Provider-agnostic LLM with strict JSON-schema output (`apps/extraction/services`) |
| Anti-hallucination guarantees | Every fact must cite a real page in the chunk it was extracted from, and a real snippet; **Python re-validates every AI field** |
| Human-in-the-loop review | Confirm / correct / reject / request-evidence, with an append-only audit trail (`apps/facts`) |
| Automatic gap detection | Five deterministic gap types + AI-adjudicated conflicts (`apps/gaps`, `apps/extraction/services/conflict_checker.py`) |
| Explainable, configurable scoring | Nine-step CRI engine reading DB-configurable pillar/criterion weights (`apps/scoring/services/cri_engine.py`) |
| Governance / sign-off | Baseline approval workflow with a locked, immutable `ScoringRun` (`apps/scoring/services/baseline.py`) |
| Actionable output | Data-derived recommendations + versioned PDF/DOCX report (`apps/recommendations`, `apps/reports`) |
| Traceable benchmark library | Versioned sources → quote-verified requirements → benchmarks → approved, hashed releases (`apps/benchmarks`) |
| Change monitoring | Daily watcher of official source pages; records changes for human review, never auto-publishes (`apps/benchmarks/services/watcher.py`) |
| Assessment against benchmarks | Evidence requests from the release, reviewer scoring, four separate scores (`apps/assessments`) |
| Cost visibility | Every AI call's tokens and cost recorded (`apps/extraction` `AIUsage`) |

## Main users / roles

Eleven roles, defined in `backend/apps/accounts/models.py` (`User.Role`). **One role
per user** — there is no many-to-many role model.

| Role key | Label | Scope | Typical actions |
|---|---|---|---|
| `super_admin` | Super Admin | **Cross-institution** | Everything, all institutions; Django admin |
| `consultant` | InGage Consultant | **Cross-institution** | Runs sprints, approves baselines, **only role (with super_admin) that may edit recommendations** |
| `institution_admin` | Institution Admin | Own institution | Create/modify sprints, approve baselines, manage documents |
| `iqac_coordinator` | IQAC Coordinator | Own institution | NAAC/AQAR evidence, review facts, manage documents |
| `registrar` | Registrar | Own institution | Enrolment/approval records, review facts |
| `hod` | Head of Department | Own institution | Curriculum/department facts |
| `hr_officer` | HR Officer | Own institution | Faculty records |
| `lab_admin` | Lab Admin | Own institution | Lab & compute infrastructure |
| `placement_officer` | Placement Officer | Own institution | Placement/industry facts |
| `faculty` | Faculty | Own institution | Course-level AI engagement facts |
| `viewer` | Viewer | Own institution | **Read-only** — excluded from every write gate |

`User.CROSS_INSTITUTION_ROLES = (SUPER_ADMIN, CONSULTANT)` is the single definition
of "sees everything", consumed by `apps/accounts/permissions.py`.

## Major features

| # | Feature | App | Status |
|---|---|---|---|
| 1 | JWT auth (login / refresh / logout-blacklist / me / change-password / forgot password) | `accounts` | `[IMPLEMENTED]` |
| 2 | Institution CRUD | `institutions` | `[IMPLEMENTED]` |
| 2a | **Institution DNA** — profile + leadership + departments + IT systems + digital-maturity rating | `institutions` | `[IMPLEMENTED]` |
| 3 | Sprint lifecycle state machine (10 statuses) + one-call overview | `sprints` | `[IMPLEMENTED]` |
| 4 | Document upload: allowlist, 50 MB cap, SHA-256 dedupe, secure download | `documents` | `[IMPLEMENTED]` |
| 5 | Google Drive folder import — whole folder tree, parallel listing and downloads, live progress, **Stop** | `documents` | `[IMPLEMENTED]` |
| 6 | 7-stage AI extraction pipeline on Celery, with retry/backoff; per-document Stop / Process, Stop all, Process incomplete | `extraction` | `[IMPLEMENTED]` |
| 7 | Multi-provider AI (OpenAI / Anthropic / OpenAI-compatible) | `extraction` | `[IMPLEMENTED]` |
| 7a | **AI processing modes** — `single` endpoint or `multi_router` (4 routers, Redis-leased slots, cooldown on failure) | `extraction`, `config` | `[IMPLEMENTED]` — see §3.14 |
| 7b | **AI usage & cost tracking** — one `AIUsage` row per call, priced at call time; sprint and platform billing views | `extraction` | `[IMPLEMENTED]` — see §3.15 |
| 8 | Document reading: PDF via **PyMuPDF** + **PaddleOCR** for scanned pages; **Word (.docx), Excel (.xlsx), CSV and images** (OCR); old .doc/.xls and .zip get a clear "can't read" notice | `extraction` | `[IMPLEMENTED]` — see §10.1 |
| 9 | Fact review: confirm/correct/reject/request-evidence + history | `facts` | `[IMPLEMENTED]` |
| 10 | Gap detection (5 types) + AI conflict adjudication | `gaps`, `extraction` | `[IMPLEMENTED]` |
| 11 | 8-pillar CRI scoring engine + run history | `scoring` | `[IMPLEMENTED]` |
| 12 | Baseline approval / provisional approval / return-for-correction | `scoring` | `[IMPLEMENTED]` |
| 13 | Recommendation generation (3 generators) + consultant editing | `recommendations` | `[IMPLEMENTED]` |
| 14 | Versioned report generation → PDF (fpdf2) + DOCX (python-docx) | `reports` | `[IMPLEMENTED]` |
| 15 | Cross-sprint dashboard with live metrics | `dashboard` | `[IMPLEMENTED]` |
| 15a | **Project Status Dashboard** — build-progress report against the 11-module plan | frontend only | `[IMPLEMENTED]` — hand-maintained data, see §25 |
| 15b | **Vector store** — chunk/embed college document text into Pinecone; institution-isolated semantic evidence search | `vector_store` | `[IMPLEMENTED]` backend + API, **optional**; no UI consumes it yet — see §3.11 |
| 15c | **CRI & Benchmark Intelligence** — the pillar CRI, the gaps behind it and the roadmap | frontend over `scoring` / `gaps` / `recommendations` | `[IMPLEMENTED]` — real data; see §3.12 |
| 15d | **Benchmark Studio** — the benchmark library workspace (10 tabs), staff only | `benchmarks` | `[IMPLEMENTED]` for 7 tabs (Catalogue, Requirements, Applicability, Levels, Sources, Releases, Watcher); **`[UI-ONLY / DEMO DATA]`** for Editor, Approvals, AI candidates |
| 15e | **Evidence Intelligence · Transformation Plan · Goals & Tasks · AI Copilot · Reminders · Compliance Mapping · UAT Readiness** | frontend over existing endpoints | `[IMPLEMENTED]` — derived from real sprint data; several say plainly what they cannot do (no task model, no notifications) — see §3.12 |
| 15f | **Admin / Settings** — scoring rubric (read-only), account, user administration, AI usage & billing | `accounts`, `scoring`, `extraction` | `[IMPLEMENTED]` — see §3.16 |
| 16 | OpenAPI schema / Swagger / ReDoc | `config` | `[IMPLEMENTED]` |
| 17 | Celery Beat / scheduled tasks | `config`, `benchmarks` | `[IMPLEMENTED]`, **off by default** — one job, the daily source watcher, scheduled only when `WATCHER_ENABLED=true` (§11) |
| 17a | **Benchmark library** — source register, versioned source files, AI-drafted requirements, catalogue, linking, L3/L2/L1 levels, evidence rules, applicability rules, versioned releases with four-eyes approval | `benchmarks` | `[IMPLEMENTED]` (backend + Studio UI) — **content is still placeholder**: 60 imported benchmarks share identical placeholder levels, and no release is published yet. See §3.17 |
| 17b | **Daily source watcher** — snapshots of official pages, change events with importance and impact, human review | `benchmarks` | `[IMPLEMENTED]` — every feed starts disabled. See §3.18 |
| 17b2 | **Benchmark candidates** — material watcher changes become proposed library changes, approved by expert role (a different person per role) | `benchmarks` | `[IMPLEMENTED]` — see §3.20 |
| 17c | **Benchmark assessment** — college profile, assessment cycles on the published release, evidence upload + review (incl. reusing audit documents), four separate scores, finalize | `assessments` | `[IMPLEMENTED]` — see §3.19 |
| 17d | **Improvement plan** — typed gaps from a finalized assessment, expert templates, initiatives and tasks; gaps close only with accepted evidence | `assessments` | `[IMPLEMENTED]` — see §3.21 |
| 18 | User registration / self-signup | — | **Not found in the codebase.** Admins create users (`/api/v1/users`, §3.16); there is no self-signup |
| 19 | Password reset by email | `accounts/password_reset.py` | `[IMPLEMENTED]` — emailed one-time link (1 hour), same answer for unknown emails, rate-limited, signs out everywhere |
| 20 | Email/notification sending | — | **Not found in the codebase** — no mail backend configured |

## Technology stack (summary — full table in §21)

**Backend:** Python 3.12, Django 5.0.x, Django REST Framework, SimpleJWT (with
token blacklist), Celery 5.3+, Redis 5+, PostgreSQL 16 (SQLite fallback for local
dev), `drf-spectacular`, `django-filter`, **PyMuPDF** + **PaddleOCR** (PDF text and
OCR), `fpdf2`, `python-docx`, `beautifulsoup4` (watcher), `openpyxl` (register
imports), `openai>=1.50,<2`, `anthropic>=0.40,<1`, `pinecone>=5,<7` (optional — see
§3.11), Gunicorn.

**Frontend:** React 18.2, TypeScript 5.2, Vite 5.1, React Router 6.22, Axios 1.6,
Tailwind CSS 3.4, `lucide-react` icons.

**Infrastructure:** Docker + Docker Compose, GitHub Container Registry (GHCR),
GitHub Actions CI/CD, nginx 1.27-alpine (SPA + reverse proxy), deployed to a
**GCP VM** at `/opt/ai-ready`.

## High-level architecture

```mermaid
graph TB
    subgraph Browser["User's browser"]
        SPA["React 18 SPA<br/>(Vite build, 38 screens)"]
    end

    subgraph VM["GCP VM — /opt/ai-ready — docker compose"]
        NGX["frontend container<br/>nginx:1.27-alpine :80<br/>SPA + /api + /admin proxy"]
        API["backend container<br/>gunicorn, 3 workers<br/>Django 5 + DRF :8000"]
        CEL["celery container<br/>same image; worker slots<br/>from AI_PROCESSING_MODE"]
        BEAT["celery-beat container<br/>daily watcher only<br/>(WATCHER_ENABLED)"]
        PG[("db container<br/>postgres:16-alpine")]
        RDS[("redis container<br/>redis:7-alpine<br/>broker + router leases")]
        MEDIA[["media_data volume<br/>uploads · reports · source library<br/>· snapshots · assessment evidence"]]
        PADDLE[["paddle_models volume<br/>OCR models"]]
        STATIC[["static_data volume<br/>Django admin assets"]]
    end

    subgraph Ext["External services"]
        AI["AI provider<br/>OpenAI / Anthropic /<br/>OpenAI-compatible endpoint<br/>or 4 routers (multi_router)"]
        GD["Google Drive REST v3"]
        GOV["Official source sites<br/>(UGC, AICTE, NAAC, NBA…)"]
        PC["Pinecone<br/>vector index<br/>(OPTIONAL)"]
    end

    SPA -->|"HTTP /api/v1/**<br/>Bearer JWT"| NGX
    NGX --> API
    API --> PG
    API -->|".delay()"| RDS
    BEAT -.->|"schedule"| RDS
    RDS -->|"consume"| CEL
    CEL --> PG
    CEL --> MEDIA
    CEL --> PADDLE
    CEL -->|"chat.completions / messages"| AI
    CEL -->|"files.list / files.get"| GD
    CEL -.->|"daily fetch,<br/>robots.txt respected"| GOV
    CEL -.->|"upsert chunks<br/>only when configured"| PC
    API -.->|"evidence search"| PC
    API --> MEDIA
    API --> STATIC
    NGX -.->|"/static/"| STATIC
```

Dotted edges are optional: the vector store (with `PINECONE_API_KEY` unset they do
not exist at runtime) and the watcher (only when `WATCHER_ENABLED=true` and a feed
is switched on). Nothing else in the diagram changes without them.

**Defining architectural properties, all verified in code:**

* **Domain-per-app.** Fourteen Django apps, each owning its models/views/serializers/
  services. Nested `/sprints/<id>/…` routes are composed in `apps/sprints/urls.py`
  by importing views from their owning app — so URL shape does not force logic into
  one app.
* **UUID primary keys everywhere.** No integer IDs are exposed by any endpoint.
* **Nothing is fabricated.** This is an explicit, repeated design stance in the
  code: empty sources produce honest empty sections, the AI is instructed to
  return `null` rather than guess, and Python re-validates every AI-supplied field.
* **Append-only history.** `FactReviewHistory`, `BaselineDecisionHistory`,
  `ScoringRun.pillar_snapshot`, and `Report.version` all preserve prior state
  rather than overwriting it. The benchmark side goes further: `SourceAuditEvent`
  refuses updates and deletes, approved source versions freeze their file fields,
  published release items are immutable, and evidence reviews are append-only.
* **Score against a frozen release, never live data.** A benchmark assessment
  reads the published release item's JSON snapshot (levels, evidence rules,
  applicability rules, requirements, with a SHA-256 hash), so a later draft edit
  can never change who is assessed or how.
* **Deterministic where possible, AI only where necessary.**
  `apps/extraction/services/gap_detector.py` states it plainly: gap detection is
  100% rule-based; AI is reserved for the one judgement that genuinely needs
  interpretation ("do these two facts actually contradict each other?").
* **Institution scoping is enforced twice** — by queryset filtering on list
  endpoints and by an explicit object-level check on nested sub-resources
  (`apps/sprints/access.py::get_authorized_sprint`).
---

# 2. Complete project workflow

The **AI Readiness Audit** is a **linear 10-step wizard** driven by a sprint's
status, and it is the flow this section traces end to end.

It is no longer the whole application, though. The sidebar
(`frontend/src/components/Sidebar.tsx`) presents the product plan as one group,
and those ten numbered steps sit *inside* one of its modules:

```text
PLATFORM MODULES
  Dashboard                         ← live
  Institution DNA                   ← live
  AI Readiness Audit                ← live; owns the 10 steps below
     1. Sprint Setup ... 10. Report & Export
  Evidence Intelligence             ← live (derived from sprint data)
  CRI & Benchmark Intelligence      ← live (pillar CRI, gaps, roadmap)
  Benchmark Studio                  ← "admin": InGage staff only
  Benchmark Assessment              ← live (stage 5)
  Transformation Plan · Goals & Tasks · AI Copilot · Reminders
  Compliance Mapping · UAT Readiness · Admin / Settings   ← all live
```

Every entry is navigable now. The Project Status Dashboard is not in the menu
(reached by URL, §4.3). Nothing collapses — every audit step is always on screen.

The benchmark side has its own flow, described in §2.4.

## 2.1 The sprint state machine

Defined in `backend/apps/sprints/models.py::Sprint.ALLOWED_TRANSITIONS`. `archived`
is terminal and reachable from every non-terminal state.

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> collecting : first document uploaded
    collecting --> processing : POST /extraction-jobs
    processing --> reviewing : all extraction jobs finished
    reviewing --> scoring : POST /score
    scoring --> baseline_pending : first GET /baseline
    baseline_pending --> baseline_approved : approve / approve-provisional
    baseline_pending --> reviewing : return for correction
    baseline_approved --> report_ready : report generated
    report_ready --> completed
    completed --> archived
    draft --> archived
    collecting --> archived
    processing --> archived
    reviewing --> archived
    scoring --> archived
    baseline_pending --> archived
    baseline_approved --> archived
    report_ready --> archived
    archived --> [*]
```

Each status carries a **deterministic completion milestone**
(`Sprint.STATUS_COMPLETION_MILESTONES`), applied automatically on a status change
unless the caller supplies an explicit `completion_percentage`:

| Status | % | Status | % |
|---|---|---|---|
| `draft` | 0 | `baseline_pending` | 80 |
| `collecting` | 15 | `baseline_approved` | 85 |
| `processing` | 35 | `report_ready` | 90 |
| `reviewing` | 55 | `completed` | 100 |
| `scoring` | 75 | `archived` | 100 |

`Sprint.BASELINE_LOCKED_STATUSES = {baseline_approved, report_ready, completed}` —
once in any of these, `POST /score` is **refused**, so an approved baseline's
numbers can never drift out from under a report generated against them.

## 2.2 The end-to-end request/data flow

```mermaid
sequenceDiagram
    actor U as User (browser)
    participant SPA as React SPA
    participant NX as nginx
    participant API as Django/DRF
    participant DB as PostgreSQL
    participant R as Redis
    participant W as Celery worker
    participant AI as AI provider
    participant GD as Google Drive

    U->>SPA: Screen 1 — create sprint
    SPA->>NX: POST /api/v1/sprints (Bearer JWT)
    NX->>API: proxy_pass backend:8000
    API->>API: JWTAuthentication → CanManageSprint → institution check
    API->>DB: INSERT sprint (status=draft)
    API-->>SPA: 201 Sprint

    U->>SPA: Screen 2 — upload files / paste Drive link
    SPA->>API: POST /sprints/{id}/upload-file (multipart)
    API->>API: extension allowlist + 50MB cap + SHA-256 dedupe
    API->>DB: INSERT document (status=uploaded); sprint draft→collecting
    Note over API,GD: Drive path instead:<br/>POST /drive-import-jobs → Celery → GD list+download → same create path

    U->>SPA: Screen 3 — Start AI Processing
    SPA->>API: POST /sprints/{id}/extraction-jobs
    API->>DB: sprint collecting→processing; INSERT ExtractionJob per document
    API->>R: run_extraction_job.delay(job_id)
    API-->>SPA: 201 [ExtractionJob]  (returns immediately)

    R->>W: deliver task
    loop 7 pipeline stages
        W->>DB: UPDATE job.current_step / progress_percentage
    end
    W->>AI: classify (1 call)
    W->>W: PyMuPDF reads pages (PaddleOCR for scanned ones)
    W->>AI: extract facts (1 call per ≤12k-char chunk)
    W->>DB: INSERT ExtractedFact rows
    W->>DB: INSERT GapItem rows (deterministic)
    W->>AI: conflict verdicts (≤10 calls)
    W->>DB: INSERT conflict GapItems; document→processed
    W->>DB: last job done → sprint processing→reviewing + sprint-wide gap pass

    loop every 3s
        SPA->>API: GET /sprints/{id}/extraction-jobs
    end

    U->>SPA: Screens 4–6 — review facts, resolve gaps
    SPA->>API: POST /facts/{id}/confirm | correct | reject | request-evidence
    API->>DB: INSERT FactReviewHistory (old value) + UPDATE fact

    U->>SPA: Screen 7 — Live CRI
    SPA->>API: POST /sprints/{id}/score
    API->>DB: run 9-step engine → PillarScore ×8 + ScoringRun + sprint.overall_cri

    U->>SPA: Screen 8 — Baseline approval
    SPA->>API: GET /sprints/{id}/baseline   (bootstraps PENDING baseline)
    SPA->>API: POST /baseline/approve
    API->>DB: Baseline→approved; sprint→baseline_approved

    U->>SPA: Screen 9 — Recommendations
    SPA->>API: POST /sprints/{id}/recommendations/generate
    API->>DB: 3 generators → Recommendation rows

    U->>SPA: Screen 10 — Report
    SPA->>API: POST /sprints/{id}/reports
    API->>R: generate_report_task.delay(report_id)
    W->>DB: build 11 sections
    W->>W: render PDF (fpdf2) + DOCX (python-docx)
    W->>DB: report→ready; sprint baseline_approved→report_ready
    SPA->>API: GET /reports/{id}/download?file=pdf
    API-->>U: FileResponse (attachment)
```

## 2.3 Per-step breakdown (the 16 dimensions requested)

### Step 1 — Create a sprint

| Dimension | Detail |
|---|---|
| **1. User does** | **Selects** an existing institution and sets the academic year. That is the whole form now — see the two narrowings below |
| **2. Frontend** | `pages/sprints/SprintSetup.tsx` (~150 lines) |
| **3–5. API** | `POST /api/v1/sprints` (plus `GET /institutions` to populate the select) |
| **6. Request** | `{institution_id, academic_year}` |
| **7. Auth** | Bearer JWT required; `CanManageSprint` → write requires `super_admin`/`consultant`/`institution_admin` |
| **8. Controller** | `apps/sprints/views.py::SprintViewSet.create` → `perform_create` |
| **9. Business logic** | `user_can_access_institution()` re-checked at create time; `Sprint.save()` auto-assigns `sprint_code = SPR-<first 8 of UUID, uppercased>` |
| **10. DB** | `sprints_sprint` (INSERT), FK → `institutions_institution`, `accounts_user` |
| **11–12. External / jobs** | None |
| **13. Sequence** | Auth → role gate → institution gate → serializer validation → INSERT |
| **14. Response** | `201` + `SprintSerializer` |
| **15. Frontend use** | Navigates to `/sprint/{id}/upload` |
| **16. User sees** | The Upload Data Pack screen, with the sprint code in the sidebar |

**Two deliberate narrowings to this screen:**

1. **It no longer creates institutions.** The inline "create new institution
   profile" form is gone; institutions are owned by Institution DNA, so one place
   is responsible for institutional master data rather than two forms that can
   disagree. With no institutions on record the screen says so and disables
   submit, instead of quietly offering a create form.
2. **There is no sprint-mode picker.** The three cards (Quick CRI / Verified CRI /
   Full Digital Twin) were removed — the platform runs one discovery method. The
   frontend now omits `sprint_mode` from the payload entirely rather than
   hardcoding a value, so `Sprint.mode`'s model default (`verified_cri`) is the
   single place that decides it. `sprint_mode` was already `required=False` on
   `SprintSerializer`, so no backend change was needed. The `SprintMode` enum and
   the `mode` column both remain, unused by the UI.

### Step 2 — Upload the data pack

| Dimension | Detail |
|---|---|
| **1. User does** | Drags PDF/DOCX/XLSX/CSV/ZIP/images against a 10-item checklist, **or** pastes one Google Drive folder link (and can **Stop** a running import); then ticks documents and starts AI processing for just those |
| **2. Frontend** | `pages/documents/UploadDataPack.tsx` (753 lines — the largest audit screen; a records table with filters, the Drive import progress panel, and per-row selection) |
| **3–5. API** | `POST /sprints/{id}/upload-file` (multipart) · `POST /sprints/{id}/drive-import-jobs` · `POST /sprints/{id}/drive-import-jobs/{job}/stop` · `GET /sprints/{id}/documents` · `DELETE /documents/{id}` · `POST /sprints/{id}/extraction-jobs {document_ids}` |
| **6. Request** | multipart: `file`, `document_type`, `title?`, `owner_role?` — or `{drive_url}` |
| **7. Auth** | Bearer JWT; `get_authorized_sprint()` institution check |
| **8. Controller** | `apps/documents/views.py::SprintDocumentUploadView` / `SprintDriveImportJobListCreateView` / `SprintDriveImportJobStopView` |
| **9. Business logic** | `services.create_document_from_file()` → `DocumentUploadSerializer` validates **extension allowlist**, **`MAX_DOCUMENT_UPLOAD_SIZE` (50 MB)**, and **SHA-256 checksum uniqueness per sprint**; sets `ocr_required` from the extension; `mark_sprint_collecting()` moves `draft → collecting`. A Drive import now brings in **every** supported file: the first filename matching each checklist slot fills it, everything else is imported as `supporting_document` |
| **10. DB** | `documents_document` (+ unique constraint `unique_document_checksum_per_sprint`), `documents_driveimportjob` |
| **11. External** | Google Drive REST v3 (`files.list`, `files.get?alt=media`, `files.export`) — Drive path only |
| **12. Jobs** | `run_drive_import_job` (Drive path only; direct upload is synchronous) |
| **13. Sequence** | Auth → sprint access → validate → checksum → save file to `media/` → INSERT → sprint status bump |
| **14. Response** | `201 DocumentSerializer` (with a `download_url`) or `201 DriveImportJobSerializer` |
| **15. Frontend use** | Refreshes the checklist, ticking off matched types |
| **16. User sees** | A green tick per required document; Drive import shows found/missing/unmatched/skipped |

### Step 3 — AI processing

| Dimension | Detail |
|---|---|
| **1. User does** | Clicks "Start AI Processing", then watches a live progress board; can **Stop** one document or all, **Process** a failed/stopped one again, or **Process incomplete** |
| **2. Frontend** | `pages/documents/AIProcessingMonitor.tsx` (520 lines) — polls **every 3000 ms** (`POLL_INTERVAL_MS`); shows elapsed time and an estimate (`utils/extractionTiming.ts`), the AI mode, which router ran each job, and the sprint's AI token usage and cost |
| **3–5. API** | `POST /sprints/{id}/extraction-jobs` · `GET /sprints/{id}/extraction-jobs` · `POST /extraction-jobs/{id}/cancel` · `POST /extraction-jobs/{id}/process` · `POST /extraction-jobs/sprints/{id}/cancel` · `POST /extraction-jobs/sprints/{id}/process-incomplete` · `GET /sprints/{id}/ai-usage` · `DELETE /extraction-jobs/{id}` |
| **6. Request** | `{}` (all eligible documents), `{document_id}` for one, or `{document_ids: [...]}` for the ticked set |
| **7. Auth** | Bearer JWT + institution check |
| **8. Controller** | `apps/extraction/views.py::SprintExtractionJobListCreateView.create` |
| **9. Business logic** | `_eligible_documents()` = documents in `uploaded`/`failed` **excluding** any with an active job; **sprint status is flipped to `processing` *before* dispatch** (deliberate — an eager task would otherwise race the "advance to reviewing" check). Stop marks the job `cancelled`; the worker checks between pipeline steps **and between AI calls** and abandons the document cleanly (`ExtractionCancelled`). Process resets the same job row and queues it again |
| **10. DB** | `extraction_extractionjob` (INSERT per document); later `facts_extractedfact`, `gaps_gapitem`, `documents_document` |
| **11. External** | The configured AI provider |
| **12. Jobs** | `run_extraction_job` — `max_retries=EXTRACTION_MAX_RETRIES` (3), `acks_late=True` |
| **13. Sequence** | See the 7-stage pipeline in §9.2 |
| **14. Response** | `201 [ExtractionJobSerializer]` immediately — never waits for the AI |
| **15. Frontend use** | Renders per-document `current_step` + `progress_percentage`; `humanizeExtractionError()` rewrites raw SDK errors into readable lines |
| **16. User sees** | A 7-stage progress bar per document, then "review workspace ready" |

### Step 4–6 — Fact review, gaps, owner workspace

| Dimension | Detail |
|---|---|
| **1. User does** | Filters extracted facts, reads the source snippet, then confirms / corrects / rejects / requests evidence; separately works the gap list |
| **2. Frontend** | `pages/facts/FactsReview.tsx`, `pages/facts/ConfirmationWorkspace.tsx`, `pages/gaps/GapDashboard.tsx` |
| **3–5. API** | `GET /sprints/{id}/facts` · `POST /facts/{id}/{confirm\|correct\|reject\|request-evidence}` · `GET /sprints/{id}/gaps` · `POST /gaps/{id}/{resolve\|mark-unavailable\|skip}` |
| **6. Request** | `{comment}` or `{corrected_value, comment}` / `{value}` |
| **7. Auth** | `CanReviewFacts` / `CanResolveGaps` — **every role except `viewer`**; plus per-object institution check |
| **8. Controller** | `apps/facts/views.py::BaseFactActionView` (shared plumbing for all four actions), `apps/gaps/views.py::BaseGapActionView` |
| **9. Business logic** | The history row is written **first**, capturing `original_value` as it stood *before* the action; only then is the fact updated — both inside one transaction. Confirm/Correct also **closes that fact's own `unconfirmed_fact` gap** (and its −3 CRI penalty); conflicts, missing documents and low-confidence gaps are untouched. Migration `gaps/0003` back-filled this for facts reviewed before the rule existed. There is deliberately **no generic `PATCH /facts/{id}`** — every change must go through an action so nothing bypasses the audit trail. Facts and gaps lists now have filter bars (`components/TableFilters.tsx`); gaps show their source document's filename |
| **10. DB** | `facts_extractedfact`, `facts_factreviewhistory`, `gaps_gapitem` |
| **11–12.** | None — fully synchronous |
| **13. Sequence** | Auth → role gate → object institution check → serializer → INSERT history → UPDATE fact/gap |
| **14. Response** | `200 ExtractedFactDetailSerializer` / `GapItemSerializer` |
| **15. Frontend use** | Optimistically updates the row and advances to the next item |
| **16. User sees** | The fact turns green (confirmed) / amber (corrected) / grey (rejected); gap counters drop |

### Step 7 — Live CRI

| Dimension | Detail |
|---|---|
| **1. User does** | Opens the score screen; optionally clicks "Recalculate" |
| **2. Frontend** | `pages/scoring/LiveCRIPreview.tsx` |
| **3–5. API** | `GET /sprints/{id}/score` (bootstraps a first run if never scored) · `POST /sprints/{id}/score` (forced recalculation) · `GET /sprints/{id}/score/history` |
| **7. Auth** | `CanManageSprint` |
| **8. Controller** | `apps/scoring/views.py::SprintScoreView` |
| **9. Business logic** | `run_scoring_engine()` — the nine-step engine in §6.4. `POST` is **refused** if `sprint.status in BASELINE_LOCKED_STATUSES`. A successful `POST` also moves `reviewing → scoring` |
| **10. DB** | Reads `facts_extractedfact` (confirmed/corrected only) + `gaps_gapitem` (open/in_progress); writes `scoring_pillarscore` (upsert ×8), `scoring_scoringrun` (INSERT), `sprints_sprint.overall_cri/confidence_score` |
| **11–12.** | None — **no AI is involved in scoring** |
| **14. Response** | `SprintScoreSerializer`: overall CRI, confidence, 8 pillar scorecards, strengths, weaknesses, live evidence metrics, unresolved blocking gaps |
| **16. User sees** | An 8-pillar radar/bar view with a headline CRI/100 and a confidence percentage |

### Step 8 — Baseline approval

| Dimension | Detail |
|---|---|
| **1. User does** | Reviews the score, then approves / approves provisionally / returns for correction with a reason |
| **2. Frontend** | `pages/scoring/BaselineApproval.tsx` (352 lines) |
| **3–5. API** | `GET /sprints/{id}/baseline` · `POST /baseline/approve` · `POST /baseline/approve-provisional` · `POST /baseline/return` |
| **7. Auth** | `CanApproveBaseline` → `super_admin` / `consultant` / `institution_admin` only |
| **9. Business logic** | `GET` **bootstraps** a `PENDING` Baseline pinned to the latest `ScoringRun` and moves the sprint to `baseline_pending`. **Full approval is refused server-side while any blocking gap is unresolved** — provisional approval is the documented way past it. Return requires non-blank `comments` and sends the sprint back to `reviewing` |
| **10. DB** | `scoring_baseline` (FK `PROTECT` → `scoring_scoringrun`), `scoring_baselinedecisionhistory` (append-only) |
| **14. Response** | `{baseline, score, high_priority_gaps, can_approve}` on GET; `BaselineSerializer` on the actions |
| **16. User sees** | The approve button disabled with a blocking-gap count, or a confirmed approval banner |

### Step 9–10 — Recommendations and report

| Dimension | Detail |
|---|---|
| **1. User does** | Generates recommendations, edits them (consultants only), then generates and downloads the report |
| **2. Frontend** | `pages/recommendations/RecommendationsReview.tsx`, `pages/reports/ReportPreviewExport.tsx` (polls every 3 s) |
| **3–5. API** | `POST /sprints/{id}/recommendations/generate` · `PATCH /recommendations/{id}` · `POST /sprints/{id}/reports` · `GET /reports/{id}` · `GET /reports/{id}/download?file=pdf\|docx` |
| **7. Auth** | `CanManageRecommendations` to generate; **`CanEditRecommendation` (super_admin/consultant only)** to edit; `CanManageSprint` for reports |
| **9. Business logic** | Three idempotent generators (gap-driven, evidence-driven, pillar-weakness-driven). Report generation creates a **new version row** (`next_report_version`) and dispatches `generate_report_task` |
| **12. Jobs** | `generate_report_task` — **no retries by design** (it reads already-validated data; a failure is a real bug) |
| **10. DB** | `recommendations_recommendation` (+ M2M `supporting_facts`), `reports_report` (unique `(sprint, version)`) |
| **14. Response** | `202` + `ReportSerializer` while generating; `FileResponse` on download |
| **16. User sees** | An 11-section report preview and a PDF/DOCX download |

## 2.4 The benchmark workflow (InGage-internal, then the college)

The second half of the product. Stages 1–4 happen inside **Benchmark Studio**
(InGage staff only, `IsInGageStaff`); stage 5 is the **Benchmark Assessment**
page, shared by staff and the college being assessed.

```mermaid
flowchart TD
    REG["Source Register workbook<br/>(collected by hand from official sites)"] -->|"import_source_register"| SRC["1. Source Library<br/>SourceDocument + SourceVersion (draft)"]
    SRC -->|"ingest_source_files: fetch from Drive,<br/>SHA-256 must match"| VER["file verified"]
    VER -->|"approve (staff)"| ACT["active version<br/>file fields frozen"]
    ACT -->|"Draft requirements (Celery)"| CAND["2. RequirementCandidate<br/>AI-drafted; quote must appear in the source"]
    CAND -->|"accept / reject (staff)"| REQ["Requirement (approved)"]
    PACK["Benchmark Source Pack workbook"] -->|"import_benchmark_catalogue"| CAT["3. Catalogue<br/>Pillar · Capability · Benchmark (draft)<br/>+ placeholder L3/L2/L1"]
    REQ -->|"link: primary / supporting / crosswalk"| CAT
    CAT -->|"experts write"| AUTH["levels · evidence rules ·<br/>applicability rules · owner"]
    AUTH -->|"readiness checklist passes"| REL["3.6 Release: draft → review → approved → published<br/>approver ≠ submitter; snapshot + SHA-256 per benchmark"]
    WAT["4. Daily watcher<br/>(official pages, enabled feeds only)"] -.->|"change events for review —<br/>never edits anything"| SRC
    REL -->|"current published release"| CYC["5. Assessment cycle for one college<br/>applicability from the college profile"]
    CYC --> EVI["college uploads evidence<br/>per evidence request"]
    EVI --> REV["InGage reviews each item<br/>(5 quality scores + decision)"]
    REV --> SCO["four scores per benchmark<br/>compliance · maturity · evidence confidence · outcome"]
    SCO --> FIN["finalize — frozen; college sees the scorecard"]
```

| Stage | Who | Where | Key rule |
|---|---|---|---|
| 1. Source Library | Staff | Studio › Sources | A source version becomes `active` only after its file is checksum-verified and a person approves it; then its file fields are frozen. Licensed (ISO/IEC) texts are recorded as links, never stored |
| 2. Requirements | AI drafts, staff decide | Studio › Sources › candidates | A candidate whose quote is not found in the source text is **dropped**, not shown. Only accepted candidates become `Requirement` rows |
| 3.1–3.3 Catalogue + linking + levels | Staff / experts | Studio › Catalogue, Requirements, Levels | Benchmarks imported from the Source Pack start `draft` with placeholder levels; a re-import never overwrites an expert-edited level |
| 3.4 Evidence rules | Experts | Levels tab panel | Per level (or any level), with minimum count, maximum age and scope; `minimum_count` must be ≥ 1 |
| 3.5 Applicability | Experts | Studio › Applicability | Rules by institution type, autonomous status, programme type, approval body, jurisdiction; first matching rule wins; **every inclusion and exclusion carries a reason**; no rules = "requires review", never silently "applies" |
| 3.6 Releases | Staff, two people | Studio › Releases | Readiness checks before review; approver must differ from submitter; benchmarks in a release under review/approved cannot be edited; publishing freezes each benchmark's snapshot + hash and retires the previous release |
| 4. Watcher | Celery Beat + staff | Studio › Watcher | Records snapshots and change events only; a person decides; never publishes |
| 5. Assessment | Staff + the college | Benchmark Assessment | Scores against the **release snapshot**, not live benchmarks; the college sees scores only after finalize |

Full rules: `backend/docs/SOURCE_LIBRARY.md` (stages 1–4) and
`backend/docs/BENCHMARK_ASSESSMENTS.md` (stage 5).

**State of the content today (dev database):** 88 sources registered, 14 files
ingested, 60 benchmarks imported with identical placeholder levels, 48 watcher
feeds (all off), **no approved requirements, no release published** — so no college
can be assessed yet. The machinery is built; the expert content is not.

---

# 3. Every major feature

## 3.1 Authentication

**Purpose:** Issue and verify JWTs; there is no self-registration.

- **User flow:** open `/login` → either type credentials or click one of eleven
  quick-login persona buttons → land on `/dashboard`.
- **Frontend:** `pages/auth/Login.tsx`, `context/AuthContext.tsx`, `api/client.ts`.
- **API:** `POST /auth/login` → `{access_token, refresh_token, user}`;
  `GET /auth/me`; `POST /auth/logout` (blacklists the refresh token, returns `205`);
  `POST /auth/refresh`; `POST /auth/change-password`; `POST /auth/password-reset`;
  `POST /auth/password-reset/confirm`.
- **Backend:** `apps/accounts/views.py`, `serializers.py`, `tokens.py`.
- **Database:** `accounts_user`, plus SimpleJWT's `token_blacklist_*` tables.
- **External services:** none.
- **Processing:** `LoginSerializer` calls Django's `authenticate()` with
  `username=email` (the model's `USERNAME_FIELD` is `email`), rejects inactive
  accounts, then `get_tokens_for_user()` mints the pair.
- **Output:** tokens stored in `localStorage` under `aios_token` / `aios_refresh_token`.

## 3.2 Institution management

**Purpose:** The tenant boundary — every other record is ultimately scoped to one.

- **API:** `GET|POST /institutions`, `GET|PUT|PATCH|DELETE /institutions/{id}`.
- **Backend:** `apps/institutions/views.py::InstitutionViewSet`.
- **Frontend:** `pages/institutions/InstitutionList.tsx` — the list, the **create form**, and per-row delete.
- **Database:** `institutions_institution` (UUID PK). `is_active` still exists on the
  model, but **DELETE is now a hard cascade**, not a flag flip — so the field only
  lingers on institutions removed before that change. The list page hides its Status
  column entirely when nothing is inactive.
- **Notable:** list is filtered by `get_accessible_institution_ids()`, but **detail
  actions deliberately use the unscoped queryset** so an out-of-scope institution
  returns `403` (via `IsInstitutionMember`) rather than `404` — the same pattern
  is used in `SprintViewSet`.
- **Two role sets, deliberately asymmetric:** `WRITE_INSTITUTION_ROLES` =
  `super_admin` / `consultant` / `institution_admin` for create and update;
  `DELETE_INSTITUTION_ROLES` = `super_admin` / `consultant` for delete, which is
  narrower because deleting an institution takes every sprint under it with it.

## 3.2a Institution DNA

**Purpose:** The institutional baseline every discovery sprint is measured
against — who the institution is, who leads it, what departments it has, and what
IT estate it runs. Previously this lived nowhere; the sprint-setup form captured a
handful of fields and nothing else.

**User flow:** open **Institution DNA** → pick an institution (a selector appears
only when more than one is accessible) → work three tabs:

| Tab | Contents |
|---|---|
| **Institution Profile** | Name, type, location, accreditation, student/faculty counts, derived department & programme counts, leadership list, priority tags |
| **Departments** | One card per department: head, faculty / students / programmes |
| **Systems & IT** | Digital-maturity level (1–5) with its rubric description, the systems list with `Legacy` / `Manual` tags, and a current-AI-usage note |

**Frontend:** two pages. `pages/institutions/InstitutionList.tsx` (323 lines) is the
landing page — the table, the create form, and per-row delete;
`pages/institutions/InstitutionDetail.tsx` (1 035 lines) is one institution's
workspace — three tab components, an inline `Field`, a priority-tag editor, a
leadership card, and a department stat tile. Create and delete live on the *list*
because they act on the institution as a whole rather than on any field of its
profile.

**API:** `GET /institutions/{id}` (detail serializer) · `PATCH /institutions/{id}`
· `GET|POST /institutions/{id}/{leaders,departments,systems}` ·
`GET|PATCH|DELETE` on each `/{id}` beneath those. See §7.

**Backend:** `apps/institutions/` — `models.py`, `serializers.py`, `views.py`,
`constants.py`, `urls.py`, migration `0003`.

**Database:** `institutions_institution` gained `student_count`, `faculty_count`,
`priorities` (JSON), `digital_maturity_level`, `current_ai_usage`. Three new
tables: `institutions_institutionleader`, `institutions_department`,
`institutions_institutionsystem`. See §6.

**External services:** none.

**Processing / design decisions worth knowing:**

- **Derived vs. stored counts.** Department and programme counts are *computed*
  from the department rows (`department_count`, `program_count` on the detail
  serializer) and are read-only in the UI, labelled `DERIVED`. Student and
  faculty totals are *stored* on the institution, because an institution's
  official total legitimately differs from the sum of whichever departments have
  been entered so far — reporting a partial sum as the total would be wrong
  rather than merely incomplete.
- **Leader initials are derived** from the name in the serializer, never stored, so
  they cannot go stale when a name is corrected.
- **The maturity rubric is a constant, the level is data.** `constants.py` holds
  the five level descriptions; the level itself is a column. Same split
  `apps.scoring.constants` makes between pillar keys and pillar weights.
- **One access check covers all three sub-resources.** They are nested under
  `/institutions/{institution_id}/…`, and `InstitutionScopedMixin` resolves and
  authorizes the institution once, scoping every queryset to it — which is what
  makes an id from another institution a `404` on the route rather than something
  each view has to check for.

**Output:** the institution's full profile, editable in place by the roles in §8.

**Dependencies:** requires an `Institution` to exist. Sprint Setup now depends on
this module for institution creation.

## 3.3 Sprint management

**Purpose:** The unit of work. Everything else hangs off a sprint.

- **API:** full CRUD plus `GET /sprints/{id}/overview` — a single call returning the
  sprint, institution, document counts by status (7 buckets), fact counts by status
  (6 buckets), gap counts (5 buckets), the scorecard, recommendations, reports, and
  the latest extraction job.
- **Backend:** `apps/sprints/views.py`, `serializers.py`, `filters.py`, `access.py`.
- **Notable:** `DELETABLE_STATUSES = {draft, completed, archived}` — an in-progress
  sprint cannot be hard-deleted, only archived. `overview` calls
  `build_score_snapshot(sprint, bootstrap=False)` specifically so that *loading a
  dashboard does not persist new scoring rows*.
- **Dependency:** every other feature requires a sprint.

## 3.4 Document management + Google Drive import

**Purpose:** Get institutional evidence into the system safely.

- **User flow (Drive):** paste `https://drive.google.com/drive/folders/<id>` →
  job created → worker walks the **whole** folder tree breadth-first, fetching each
  level's folders **in parallel** → every file with a supported extension (or a
  Google Doc/Sheet/Slides, **exported** to PDF/XLSX) is imported through the *same*
  `create_document_from_file()` path as a manual upload. The first filename
  matching each `DRIVE_IMPORT_CHECKLIST` slot fills that slot; every other file is
  imported as `supporting_document` (with its folder path). Downloads prefetch in
  parallel, but each file is saved and the job's progress written one at a time,
  so the page's records table fills in live.
- **Stop:** `POST /sprints/{id}/drive-import-jobs/{job}/stop` sets the job
  `cancelled`; the worker checks between files, so documents already imported stay
  and nothing further is imported.
- **API:** `POST /sprints/{id}/drive-import-jobs`, `GET` the same path, `…/{job}/stop`.
- **Backend:** `apps/documents/{views,services,tasks,drive_import,constants}.py`.
- **Database:** `documents_document`, `documents_driveimportjob` (status gained
  `cancelled` in migration `0003`; `results` JSON holds per-checklist-slot
  `found`/`missing`, `additional_files`, `skipped_files` with reasons, and a live
  `progress` block `{processed, total, current_file}`).
- **External:** Google Drive REST v3, authenticated with a **single server-side API
  key** — no OAuth, no per-institution tokens. This requires the folder to be
  shared *"Anyone with the link — Viewer"*.
- **Safety caps:** `GOOGLE_DRIVE_IMPORT_MAX_FILES` (200),
  `GOOGLE_DRIVE_IMPORT_MAX_FOLDERS` (200), `GOOGLE_DRIVE_IMPORT_CONCURRENCY` (6
  parallel requests), `visited` set against cycles, 30 s list timeout / 60 s
  download timeout, 3 retries with exponential backoff. Listing order stays
  deterministic despite the parallel fetch, because "first match wins" depends on it.
- **Known inconsistency (documented in the code):** `DRIVE_IMPORT_CHECKLIST` slugs
  (`aqar_report`, `faculty_master`, `research_publications`, `syllabi_curriculum`,
  `ai_policy_doc`) **deliberately differ** from `DOCUMENT_TYPES` /
  `REQUIRED_DOCUMENT_TYPES` (`aqar`, `faculty_master_list`, …). The constants file
  says so explicitly and marks it out of scope. **Consequence:** a Drive-imported
  AQAR is stored as `aqar_report`, which does **not** satisfy the
  `missing_document` gap check for `aqar`. This is a real, live defect (see §17/§27).

## 3.5 AI extraction — see §9 for the deep dive

## 3.6 Fact review

**Purpose:** Human confirmation is what turns an AI guess into scoring evidence.

- Only `confirmed` and `corrected` facts count toward the CRI
  (`cri_engine._EVIDENCE_STATUSES`).
- Five statuses: `extracted` → `confirmed` | `corrected` | `rejected` |
  `evidence_requested`.
- `ExtractedFact.document` (extraction lineage, set once) is deliberately separate
  from `ExtractedFact.source_document` (the *current* evidence citation, which a
  correction may repoint) — so a correction never rewrites where the fact came from.
- Filtering/ordering via `django-filter` on `field_key`, status, confidence, etc.
- **Confirm or Correct closes the fact's own `unconfirmed_fact` gap**
  (`gaps.services.resolve_unconfirmed_fact_gap`), in the same transaction as the
  history row — so a reviewed fact no longer keeps its −3 CRI penalty. Only that
  one gap type, only for that fact.

## 3.7 Gap management

Five gap types, each with its own dedup key enforced by **three partial unique
constraints** on `GapItem`:

| Gap type | Scoped by | Raised by | Priority |
|---|---|---|---|
| `missing_document` | `(sprint, gap_type, title)` | sprint-wide pass only | **blocking** |
| `unconfirmed_fact` | `source_fact` | per-document + sprint-wide | medium |
| `low_confidence` | `source_fact` | per-document + sprint-wide | high (<0.5) / medium (<0.7) |
| `conflict` | `title` (stable per `field_key`) | AI conflict checker + sprint-wide | high |
| `stale_data` | `related_document` | per-document + sprint-wide | medium |

`create_gap_if_new()` is the single shared idempotency primitive — an `exists()`
check plus an `IntegrityError` catch for the race, so the per-document detector and
the end-of-sprint pass can both run without duplicating rows.

## 3.8 CRI scoring — see §6.4

## 3.9 Baseline approval, recommendations, reports — covered in §2.3

## 3.10 Dashboard

`GET /api/v1/dashboard` returns seven live metrics (`active_sprints`,
`completion_percentage`, `reports_ready`, `pending_confirmations`,
`high_priority_gaps`, `sprint_count`, `institution_count`) plus the accessible
sprint list. The code comments explicitly explain why each metric is its own query
rather than one combined `.aggregate()` — mixing `Count()` over multiple reverse
FKs fans out the join and inflates results.

## 3.11 Vector store — semantic evidence retrieval `[IMPLEMENTED]`

`apps/vector_store/` (2 703 lines across 15 modules) indexes the **text of a
college's uploaded documents** into **Pinecone** so that a natural-language
question — *"AI-certified faculty and faculty AI training"* — returns the passages
that answer it, each citable back to a document and a page.

**It is entirely optional.** With `PINECONE_API_KEY` / `PINECONE_INDEX_NAME` unset,
`indexer.is_enabled()` is `False`: no task is queued, no row is written, and upload,
extraction, scoring, approval and reports behave exactly as they did before the app
existed. The three endpoints answer **`503` with a stated reason**, not `500` and not
a silently empty list — "not configured" and "no results" must be distinguishable.
`pinecone` is imported lazily inside `pinecone_client`, so the project boots and the
whole suite passes with the SDK absent.

### What it is not

Stated explicitly because the scope is easy to overread:

| Not this | Why |
|---|---|
| A replacement for PostgreSQL | Postgres remains the source of truth for **every** structured record. Pinecone holds embeddings plus the metadata needed to filter and cite them — nothing else is copied across |
| Part of CRI scoring | The 9-step engine (§6.4) is untouched and still fully deterministic. No vector influences a score |
| Part of the benchmark library | The benchmark library (§3.17) now exists, but it is **relational** — sources, requirements and benchmarks live in PostgreSQL and never touch Pinecone. `source_type` is pinned to `college_document` on every write *and* every query, so benchmark vectors could later share the index without either kind leaking into the other |
| Coupled to one vendor | `EmbeddingService` is an ABC; `OpenAIEmbeddingService` is one implementation, and `EMBEDDING_BASE_URL` points it at any OpenAI-compatible endpoint. `pinecone_client` is the **only** module that imports the SDK |

### The indexing pipeline

`services/indexer.py::index_document` — read → hash → chunk → embed → upsert:

```mermaid
flowchart TD
    UP["Document reaches status=processed<br/>(end of the extraction task)"] --> Q{"indexer.is_enabled()?"}
    Q -->|no| SKIP["Nothing happens.<br/>No row, no task, no error"]
    Q -->|yes| ROW["VectorDocumentIndex row → pending"]
    ROW --> T["Celery: index_document_vectors"]
    T --> READ["PDFPageReader.read_pages()<br/>the SAME reader the AI pipeline uses"]
    READ --> CH["chunk_pages()<br/>≤1200 chars, 150 overlap, ≥40 min<br/>never spans a page · never splits a sentence"]
    CH --> HASH{"SHA-256 of chunk text<br/>== stored content_hash<br/>AND same embedding model?"}
    HASH -->|yes, and not force| NOOP["No-op → status stays indexed<br/>(re-running a sprint is cheap)"]
    HASH -->|no| MODE{"Index embeds<br/>server-side?"}
    MODE -->|"integrated"| UPR["upsert_records()<br/>Pinecone embeds · batches of 96"]
    MODE -->|"manual"| EMB["EmbeddingService.embed()<br/>→ upsert() raw vectors · batches of 100"]
    UPR --> STALE
    EMB --> STALE["Delete ids new_count … old vector_count-1<br/>(chunks that no longer exist)"]
    STALE --> OK["status=indexed · vector_count · embedding_model · indexed_at"]
    T -.->|RecoverableVectorStoreError| RETRY["retry ×3, 20 s × 2ⁿ"]
    T -.->|PermanentVectorStoreError| FAIL["status=failed + reason on the row"]
```

Three details worth naming:

- **A chunk never spans a page.** The page number *is* the citation this platform
  promises, so a chunk straddling a page boundary could not be cited honestly.
- **The content hash is over extracted text, not the file.** Re-uploading the same
  PDF with different metadata is a no-op; a file whose text extraction *improved*
  re-embeds. `Document.checksum` cannot express either.
- **Vector ids are deterministic** —
  `college_{institution}_document_{document}_chunk_{n}` — so a re-index overwrites
  in place instead of duplicating. That, plus the stale-id delete, is what makes
  indexing idempotent.

### Institution isolation

The hard requirement: one college must never retrieve another's documents.

```python
metadata_filter = {
    'college_id':  {'$eq': str(institution_id)},
    'source_type': {'$eq': SOURCE_TYPE_COLLEGE_DOCUMENT},
}
```

- The filter is **built inside `search.build_filter()`**, never accepted from the
  caller, so no call site can omit or widen it.
- `institution_id` comes from **the sprint in the URL**, never the request body — the
  search serializer has no institution field at all.
- Filtering happens **server-side in Pinecone**, not by discarding rows after
  retrieval.
- `pinecone_client._require_filter()` raises rather than issuing an unfiltered
  query: *"an unfiltered query would cross institutions."*

### Vector metadata

Exactly nine keys, doing exactly two jobs — isolation and traceability:

| Key | Job |
|---|---|
| `college_id`, `sprint_id`, `source_type` | Isolation (filtered on, server-side) |
| `document_id`, `document_name`, `document_type`, `page_number`, `chunk_index` | Traceability — so a hit renders as *"Faculty_Report.pdf, page 17"* |
| `text` | The chunk itself, so a result is readable without a second round trip |

Nothing else from PostgreSQL is copied in; a field that is neither filtered nor
cited would only be a second copy that drifts. **The original PDF/DOCX is never
uploaded to Pinecone** — only extracted text.

### Two Pinecone modes

The index may embed server-side or take raw vectors, and the two use *different
APIs* — which is why this is a mode, not just another embedding provider:

| Mode | Who embeds | Pinecone API | Batch cap |
|---|---|---|---|
| `integrated` | Pinecone (e.g. `llama-text-embed-v2`) | `upsert_records` / `search` | **96** |
| `manual` | This app, via `EmbeddingService` | `upsert` / `query` | 100 |
| `auto` *(default)* | Detected once per process via a cached `describe_index`, never in the request path | — | — |

Because Anthropic publishes no embedding endpoint, `EMBEDDING_API_KEY` is separate
from `AI_API_KEY`: a deployment running Claude for extraction still needs an
OpenAI-compatible key *for manual mode only*. Integrated mode needs no embedding key
at all, and `is_enabled()` knows not to demand one.

### Observability

`VectorDocumentIndex` (one row per document) is the retryable, inspectable record —
the same role `ExtractionJob` plays for extraction. It stores *that* a document is
indexed, with which model, how many vectors, when, and why it failed. **It stores no
embeddings**: those live in Pinecone, and a second copy here would have no reader.

### Endpoints

Three, all sprint-scoped — see §7.1. Pinecone is never exposed: no index name, no
host, no key, and no raw match object reaches the client.

**First consumer:** the **AI Copilot** page (§3.12) sends questions it cannot
answer from the score/gap/document APIs to `POST /sprints/{id}/evidence-search` and
shows the cited passages. It treats `503` as "not available on this server", not
"nothing found". Indexing is still not triggered from any screen.

## 3.12 The ported prototype modules — now on real data

Nine screens were ported from an InGage React prototype (`ai-future-ready-platform`)
and first ran on hardcoded sample content. Commits `44b57e9` and `398bd21`
**rewired eight of them to the existing backend**: each now derives everything
from endpoints that already existed (sprints, documents, facts, gaps, scoring,
recommendations, reports, baseline, evidence search). No new Django app was needed
for them, and none of them shows a `DemoDataNotice` banner any more.

Several are deliberately **narrower than their names**, and each page says so
rather than inventing what the backend cannot supply:

| Module | Route | What it shows now | What it says it cannot do |
|---|---|---|---|
| Evidence Intelligence | `/evidence` | The sprint's documents, their processing state, facts per document, and missing required documents — read from the backend's own `missing_document` gaps, not a frontend copy of the list | — |
| **CRI & Benchmark Intelligence** | `/cri-benchmark` | The **pillar** CRI from `apps/scoring`, the gaps behind it, and the recommendation roadmap | Its header comment still says the benchmark library "has no backend yet" — **out of date**: §3.17 now exists, but this page does not read it |
| Transformation Plan | `/transformation-plan` | The audit's recommendations grouped by the timeline the generators already stamp, with expected CRI lift | No editable plan, owners or dates |
| Goals & Tasks | `/goals-tasks` | Tasks = open gaps + facts awaiting confirmation; goals = recommendations; each row links to the screen that resolves it | **No Task/Goal model** — cannot create, assign or date a task |
| **AI Copilot** (was AI Chatbot) | `/ai-copilot` | Answers score / gap / document / next-step questions **deterministically from the live API**; anything else goes to the vector store's evidence search and returns cited passages | **Not a language model** — no chat endpoint, no LLM call. Shows "search unavailable" when Pinecone is not configured |
| Reminders | `/reminders` | What is waiting on whom, computed from the sprint's state | Nothing is **sent** — no email provider, no notification job |
| Compliance Mapping | `/compliance` | Which accreditation-relevant documents the sprint holds or lacks; only types whose name identifies a framework (`naac_ssr` → NAAC) are claimed | No criterion-level coverage — no official criteria lists are loaded |
| UAT Readiness | `/uat-readiness` | Hand-over checks computed from the sprint (documents processed, facts reviewed, blocking gaps, baseline, report) | Cannot record a client sign-off |
| **Benchmark Studio** | `/benchmark-studio` | **InGage staff only** (frontend gate + `IsInGageStaff` on every API). Eight real tabs — Catalogue, Requirements, Applicability, Levels, Sources, Releases, Watcher, Candidates (§3.17–§3.20) | — (the prototype's seed-data Editor / Approvals / AI-candidates tabs were removed on 15 Oct) |

### The prototype's data is gone

`frontend/src/data/` (seed benchmarks, the in-browser CRI engine, workspace demo
content) and `components/DemoDataNotice.tsx` were deleted on 15 Oct 2026 once
nothing used them. **No screen in the product renders sample data any more.**

> ⚠️ **The maturity levels are numbered in reverse: `L1` is the HIGHEST
> (Advanced), `L3` the lowest (Foundational).** The prototype's convention was kept
> by the real benchmark backend too (`MaturityDefinition.Level`: L3 Foundational,
> L2 Operating, L1 Advanced), and the assessment scores it the same way (§3.19). It
> is consistent, but it reverses what most readers expect — worth stating on any
> client-facing scorecard.

## 3.13 Feature dependency graph

```mermaid
graph LR
    AUTH[Authentication] --> INST[Institutions]
    INST --> DNA[Institution DNA]
    INST --> SPR[Sprints]
    SPR --> DOC[Documents / Drive import]
    DOC --> EXT[AI Extraction]
    EXT --> FACT[Facts]
    EXT --> GAP[Gaps]
    FACT --> GAP
    FACT --> SCORE[CRI Scoring]
    GAP --> SCORE
    SCORE --> BASE[Baseline approval]
    SCORE --> REC[Recommendations]
    GAP --> REC
    BASE --> REP[Reports]
    REC --> REP
    SPR --> DASH[Dashboard]
    SCORE --> DASH
    DNA -.->|"supplies the institution<br/>Sprint Setup selects"| SPR
    DOC -.->|"optional · only when<br/>Pinecone is configured"| VEC[Vector store]
    VEC -.->|"evidence search"| COP[AI Copilot]
    EXT --> USE[AI usage & cost]

    SRC[Source Library] --> REQ[Requirements]
    REQ --> BM[Benchmark catalogue<br/>levels · evidence rules · applicability]
    BM --> RELS[Releases]
    WATCH[Daily watcher] -.->|"change events,<br/>human review"| SRC
    RELS --> ASMT[Benchmark assessment]
    INST --> ASMT
```

Institution DNA sits alongside the audit rather than inside it: it holds the
institution's standing baseline, which every sprint is then measured against. It is
also where institutions are **created** — Sprint Setup only selects one — but the
audit pipeline does not read DNA records; connecting the two (for example, checking
an extracted faculty count against the recorded one) is not implemented.

The vector store hangs off documents as a **leaf**: extraction feeds it, and only
the AI Copilot reads it. Removing it, or never configuring it, changes no other
edge in this graph.

**The two halves are not connected yet.** The benchmark side (bottom) shares only
the `Institution` with the audit (top): a benchmark assessment does not read the
sprint's documents or confirmed facts, and the pillar CRI does not read benchmarks.
Linking them — for example, offering a sprint document as benchmark evidence — is
not implemented.

## 3.14 AI processing modes and the router pool `[IMPLEMENTED]`

**Purpose:** choose, with one setting, how extraction jobs reach the AI.

| `AI_PROCESSING_MODE` | AI connection | Worker slots (default) |
|---|---|---|
| `single` (default) | `AI_BASE_URL` + `AI_API_KEY` + `AI_MODEL` (or provider auto-detect, §9.1) | 2 |
| `multi_router` | the routers in `AI_ROUTER_URLS` (keys `AI_ROUTER_API_KEYS`, model `AI_ROUTER_MODEL` or `AI_MODEL`) | routers × `AI_ROUTER_MAX_CONCURRENT` (4 × 2 = 8) |

- **Switch:** `config/ai_processing_mode.py` parses the mode (an invalid value stops
  Django and the worker from starting) and derives `CELERY_WORKER_CONCURRENCY`
  unless that is set explicitly.
- **Router pool:** `apps/extraction/services/router_pool.py`. Each document's job
  **leases one slot** on the least-busy healthy router (Redis keys shared by every
  worker process, 2 slots per router, a TTL that the job keeps extending), and
  every AI call for that document goes to that router (`use_lease` context
  variable). A router that fails with a recoverable error is used last for
  `AI_ROUTER_COOLDOWN_SECONDS` (60); the Celery retry then leases another one. If
  every slot is busy a job waits up to `AI_ROUTER_WAIT_SECONDS` (300), then retries.
- **No silent fallback:** in `multi_router` mode `get_ai_service()` **refuses** an AI
  call that has no router lease, rather than quietly using `AI_BASE_URL`.
- **Duplicate protection (both modes):** a job only starts from
  pending / retrying / running (`_claim`), a finished job is never re-run, and a
  stale queue message for a job that was re-processed since (different
  `celery_task_id`) is skipped. `CELERY_WORKER_PREFETCH_MULTIPLIER=1` and a 6-hour
  broker visibility timeout stop one worker hoarding jobs or a long document being
  delivered twice.
- **Visibility:** `ExtractionJob.ai_router` records which router ran the latest
  attempt (shown on the monitor); the worker logs its mode on start
  (`worker_ready`); `python manage.py ai_mode_status [--workers]` and a Django
  system check (`extraction.E001/W001`) report configuration problems without
  printing keys.
- **Dev scripts (Windows):** `start-dev.ps1` (Redis in WSL on 6380, the 4 WSL routers
  in multi_router mode, one worker window, health check) and `switch-ai-mode.ps1`
  (edits only the mode line in `.env`, warm-stops the worker so running jobs finish,
  then runs `start-dev.ps1`). Full guide: `backend/docs/AI_PROCESSING_MODES.md`.

## 3.15 AI usage and cost tracking `[IMPLEMENTED]`

**Purpose:** know — and bill — what each sprint and institution spends on AI.

- **One `AIUsage` row per AI call** made during extraction: provider, model, input /
  output / cache-read / cache-write / reasoning tokens, duration, and `cost_usd`.
  The pipeline opens a `usage_scope(job, document, sprint, stage)` and the AI
  clients record each raw response inside it (`apps/extraction/usage.py`).
  Recording failures are logged and swallowed — they never break an extraction.
- **Priced at call time** (`apps/extraction/pricing.py`, USD per 1 M tokens), so a
  later price change never rewrites an earlier sprint's cost. Built-in prices
  cover Anthropic models; anything else (a router combo, a self-hosted model) has
  its tokens recorded and its cost left **empty**, until a price is given in
  `AI_PRICING_JSON`.
- **Survives deletion:** every link is `SET_NULL` — it is a billing record.
- **Three sources:** `recorded` (from the provider response, exact), `imported`
  (a dashboard total for usage from before recording existed —
  `manage.py import_ai_usage`, refuses a duplicate note), `estimated`.
- **Where it is shown:** `GET /sprints/{id}/ai-usage` (any member of the
  institution; totals, by stage, by model, costliest documents, optional date
  range) on the AI Processing Monitor; `GET /extraction-jobs/usage-report`
  (**super admin / consultant only**; one row per institution × sprint × month) on
  Admin › AI Usage & Billing; `manage.py ai_usage_report` on the command line.

## 3.16 User administration and Admin / Settings `[IMPLEMENTED]`

**Admin / Settings** (`/admin-settings`, `pages/admin/AdminSettings.tsx`) has four
tabs: **Scoring rubric** (the live pillar/criterion weights from `GET
/scoring/config`, read-only), **Account** (own profile + change password),
**Users**, and **AI Usage & Billing** (staff only).

**User administration** — `apps/accounts/user_admin.py`, mounted at
`/api/v1/users`:

| Rule | Detail |
|---|---|
| Who may use it | `super_admin` and `institution_admin` only (`CanAdministerUsers`). A consultant cannot |
| Institution scoping | An institution admin sees, fetches, edits and deactivates **only their own college's** users — another college's ids are not reachable |
| No privilege escalation | An institution admin cannot create or promote a `super_admin` / `consultant`, nor move a user to another institution |
| No self-lockout / self-promotion | Nobody may deactivate themselves or change their own role |
| Delete = deactivate | `DELETE` sets `is_active=False` (login refuses it) and keeps the row, because reviews, decisions and uploads name their user |
| Passwords | Write-only, optional on update, checked by Django's validators |

Tests: `apps/accounts/tests_user_admin.py`.

## 3.17 The benchmark library — stages 1–3 `[IMPLEMENTED]`

`apps/benchmarks/` (24 models, 10 migrations, 12 service modules). **InGage
staff only** — every endpoint uses `IsInGageStaff`, and Benchmark Studio refuses
other roles. The design follows the manager's *Database Foundation*
(`db/schema.sql`) and *Source Library* packs; table names are noted on each model.

| Stage | What it holds | Key code |
|---|---|---|
| **1 · Source Library** | `Authority` → `Framework` → `SourceDocument` (source code, role: mandatory / authoritative framework / good practice / intelligence) → `SourceVersion` (draft → active → superseded / withdrawn; collection status; file checksum) · `SourceFeed` (pages for the watcher) · `SourceAuditEvent` (append-only) | `import_source_register` (reads the interns' workbook, dry-run report), `ingest_source_files` (fetches the file from Drive, stores it content-addressed under `media/source_library/<sha[:2]>/<sha>.<ext>`, verifies SHA-256; refuses `.crdownload`; never fetches licensed text), `services/approval.py` |
| **2 · Requirements** | `SourceSection` → `RequirementCandidate` (AI draft) → `Requirement` (approved, with page and verbatim quote) | `tasks.draft_source_requirements` (Celery; leases a router like an extraction job), `services/requirement_drafting.py` — **a candidate whose quote is not in the source text is dropped** |
| **AI-QIF v1.0 (the framework)** | `Pillar` `AIQIF-C1..C9` (weights out of 1000), `Benchmark` `AIQIF-C1.1..C9.4` (36 key indicators, KI weight, `naac_crosswalk`), `Framework` `AIQIF-V1.0` (principles, scoring architecture, rules) | `import_aiqif` (master workbook; `--withdraw-others` withdraws the old Source Pack drafts; keeps expert-written levels) — see `docs/SOURCE_LIBRARY.md` |
| **3.1 · Catalogue (replaced by AI-QIF)** | `Pillar` (10), `Capability`, `Benchmark` (draft → active → superseded / withdrawn; kind mandatory / recommended / guidance / proposed; expert owner), `EvidenceType` (EV codes), `MaturityDefinition` (L3/L2/L1, placeholder flag) | `import_benchmark_catalogue` (Source Pack workbook; keeps expert-edited levels on re-import) |
| **3.2 · Linking** | `BenchmarkRequirement` (primary / supporting / crosswalk) | `services/linking.py` — suggestions by source code and title acronym |
| **3.3 · Levels** | Expert-written L3/L2/L1: definition, measurement rule, observable requirements, minimum evidence, outcomes, **non-examples** | `services/authoring.py` — the **readiness checklist** (required vs recommended items) |
| **3.4 · Evidence rules** | `EvidenceRule` per benchmark level (or any level) or per requirement: evidence type, mandatory, minimum count ≥ 1, maximum age in months, scope, validation method, privacy class | `services/evidence_rules.py` |
| **3.5 · Applicability** | `InstitutionType` (6 seeded), `ProgrammeType` (11 seeded), `ApplicabilityRule` (applies / does not apply / optional / requires review; by institution type, autonomous status, programme, approval body, jurisdiction; priority) | `services/applicability.py` — first matching rule wins, **every result has a reason**; no rules ⇒ "requires review". `evaluate_snapshot()` evaluates a release's frozen rules |
| **3.6 · Releases** | `BenchmarkRelease` (draft → review → approved → published → retired; based on the previous release; content hash) · `BenchmarkReleaseItem` (added / updated / retired / unchanged; JSON snapshot + SHA-256; immutable once published) | `services/releases.py` (readiness before review, **approver ≠ submitter**, publish freezes snapshots and retires the previous release), `services/release_lock.py` (no edits while a benchmark is in a release under review/approved), reopen = new draft version |

Editing is guarded everywhere: only draft benchmarks are editable, requirement
rules only while every linked benchmark is a draft, and every change writes a
`SourceAuditEvent`. Studio tabs: `CatalogueTab`, `RequirementLinking`,
`Applicability`, `LevelsEditorTab` (+ `EvidenceRulesPanel`), `SourceVersionPanel`,
`ReleasesTab`, `WatcherTab`.

**Honest state:** the machinery works end to end in tests, but the content is not
there yet — the 60 imported benchmarks carry identical placeholder levels and
applicability text, no requirement is approved, and no release is published.

## 3.18 The daily source watcher — stage 4 `[IMPLEMENTED]`, off by default

`apps/benchmarks/services/watcher.py`, task `run_source_watcher`, Studio › Watcher.

- **Only switched-on feeds are checked.** All 48 imported feeds start disabled; a
  person opens the address and clicks *Watch daily* (audited). Manual-upload
  sources are never fetched.
- **Polite:** robots.txt respected (re-read each run), honest User-Agent, one
  request per page, 2 s pause per host, 30 s timeout, 20 MB limit.
- **Compares what matters:** document-index pages by their **list of linked
  documents**; web pages by visible text **minus** dates, times, visitor counters
  and number-only lines; files by bytes. The first check is a baseline.
- **Change events** (`SourceChangeEvent`): new document, withdrawal (link gone or
  page now 404/410), new version (file changed), content change, access change
  (403/401 or robots now blocks). Each has an **importance score 0–100** (higher for
  titles like regulation / amendment / notification / guideline / SAR / norms) and
  an **impact list** (approved requirements from that source → linked benchmarks →
  published releases containing them). A page that breaks raises **one** event
  when it stops working, not one per day.
- **Snapshots** (`SourceSnapshot`, one per distinct content, raw copy in
  `media/source_snapshots/`) and a run log (`WatcherRun`: complete / partial
  failure / failed, per-feed errors).
- **People decide:** each event is marked looking into it / accept / reject /
  ignore (note required, audited). **The watcher never edits a source,
  requirement, benchmark or release, and never publishes.** Accepting only
  records the decision.
- **Scheduling:** the project's **first Celery Beat job** — `CELERY_BEAT_SCHEDULE`
  is filled only when `WATCHER_ENABLED=true` (20:30 UTC = 02:00 IST by default), so
  a dev machine never contacts government sites on its own. "Check now" (one page,
  synchronous) and "Check all now" (queued) work without the schedule.
  `manage.py run_source_watcher --codes … --dry-run --include-disabled` tries pages
  without saving anything.
- **Candidates:** material changes now become benchmark candidates for expert review
  (§3.20); `WatcherRun.candidates_created` counts them.

## 3.19 Benchmark assessment — stage 5 `[IMPLEMENTED]`

`apps/assessments/` (9 models, 2 migrations), page **Benchmark Assessment**
(`/benchmark-assessment`). Full rules: `backend/docs/BENCHMARK_ASSESSMENTS.md`.

| Step | Who | What happens |
|---|---|---|
| Profile | Staff | `BenchmarkProfile` next to the existing `Institution` (institution type, autonomous status, approval bodies, jurisdiction) + `Programme` rows. It decides applicability |
| Start | Staff | `AssessmentCycle` on the **current published release** (refused if none); each release item's frozen applicability rules are evaluated against the profile, with the reason stored; "requires review" ones must be decided before evidence is requested; going against the rules needs a note. The profile used is copied into the cycle |
| Ask for evidence | Staff | `not_started → in_progress` |
| Upload | College (any role except viewer) | `EvidenceItem` per evidence request from the release: a file (PDF / Office / CSV / image / text, 25 MB, SHA-256 recorded) or a link, with issue and expiry dates |
| Submit / send back | College / staff | `→ submitted`; staff can return it with a note |
| Review | Staff | `EvidenceReview` — five 0–100 scores (relevance, completeness, currency, authenticity, scope) + accept / ask for more / reject; **reviewer ≠ uploader**; note required unless accepted; append-only |
| Score | Staff | Needs every item reviewed. Writes `BenchmarkAssessment` per included benchmark |
| Finalize | Staff | Needs fresh scores (no review after scoring) and any manual-review level confirmed; then frozen, and the **college can see the scorecard** |

**The four scores** (method `stage5-v1`, each 0–100, kept separate as the
architecture requires):

| Score | How |
|---|---|
| Compliance | Share of mandatory foundational (L3 or any-level) evidence requests met. **Empty** for InGage-proposed benchmarks — nothing legal to comply with |
| Maturity | Level reached — none 0, L3 33.33, L2 66.67, L1 100; a level counts only when all its mandatory requests and those below are met. The assessor may set a different level **with a reason** |
| Evidence confidence | Average of the reviewers' five quality scores over accepted, current evidence |
| Outcome | Entered by the assessor from a measured result (note required); empty until then |
| Composite | Only with weights the benchmark owner approved (`BenchmarkScoreRule`, must add up to 1) for the active `ScoringModel` (`BM-SCORE-1`, seeded **with no weights**); empty while any weighted score is empty. The weights used are copied into the assessment |

Evidence does not count if it is not accepted, has expired, or is older than the
request's maximum age (an issue date is then required). Every score carries its
reason in `detail`; "—" on the scorecard means *not calculated*, never zero.

**Reusing audit documents:** when uploading evidence, a college can pick a document
it already uploaded in an AI Readiness Audit sprint (its own only); the file is
served from there. This is the first link between the two halves of the product.

**Not built yet:** AI-suggested evidence claims (`evidence_claims`), comparing
assessments across releases, and a stated relationship between the pillar CRI and
the benchmark scores on a client report.

## 3.20 Benchmark candidates — stage 4b `[IMPLEMENTED]`

`apps/benchmarks/services/candidates.py`, Studio › Candidates (schema:
`benchmark_candidates`, `candidate_reviews`).

- **From the watcher:** every change event with importance ≥ 50 (new document, new
  version, content change, withdrawal) creates one *update benchmark* candidate per
  benchmark linked to the changed source — or one *review this source* candidate when
  nothing is linked yet — straight into expert review.
- **Filtered automatically:** low-authority sources (intelligence signals, feed trust
  < 50) are created as rejected; a candidate duplicating an open one is not created.
- **By staff:** new / update / retire / source-review candidates, from any watcher
  event or from scratch.
- **Who approves:** by source and topic — regulatory → accreditation + legal;
  accreditation bodies → accreditation + academic; AI or InGage-proposed benchmarks →
  + AI governance + academic. **A different person per role**; any reject rejects;
  "needs research" sends it back. Reviews are append-only and audited.
- **Never automatic:** an approved candidate only lets staff reopen the benchmark as a
  new draft; it is marked *published* when a release carrying that benchmark is
  published (hook in `releases.publish`).

## 3.21 Improvement plan — stage 6 `[IMPLEMENTED]`

`apps/assessments/plan.py`, shown on the Benchmark Assessment page once a cycle is
finalized (schema: `gaps`, `transformation_templates`, `initiatives`, `tasks`).

| Gap | When | Severity |
|---|---|---|
| Capability | level below target | critical (no level, mandatory) / high (2+ short) / medium |
| Compliance | compliance < 100 | critical / high (mandatory), medium (recommended), low |
| Evidence | confidence < 60 with accepted evidence | medium |
| Outcome | outcome < 70 | high (< 50) / medium |
| Dependency | added by staff | — |

Each gap gets an initiative due by severity (30 / 60 / 90 / 180 days): from the
benchmark's **transformation template** for that gap type when experts wrote one,
otherwise one task per unmet mandatory evidence request up to the target. The
college runs initiatives and tasks (owners, dates, status, extra tasks); staff decide
on gaps. **A gap is validated only by linking accepted evidence** for the same
benchmark and college, and only a validated gap closes — the manager's rule "never
close a gap without accepted evidence".

---

# 4. Frontend architecture

## 4.1 Framework and build

**React 18.2 + TypeScript 5.2 + Vite 5.1**, no meta-framework, no SSR. Built with
`tsc && vite build` into `dist/`, then baked into an nginx image.

Dev server: `vite --host 0.0.0.0 --port 3000`, with a proxy sending `/api` →
`http://localhost:8000` (`vite.config.ts`). In production nginx does the same job.

## 4.2 Structure

```
frontend/src/                 # 92 .ts/.tsx files
├── main.tsx              # ReactDOM.createRoot bootstrap
├── App.tsx               # Router + all 30 route entries; ProtectedLayout + StandaloneRoute
├── api/                  # 19 axios modules, one per backend domain
│   ├── client.ts         #   the shared axios instance + interceptors
│   ├── benchmarks.ts     #   the whole benchmark library API (stages 1–4)
│   ├── assessments.ts    #   benchmark assessments (stage 5)
│   ├── users.ts · config.ts · evidence.ts   # user admin · scoring rubric · evidence search
├── context/
│   ├── AuthContext.tsx   # user/token/login/logout/loading
│   └── ThemeContext.tsx  # light/dark
├── hooks/useApiResource.ts   # the single data-fetching hook
├── layouts/AppShell.tsx      # Navbar + Sidebar + content
├── components/           # Navbar, Sidebar, ApiStates, PageHeader (PageHeader / TabStrip / FilterPills),
│                         #   TableFilters, ScrollableTable, ScrollToTop,
│                         #   DemoDataNotice (no longer rendered anywhere)
├── data/                 # prototype content — now used ONLY by 3 Benchmark Studio tabs
│   ├── benchmark/        #   types (455 L) · seed (267 L) · scoring (342 L; calculateCRI unused)
│   └── workspaceDemo.ts  #   imported by nothing — dead
├── pages/                # 38 screens/panels across 19 folders
│   ├── benchmark/        #   BenchmarkStudio + 8 real tab/panel components; CRI & Benchmark Intelligence
│   ├── assessments/      #   BenchmarkAssessments + CycleBenchmarkPanel (stage 5)
│   ├── admin/            #   AdminSettings · UsersTab · AIUsageTab
│   ├── evidence/ chat/ compliance/ workspace/   # rewired to real data (§3.12)
│   ├── previews/         #   design previews — not linked from the menu
│   └── …                 #   auth, dashboard, institutions, sprints, documents,
│                         #   facts, gaps, scoring, recommendations, reports, status
├── types/                # 13 type modules, re-exported by types/index.ts
├── utils/                # errors.ts (getErrorMessage + humanizeExtractionError),
│                         #   extractionTiming.ts (elapsed / estimate for a run)
└── index.css             # Tailwind + design tokens
```

**The `data/` folder has shrunk to one consumer.** It was the first
frontend-owned "facts" in the project; after the rewiring only the Editor,
Approvals and AI-candidates tabs of Benchmark Studio still read it, and each says
it is sample content.

## 4.3 Routing

All routes are declared in `App.tsx`. **There is no lazy loading** — every page is
a static top-level import, so the whole app ships as one bundle.

| Path | Guard | Component |
|---|---|---|
| `/login` | `LoginRoute` — redirects to `/dashboard` if a session exists | `Login` |
| `/dashboard` | `ProtectedLayout` | `Dashboard` |
| `/status-dashboard` | **`StandaloneRoute`** | `StatusDashboard` — session-guarded but **outside the app shell**: no Navbar, no Sidebar, and absent from the menu. It reports on how much of the product plan exists, which makes it a report *about* the app rather than a module of it. Reached by URL; carries its own "back to the platform" link |
| `/institution-dna` | `ProtectedLayout` | `InstitutionList` — the list, create form and delete |
| `/institution-dna/:institutionId` | `ProtectedLayout` | `InstitutionDetail` — one institution's 3-tab workspace |
| `/evidence` | `ProtectedLayout` | `EvidenceIntelligence` |
| `/cri-benchmark` | `ProtectedLayout` | `CriBenchmarkIntelligence` |
| `/benchmark-studio` | `ProtectedLayout` | `BenchmarkStudio` — renders "InGage staff only" for any other role; 3 of 10 tabs still on seed data |
| `/benchmark-assessment` | `ProtectedLayout` | `BenchmarkAssessments` — staff see every college; a college user sees only their own |
| `/transformation-plan` | `ProtectedLayout` | `TransformationPlan` |
| `/goals-tasks` | `ProtectedLayout` | `GoalsTasks` |
| `/ai-copilot` | `ProtectedLayout` | `AICopilot` (replaced `/ai-chatbot`) |
| `/reminders` | `ProtectedLayout` | `Reminders` |
| `/compliance` | `ProtectedLayout` | `ComplianceMapping` |
| `/uat-readiness` | `ProtectedLayout` | `UatReadiness` |
| `/admin-settings` | `ProtectedLayout` | `AdminSettings` — 4 tabs; Users and AI Usage are role-gated server-side |
| `/preview/:moduleKey` | `ProtectedLayout` | `ModulePreview` — design write-ups for unbuilt modules. **No longer linked from the menu**; reachable by URL only (see §25) |
| `/sprint/setup` | `ProtectedLayout` | `SprintSetup` |
| `/sprint/:sprintId/upload` | `ProtectedLayout` | `UploadDataPack` |
| `/sprint/:sprintId/monitor` | `ProtectedLayout` | `AIProcessingMonitor` |
| `/sprint/:sprintId/facts` | `ProtectedLayout` | `FactsReview` |
| `/sprint/:sprintId/gaps` | `ProtectedLayout` | `GapDashboard` |
| `/sprint/:sprintId/confirmation` | `ProtectedLayout` | `ConfirmationWorkspace` |
| `/sprint/:sprintId/score` | `ProtectedLayout` | `LiveCRIPreview` |
| `/sprint/:sprintId/approval` | `ProtectedLayout` | `BaselineApproval` |
| `/sprint/:sprintId/recommendations` | `ProtectedLayout` | `RecommendationsReview` |
| `/sprint/:sprintId/report` | `ProtectedLayout` | `ReportPreviewExport` |
| `/`, `*` | — | `Navigate → /dashboard` |

**`ProtectedLayout` checks only for a session (`user`), never a role.** All
role enforcement is server-side. This is a deliberate simplification, but it means
a `viewer` can open the Baseline Approval screen and only discover they cannot act
when the API returns `403`.

**Benchmark Studio is the one page with a client-side role check** — it renders
"available to InGage staff only" for any role other than `super_admin` /
`consultant`. That is a courtesy; the real gate is server-side, where every
`/benchmarks/*` endpoint uses `IsInGageStaff`.

### Sidebar module states

`components/Sidebar.tsx` still supports five row kinds, but only two are in use:

| State | Rendering | In use by |
|---|---|---|
| `live` | Normal link | Every module except Benchmark Studio |
| `admin` | Link + "InGage internal" label | Benchmark Studio |
| `demo` | Link + `DEMO` badge | **None any more** |
| `next` / `planned` | Dimmed, `aria-disabled`, **not a link** | **None any more** |
| — | — | Project Status Dashboard is **not in the sidebar at all** |

## 4.4 State management

There is **no Redux/Zustand/React Query**. State is:

1. **`AuthContext`** — the only global state (user, token, loading).
2. **`ThemeContext`** — light/dark.
3. **`useApiResource<T>(fetcher, deps, enabled)`** — a custom hook giving
   `{data, setData, loading, error, refetch}`. It stores the fetcher in a ref so
   callers can pass a fresh inline arrow on every render without retriggering the
   effect; only `deps`/`enabled` do that. `enabled` exists so a page can skip the
   request while its `sprintId` is still a placeholder, without violating the rules
   of hooks.
4. **Local `useState`** per page for forms and optimistic updates.

## 4.5 API communication

`api/client.ts` is a single axios instance with `baseURL: '/api/v1'` and two
interceptors:

**Request interceptor** — attaches `Authorization: Bearer <aios_token>` from
`localStorage`.

**Response interceptor — silent refresh on 401:**

```mermaid
sequenceDiagram
    participant P as Page
    participant A as api (axios)
    participant RC as refreshClient (plain axios)
    participant API as Backend

    P->>A: GET /sprints/{id}/facts
    A->>API: + Bearer <expired>
    API-->>A: 401
    A->>A: not /auth/login|/auth/refresh, not already _retried
    A->>RC: POST /auth/refresh {refresh}
    Note over A,RC: refreshInFlight promise dedupes<br/>concurrent 401s into ONE refresh call
    RC->>API: (no interceptors — cannot recurse)
    API-->>RC: {access}
    RC-->>A: new token → localStorage
    A->>API: retry original request with new token
    API-->>P: 200
```

If the refresh fails, `clearSessionAndRedirect()` wipes both tokens and hard-navigates
to `/login` (guarding against a redirect loop when already there).

## 4.6 Token / session handling

| Concern | Implementation |
|---|---|
| Storage | `localStorage`: `aios_token` (access), `aios_refresh_token` (refresh) |
| Rehydration | `AuthContext` effect calls `GET /auth/me` whenever `token` changes; a failure clears the session |
| Logout | Best-effort `POST /auth/logout` to blacklist the refresh token, **then** clear locally — the comment explains the ordering matters because clearing first would race the outgoing request's `Authorization` header out from under it |
| Refresh rotation | Access token replaced in place; the refresh token is **not** rotated (backend has `ROTATE_REFRESH_TOKENS: False`) |

## 4.7 Forms, uploads, errors, loading

- **Forms:** plain controlled `useState` inputs. No form library.
- **File upload:** `FormData` + `api.post(..., {headers: {'Content-Type': 'multipart/form-data'}})` in `api/documents.ts`.
- **File download:** `api.get('/reports/{id}/download', {responseType: 'blob'})`.
- **Errors:** `utils/errors.ts::getErrorMessage()` normalises all three DRF error
  shapes — `{detail}`, `{non_field_errors: [...]}`, and `{field: [msg]}` — into one
  display string. `humanizeExtractionError()` additionally rewrites known backend
  extraction errors (rate limit, timeout, unreachable, corrupt PDF, unconfigured
  key) into user-facing guidance, and correctly suppresses "this will retry
  automatically" once retries are exhausted.
- **Loading/empty/error UI:** shared in `components/ApiStates.tsx`.
- **Polling:** `AIProcessingMonitor`, `ReportPreviewExport` and (while a Drive
  import runs) `UploadDataPack` all `setInterval` at **3000 ms**, using a ref to the
  latest refetch so the interval isn't rebuilt.
- **Tables:** `components/TableFilters.tsx` (search + filter pills) and
  `components/ScrollableTable.tsx` are shared by the documents, facts and gaps
  tables.

## 4.8 Page / component table

| Page or component | Purpose | APIs used | Important logic |
|---|---|---|---|
| `pages/auth/Login.tsx` | Sign in, "Forgot password?" link | `POST /auth/login` | Demo quick-login only in a dev build (`VITE_SHOW_DEMO_PERSONAS=true`) |
| `pages/auth/PasswordReset.tsx` | `/forgot-password`, `/reset-password` (public) | `POST /auth/password-reset`, `/auth/password-reset/confirm` | — |
| `pages/dashboard/Dashboard.tsx` (245) | Cross-sprint overview | `GET /dashboard` | Renders 7 metric tiles + sprint cards |
| `pages/status/StatusDashboard.tsx` (318) | Build-progress report | — | **No API calls.** Every figure is a module-level constant; the headline counts are derived from that list rather than typed. Renders outside the app shell. See §25 |
| `pages/evidence/EvidenceIntelligence.tsx` (355) | Evidence position for one sprint | documents, facts, gaps, sprints | Missing documents read from the backend's `missing_document` gaps — no frontend copy of the required list |
| `pages/benchmark/CriBenchmarkIntelligence.tsx` (533) | Pillar CRI, gaps, roadmap | scoring, gaps, recommendations, sprints | Reads the real 8-pillar engine. Its header comment ("benchmark library has no backend") predates §3.17 |
| `pages/benchmark/BenchmarkStudio.tsx` (730) | Benchmark library workspace, 10 tabs | `api/benchmarks.ts` | Staff gate; hosts the 7 real tab components below plus 3 seeded prototype tabs |
| `pages/benchmark/CatalogueTab.tsx` (154) · `RequirementLinking.tsx` (195) · `Applicability.tsx` (223) · `LevelsEditorTab.tsx` (236) · `EvidenceRulesPanel.tsx` (152) · `SourceVersionPanel.tsx` (202) · `ReleasesTab.tsx` (203) · `WatcherTab.tsx` (283) | The real Studio tabs (§3.17–§3.18) | `/benchmarks/*` | Every rule (readiness, four-eyes, review lock, quote check) is enforced server-side; the tabs show the server's reasons |
| `pages/assessments/BenchmarkAssessments.tsx` (362) · `CycleBenchmarkPanel.tsx` (326) | Benchmark assessment (§3.19) | `/assessments/*` | College picker, profile, cycles, step bar, evidence upload/review, assessor input, weights, scorecard. Scores hidden from the college until finalize |
| `pages/workspace/TransformationPlan.tsx` (328) | Recommendations as a phased plan | recommendations, scoring, sprints | Groups by the timeline the generators already stamp |
| `pages/workspace/GoalsTasks.tsx` (406) | Who owes what | facts, gaps, recommendations, sprints | Derived work items; says plainly there is no task model |
| `pages/chat/AICopilot.tsx` (393) | Questions about the sprint | sprints, scoring, gaps, documents, recommendations, **evidence-search** | **No LLM.** Fixed intents answered from the API; everything else goes to vector search with citations |
| `pages/workspace/Reminders.tsx` (256) | What is waiting on whom | documents, facts, gaps, sprints | Nothing is sent — no notifier exists |
| `pages/compliance/ComplianceMapping.tsx` (226) | Accreditation evidence held / missing | documents, gaps, sprints | Only claims a framework when the document type names it |
| `pages/workspace/UatReadiness.tsx` (273) | Hand-over readiness | baseline, documents, facts, gaps, reports, sprints | Six computed checks; cannot record a sign-off |
| `pages/admin/AdminSettings.tsx` (296) · `UsersTab.tsx` (314) · `AIUsageTab.tsx` (227) | Admin / Settings (§3.16) | `/scoring/config`, `/users`, `/extraction-jobs/usage-report` | Users and AI Usage tabs are enforced server-side by role |
| `pages/previews/ModulePreview.tsx` (299) | Design write-up for an unbuilt module | — | Grey wireframes with **no values that could pass for data**. Unlinked from the menu since the ports landed |
| `pages/institutions/InstitutionList.tsx` (323) | Institution DNA landing page | `GET/POST /institutions`, `DELETE /institutions/{id}` | Create gated to `WRITE_INSTITUTION_ROLES`, delete to the narrower `DELETE_INSTITUTION_ROLES`; blank optional fields are omitted from the POST rather than sent as `""` |
| `pages/institutions/InstitutionDetail.tsx` (1 035) | One institution, 3 tabs | `GET/PATCH /institutions/{id}`, `+/leaders`, `+/departments`, `+/systems` | Derived vs. stored counts; write actions offered only to the roles in §8 |
| `pages/sprints/SprintSetup.tsx` (191) | Audit step 1 | `GET /institutions`, `POST /sprints` | **Selects** an institution — no longer creates one, and no mode picker |
| `pages/documents/UploadDataPack.tsx` (753) | Screen 2 | `GET/POST /sprints/{id}/documents`, `upload-file`, `drive-import-jobs` (+ `/stop`), `extraction-jobs {document_ids}`, `DELETE /documents/{id}` | Holds `REQUIRED_CHECKLIST`, the frontend twin of `DRIVE_IMPORT_CHECKLIST` — **kept in sync by hand**; live Drive progress; filterable records table with row selection |
| `pages/documents/AIProcessingMonitor.tsx` (520) | Screen 3 | `extraction-jobs`, per-job `cancel` / `process`, sprint `cancel` / `process-incomplete`, `ai-usage`, `DELETE` | 3 s polling; run timing + estimate; AI mode, router per job, token usage and cost; `humanizeExtractionError` |
| `pages/facts/FactsReview.tsx` (307) | Screen 4 | `GET /sprints/{id}/facts`, 4 fact actions | `TableFilters` by status/pillar/confidence/document |
| `pages/gaps/GapDashboard.tsx` (259) | Screen 5 | `GET /sprints/{id}/gaps`, resolve/skip/mark-unavailable | Groups by priority; shows each gap's source document |
| `pages/facts/ConfirmationWorkspace.tsx` (193) | Screen 6 | facts + fact actions | Owner-role-oriented queue |
| `pages/scoring/LiveCRIPreview.tsx` (127) | Screen 7 | `GET/POST /sprints/{id}/score` | Shows 8 pillars + confidence |
| `pages/scoring/BaselineApproval.tsx` (352) | Screen 8 | `GET /baseline`, approve, approve-provisional, return | Disables approve when `can_approve === false` |
| `pages/recommendations/RecommendationsReview.tsx` (200) | Screen 9 | `GET/POST recommendations`, `PATCH /recommendations/{id}` | Renders `trigger_gap` as the citation |
| `pages/reports/ReportPreviewExport.tsx` (247) | Screen 10 | `GET/POST reports`, `GET /reports/{id}/download` | 3 s polling until `ready`; blob download |
| `components/Sidebar.tsx` (350) | Whole-platform nav | — | One group (Platform Modules); the 10 audit steps nest under AI Readiness Audit and never collapse; Benchmark Studio carries the "InGage internal" label |
| `components/Navbar.tsx` (66) | User menu | — | Uses `user.name` from the serializer |
| `components/ApiStates.tsx` (53) | Loading/error/empty | — | Shared across every page |
| `layouts/AppShell.tsx` (25) | Chrome | — | Navbar + Sidebar + `activeSprintId` |
| `hooks/useApiResource.ts` (49) | Fetch hook | all | Ref-stabilised fetcher, `enabled` gate |
| `api/client.ts` (80) | HTTP core | all | Token attach + dedupe-safe silent refresh |

## 4.9 Frontend execution flow

```
main.tsx
  └─ <App>
       └─ ThemeProvider
            └─ BrowserRouter
                 └─ AuthProvider          ← reads localStorage token, GET /auth/me
                      └─ AppRoutes
                           ├─ /login  → LoginRoute → Login
                           └─ /*      → ProtectedLayout
                                          ├─ loading?  → FullScreenLoading
                                          ├─ no user?  → <Navigate to="/login">
                                          └─ AppShell(activeSprintId)
                                               ├─ Navbar
                                               ├─ Sidebar (modules + the 10 audit steps)
                                               └─ <Page>
                                                     └─ useApiResource(...)
                                                          └─ api.get(...) → interceptors → /api/v1
```

---

# 5. Backend architecture

## 5.1 Framework

**Django 5.0.x + Django REST Framework**, served by **Gunicorn** (3 sync workers,
120 s timeout). `config/asgi.py` exists and `uvicorn` is in
`requirements/production.txt`, but **the compose file runs WSGI/gunicorn** — ASGI
is present but unused.

## 5.2 Structure

```
backend/
├── manage.py
├── config/
│   ├── settings.py        # single settings module; prod hardening under `if not DEBUG`
│   ├── ai_processing_mode.py  # parse AI_PROCESSING_MODE; derive worker concurrency
│   ├── urls.py            # root router + drf-spectacular schema/docs
│   ├── celery.py          # Celery('aios_backend'), autodiscover_tasks(), worker_ready mode log
│   ├── pagination.py      # OptionalPageNumberPagination
│   ├── wsgi.py / asgi.py
├── apps/
│   ├── accounts/          models, serializers, views, tokens, permissions, user_admin (+ user_urls), management/commands/seed_demo_users
│   ├── institutions/      models (Institution + Leader/Department/System), serializers, views, constants, filters
│   ├── sprints/           models (state machine), views (+overview), access.py, filters
│   ├── documents/         models, serializers, views, services, tasks, drive_import, constants, utils, exceptions
│   ├── extraction/        models (ExtractionJob, AIUsage), views, tasks, usage, pricing, checks,
│   │                      management/commands/{ai_mode_status, ai_usage_report, import_ai_usage}, services/ (15 modules)
│   ├── facts/             models, serializers, views, filters
│   ├── gaps/              models, serializers, views, services, filters, constants
│   ├── scoring/           models, serializers, views, constants, services/{cri_engine, baseline}
│   ├── recommendations/   models, serializers, views, services
│   ├── reports/           models, serializers, views, services, tasks, rendering, utils
│   ├── dashboard/         serializers, views     ← no models; pure aggregation
│   ├── vector_store/      models, serializers, views, tasks, exceptions, services/ (5 modules)
│   ├── benchmarks/        models (24), serializers, views, urls, tasks, admin, services/ (12 modules),
│   │                      management/commands/{import_source_register, ingest_source_files,
│   │                      import_benchmark_catalogue, run_source_watcher}
│   └── assessments/       models (9), services, serializers, views, urls, admin
├── requirements/{base,ocr,development,production}.txt
├── docs/{API_CONTRACT.md, openapi.yaml, VECTOR_STORE.md, AI_PROCESSING_MODES.md,
│         SOURCE_LIBRARY.md, BENCHMARK_ASSESSMENTS.md}
├── Dockerfile, docker-entrypoint.sh, .dockerignore
```

## 5.3 Module table

| App | Purpose | Important files | Main responsibility |
|---|---|---|---|
| `config` | Project wiring | `settings.py`, `ai_processing_mode.py`, `urls.py`, `celery.py`, `pagination.py` | Settings, the AI mode switch, root routing, Celery app (+ the one beat schedule), opt-in pagination |
| `accounts` | Identity + authorization | `models.py`, `permissions.py` (198 L), `user_admin.py` (198 L), `tokens.py`, `management/commands/seed_demo_users.py` (163 L) | Custom `User`, 11 roles, **all reusable permission classes and the institution-scoping helpers**, user administration |
| `institutions` | Tenant **+ Institution DNA** | `models.py` (4 models), `serializers.py`, `views.py`, `constants.py`, `urls.py` | Institution CRUD (**DELETE is a hard cascade** — see §7.1); leadership, departments and IT systems as nested sub-resources; the digital-maturity rubric |
| `sprints` | Workflow spine | `models.py` (124 L, state machine), `views.py` (130 L), `access.py`, `urls.py` (144 L) | Sprint lifecycle, one-call overview, **composes every nested `/sprints/<id>/…` route** |
| `documents` | Evidence intake | `services.py`, `tasks.py` (303 L), `drive_import.py` (231 L), `constants.py` (84 L) | Upload validation, checksum dedupe, whole-folder Drive import with Stop, authenticated download |
| `extraction` | The AI pipeline | `services/` (15 modules, ~2 550 L), `tasks.py` (219 L), `usage.py`, `pricing.py` | 7-stage pipeline, provider-agnostic AI, PyMuPDF + PaddleOCR reading, router pool, retry policy, Stop/Process, AI usage + cost |
| `facts` | Human review | `models.py`, `views.py` (136 L) | 4 review actions + append-only `FactReviewHistory` |
| `gaps` | Data-gap tracking | `services.py` (208 L), `models.py` (114 L, 3 partial constraints) | 5 detectors + `create_gap_if_new` idempotency primitive |
| `scoring` | CRI engine | `services/cri_engine.py` (340 L), `services/baseline.py` (144 L), `models.py` (218 L) | 9-step deterministic scoring; baseline approval workflow |
| `recommendations` | Actionable output | `services.py` (204 L) | 3 idempotent generators |
| `reports` | Deliverable | `services.py` (203 L), `rendering.py` (204 L), `tasks.py` (80 L) | 11-section report data + PDF/DOCX rendering |
| `dashboard` | Aggregation | `views.py` (90 L) | Cross-sprint metrics; **owns no models** |
| `vector_store` | Semantic retrieval | `services/pinecone_client.py` (470 L), `services/indexer.py` (300 L), `services/embeddings.py` (221 L), `services/search.py` (157 L), `services/chunking.py` (145 L) | Chunk → embed → upsert college document text; institution-isolated evidence search. **Entirely optional** — see §3.11 |
| `benchmarks` | Benchmark library (stages 1–4) | `models.py` (788 L, 24 models), `views.py` (816 L), `services/` (12 modules: register/catalogue import, file intake, approval, requirement drafting, linking, authoring, evidence rules, applicability, releases, release lock, watcher), `tasks.py` | Source Library → requirements → catalogue → levels / evidence / applicability → releases → daily watcher. **Staff only.** See §3.17–§3.18 |
| `assessments` | Benchmark assessment (stage 5) | `services.py` (543 L), `views.py` (353 L), `models.py` (240 L, 9 models) | College profile, cycles on the published release, evidence upload + review, four scores, finalize. See §3.19 |

## 5.4 How a request travels through the backend

```mermaid
graph TD
    A["HTTP request"] --> B["CorsMiddleware"]
    B --> C["SecurityMiddleware<br/>(HSTS, SSL redirect when DEBUG=False)"]
    C --> D["Session / Common / CSRF / Auth / Message / XFrameOptions"]
    D --> E["config.urls → apps.*.urls<br/>(APPEND_SLASH=False; both slash forms registered)"]
    E --> F["DRF view dispatch"]
    F --> G["JWTAuthentication<br/>DEFAULT_AUTHENTICATION_CLASSES"]
    G --> H["permission_classes<br/>IsAuthenticated + role gate"]
    H --> I{"nested /sprints/id/… ?"}
    I -->|yes| J["get_authorized_sprint()<br/>404 if missing, 403 if wrong institution"]
    I -->|no| K["has_object_permission<br/>IsInstitutionMember"]
    J --> L["Serializer validation"]
    K --> L
    L --> M["Service layer<br/>(gaps.services / cri_engine / baseline / documents.services)"]
    M --> N["Django ORM → PostgreSQL"]
    M -.->|"async work"| O[".delay() → Redis → Celery"]
    N --> P["Serializer → Response"]
    O -.-> P
    P --> Q["DRF exception handler<br/>400/401/403/404/405 JSON"]
```

**Verified specifics:**

- `APPEND_SLASH = False`, and **every collection/action route is registered twice**
  (with and without a trailing slash) because the frontend's axios calls are
  inconsistent about it. The settings comment explains why the default redirect was
  unacceptable: it turns a `POST` body into a dropped `GET`.
- `DEFAULT_PERMISSION_CLASSES = (IsAuthenticated,)` — **everything is authenticated
  by default**; only `LoginView` opts out with `AllowAny`.
- Pagination is **opt-in**: without `?page`/`?page_size`, list endpoints return a
  bare JSON array (what the frontend's `.map()` expects); adding either switches to
  `{count, next, previous, results}`.

## 5.5 The permission model

`apps/accounts/permissions.py` separates two orthogonal questions:

**(a) Role gates** — may this *kind* of user do this *kind* of action?

| Class | Write allowed for |
|---|---|
| `CanManageSprint` | `super_admin`, `consultant`, `institution_admin` |
| `CanApproveBaseline` | same three (baseline approval is a management decision) |
| `CanReviewFacts` | **every role except `viewer`** |
| `CanResolveGaps` | **every role except `viewer`** |
| `CanManageRecommendations` | `super_admin`, `consultant`, `institution_admin`, `iqac_coordinator` |
| `CanEditRecommendation` | **`super_admin`, `consultant` only** |
| `CanManageDocument` (in `documents/views.py`) | owner always; DELETE also needs `super_admin`/`consultant`/`institution_admin`/`iqac_coordinator` |
| `CanManageInstitution` (in `institutions/views.py`) | writes: `super_admin`, `consultant`, `institution_admin`; **DELETE: `super_admin`, `consultant` only** |
| `CanManageInstitutionDna` (in `institutions/views.py`) | `super_admin`, `consultant`, `institution_admin` — **including DELETE** |
| **`IsInGageStaff`** | `super_admin`, `consultant` — **for reading too**. Every `/benchmarks/*` endpoint and the staff-only assessment actions; the benchmark library is InGage IP and is never shown to institutions |
| `CanAdministerUsers` (in `accounts/user_admin.py`) | `super_admin`, `institution_admin` (a consultant cannot) — plus the scoping and no-escalation rules in §3.16 |
| `IsSuperAdmin \| IsConsultant` | the platform AI usage & billing report |
| `IsSuperAdmin` / `IsConsultant` / `IsInstitutionAdmin` | single-role gates; the first two are now used (above) |

**Assessments use role checks inside the view** rather than a class: staff create
cycles, review evidence, score and finalize; any institution role except `viewer`
may upload evidence and submit; everyone is held to their own institution by
`require_institution_access`, and a college sees scores only once the cycle is
finalized.

The last two look redundant but are not, and the difference is deliberate:
`CanManageInstitution` restricts DELETE to platform staff because deleting an
*institution* orphans every sprint hanging off it. Removing one department row or
one IT system is an ordinary correction to a list the institution admin maintains,
so `CanManageInstitutionDna` lets DELETE follow the same rule as any other write.
Reusing the stricter class for the sub-resources left institution admins able to
add and edit departments but not remove them — caught by a test, not by review.

All of the sprint-side gates return `True` for `SAFE_METHODS`, so **reading
audit data is open to any authenticated user within their institution scope**.
`IsInGageStaff` is the exception: it gates reads as well.

**(b) Institution scoping** — may this user touch *this particular* record?

- `IsInstitutionMember.has_object_permission()` → `user_can_access_institution()`.
- `_resolve_institution_id(obj)` handles an `Institution` directly, anything with
  `institution_id` (Sprint), or anything nested under a sprint (Document, Fact, Gap,
  Report) via `.sprint`.
- `get_accessible_institution_ids(user)` returns `None` (unrestricted) for
  cross-institution roles, else `{user.institution_id}`.
- `require_institution_access(user, obj)` raises `PermissionDenied` — used by the
  nested views that look up their object manually.

## 5.6 Validation

- **Serializer-level:** `DocumentUploadSerializer` (extension, size, checksum
  dedupe), `LoginSerializer` (`authenticate()` + `is_active`),
  `ChangePasswordSerializer` (old-password check + Django's
  `validate_password` against `AUTH_PASSWORD_VALIDATORS`),
  `DriveImportJobCreateSerializer` (URL parseable to a folder ID before any job runs).
- **Model-level:** `RegexValidator` on phone and `document_type`;
  `MinValueValidator`/`MaxValueValidator` on every 0–1 confidence and 0–100 score;
  `UniqueConstraint`s (see §6).
- **Service-level:** the sprint state machine, `DELETABLE_STATUSES`,
  `BASELINE_LOCKED_STATUSES`, blocking-gap check on full baseline approval. On
  the benchmark side every rule lives in a service module and raises a typed
  error the view turns into a `400` with reasons (`ReleaseError.problems`,
  `AssessmentError.problems`): draft-only editing, the review lock, readiness
  before review, approver ≠ submitter, reviewer ≠ uploader, weights summing to 1.
- **Model-level guards that cannot be bypassed by a careless caller:**
  `SourceVersion.save()` refuses to change frozen fields once a version is no
  longer draft; `SourceAuditEvent` and `EvidenceReview` refuse updates;
  `BenchmarkReleaseItem` refuses changes once its release is published.
- **AI-output-level:** every AI field is re-validated in Python — see §9.4.
---

# 6. Database architecture

**Engine:** PostgreSQL 16 in production (via `dj-database-url` / `DATABASE_URL`);
**SQLite fallback** (`db.sqlite3`) when `DATABASE_URL` is unset — which is how local
development currently runs. `conn_max_age=600` (10-minute persistent connections).

**Every model uses a UUID4 primary key** (`models.UUIDField(primary_key=True,
default=uuid.uuid4, editable=False)`), except Django's own built-ins.

**39 migrations** across 14 apps (54 models), including four data migrations:
`scoring/0002_seed_pillars.py` (the eight pillars), `gaps/0003` (back-fills the
"confirmed fact closes its unconfirmed gap" rule), `benchmarks/0008` (6
institution types, 11 programme types) and `assessments/0002` (the `BM-SCORE-1`
scoring model, active, with no weights).

## 6.1 Model-by-model reference

### `accounts.User` — `accounts_user`
- **Purpose:** identity + role + institution binding. Extends `AbstractBaseUser` + `PermissionsMixin`.
- **PK:** `id` (UUID).
- **Key fields:** `email` (**unique, USERNAME_FIELD**), `username` (unique), `first_name`, `last_name`, `phone` (regex-validated), `role` (11 choices, default `viewer`), `department_name`, `is_active`, `is_staff`, `date_joined`, `updated_at`.
- **FK:** `institution → institutions.Institution` (`SET_NULL`, `related_name='users'`) — null for cross-institution roles.
- **Property:** `is_cross_institution`.
- **Meta:** `ordering = ['email']`.

### `institutions.Institution` — `institutions_institution`
- **Purpose:** the tenant, and (since Institution DNA) the institutional baseline record.
- **Key fields:** `name`, `short_name`, `institution_type`, `university_affiliation`, `website_url`, `location`, `city`, `state`, `country` (default `'India'`), `accreditation_details`, `contact_email`, `contact_phone`, `is_active`.
- **Institution DNA fields:** `student_count`, `faculty_count` (both nullable — an unset count reads as "not recorded", never as zero), `priorities` (JSON list of labels), `digital_maturity_level` (1–5 `IntegerChoices`, nullable), `current_ai_usage` (text).
- **FK:** `created_by → User` (`SET_NULL`, `related_name='created_institutions'`).
- **Not stored:** department and programme counts. Both are derived in `InstitutionDetailSerializer` from the department rows, so a stored copy cannot drift.

### `institutions.InstitutionLeader` — `institutions_institutionleader`
- **Purpose:** one named person on the institution's leadership list.
- **Key fields:** `name`, `role`, `email`, `display_order`.
- **FK:** `institution` (`CASCADE`, `related_name='leaders'`).
- **Notable:** deliberately **not** a link to `accounts.User` — the Director named here is a fact about the org chart, and recording them must not depend on whether they hold a login. `initials` is derived in the serializer, never stored.
- **Meta:** `ordering = ['display_order', 'name']`.

### `institutions.Department` — `institutions_department`
- **Purpose:** an academic department and the headcounts it reports for itself.
- **Key fields:** `name`, `head_name`, `faculty_count`, `student_count`, `program_count`, `display_order`.
- **FK:** `institution` (`CASCADE`, `related_name='departments'`).
- **Constraint:** `UniqueConstraint(['institution', 'name'], name='unique_department_name_per_institution')`. The serializer additionally rejects duplicates **case-insensitively**, so the DB constraint never surfaces as a 500.

### `institutions.InstitutionSystem` — `institutions_institutionsystem`
- **Purpose:** one system in the institution's current IT estate.
- **Key fields:** `name`, `tag` (`legacy` | `manual` | blank), `notes`, `display_order`.
- **FK:** `institution` (`CASCADE`, `related_name='systems'`).
- **Notable:** `tag` marks the two states that matter to an AI-readiness assessment — a legacy system and a still-manual process are both obstacles. It is not a general-purpose category field.

### `sprints.Sprint` — `sprints_sprint`
- **Purpose:** one discovery engagement; the spine every other record hangs off.
- **Key fields:** `name`, `sprint_code` (**unique**, auto `SPR-XXXXXXXX`), `mode` (3 choices), `status` (10 choices), `academic_year`, `description`, `start_date`, `target_completion_date`, `completion_percentage` (0–100), **`overall_cri`** and **`confidence_score`** (denormalized from the latest `ScoringRun` by the engine).
- **FK:** `institution` (`CASCADE`, `related_name='sprints'`), `created_by → User` (`SET_NULL`).
- **Class constants:** `ALLOWED_TRANSITIONS`, `BASELINE_LOCKED_STATUSES`, `STATUS_COMPLETION_MILESTONES`.
- **Meta:** `ordering = ['-created_at']`.

### `documents.Document` — `documents_document`
- **Purpose:** one uploaded evidence file.
- **Key fields:** `document_type` (snake_case slug, regex-validated — **free text, not a `choices=` enum**, so a new type needs no migration), `title`, `file` (FileField → `document_upload_path`), `original_filename`, `mime_type`, `file_size`, **`checksum`** (SHA-256 hex, `db_index=True`), `status` (6 choices), `page_count`, `quality_score`, `ocr_required`, `ocr_warnings` (JSON list), `processing_status` (free-text sub-stage), `uploaded_at`, `processed_at`.
- **FK:** `sprint` (`CASCADE`, `related_name='documents'`), `uploaded_by → User` (`SET_NULL`).
- **Constraint:** `UniqueConstraint(fields=['sprint','checksum'], condition=~Q(checksum=''), name='unique_document_checksum_per_sprint')` — **the same file cannot be uploaded twice to one sprint**.

### `documents.DriveImportJob` — `documents_driveimportjob`
- **Purpose:** one Google Drive folder import run.
- **Key fields:** `drive_url`, `status` (6 choices — `cancelled` added in `0003` for the Stop button), **`results`** (JSON: per-checklist-slot `{status, filename, document_id}` + `additional_files` + `skipped_files` + a live `progress` block), `files_scanned`, `files_imported`, `error_message`, `celery_task_id`, timestamps.
- **Class constant:** `ACTIVE_STATUSES = (pending, scanning, downloading)` — only these can be stopped.
- **FK:** `sprint` (`CASCADE`, `related_name='drive_import_jobs'`), `created_by → User` (`SET_NULL`).

### `extraction.ExtractionJob` — `extraction_extractionjob`
- **Purpose:** one document's trip through the pipeline.
- **Key fields:** `status` (6: pending/running/retrying/completed/failed/cancelled — `cancelled` is now set by the Stop buttons), **`current_step`** (7 fixed stages), `progress_percentage` (0–100), `started_at`, `completed_at`, `error_message`, `retry_count`, `celery_task_id` (also used to skip a stale queue message after a re-process), **`ai_router`** (which router ran the latest attempt, multi_router only — migration `0005`).
- **FK:** `sprint` (`CASCADE`, `related_name='extraction_jobs'`), `document` (`CASCADE`, `related_name='extraction_jobs'`).

### `extraction.AIUsage` — `extraction_aiusage`
- **Purpose:** one AI API call and what it cost — the billing record (§3.15).
- **Key fields:** `stage` (classification / fact_extraction / conflict_check / other), `source` (recorded / imported / estimated), `request_count`, `note`, `provider`, `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`, `duration_ms`, **`cost_usd`** (computed at call time; NULL when the model has no price), `created_at` (indexed).
- **FK:** `institution`, `sprint`, `document`, `extraction_job` — **all `SET_NULL`**, so the usage history survives deleting any of them.
- **Indexes:** `(sprint, created_at)`, `(institution, created_at)`.

### `facts.ExtractedFact` — `facts_extractedfact`
- **Purpose:** one structured fact pulled out of a document.
- **Key fields:** `field_name` (human label), `field_key` (snake_case machine key), **`value`** (JSON, nullable — a correction may legitimately set "unknown"), `normalized_value` (JSON), `data_type` (7 choices), `pillar` (one of the 8 keys), `owner_role`, `source_page`, **`source_snippet`**, `confidence_score` (0–1), `confidence_reason`, `extraction_method`, `status` (5 choices), `reviewed_at`.
- **FK:** `sprint` (`CASCADE`, `related_name='facts'`); **`document`** (`SET_NULL`, `related_name='extracted_facts'`) = extraction lineage, set once; **`source_document`** (`SET_NULL`, `related_name='+'`) = current evidence citation, repointable by a correction; `reviewed_by → User` (`SET_NULL`).

### `facts.FactReviewHistory` — `facts_factreviewhistory`
- **Purpose:** append-only audit of every review action.
- **Key fields:** `action` (4 choices), `original_value` (JSON — the value *before* this action), `new_value` (JSON, only for corrections), `reason`, `created_at`.
- **FK:** `fact` (`CASCADE`, `related_name='review_history'`), `user` (`SET_NULL`).

### `gaps.GapItem` — `gaps_gapitem`
- **Purpose:** something missing, unconfirmed, contradictory, stale, or low-confidence.
- **Key fields:** `gap_type` (5), `title`, `description`, `pillar`, `priority` (4: blocking/high/medium/optional), `status` (5: open/in_progress/resolved/unavailable/skipped), `resolution`, `resolved_at`; conflict-only: `conflict_value_a`, `conflict_value_b` (immutable snapshots), `conflict_confidence` (0–1).
- **FK:** `sprint` (`CASCADE`, `related_name='gaps'`), `source_fact → ExtractedFact` (`SET_NULL`, `related_name='gaps'`), `related_document → Document` (`SET_NULL`, `related_name='gaps'`), `conflict_fact_b → ExtractedFact` (`SET_NULL`), `resolved_by → User` (`SET_NULL`).
- **Three partial unique constraints** (all conditioned on `status__in=['open','in_progress']`):
  1. `unique_active_gap_per_fact_and_type` — `(gap_type, source_fact)` where `source_fact` is not null
  2. `unique_active_gap_per_document_and_type` — `(gap_type, related_document)` where document set and fact null
  3. `unique_active_gap_per_sprint_type_title` — `(sprint, gap_type, title)` where both null
- **Class constant:** `ACTIVE_STATUSES = [open, in_progress]`.

### `scoring.Pillar` — `scoring_pillar`
- **Purpose:** one of the eight CRI pillars, **as a configurable DB row**, so an admin can retune a weight without a deploy.
- **Key fields:** `key` (**unique slug** — the same string stored as `pillar` on Fact/Gap/Recommendation; they join by **string equality, not FK**), `name`, `description`, `weight` (0–1), `display_order`, `is_active`.
- Seeded by `scoring/migrations/0002_seed_pillars.py`.

### `scoring.PillarCriterion` — `scoring_pillarcriterion`
- **Purpose:** a named, weighted check within a pillar.
- **Key fields:** `key`, `name`, `weight` (0–1, normalised against active siblings at evaluation time), **`fact_field_keys`** (JSON list — empty means "every confirmed fact tagged to this pillar"), `is_active`.
- **FK:** `pillar` (`CASCADE`, `related_name='criteria'`); `unique_together = ('pillar','key')`.

### `scoring.PillarScore` — `scoring_pillarscore`
- **Purpose:** the **current** score for one pillar of one sprint. **Overwritten in place** each run.
- **Key fields:** `raw_score` (0–100, pre-weight), `weighted_score` (`raw × pillar.weight`), `confidence_score` (0–1), `status` (not_started/at_risk/developing/strong), `evidence_count`, `gap_count`, `calculation_version`, `calculated_at`.
- **FK:** `sprint` (`CASCADE`, `related_name='pillar_scores'`), `pillar` (`CASCADE`); `unique_together = ('sprint','pillar')`.

### `scoring.ScoringRun` — `scoring_scoringrun`
- **Purpose:** the immutable audit trail of one engine execution.
- **Key fields:** `calculation_version`, `overall_cri`, `overall_confidence`, `evidence_count`, `gap_count`, **`pillar_snapshot`** (JSON — freezes each pillar's numbers, because `PillarScore` rows get overwritten by the next run).
- **FK:** `sprint` (`CASCADE`, `related_name='scoring_runs'`), `triggered_by → User` (`SET_NULL`).

### `scoring.Baseline` — `scoring_baseline`
- **Purpose:** one approval decision-cycle, pinned to an exact `ScoringRun`.
- **Key fields:** `status` (pending/approved/provisional/returned), `approved_at`, `comments`.
- **FK:** `sprint` (`CASCADE`, `related_name='baselines'`), **`scoring_run` (`PROTECT`)** — the pinned run can never be deleted while a baseline references it; `approved_by → User` (`SET_NULL`).
- **Invariant:** once `APPROVED`, never modified again (enforced in `services/baseline.py::_require_pending`). A returned baseline is not reused — a new row is created for the next cycle.

### `scoring.BaselineDecisionHistory` — `scoring_baselinedecisionhistory`
- **Purpose:** append-only log of every submit/approve/approve-provisional/return.
- **FK:** `baseline` (`CASCADE`, `related_name='history'`), `user` (`SET_NULL`).

### `recommendations.Recommendation` — `recommendations_recommendation`
- **Purpose:** one actionable, traceable suggestion.
- **Key fields:** `title`, `description` (always states the triggering data point), `trigger_gap` (display citation), `pillar`, `owner_role`, `priority` (4), `timeline`, **`expected_cri_lift`** (0–100), `support_offering`, `consultant_notes`, `status` (draft/accepted/edited/hidden/completed).
- **FK:** `sprint` (`CASCADE`), `source_gap → GapItem` (`SET_NULL`, `related_name='recommendations'`), `created_by`/`updated_by → User` (`SET_NULL`).
- **M2M:** `supporting_facts → ExtractedFact` (`related_name='recommendations'`).

### `reports.Report` — `reports_report`
- **Purpose:** one generated Discovery Report, **versioned, never overwritten**.
- **Key fields:** `version` (sequential per sprint), `status` (draft/generating/ready/failed), `executive_summary`, `overall_cri`, `confidence_score`, `generated_at`, `pdf_file`, `docx_file`, **`report_data`** (JSON, all 11 sections, `DjangoJSONEncoder`).
- **FK:** `sprint` (`CASCADE`, `related_name='reports'`), `generated_by → User` (`SET_NULL`).
- **Constraint:** `UniqueConstraint(['sprint','version'], name='unique_report_version_per_sprint')`.
- **Meta:** `ordering = ['-version']`.

### `vector_store.VectorDocumentIndex` — `vector_store_vectordocumentindex`
- **Purpose:** tracks one document's presence in the Pinecone index, so indexing is **observable and retryable**. Pinecone cannot answer *"did this document ever index, and if not why"*; this row can. Same role `ExtractionJob` plays for extraction.
- **Key fields:** `status` (pending/processing/indexed/failed), `vector_count`, `embedding_model`, **`content_hash`** (SHA-256 of the extracted *text*, `db_index=True` — not of the file, because text is what gets embedded), `indexed_at`, `error_message`, `celery_task_id`.
- **FK:** `document` (**`OneToOneField`**, `CASCADE`) — re-indexing updates the row rather than accumulating history; `sprint` (`CASCADE`), `institution` (`CASCADE`).
- **`institution` is denormalised** from `document.sprint.institution` so status can be listed per institution without a two-table join on every read. Safe to copy: a document never moves between institutions.
- **Holds no embedding arrays** — those live in Pinecone; a second copy here would have no reader.
- **Index:** `models.Index(['sprint','status'], name='ix_vecidx_sprint_status')` — the only hand-written composite index in the project.
- **Meta:** `ordering = ['-updated_at']`.

### The benchmark library — `apps/benchmarks` (24 models)

All UUID primary keys; each model's docstring names its table in the manager's
`db/schema.sql`. Grouped by stage rather than listed one by one — field-level
detail is in `backend/docs/SOURCE_LIBRARY.md`.

| Stage | Models | Notable rules |
|---|---|---|
| 1 · Sources | `Authority` (code unique) · `Framework` (code unique) · `SourceDocument` (`source_code` unique; role; licensed flag) · `SourceVersion` (draft / active / superseded / withdrawn; collection status; file URI + SHA-256; extraction status) · `SourceFeed` (`unique_source_feed`; `enabled=False` by default) · `SourceAuditEvent` | `unique_source_version` per document; **frozen file fields once a version leaves draft**; audit rows refuse update and delete |
| 2 · Requirements | `SourceSection` (`unique_section_ordinal`) · `RequirementCandidate` (pending / accepted / rejected) · `Requirement` (`code` unique; page; verbatim `source_quote`; kind mandatory / recommended / guidance / proposed) | Accepting a candidate creates the requirement (`created_from`, one-to-one) |
| 3 · Catalogue | `Pillar` (10) · `EvidenceType` (EV codes) · `Capability` · `Benchmark` (`benchmark_code` unique; draft / active / superseded / withdrawn; kind; version label; expert owner) · `BenchmarkRequirement` (`unique_benchmark_requirement`) · `MaturityDefinition` (`unique_benchmark_level`; placeholder flag; non-examples) | Only draft benchmarks are editable |
| 3.4 · Evidence | `EvidenceRule` — **exactly one of** benchmark or requirement (`evidence_rule_one_target` check); `minimum_count ≥ 1` | `unique_requirement_evidence_type` |
| 3.5 · Applicability | `InstitutionType` (6) · `ProgrammeType` (11) · `ApplicabilityRule` (`applicability_rule_one_target` check; M2M to both type tables) | Seeded by `0008` |
| 3.6 · Releases | `BenchmarkRelease` (`release_label` unique; draft → review → approved → published → retired; `based_on`; `content_hash`) · `BenchmarkReleaseItem` (`unique_release_benchmark`; change type; JSON `snapshot` + `snapshot_hash`) | Items refuse changes once published; `PROTECT` from assessments keeps a scored release item from ever being deleted |
| 4 · Watcher | `SourceSnapshot` (`unique_feed_snapshot` on feed + content hash) · `SourceChangeEvent` (kind, materiality 0–100, details, impact, review status) · `WatcherRun` | Snapshots are stored once per distinct content |

### Benchmark assessment — `apps/assessments` (9 models)

| Model | Table (schema) | Key fields / rules |
|---|---|---|
| `BenchmarkProfile` | `institutions` | One-to-one with `Institution`: institution type (FK), autonomous status, approval bodies, jurisdiction |
| `Programme` | `programmes` | Institution, programme type (FK), name, approval body, active |
| `ScoringModel` | `scoring_models` | `code` unique, formula version, description, `active` |
| `BenchmarkScoreRule` | `benchmark_score_rules` | `unique_score_rule` (benchmark × model); four weights 0–1 that must add up to 1; approved by / at / note |
| `AssessmentCycle` | `assessment_cycles` | Institution, name, opens/closes, status (not_started → in_progress → submitted → reviewed → finalized), **`release` FK `PROTECT`**, `profile_snapshot` |
| `ApplicableBenchmark` | `applicable_benchmarks` | `unique_cycle_benchmark`; `release_item` FK `PROTECT` (its snapshot is what is assessed); result + reason; `included` (NULL = a reviewer must decide); target level; selected by |
| `EvidenceItem` | `evidence_items` | Cycle, applicable benchmark, `rule_key` (which request), evidence type, file (`media/assessment_evidence/<cycle>/…`) + SHA-256 or link, issued / valid-until dates, status |
| `EvidenceReview` | `evidence_reviews` | Five 0–100 scores + decision + notes; **append-only** (refuses update) |
| `BenchmarkAssessment` | `benchmark_assessments` | One-to-one with the applicable benchmark; computed level, override + note, the four scores (nullable — empty is not zero), composite, scoring model, **copied weights**, `detail` (the reasons) |

## 6.2 Entity-relationship diagram

```mermaid
erDiagram
    INSTITUTION ||--o{ USER : "employs"
    INSTITUTION ||--o{ SPRINT : "runs"
    INSTITUTION ||--o{ INSTITUTION_LEADER : "is led by"
    INSTITUTION ||--o{ DEPARTMENT : "is organised into"
    INSTITUTION ||--o{ INSTITUTION_SYSTEM : "runs IT"
    USER ||--o{ INSTITUTION : "created_by"
    USER ||--o{ SPRINT : "created_by"

    SPRINT ||--o{ DOCUMENT : "collects"
    SPRINT ||--o{ DRIVE_IMPORT_JOB : "imports via"
    SPRINT ||--o{ EXTRACTION_JOB : "processes"
    SPRINT ||--o{ EXTRACTED_FACT : "yields"
    SPRINT ||--o{ GAP_ITEM : "surfaces"
    SPRINT ||--o{ PILLAR_SCORE : "scores"
    SPRINT ||--o{ SCORING_RUN : "audits"
    SPRINT ||--o{ BASELINE : "approves"
    SPRINT ||--o{ RECOMMENDATION : "advises"
    SPRINT ||--o{ REPORT : "publishes"

    DOCUMENT ||--o{ EXTRACTION_JOB : "is processed by"
    DOCUMENT ||--o{ EXTRACTED_FACT : "is source of"
    DOCUMENT ||--o{ GAP_ITEM : "is stale in"
    DOCUMENT ||--o| VECTOR_DOCUMENT_INDEX : "is indexed as (1:1)"

    INSTITUTION ||--o{ VECTOR_DOCUMENT_INDEX : "owns (denormalised)"
    SPRINT ||--o{ VECTOR_DOCUMENT_INDEX : "tracks"

    EXTRACTED_FACT ||--o{ FACT_REVIEW_HISTORY : "logs"
    EXTRACTED_FACT ||--o{ GAP_ITEM : "triggers"
    EXTRACTED_FACT }o--o{ RECOMMENDATION : "supports"

    GAP_ITEM ||--o{ RECOMMENDATION : "drives"

    PILLAR ||--o{ PILLAR_CRITERION : "is measured by"
    PILLAR ||--o{ PILLAR_SCORE : "is scored as"

    SCORING_RUN ||--o{ BASELINE : "is pinned by"
    BASELINE ||--o{ BASELINE_DECISION_HISTORY : "logs"

    USER ||--o{ EXTRACTED_FACT : "reviewed_by"
    USER ||--o{ GAP_ITEM : "resolved_by"
    USER ||--o{ BASELINE : "approved_by"
    USER ||--o{ REPORT : "generated_by"
```

**The benchmark side** (a separate diagram — it shares only `Institution` and
`User` with the audit):

```mermaid
erDiagram
    AUTHORITY ||--o{ FRAMEWORK : "issues"
    FRAMEWORK ||--o{ SOURCE_DOCUMENT : "contains"
    SOURCE_DOCUMENT ||--o{ SOURCE_VERSION : "is versioned as"
    SOURCE_DOCUMENT ||--o{ SOURCE_FEED : "is watched via"
    SOURCE_FEED ||--o{ SOURCE_SNAPSHOT : "captures"
    SOURCE_DOCUMENT ||--o{ SOURCE_CHANGE_EVENT : "changes in"
    SOURCE_VERSION ||--o{ SOURCE_SECTION : "splits into"
    SOURCE_VERSION ||--o{ REQUIREMENT_CANDIDATE : "drafts"
    SOURCE_VERSION ||--o{ REQUIREMENT : "is source of"
    REQUIREMENT_CANDIDATE ||--o| REQUIREMENT : "accepted as"
    PILLAR ||--o{ BENCHMARK : "groups"
    CAPABILITY ||--o{ BENCHMARK : "is assessed by"
    BENCHMARK ||--o{ BENCHMARK_REQUIREMENT : "interprets"
    REQUIREMENT ||--o{ BENCHMARK_REQUIREMENT : "is interpreted by"
    BENCHMARK ||--o{ MATURITY_DEFINITION : "L3 / L2 / L1"
    BENCHMARK ||--o{ EVIDENCE_RULE : "needs"
    REQUIREMENT ||--o{ EVIDENCE_RULE : "needs"
    BENCHMARK ||--o{ APPLICABILITY_RULE : "applies when"
    BENCHMARK_RELEASE ||--o{ BENCHMARK_RELEASE_ITEM : "freezes"
    BENCHMARK ||--o{ BENCHMARK_RELEASE_ITEM : "snapshot of"
    INSTITUTION ||--o| BENCHMARK_PROFILE : "is profiled as"
    INSTITUTION ||--o{ PROGRAMME : "offers"
    INSTITUTION ||--o{ ASSESSMENT_CYCLE : "is assessed in"
    BENCHMARK_RELEASE ||--o{ ASSESSMENT_CYCLE : "is used by (PROTECT)"
    ASSESSMENT_CYCLE ||--o{ APPLICABLE_BENCHMARK : "includes"
    BENCHMARK_RELEASE_ITEM ||--o{ APPLICABLE_BENCHMARK : "assessed as (PROTECT)"
    APPLICABLE_BENCHMARK ||--o{ EVIDENCE_ITEM : "is proven by"
    EVIDENCE_ITEM ||--o{ EVIDENCE_REVIEW : "is reviewed in"
    APPLICABLE_BENCHMARK ||--o| BENCHMARK_ASSESSMENT : "is scored as"
    SCORING_MODEL ||--o{ BENCHMARK_SCORE_RULE : "weights"
    BENCHMARK ||--o{ BENCHMARK_SCORE_RULE : "is weighted by"
```

**Note on `Pillar` ↔ facts/gaps/recommendations:** these are **not** foreign keys.
`ExtractedFact.pillar`, `GapItem.pillar`, and `Recommendation.pillar` are
`CharField(choices=PILLAR_CHOICES)`, joined to `scoring_pillar.key` by string
equality. The rationale is stated in `apps/scoring/constants.py`: the eight keys are
a closed set the CRI framework itself defines (a constant), whereas *weights and
criteria* are configuration (DB rows).

## 6.3 Constraints & indexes summary

| Constraint / index | Table | Purpose |
|---|---|---|
| `email` unique, `username` unique | `accounts_user` | Identity |
| `sprint_code` unique | `sprints_sprint` | Human-readable sprint id |
| `unique_document_checksum_per_sprint` (partial) | `documents_document` | Same file cannot be uploaded twice |
| `checksum` `db_index=True` | `documents_document` | Fast dedupe lookup |
| `unique_active_gap_per_fact_and_type` (partial) | `gaps_gapitem` | No duplicate active gap per fact |
| `unique_active_gap_per_document_and_type` (partial) | `gaps_gapitem` | No duplicate active stale-data gap |
| `unique_active_gap_per_sprint_type_title` (partial) | `gaps_gapitem` | No duplicate active missing-document gap |
| `unique_together (pillar, key)` | `scoring_pillarcriterion` | One criterion key per pillar |
| `unique_together (sprint, pillar)` | `scoring_pillarscore` | One current score per pillar per sprint |
| `unique_report_version_per_sprint` | `reports_report` | Version numbers never reused |
| `scoring_run` FK `on_delete=PROTECT` | `scoring_baseline` | An approved baseline's run cannot be deleted |
| `unique_department_name_per_institution` | `institutions_department` | No two departments share a name within one institution |
| `document` **`OneToOneField`** (implicit unique) | `vector_store_vectordocumentindex` | One index-tracking row per document; a re-index updates it rather than appending |
| `content_hash` `db_index=True` | `vector_store_vectordocumentindex` | Skip re-embedding unchanged text |
| `ix_vecidx_sprint_status` (composite) | `vector_store_vectordocumentindex` | The status endpoint's exact filter |
| `(sprint, created_at)`, `(institution, created_at)` indexes | `extraction_aiusage` | Billing queries by sprint / institution and period |
| `source_code`, `benchmark_code`, `release_label`, requirement `code` unique | `benchmarks_*` | Human-readable ids for the library |
| `unique_source_version`, `unique_section_ordinal`, `unique_benchmark_level`, `unique_benchmark_requirement`, `unique_release_benchmark`, `unique_feed_snapshot`, `unique_source_feed`, `unique_requirement_evidence_type` | `benchmarks_*` | No duplicate version / section / level / link / release item / snapshot / feed |
| `evidence_rule_one_target`, `applicability_rule_one_target` (check) | `benchmarks_evidencerule`, `benchmarks_applicabilityrule` | A rule belongs to exactly one benchmark **or** one requirement |
| `unique_cycle_benchmark`, `unique_score_rule` | `assessments_*` | One row per benchmark per cycle; one weight set per benchmark per scoring model |
| `release`, `release_item` FKs `on_delete=PROTECT` | `assessments_assessmentcycle`, `…_applicablebenchmark` | A release a college was assessed against can never be deleted |

**Explicit `db_index` on `checksum` and `content_hash`; three composite indexes**
(`ix_vecidx_sprint_status` and the two on `AIUsage`). Foreign keys get Django's
automatic indexes. On a large deployment the hot filters — `facts(sprint_id,
status)`, `gaps(sprint_id, status, priority)`, `documents(sprint_id, status)` — would
each benefit from a composite index of the same shape (see §18).

## 6.4 The CRI scoring engine — nine steps

`apps/scoring/services/cri_engine.py`. **Fully deterministic:** every input is a DB
aggregation or a configuration read; there is no randomness, no wall-clock
dependence, and no external call anywhere in the calculation.

| Step | Function | What it does |
|---|---|---|
| 1 | `_confirmed_facts_for_criterion` | Reads `confirmed`/`corrected` facts for the pillar, narrowed to `criterion.fact_field_keys` if set |
| 2 | `_unresolved_gaps_for_pillar` | Reads `open`/`in_progress` gaps tagged to the pillar |
| 3 | `_evaluate_criterion` | Criterion fulfilment = **average confidence of backing facts × 100**; honestly `0` if none |
| 4 | `_evaluate_pillar` | Weighted average of active criteria, **minus** `GAP_PRIORITY_SCORE_PENALTY` summed over unresolved gaps; clamped to 0–100 |
| 5 | `run_scoring_engine` | `overall_cri = Σ weighted_score`, clamped 0–100 |
| 6 | (in 4 & 5) | Evidence confidence at both levels; `overall_confidence = Σ (pillar_confidence × weight)` |
| 7 | `_persist_pillar_scores` + run creation | Upserts 8 `PillarScore` rows, inserts one `ScoringRun`, updates `Sprint.overall_cri/confidence_score` |
| 8 | `_compute_calculation_version` | `"1.0+<sha256[:12] of active pillar/criterion weights>"` — **an admin retuning a weight automatically changes the version**, flagging older runs as computed under different configuration |
| 9 | `build_score_snapshot` | Returns the explainable payload: pillars, strengths, weaknesses, **live** evidence metrics, unresolved blocking gaps |

**Gap penalty rubric** (`apps/gaps/constants.py`), shared with recommendations as
"expected CRI lift":

| Priority | Penalty / lift |
|---|---|
| `blocking` | 8.0 |
| `high` | 5.0 |
| `medium` | 3.0 |
| `optional` | 1.0 |

**Pillar status rubric** (`apps/scoring/constants.py`), applied in a fixed order:

1. `evidence_count == 0` → **`not_started`**, regardless of score.
2. any unresolved **blocking** gap, or `raw_score < 40` → **`at_risk`**.
3. `raw_score < 70` → **`developing`**.
4. otherwise → **`strong`**.

**Honest non-renormalisation:** if the active pillars' weights do not sum to 1.0,
`overall_cri` is simply the sum of the weighted scores — it is *not* renormalised,
and a deactivated pillar contributes zero rather than redistributing its weight. The
docstring states this is deliberate.

**`build_score_snapshot(bootstrap=...)`** — `True` (used by `GET`/`POST /score` and
report generation) computes a first run on the spot; `False` (used by the read-only
sprint overview) returns `None`, so *loading a dashboard never has the side effect of
persisting scoring rows*.

## 6.5 The eight pillars

| Key | Label |
|---|---|
| `governance_strategy` | Governance & Strategy |
| `curriculum_academic_readiness` | Curriculum & Academic Readiness |
| `faculty_ai_capability` | Faculty AI Capability |
| `student_ai_readiness` | Student AI Readiness |
| `infrastructure_digital_capability` | Infrastructure & Digital Capability |
| `research_innovation` | Research & Innovation |
| `industry_placement` | Industry & Placement Outcomes |
| `evidence_quality` | Evidence Quality & Data Confidence |

## 6.6 A second, server-side scoring engine — benchmark assessment

`apps/assessments/services.py::compute()` scores **one benchmark for one college**
against the frozen release snapshot: compliance, maturity, evidence confidence and
outcome, each 0–100 and kept separate, plus a composite only when approved weights
exist (§3.19). It is deterministic, in Python, tested, and **independent of the
pillar CRI above** — the two answer different questions (audit readiness from
confirmed facts vs. benchmark attainment from reviewed evidence) and nothing
combines them yet. This replaces the earlier situation where the second model was
the prototype's in-browser `calculateCRI` (§3.12).
---

# 7. API documentation

**Base URL:** `/api/v1`. **Auth:** `Authorization: Bearer <access_token>` on
everything except `POST /auth/login` and `POST /auth/refresh`.
**Trailing slashes:** both forms work everywhere (`APPEND_SLASH=False` +
dual registration). **IDs:** UUID4 strings.
**Pagination:** opt-in — add `?page=` or `?page_size=` (default 20, max 100) to
switch a list from a bare array to `{count, next, previous, results}`.

**Interactive docs:** `/api/schema` (OpenAPI YAML), `/api/docs` (Swagger UI),
`/api/redoc`. A checked-in contract also exists at `backend/docs/API_CONTRACT.md`
and `backend/docs/openapi.yaml` — **both last updated at `8742ea7` (1 Sep 2026)**:
they do not cover user admin, AI usage, Drive stop, extraction Stop/Process, the
benchmark library or assessments. The live `/api/schema` does (most of the newer
views are plain `APIView`s, so their request bodies are documented in their
docstrings rather than as serializers).

## 7.1 Full endpoint table

### Authentication — `/api/v1/auth`

| Method | Endpoint | Purpose | Auth | Request | Response |
|---|---|---|---|---|---|
| POST | `/auth/login` | Sign in | **None** | `{email, password}` | `200 {access_token, refresh_token, user}` |
| POST | `/auth/refresh` | New access token | **None** (refresh token is the credential) | `{refresh}` | `200 {access}` |
| POST | `/auth/logout` | Blacklist a refresh token | JWT | `{refresh}` | `205` empty |
| GET | `/auth/me` | Current user | JWT | — | `200 User` |
| POST | `/auth/change-password` | Change own password | JWT | `{old_password, new_password}` | `200 {detail}` |
| POST | `/auth/password-reset` | Email a reset link | **None** | `{email}` | `200 {detail}` (same for unknown emails) |
| POST | `/auth/password-reset/confirm` | Set a new password from the link | **None** | `{uid, token, new_password}` | `200 {detail}` |

### Users — `/api/v1/users`

| Method | Endpoint | Purpose | Auth | Notes |
|---|---|---|---|---|
| GET / POST | `/users` | List / create users | `CanAdministerUsers` — `super_admin`, `institution_admin` | Institution admins see and create only their own college's users and cannot hand out platform roles. Filter, search, optional pagination |
| GET / PUT / PATCH | `/users/{id}` | One user | same | No changing your own role; no moving a user to another institution (institution admin) |
| DELETE | `/users/{id}` | **Deactivate** (`is_active=False`) | same | Never deletes the row; you cannot deactivate yourself |

### Institutions — `/api/v1/institutions`

| Method | Endpoint | Purpose | Auth | Notes |
|---|---|---|---|---|
| GET | `/institutions` | List | JWT | Scoped by `get_accessible_institution_ids`. Returns the **lean** serializer — no leaders, no derived counts |
| POST | `/institutions` | Create | `CanManageInstitution` — `super_admin` / `consultant` / `institution_admin` | Reached from the **Institution DNA list page**; Sprint Setup no longer creates institutions |
| GET | `/institutions/{id}` | Detail | JWT + `IsInstitutionMember` | Returns `InstitutionDetailSerializer`: adds `leaders[]`, `department_count`, `program_count`, `digital_maturity_label`, `digital_maturity_description` |
| PUT/PATCH | `/institutions/{id}` | Update | `CanManageInstitution` | Also how the DNA profile and the Systems & IT assessment are saved |
| DELETE | `/institutions/{id}` | **Hard delete** | `super_admin` / `consultant` only | Cascades to departments, leaders, systems, sprints and everything scoped to those sprints. `perform_destroy` clears `Baseline` rows first, inside a transaction, to dodge the `PROTECT`-vs-`CASCADE` collector trap on `Baseline.scoring_run` |

Out-of-scope detail requests give **403**, not 404 — the queryset is deliberately
unscoped for detail actions so an authorization failure isn't masked as "missing".

### Institution DNA sub-resources — `/api/v1/institutions/{institution_id}/…`

All three follow the identical shape. `InstitutionScopedMixin` resolves and
authorizes the parent institution once, and scopes every queryset to it — so an id
belonging to another institution is a **404 on this route**, not a leak.

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET / POST | `…/leaders` | List / add a leadership entry | read: any member · write: `CanManageInstitutionDna` |
| GET / PATCH / DELETE | `…/leaders/{id}` | One leader | same |
| GET / POST | `…/departments` | List / add a department | same |
| GET / PATCH / DELETE | `…/departments/{id}` | One department | same |
| GET / POST | `…/systems` | List / add an IT system | same |
| GET / PATCH / DELETE | `…/systems/{id}` | One system | same |

**Validation worth noting:** a duplicate department name is rejected
case-insensitively by the serializer (`400`), rather than being left to the
database's unique constraint; an unknown system `tag` is a `400`; and
`priorities` on the institution PATCH is cleaned of blanks and duplicates before
it is stored.

### Sprints — `/api/v1/sprints`

| Method | Endpoint | Purpose | Auth | Notes |
|---|---|---|---|---|
| GET | `/sprints` | List | JWT | Filter (`SprintFilter`) + order + optional pagination |
| POST | `/sprints` | Create | `CanManageSprint` | Institution re-checked in `perform_create` |
| GET | `/sprints/{id}` | Detail | JWT + institution | |
| PUT/PATCH | `/sprints/{id}` | Update | `CanManageSprint` | Status transitions validated against `ALLOWED_TRANSITIONS` |
| DELETE | `/sprints/{id}` | Hard delete | `CanManageSprint` | **Only** from `draft`/`completed`/`archived` |
| GET | `/sprints/{id}/overview` | Everything in one call | JWT + institution | Uses `bootstrap=False` — no scoring side effect |

### Documents

| Method | Endpoint | Purpose | Auth | Notes |
|---|---|---|---|---|
| GET | `/sprints/{id}/documents` | List | JWT + sprint access | Read-only view |
| POST | `/sprints/{id}/upload-file` | **Upload** | JWT + sprint access | `multipart/form-data`; `file`, `document_type`, `title?`, `owner_role?` |
| GET | `/sprints/{id}/drive-import-jobs` | List import jobs | JWT + sprint access | |
| POST | `/sprints/{id}/drive-import-jobs` | Start Drive import | JWT + sprint access | `{drive_url}` |
| POST | `/sprints/{id}/drive-import-jobs/{job}/stop` | Stop a running import | JWT + sprint access | Already-imported documents stay; `400` if the job is no longer active |
| GET/PUT/PATCH | `/documents/{id}` | Detail / edit | `CanManageDocument` | Owner, or any non-viewer |
| DELETE | `/documents/{id}` | Delete + remove file | `CanManageDocument` | Owner, or one of 4 manage roles |
| GET | `/documents/{id}/download` | **Authenticated download** | `IsInstitutionMember` | `FileResponse`, `as_attachment=True` |

### Extraction

| Method | Endpoint | Purpose | Auth | Notes |
|---|---|---|---|---|
| GET | `/sprints/{id}/extraction-jobs` | Job list (polled every 3 s) | JWT + sprint access | |
| POST | `/sprints/{id}/extraction-jobs` | Start extraction | JWT + sprint access | `{}` = all eligible, `{document_id}`, or `{document_ids: [...]}` (the ticked set; already-active ones skipped) |
| GET | `/extraction-jobs/{id}` | Job detail | `IsInstitutionMember` | |
| DELETE | `/extraction-jobs/{id}` | Delete a job | `IsInstitutionMember` | **Only `failed` jobs** |
| POST | `/extraction-jobs/{id}/cancel` | Stop one document | `IsInstitutionMember` | A queued job is skipped when reached; a running one stops at the next checkpoint (between steps or AI calls) |
| POST | `/extraction-jobs/{id}/process` | Run a failed / stopped job again | `IsInstitutionMember` | Resets and re-queues the **same** row |
| POST | `/extraction-jobs/sprints/{id}/cancel` | Stop all active | `IsInstitutionMember` | Marks every queued/running job cancelled; sprint leaves `processing` when nothing is left running |
| POST | `/extraction-jobs/sprints/{id}/process-incomplete` | Re-run every not-completed document | `IsInstitutionMember` | The latest failed/stopped job per document |
| GET | `/sprints/{id}/ai-usage` | Sprint AI tokens + cost | `IsInstitutionMember` + sprint access | Totals, by stage, by model, costliest documents; `?since=&until=` |
| GET | `/extraction-jobs/usage-report` | Platform AI usage & billing | **`super_admin` / `consultant` only** | One row per institution × sprint × month; `?since=&until=&institution=` |

### Facts

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/sprints/{id}/facts` | List (filter + order + optional pagination) | JWT + sprint access |
| GET | `/facts/{id}` | Detail | `IsInstitutionMember` |
| POST | `/facts/{id}/confirm` | Confirm | `CanReviewFacts` |
| POST | `/facts/{id}/correct` | Correct the value | `CanReviewFacts` |
| POST | `/facts/{id}/reject` | Reject | `CanReviewFacts` |
| POST | `/facts/{id}/request-evidence` | Ask the owner for evidence | `CanReviewFacts` |

> There is deliberately **no `PATCH /facts/{id}`** — every value change must go
> through an action so `FactReviewHistory` can never be bypassed.

### Gaps

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/sprints/{id}/gaps` | List | JWT + sprint access |
| GET | `/gaps/{id}` | Detail | `IsInstitutionMember` |
| POST | `/gaps/{id}/resolve` | Mark resolved | `CanResolveGaps` |
| POST | `/gaps/{id}/mark-unavailable` | Data does not exist | `CanResolveGaps` |
| POST | `/gaps/{id}/skip` | Skip for now | `CanResolveGaps` |

> Gaps are **never created by a client POST** — only by the detectors.

### Scoring & baseline

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/sprints/{id}/score` | Current CRI (bootstraps first run) | `CanManageSprint` |
| POST | `/sprints/{id}/score` | Force recalculation | `CanManageSprint` — **refused if baseline-locked** |
| GET | `/sprints/{id}/score/history` | Every past `ScoringRun` | JWT + sprint access |
| GET | `/sprints/{id}/baseline` | Baseline + score + blocking gaps + `can_approve` | `CanApproveBaseline` — **bootstraps a PENDING baseline** |
| POST | `/sprints/{id}/baseline/approve` | Full approval | `CanApproveBaseline` — **refused while blocking gaps exist** |
| POST | `/sprints/{id}/baseline/approve-provisional` | Provisional approval | `CanApproveBaseline` — allowed despite blocking gaps |
| POST | `/sprints/{id}/baseline/return` | Return for correction | `CanApproveBaseline` — **`comments` required** |
| GET | `/scoring/config` | Live pillar/criterion config | JWT |

### Recommendations & reports

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/sprints/{id}/recommendations` | List | `CanManageRecommendations` |
| POST | `/sprints/{id}/recommendations/generate` | Run the 3 generators | `CanManageRecommendations` |
| PATCH | `/recommendations/{id}` | Edit | **`CanEditRecommendation` — consultant/super_admin only** |
| GET | `/sprints/{id}/reports` | Version history | `CanManageSprint` |
| POST | `/sprints/{id}/reports` **or** `/reports/generate` | Generate next version | `CanManageSprint` → `202` |
| GET | `/reports/{id}` | Detail (polled) | `IsInstitutionMember` |
| GET | `/reports/{id}/download?file=pdf\|docx` | Download | `IsInstitutionMember` |

> `?file=` rather than `?format=` **on purpose** — DRF reserves `format` for content
> negotiation and would intercept it before the view.

### Vector store & evidence search — `[IMPLEMENTED]`, optional

Registered in `apps/sprints/urls.py` alongside every other `/sprints/{id}/…`
sub-resource, so institution scoping is the same `get_authorized_sprint()` check.
`apps/vector_store/urls.py` exists but is **deliberately empty** — the app owns a
URLConf only in case a non-nested route is ever needed.

| Method | Endpoint | Purpose | Auth | Notes |
|---|---|---|---|---|
| POST | `/sprints/{id}/vector-index` | Queue every **processed** document in the sprint for indexing | `CanManageSprint` | `202` with the tracking rows. Body: `{force?: bool}` — `force` re-embeds even when the content hash is unchanged. `200` (not an error) when the sprint has no processed documents yet |
| GET | `/sprints/{id}/vector-index/status` | Per-document indexing status | JWT + sprint access | `status`, `vector_count`, `embedding_model`, `content_hash`, `indexed_at`, `error_message`. Optional pagination |
| POST | `/sprints/{id}/evidence-search` | Semantic search over this college's indexed text | JWT + sprint access (**read-only, so any member**) | Body: `{query (3–2000 chars), top_k?, document_type?, scope_to_sprint? (default true)}`. **No institution field** — it is taken from the URL's sprint, which is what makes the filter un-spoofable |

All three return **`503` with a stated reason** when Pinecone is unconfigured, rather
than `500` or a silently empty list. A search whose provider is rate-limited or down
is also `503` ("temporarily unavailable"); a malformed query is `400`. **No Pinecone
index name, host, key or raw match object is ever serialized to the client.**

Each result carries `score`, `text`, `document_id`, `document_name`,
`document_type`, `page_number`, `chunk_index`, `sprint_id`, `institution_id` — there
is no code path that returns an anonymous vector, because a downstream LLM must be
able to say *"according to Faculty_Report.pdf, page 17"*.

### Benchmark library — `/api/v1/benchmarks` (staff only)

Every route uses `IsInGageStaff`, including reads. Grouped here; request bodies
and rules are in `backend/docs/SOURCE_LIBRARY.md`.

| Group | Endpoints |
|---|---|
| Sources (stage 1) | `GET /sources` · `GET /sources/summary` · `GET /sources/{code}` · `POST /versions/{id}/intake` · `…/approve` · `…/withdraw` |
| Requirements (stage 2) | `POST /versions/{id}/draft-requirements` (queues the Celery task) · `GET /versions/{id}/candidates` · `POST /candidates/{id}/review` · `GET /requirements` · `GET /requirements/{code}/suggestions` |
| Catalogue (3.1–3.3) | `GET /catalogue` · `GET /catalogue/{code}` · `GET /pillars` · `GET /evidence-types` · `GET/POST /catalogue/{code}/requirements` · `DELETE /catalogue/{code}/requirements/{req}` · `PUT /catalogue/{code}/levels/{L3\|L2\|L1}` · `GET /catalogue/{code}/readiness` · `GET /catalogue/{code}/history` · `POST /catalogue/{code}/reopen` |
| Evidence rules (3.4) | `GET/POST /catalogue/{code}/evidence-rules` · `GET/POST /requirements/{code}/evidence-rules` · `PATCH/DELETE /evidence-rules/{id}` |
| Applicability (3.5) | `GET /applicability/reference` · `POST /applicability/preview` (a profile → every benchmark with its result and reason) · `GET/POST /catalogue/{code}/applicability-rules` · `GET/POST /requirements/{code}/applicability-rules` · `PATCH/DELETE /applicability-rules/{id}` |
| Releases (3.6) | `GET/POST /releases` · `GET /releases/current` · `GET /releases/{label}` · `POST/DELETE /releases/{label}/items[/{code}]` · `GET /releases/{label}/diff` · `POST /releases/{label}/{submit\|approve\|publish\|send-back}` |
| Watcher (4) | `GET /watcher/summary` · `GET /watcher/feeds` · `POST /watcher/feeds/{id}/enable` · `POST /watcher/feeds/{id}/check` · `GET/POST /watcher/runs` · `GET /watcher/events` · `POST /watcher/events/{id}/review` |

### Benchmark assessment — `/api/v1/assessments`

| Method | Endpoint | Purpose | Who |
|---|---|---|---|
| GET | `/reference` | Choices for the profile form, current release, scoring model, the caller's rights | Any user |
| GET | `/institutions` | Colleges the caller can see, with profile status | Any user (scoped) |
| GET / PUT | `/institutions/{id}/profile` | Benchmark profile + programmes | Read: own college or staff · write: **staff** |
| GET / POST | `/cycles` | List (scoped) / start an assessment on the current published release | Create: **staff**; `400` if no release is published |
| GET | `/cycles/{id}` | Cycle + every benchmark with its applicability reason and evidence counts | Own college or staff; scores only when visible |
| POST | `/cycles/{id}/{open\|submit\|return\|score\|finalize}` | Move the cycle | `submit`: any non-viewer of the college; the rest: **staff** |
| GET / PATCH | `/cycles/{id}/benchmarks/{code}` | Levels, evidence requests with items, scores / include-exclude, target level | PATCH: **staff**; a note is required when overriding the rules |
| POST | `/cycles/{id}/benchmarks/{code}/evidence` | Upload evidence (multipart, or a link) | Any non-viewer of the college, while collecting |
| POST | `/cycles/{id}/benchmarks/{code}/assessment` | Outcome score, level override, notes | **Staff** |
| GET | `/evidence/{id}/file` | Download an evidence file | Own college or staff |
| POST | `/evidence/{id}/review` | Five scores + decision | **Staff**, not the uploader |
| GET | `/cycles/{id}/scorecard` | The scorecard with release hash and scoring model | Staff any time; the college **only once finalized** (`403` before) |
| GET / PUT | `/score-rules[/{code}]` | Composite weights per benchmark for the active model | **Staff** |

### Dashboard & docs

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/dashboard` | 7 metrics + accessible sprint list | JWT |
| GET | `/api/schema`, `/api/docs`, `/api/redoc` | OpenAPI / Swagger / ReDoc | Public |
| — | `/admin/` | Django admin | Session auth |

## 7.2 Detailed specs for the pivotal endpoints

### `POST /api/v1/auth/login`
- **Auth / permission:** `AllowAny`.
- **Body:** `{"email": str, "password": str}`.
- **Validation:** `LoginSerializer` → `authenticate(username=email, password=...)`; rejects `is_active=False`.
- **Processing:** `get_tokens_for_user(user)` mints an HS256 pair signed with `JWT_SECRET_KEY` (falling back to `SECRET_KEY`).
- **DB:** SELECT on `accounts_user`. `UPDATE_LAST_LOGIN` is **False**, so `last_login` is never written.
- **External:** none.
- **Response `200`:** `{access_token, refresh_token, user: {id, institution_id, username, name, first_name, last_name, email, phone, role, department_name, is_active, is_staff, date_joined, updated_at}}`.
- **Errors:** `400 {"non_field_errors": ["Invalid login credentials"]}` or `["This account has been disabled"]`.

### `POST /api/v1/sprints/{id}/upload-file`
- **Permission:** JWT + `get_authorized_sprint()`.
- **Parsers:** `MultiPartParser`, `FormParser`.
- **Body:** `file` (required), `document_type` (required, `^[a-z][a-z0-9_]*$`), `title`, `owner_role`.
- **Validation, in order:** size ≤ `MAX_DOCUMENT_UPLOAD_SIZE` (50 MB) → extension ∈ `ALLOWED_UPLOAD_EXTENSIONS` (`.pdf .doc .docx .xls .xlsx .csv .zip .png .jpg .jpeg`) → SHA-256 checksum not already present in this sprint.
- **Processing:** compute checksum → derive `mime_type` → default `title` from the filename → `Document.objects.create(status=uploaded, ocr_required=ext in OCR_REQUIRED_EXTENSIONS)` → `mark_sprint_collecting()`.
- **DB:** INSERT `documents_document`; possible UPDATE `sprints_sprint.status`.
- **Response `201`:** `DocumentSerializer` including a computed absolute `download_url`.
- **Errors:** `400` (too large / unsupported type / duplicate file / bad `document_type`), `403` (wrong institution), `404` (no such sprint).

### `POST /api/v1/sprints/{id}/extraction-jobs`
- **Body:** `{}` or `{"document_id": uuid}`.
- **Processing:** resolve eligible documents (`uploaded`/`failed`, no active job) → **flip sprint to `processing` before dispatch** → per document: INSERT `ExtractionJob` → `run_extraction_job.delay(job.id)` → store `celery_task_id` → `refresh_from_db()`.
- **Broker down:** the `except Exception` branch marks the job `failed` with `"Could not reach the Celery broker: …"` — **the API stays usable and returns 201 rather than 500**.
- **Response `201`:** array of `ExtractionJobSerializer`.
- **Errors:** `404` (document not in this sprint), `403`.

### `POST /api/v1/sprints/{id}/score`
- **Permission:** `CanManageSprint`.
- **Guard:** `400` if `sprint.status ∈ {baseline_approved, report_ready, completed}`.
- **Processing:** `run_scoring_engine(sprint, triggered_by=user)` → 8 `PillarScore` upserts + 1 `ScoringRun` insert + `Sprint` denormalised fields; then `reviewing → scoring`.
- **Response `200`:** `SprintScoreSerializer` — `overall_cri`, `overall_confidence`, `calculation_version`, `calculated_at`, `pillar_scores[8]`, `strengths[]`, `weaknesses[]`, `evidence_metrics{}`, `unresolved_blocking_gaps[]`.

### `POST /api/v1/sprints/{id}/baseline/approve`
- **Permission:** `CanApproveBaseline`.
- **Validation:** the latest baseline must exist and be `pending`; **`400` if any `blocking` gap is `open`/`in_progress`**, with the count and a pointer to approve-provisionally.
- **Processing:** `Baseline.status = approved`, `approved_by`, `approved_at`, `comments` → `BaselineDecisionHistory` row → `sprint.status = baseline_approved`.
- **Response `200`:** `BaselineSerializer`.

---

# 8. Authentication & authorization

## 8.1 Mechanism

**JWT via `djangorestframework-simplejwt`**, HS256.

| Setting | Value | Source |
|---|---|---|
| `ACCESS_TOKEN_LIFETIME` | **60 minutes** (`JWT_ACCESS_TOKEN_LIFETIME_MINUTES`) | `config/settings.py` |
| `REFRESH_TOKEN_LIFETIME` | **1 day** (`JWT_REFRESH_TOKEN_LIFETIME_DAYS`) | same |
| `ROTATE_REFRESH_TOKENS` | **False** | same |
| `BLACKLIST_AFTER_ROTATION` | **False** | same |
| `UPDATE_LAST_LOGIN` | **False** | same |
| `ALGORITHM` | `HS256` | same |
| `SIGNING_KEY` | `JWT_SECRET_KEY` **falling back to `SECRET_KEY`** | same |
| `AUTH_HEADER_TYPES` | `('Bearer',)` | same |
| `USER_ID_CLAIM` | `user_id` | same |

`rest_framework_simplejwt.token_blacklist` **is** installed, so `POST /auth/logout`
genuinely invalidates a refresh token server-side.

## 8.2 Login flow

```mermaid
sequenceDiagram
    actor U as User
    participant L as Login.tsx
    participant AC as AuthContext
    participant API as POST /auth/login
    participant DB as accounts_user

    U->>L: email + password (or a quick-login button)
    L->>AC: login(email, password)
    AC->>API: {email, password}
    API->>API: LoginSerializer → authenticate(username=email)
    API->>DB: SELECT user WHERE email
    alt no user / bad password
        API-->>AC: 400 {"non_field_errors": ["Invalid login credentials"]}
        AC-->>U: inline error
    else is_active = False
        API-->>AC: 400 ["This account has been disabled"]
    else success
        API->>API: get_tokens_for_user() → HS256 pair
        API-->>AC: 200 {access_token, refresh_token, user}
        AC->>AC: localStorage: aios_token, aios_refresh_token
        AC->>AC: setToken → effect fires GET /auth/me
        AC-->>U: <Navigate to="/dashboard">
    end
```

## 8.3 Token refresh flow

```mermaid
sequenceDiagram
    participant P as Any page
    participant AX as api (interceptors)
    participant RF as refreshClient
    participant API as Backend

    P->>AX: request
    AX->>API: + Bearer access
    API-->>AX: 401
    alt url is /auth/login or /auth/refresh, or already retried
        AX-->>P: reject
    else
        AX->>AX: _retried = true
        Note over AX: refreshInFlight dedupes<br/>parallel 401s into one call
        AX->>RF: POST /auth/refresh {refresh}
        RF->>API: (interceptor-free)
        alt refresh valid
            API-->>RF: {access}
            RF-->>AX: store + return
            AX->>API: replay original + new Bearer
            API-->>P: 200
        else refresh expired / blacklisted
            API-->>RF: 401
            RF-->>AX: null
            AX->>AX: clear both tokens
            AX-->>P: window.location = /login
        end
    end
```

## 8.4 Registration, logout, password

- **Registration:** no self-signup. Accounts come from `python manage.py
  seed_demo_users`, `createsuperuser`, the Django admin, or — since `398bd21` —
  **Admin › Users** (`/api/v1/users`), where a super admin or an institution admin
  creates them under the rules in §3.16.
- **Logout:** `POST /auth/logout {refresh}` → `RefreshToken(...).blacklist()` →
  `205`. The frontend clears local state *after* the call settles.
- **Password change:** `POST /auth/change-password` — verifies `old_password`, runs
  `validate_password` against Django's four validators (similarity, min length,
  common-password list, numeric-only), then `set_password`.
- **Forgot password:** `POST /auth/password-reset {email}` emails
  `{FRONTEND_BASE_URL}/reset-password?uid=..&token=..` (Django's token: works once, expires after
  `PASSWORD_RESET_TIMEOUT`, 1 hour); the answer is the same whether or not the email exists; limited to 10/hour per
  address and 3/hour per email. `POST /auth/password-reset/confirm` runs the same validators, sets the password
  and blacklists every refresh token of the user. Mail goes through Gmail SMTP (`EMAIL_HOST_USER` /
  `EMAIL_HOST_PASSWORD`, an app password); `ADMIN_EMAILS` also receive server errors in production. Set both on
  the server with `scripts/set-email-and-admin.sh`.
- **Password reset by email:** **Not found in the codebase.**
- **Password storage:** Django's default PBKDF2 hasher.
- **Account lockout / brute-force protection:** **Not found in the codebase.**
- **Rate limiting / DRF throttling:** **Not found in the codebase.**

## 8.5 Authorization — the two-layer model

```mermaid
flowchart TD
    A["Request + Bearer token"] --> B["JWTAuthentication<br/>decode HS256, load user by user_id"]
    B -->|invalid| Z1["401 {detail}"]
    B --> C["IsAuthenticated (global default)"]
    C --> D["Layer 1 — ROLE GATE"]
    D --> D1{"SAFE_METHOD?"}
    D1 -->|"yes"| E
    D1 -->|"no"| D2{"role in the gate's allowed set?"}
    D2 -->|no| Z2["403 {detail: gate.message}"]
    D2 -->|yes| E["Layer 2 — INSTITUTION SCOPE"]
    E --> E1{"role in CROSS_INSTITUTION_ROLES<br/>(super_admin, consultant)?"}
    E1 -->|yes| F["Allowed"]
    E1 -->|no| E2{"user.institution_id == object's institution_id?"}
    E2 -->|no| Z3["403 'You do not have access to this institution.'"]
    E2 -->|yes| F
    F --> G["View executes"]
```

- **List endpoints** apply layer 2 by *filtering the queryset*
  (`get_accessible_institution_ids`).
- **Detail endpoints** apply it via `IsInstitutionMember.has_object_permission`,
  deliberately using the **unscoped** queryset so an out-of-scope record returns
  `403` rather than `404`.
- **Nested `/sprints/{id}/…` endpoints** call `get_authorized_sprint()` explicitly,
  because they fetch their sprint from a URL kwarg rather than through DRF's
  generic `get_object()`.

## 8.6 Protected frontend routes

Role-aware, from one file: **`frontend/src/utils/access.ts`**. It holds
`ACTION_ROLES` (each matching a server permission), `MENU_ROLES` (which sidebar
entries and routes a role gets) and `SETTINGS_TAB_ROLES`. The sidebar hides what a
role cannot use; `ProtectedLayout menu="..."` shows **No access** for a typed-in
address; pages hide buttons with `useAccess().can('...')`. The server stays the
authority.

| Who | Menus | Can act |
|---|---|---|
| Super admin / Consultant | Everything; Benchmark Studio is theirs only | All sprint work; edit / accept / hide recommendations; AI usage. Users: super admin only |
| Institution admin | All except Benchmark Studio | Sprints (create, score, baseline, reports), Institution DNA, users of their college |
| IQAC coordinator | Work screens, Baseline Approval (to follow it), Compliance | Upload, facts, gaps, generate recommendations, delete any document |
| Registrar, HOD, HR, Lab, Placement, Faculty | Work screens (Compliance: registrar too) | Upload, facts, gaps; delete their own documents |
| Viewer | Dashboard, Institution DNA, CRI preview, Recommendations, Report, CRI page, Benchmark Assessment, Transformation Plan, AI Copilot, Settings (account) | Read only. The server also refuses uploads, Drive imports and AI processing (`CanContribute`) |

Benchmark Assessment still decides its own actions from the server's `is_staff` /
`can_upload` flags.
---

# 9. AI / LLM workflow

This is the heart of the product. Four call sites — the three extraction stages
below plus **requirement drafting** in the benchmark library (§9.8) — one
provider-agnostic factory, and a hard rule that **Python re-validates everything
the model returns**.

## 9.1 Provider selection

`apps/extraction/services/ai_service.py::get_ai_service()`.

**First, the mode** (§3.14). In `multi_router` mode the factory uses the router
held by the current job's lease (`AI_ROUTER_URLS` / `AI_ROUTER_API_KEYS` /
`AI_ROUTER_MODEL`) and **refuses** to make a call without a lease — it never falls
back to `AI_BASE_URL`. In `single` mode it follows the flow below.

```mermaid
flowchart TD
    A["get_ai_service()"] --> B["resolved_key =<br/>AI_API_KEY or OPENAI_API_KEY"]
    B -->|empty| Z1["ImproperlyConfigured:<br/>'No AI provider API key is configured'"]
    B --> C{"AI_BASE_URL set?"}
    C -->|yes| D["OpenAI-COMPATIBLE endpoint<br/>(local router / gateway / proxy)"]
    D --> D1{"model configured?"}
    D1 -->|no| Z2["ImproperlyConfigured:<br/>'AI_BASE_URL is set but no model'"]
    D1 -->|yes| D2["OpenAIExtractionService(base_url=…)"]
    C -->|no| E["detect_provider(key) — by prefix"]
    E --> E1{"starts with 'sk-ant-'"}
    E1 -->|yes| F["AnthropicExtractionService<br/>default: claude-haiku-4-5-20251001"]
    E1 -->|no| E2{"starts with 'sk-'"}
    E2 -->|yes| G["OpenAIExtractionService<br/>default: gpt-4o-mini"]
    E2 -->|no| Z3["ImproperlyConfigured:<br/>unrecognized key format — fails loudly"]
```

Three points worth naming:

1. **Prefixes are checked longest-first** (`sk-ant-` before `sk-`), because a naive
   `sk-` check would swallow Anthropic keys.
2. **`AI_BASE_URL` wins outright** over key detection — a custom endpoint already
   states where to send requests, and its keys follow neither provider's format.
3. **`OPENAI_EXTRACTION_MODEL` is only honoured when the key is actually an OpenAI
   key** — otherwise a leftover `gpt-4o-mini` would be handed to a Claude client the
   moment someone swaps the key.

Both concrete services implement the identical contract:

```python
extract_structured_data(*, system_prompt, user_content,
                        response_schema, schema_name, timeout=60) -> dict
```

and raise the same `RecoverableExtractionError` / `PermanentExtractionError`
taxonomy — so nothing downstream knows or cares which provider answered.

| | OpenAI | Anthropic |
|---|---|---|
| Structured output | `response_format={'type':'json_schema', 'json_schema':{…, 'strict': True}}` | **Forced single tool call** whose `input_schema` *is* the requested schema, `strict: True`, `disable_parallel_tool_use: True` |
| Result read from | `choices[0].message.content` → `json.loads` | the matching `tool_use` block's `.input` |
| Truncation detected via | `finish_reason == 'length'` | `stop_reason == 'max_tokens'` |
| Also detects | `finish_reason == 'content_filter'` | `stop_reason == 'refusal'`, `'model_context_window_exceeded'` |
| Output cap | provider default | **`DEFAULT_MAX_TOKENS = 16000`** — the comment explains 4096 silently truncated dense fact chunks |

**OpenAI-compatible endpoints (routers such as 9router) get extra handling**
(`1473056`), because many drop `response_format` and the model then answers in
prose:

1. The JSON Schema is **also written into the system prompt** with an "output only
   JSON" instruction, so it works whether or not the router forwards
   `response_format` (still sent for those that do). Endpoints that reject
   `response_format` outright are remembered and it is no longer sent to them.
2. Replies are parsed **leniently** — a ```json fence or a sentence around the JSON
   is tolerated; plain JSON parses exactly as before.
3. If the reply still is not valid JSON, **one corrective retry** is made ("that was
   not valid JSON…"); a second failure is reported as before.

Every call's token usage is recorded as an `AIUsage` row (§3.15) by both clients.

## 9.2 The seven-stage pipeline

`apps/extraction/services/pipeline.py::ExtractionPipeline.run(job)`.

```mermaid
flowchart LR
    S1["1. classifying_documents<br/>15%<br/>OpenAIDocumentClassifier<br/>🤖 1 AI call"]
    S2["2. reading_pages<br/>30%<br/>PDFPageReader (PyMuPDF<br/>+ PaddleOCR for scans)<br/>no LLM"]
    S3["3. extracting_facts<br/>45%<br/>OpenAIFactExtractor<br/>🤖 1 call per chunk"]
    S4["4. mapping_audit_fields<br/>60%<br/>IdentityAuditFieldMapper<br/>pass-through"]
    S5["5. detecting_gaps<br/>75%<br/>RuleBasedGapDetector<br/>deterministic"]
    S6["6. checking_conflicts<br/>90%<br/>OpenAIConflictChecker<br/>🤖 ≤10 calls"]
    S7["7. preparing_review_workspace<br/>100%<br/>document → processed"]
    S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7
```

Each stage is defined as an ABC in `services/base.py`
(`DocumentClassifier`, `PageReader`, `OCRProvider`, `FactExtractor`,
`AuditFieldMapper`, `GapDetector`, `ConflictChecker`), and `ExtractionPipeline`
takes each as a constructor kwarg — so any stage can be swapped without touching
orchestration or the Celery retry wrapper. `services/stub.py` holds honest
no-op defaults (empty results, never fabricated ones).

**Stop checkpoints.** Before every stage, and between AI calls inside fact
extraction, the pipeline checks whether the user pressed Stop (job status
`cancelled`) and raises `ExtractionCancelled` — deliberately *not* an
`ExtractionError`, so a stop is never retried or counted as a failure. Each stage
runs inside a `usage_scope(...)`, so every AI call is attributed to its sprint,
document, job and stage (§3.15).

### Stage 1 — Classification
`openai_classifier.py`. Reads the first `OPENAI_CLASSIFICATION_SAMPLE_PAGES` (**3**)
pages, sends filename + uploader-tagged type + text sample, asks for
`{document_type, document_title, reporting_year, institution_name, confidence,
reasoning}` — every string field **nullable**. The prompt states plainly:
*"A null is the correct, honest answer when you don't know — it is not a failure"*
and *"The uploader's tagged document type is a hint, not ground truth."*
**Note:** the result is logged but **not written back to the Document** — only
`processing_status = 'classified'` is saved.

### Stage 2 — Page reading
`pdf_reader.py` (rewritten in `e35fdc4`), using **PyMuPDF**:

1. Extract each page's text layer.
2. **Is it meaningful?** (`text_cleaning.is_meaningful_text`) — at least
   `PDF_MIN_TEXT_CHARS_PER_PAGE` (**40**) characters **and** mostly real
   letters/digits, so a PDF with a broken font map (boxes and punctuation) counts
   as unreadable rather than as text.
3. If not, **render the page** (`OCR_DPI`, 200) and run **PaddleOCR**
   (`paddle_ocr.py`; lines below `OCR_MIN_CONFIDENCE` 0.5 are dropped rather than
   risk a misread number becoming a fact). A page still unreadable after OCR is
   flagged `requires_ocr` with a warning — never treated as empty.
4. **Clean up across the whole document:** drop running headers/footers and
   page-number lines that repeat on most pages, normalise spacing, re-join
   hyphenated line breaks (but not "2023-24").

Pages stay separate (each fact cites a page). `OCR_PROVIDER=none` (or PaddleOCR not
installed) falls back to the honest `NullOCRProvider`. PaddleOCR inference is
serialised with a lock, because the worker's threads pool would otherwise run it
concurrently. **Tables are no longer extracted** (`tables` is always `[]`).
Non-PDF files are still reported honestly as `format_supported: False`. The result
**corrects** the upload-time `ocr_required` guess.

### Stage 3 — Fact extraction
`openai_fact_extractor.py` — the largest and most carefully-guarded module.

- **Chunking:** `_build_chunks()` groups pages up to
  `OPENAI_FACT_EXTRACTION_MAX_CHUNK_CHARS` (**12 000**) characters, **never
  splitting a page**, and skips pages with no text entirely.
- **Hard cap:** `OPENAI_FACT_EXTRACTION_MAX_CHUNKS` (**20**) — an oversized
  document logs a warning and processes only its first 20 chunks, rather than
  making unbounded API calls.
- **Schema:** `FACT_EXTRACTION_SCHEMA` → `{facts: [FACT_ITEM_SCHEMA]}` with all ten
  fields `required` and `additionalProperties: False`. `data_type`, `pillar`, and
  `owner_role` are constrained by `enum` in the schema itself.
- **Merging:** duplicate `field_key`s across chunks are merged, keeping the
  highest-confidence version — one DB row per fact, not one per chunk.

### Stage 4 — Field mapping
`IdentityAuditFieldMapper` — a genuine pass-through, because the extractor already
returns dicts shaped exactly like `ExtractedFact` creation kwargs. Documented as
*"real, deterministic pass-through — not a stub."*

### Stage 5 — Gap detection
`gap_detector.py`. **Zero AI.** Per fact: `low_confidence` (below 0.7, escalating to
`high` priority below 0.5) or `unconfirmed_fact`. Per document: `stale_data` if
uploaded more than `GAP_STALE_DATA_DAYS` (**365**) ago. It deliberately does *not*
detect `missing_document` — that is sprint-wide and would be misleading mid-run.

### Stage 6 — Conflict checking
`conflict_checker.py`. The design principle is stated in its docstring:

> *"finding candidate conflicts … is a cheap, deterministic set comparison — AI is
> only ever consulted to interpret a pair that's already been found to disagree."*

- **Deterministic pre-filter:** pairs of non-rejected facts sharing a `field_key`
  whose `normalized_value` differs.
- **Cap:** `GAP_CONFLICT_CHECK_MAX_PAIRS` (**10**) AI calls per document.
- **The AI never picks a winner.** It answers only
  `{is_conflict, confidence, explanation}`; the two facts' values are untouched and
  a `GapItem` is raised for a human.
- It is asked to consider legitimate non-conflicts: *"different populations …
  different time periods, different units, or one is a subtotal of the other."*

### Stage 7 — Review workspace
`document.status = processed`, `processed_at = now`. When the **last** active job in
the sprint finishes, `tasks._advance_sprint_if_all_jobs_done()` moves the sprint
`processing → reviewing` and runs the sprint-wide `generate_gaps_for_sprint()` pass
(which adds `missing_document` gaps).

## 9.3 The anti-hallucination contract

The fact-extraction system prompt contains these rules verbatim:

- *"Extract only information supported by the supplied document."*
- *"Never invent numbers, names, dates, statistics or institutional information."*
- *"If information is unavailable, return no fact. Do not create a fact with a
  guessed or approximate value."*
- *"Every fact must have supporting evidence: a real snippet quoted or closely
  paraphrased from the text you were given."*
- *"Prefer null over guessing."*
- *"Only cite a page number that actually appears as a `--- Page N ---` marker in
  the text you were given."*
- *"`value` must always be a plain string … do not reformat, convert, or compute it
  yourself."*

## 9.4 Python-side validation — where AI output stops being trusted

`OpenAIFactExtractor._validate_fact()` re-checks **every field**, and
`_parse_and_normalize()` does all typing in Python:

| Field | Check |
|---|---|
| `field_name`, `field_key` | non-blank string |
| `data_type` | ∈ `ExtractedFact.DataType.values` |
| `value` | must be a `str`; then typed by `data_type` — `number`/`percentage` parsed to int/float, `currency` stripped to a numeric amount, `boolean` mapped from yes/no/true/false only, `list` split on `[;,\n]` and normalised, `string`/`date` kept as text |
| `pillar` | ∈ the eight `PILLAR_CHOICES` keys |
| `owner_role` | ∈ `FACT_OWNER_ROLE_CHOICES` (8 campus roles — **deliberately excludes `super_admin`, `consultant`, `viewer`**) |
| `source_snippet` | non-blank string |
| **`source_page`** | **must be `null` or a page number actually present in this chunk** — a citation the model invented is rejected |
| `confidence_score` | numeric (explicitly **not** `bool`) and within `[0, 1]` |
| `confidence_reason` | non-blank string |

A field that fails raises `FactValidationError` and **that one fact is dropped with
a warning** — the chunk and the document continue. The classifier and conflict
checker have their own equivalent validators
(`ClassificationValidationError`, `ConflictValidationError`).

## 9.5 Error handling, retries and cost

**Exception taxonomy** (`apps/extraction/exceptions.py`):

```
ExtractionError
├── RecoverableExtractionError   → retried with exponential backoff
└── PermanentExtractionError     → fails the job immediately
    └── AIResponseError
        ├── OpenAIResponseError
        └── AnthropicResponseError
```

| Provider condition | Classified as |
|---|---|
| Rate limit, timeout, connection error, HTTP 5xx | **Recoverable** |
| HTTP 4xx (bad request, auth) | **Permanent** |
| Empty / truncated / content-filtered / refused / unparseable JSON / missing tool call | **Permanent** (`AIResponseError`) |

**Retry policy** (`apps/extraction/tasks.py`): `EXTRACTION_MAX_RETRIES = 3`,
`countdown = EXTRACTION_RETRY_BACKOFF_SECONDS (30) × 2^retries` → **30 s, 60 s,
120 s**, then the job is marked `failed` and its document `failed`. An
**unrecognised** exception fails immediately rather than being retried, because
*"retrying blindly on an unrecognized error risks masking a real bug behind a retry
loop."*

**Logging discipline:** every AI call logs `model`, `duration_ms`, and success —
and explicitly **never the API key, never the prompt, never the response body**
(only lengths), because those carry institutional document text. The OpenAI
client also logs the endpoint **host** (not the key), so a multi-router log shows
which router answered.

**Cost is now measured, not estimated.** Every call writes an `AIUsage` row with
its token counts and a price computed at call time (§3.15), so the table below is
a planning guide and the real figures are on the AI Processing Monitor and in
Admin › AI Usage & Billing.

**Cost / token profile per document:**

| Stage | Calls | Input scale |
|---|---|---|
| Classification | 1 | 3 pages of text + system prompt (~700 tokens) |
| Fact extraction | 1 per chunk, **≤ 20** | ≤ 12 000 chars per chunk **+ the ~1 500-token system prompt resent every time** |
| Conflict checking | **≤ 10** | 2 values + 2 snippets + a ~250-token prompt |
| **Worst case** | **31 calls** | |

### Where tokens can be reduced without changing functionality

1. **Prompt caching (biggest single win).** `SYSTEM_PROMPT` in
   `openai_fact_extractor.py` is ~1 500 tokens and is **resent verbatim on every
   chunk** — up to 20 times per document. Both providers support prompt caching
   (Anthropic `cache_control`; OpenAI automatic prefix caching). Marking the system
   block cacheable would cut repeat input cost on chunks 2–20 substantially, with
   **zero behavioural change**.
2. **Batch the conflict checker.** Up to 10 separate requests each re-send the same
   250-token system prompt for a two-value comparison. Sending N pairs in one
   request against an array schema would collapse 10 calls into 1.
3. **Reuse stage 2's page read in stage 1.** `OpenAIDocumentClassifier` constructs
   its own `PDFPageReader` and re-reads the first 3 pages, which
   `ExtractionPipeline` then reads again in full at stage 2. Passing the already-read
   pages through would save one PDF parse per document (no token saving, but real
   wall-clock saving).
4. ~~Drop `tables` from the page payload when unused.~~ **Done** — the PyMuPDF
   reader no longer extracts tables. (The repeated header/footer removal also
   trims chunk text slightly.)
5. **Skip conflict checking on the first document of a sprint.**
   `_candidate_pairs()` excludes the current document, so on the very first document
   the set is always empty — the guard already returns early, but the
   per-fact query loop still runs first (see §18).
6. **Consider a smaller model for classification.** Classification is a much easier
   task than extraction; it currently uses the same model.

## 9.6 Determinism note

**Temperature is not set anywhere.** Both clients use the provider default, so
extraction output is not deterministic run-to-run. This is not called out in the
code as a decision. Scoring, by contrast, *is* explicitly deterministic.

## 9.7 Embeddings — a second, separate AI surface

The vector store (§3.11) is the project's **only other** use of a model provider, and
it is deliberately decoupled from everything above:

| | Extraction AI | Embeddings |
|---|---|---|
| Configured by | `AI_API_KEY` / `AI_MODEL` / `AI_BASE_URL` | `EMBEDDING_API_KEY` / `EMBEDDING_MODEL` / `EMBEDDING_BASE_URL` |
| Providers | OpenAI · Anthropic · any OpenAI-compatible endpoint | Any OpenAI-compatible endpoint — **or none at all**, when the Pinecone index embeds server-side |
| Abstraction | 7 ABCs in `extraction/services/base.py` | `EmbeddingService` ABC in `vector_store/services/embeddings.py` |
| Output validated? | Yes — every field re-checked in Python (§9.4) | N/A — a vector has no semantics to validate; **the retrieved text is never treated as truth**, only as a citation to a page a human can open |

The keys are separate on purpose: **Anthropic publishes no embedding endpoint**, so a
deployment running Claude for extraction would otherwise have no way to embed.
`EMBEDDING_API_KEY` falls back to `OPENAI_API_KEY` / `AI_API_KEY` when those are
usable, so the common single-provider setup still needs only one key.

**No LLM reasons over retrieved evidence anywhere in the codebase today.** Search
returns cited passages and stops there; the AI Copilot shows them as-is, and the
component that would feed them to a model does not exist yet.

## 9.8 Requirement drafting — the benchmark library's AI call site

`apps/benchmarks/services/requirement_drafting.py`, run by the Celery task
`draft_source_requirements` when staff click *Draft requirements* on an active
source version.

| | |
|---|---|
| Input | The stored, checksum-verified source file, read by the same `PDFPageReader` (OCR included) and grouped into sections of ≤ 12 000 characters, **capped at 60 sections** (60 AI calls) per document |
| Output | `RequirementCandidate` rows — statement, kind (mandatory / recommended / guidance, from shall / should / may), page, and a **verbatim 8–60-word quote** |
| Guard | **A candidate whose quote cannot be found in its section's text is dropped** — the AI cannot invent a requirement. The task reports how many were dropped |
| Human step | Only an expert's *accept* creates a `Requirement`; rejecting needs no AI |
| Mode & cost | Goes through `get_ai_service()`, takes a router lease in `multi_router` mode exactly like an extraction job, and its calls are recorded in `AIUsage` (stage `other`) |
| Duplicate safety | The task only starts a version that is `queued` (claimed atomically to `running`) |

**Status:** built and tested with a fake AI; **not yet run against a live model**
on the dev database (no requirement has been approved).

---

# 10. File upload & document processing

## 10.1 Supported types

| Set | Extensions |
|---|---|
| `ALLOWED_UPLOAD_EXTENSIONS` | `.pdf .doc .docx .xls .xlsx .csv .zip .png .jpg .jpeg` |
| `OCR_REQUIRED_EXTENSIONS` (guess at upload time) | `.pdf .doc .docx .png .jpg .jpeg` |
| **Actually readable by the pipeline** | **`.pdf`** (digital and scanned), **`.docx`** (paragraphs + tables, grouped into ~3 000-character sections), **`.xlsx`** (one page per sheet, 150 rows each), **`.csv`**, **`.png/.jpg/.jpeg`** (OCR) — `services/office_reader.py`. Old `.doc`/`.xls` and `.zip` are marked `unsupported_format` and the upload page says *"Can't read this file type"* with what to do |
| Benchmark assessment evidence (`apps/assessments`) | `.pdf .doc .docx .xls .xlsx .csv .ppt .pptx .jpg .jpeg .png .txt`, 25 MB — stored and reviewed by a person, never machine-read |
| Source Library files (`apps/benchmarks`) | Any file the register points to; checksum-verified; `.crdownload` (an unfinished browser download) refused |

> **Gap worth naming:** a DOCX/XLSX/CSV/ZIP upload is accepted, stored, and run
> through the pipeline, but `PDFPageReader` returns `format_supported: False` with
> zero pages — so it yields **no facts**. The behaviour is honest (it says so in the
> return payload and logs `pdf_reader.unsupported_format`) but the user-facing
> screens do not surface "this file type cannot be read yet".

## 10.2 Upload flow

```mermaid
flowchart TD
    A["User drops a file"] --> B["POST /sprints/{id}/upload-file<br/>multipart"]
    B --> C["get_authorized_sprint → 403/404"]
    C --> D["create_document_from_file()"]
    D --> E["DocumentUploadSerializer"]
    E --> E1{"size ≤ 50 MB?"}
    E1 -->|no| X1["400 'File is too large (…)'"]
    E1 --> E2{"extension allowed?"}
    E2 -->|no| X2["400 'Unsupported file type …'"]
    E2 --> E3["compute_file_checksum() — SHA-256 over .chunks()"]
    E3 --> E4{"checksum already in this sprint?"}
    E4 -->|yes| X3["400 'This exact file was already uploaded …'"]
    E4 --> F["derive mime_type; default title from filename"]
    F --> G["Document.objects.create(status=uploaded,<br/>ocr_required = ext ∈ OCR_REQUIRED_EXTENSIONS)"]
    G --> H["file written to MEDIA_ROOT via document_upload_path"]
    H --> I["mark_sprint_collecting(): draft → collecting"]
    I --> J["201 DocumentSerializer (+ download_url)"]
```

**Two independent size limits, on purpose:**
`DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` (Django's low-level
request-parsing limits) **and** `MAX_DOCUMENT_UPLOAD_SIZE` (the business rule that
produces a clean `400` from the serializer). All three default to 50 MB.
nginx is separately configured with `client_max_body_size 100m`.

## 10.3 Storage

- **Local filesystem**, `MEDIA_ROOT = backend/media`, mounted in production as the
  `media_data` Docker volume shared between the `backend` and `celery` containers.
  Besides sprint uploads and reports it now holds `source_library/<sha[:2]>/<sha>.<ext>`
  (content-addressed source files), `source_snapshots/` (raw watcher snapshots) and
  `assessment_evidence/<cycle>/` (college evidence). OCR models live in a separate
  `paddle_models` volume (`/root/.paddlex`) so they are not re-downloaded per deploy.
- **No S3 / GCS / object storage.** **Not found in the codebase.**
- **`MEDIA_URL` is deliberately NOT served**, even under `DEBUG`. `config/urls.py`
  says so explicitly: uploaded documents are institution-confidential and
  `static()` serves a directory with *no* authentication. Every download goes
  through `GET /documents/{id}/download`, gated by `IsInstitutionMember`.

## 10.4 Google Drive import

```mermaid
flowchart TD
    A["User pastes a Drive folder link"] --> B["DriveImportJobCreateSerializer<br/>parse_drive_folder_id() → 400 immediately if unparseable"]
    B --> C["DriveImportJob(status=pending)"]
    C --> D["run_drive_import_job.delay()"]
    D --> E{"GOOGLE_DRIVE_API_KEY set?"}
    E -->|no| X1["job failed: 'Google Drive is not configured…'"]
    E --> F["status=scanning<br/>list_drive_folder_files() — BFS; each level's folders<br/>listed IN PARALLEL (order kept deterministic)"]
    F --> F1["caps: 200 files, 200 folders, 6 parallel requests,<br/>visited-set against cycles; 30 s timeout, 3 retries × 15 s·2ⁿ"]
    F1 --> G{"any files?"}
    G -->|no| X2["job failed: 'check the link, share as Anyone-with-link Viewer'"]
    G --> H["is_importable(): unsupported types → skipped_files<br/>classify_filename(): first match per checklist slot claims it"]
    H --> I["status=downloading"]
    I --> J["downloads prefetch in parallel<br/>Google-native docs are EXPORTED (Doc→PDF, Sheet→XLSX, Slides→PDF)"]
    J --> STOP{"user pressed Stop?<br/>(checked before every file)"}
    STOP -->|yes| CAN["status=cancelled — files so far are kept"]
    STOP -->|no| K["one at a time: SimpleUploadedFile → create_document_from_file()<br/>SAME validation path as a manual upload;<br/>checklist match → slot type, else supporting_document"]
    K --> L{"per-file failure?"}
    L -->|yes| M["record in results['skipped_files'] with a reason;<br/>the job continues"]
    L -->|no| N["results[slot] or additional_files;<br/>progress {processed, total, current_file} saved"]
    M --> J
    N --> J
    J -->|"all files done"| O["status=completed, files_scanned, files_imported"]
```

## 10.5 Tracing one uploaded file end to end

**`NAAC_SSR_2025.pdf`, 14 MB, 180 pages, uploaded to sprint `SPR-3FC78B7B`:**

1. `POST /sprints/{id}/upload-file` with `document_type=naac_ssr`.
2. Serializer: 14 MB < 50 MB ✓; `.pdf` allowed ✓; SHA-256 computed, not a duplicate ✓.
3. `Document` row created — `status=uploaded`, `ocr_required=True` (extension guess),
   `title="Naac Ssr 2025"` (humanised from the filename), file written to `media/`.
4. Sprint `draft → collecting`.
5. User clicks **Start AI Processing** → `ExtractionJob(status=pending)` created,
   `run_extraction_job.delay(job_id)` published to Redis; API returns `201` at once.
6. Worker picks it up → claims the job (`pending → running`, refused if it is
   already finished or a newer message superseded this one), `started_at` set; in
   `multi_router` mode it leases a router slot first.
7. **Stage 1:** classifier reads pages 1–3, one AI call → `{document_type: "naac_ssr",
   confidence: 0.94, …}`; `processing_status='classified'`.
8. **Stage 2:** PyMuPDF reads all 180 pages. Say 174 have a real text layer and 6
   are scanned images → those 6 are rendered at 200 DPI and read by **PaddleOCR**;
   if one is still unreadable it gets an `ocr_warning` and `requires_ocr`. Repeated
   headers/footers are stripped across the document. `page_count=180`.
9. **Stage 3:** 174 pages → ~28 chunks at 12 000 chars → **capped at 20**, warning
   logged. 20 AI calls. Suppose 143 raw facts come back; 9 are dropped by
   `_validate_fact` (bad page citation, out-of-range confidence, unparseable number);
   duplicates merge by `field_key` → **97 facts**.
10. **Stage 4:** pass-through → 97 `ExtractedFact` rows inserted, each with
    `document` **and** `source_document` set to this document.
11. **Stage 5:** per fact — 22 below 0.7 → `low_confidence` gaps (6 of those below
    0.5 → `high` priority); the other 75 → `unconfirmed_fact` gaps. Uploaded today,
    so no `stale_data` gap. All routed through `create_gap_if_new`.
12. **Stage 6:** candidate pairs against other documents in the sprint; capped at 10
    AI calls; confirmed conflicts become `CONFLICT` gaps carrying immutable
    `conflict_value_a`/`_b` snapshots.
13. **Stage 7:** `document.status = processed`, `processed_at` set; job
    `completed`, `progress_percentage = 100`.
14. Last active job in the sprint → sprint `processing → reviewing`, and
    `generate_gaps_for_sprint()` adds `missing_document` gaps for whichever of the
    six `REQUIRED_DOCUMENT_TYPES` are absent.
15. **Only if Pinecone is configured** — `_queue_vector_indexing(document)` writes a
    `VectorDocumentIndex` row and queues `index_document_vectors`. The document is
    re-read, split into roughly 300 page-bounded chunks, embedded, and upserted under
    ids `college_…_document_…_chunk_0 … 299`. Wrapped in a bare `except`, so a
    missing SDK, an unconfigured index or a down broker is logged and dropped — step
    13's result is already committed and does not depend on this.
16. The monitor screen's next 3-second poll shows everything complete, with the
    run's elapsed time and the sprint's AI tokens and cost (≈ 31 `AIUsage` rows for
    this document). *(The monitor does not surface indexing state; only
    `GET /sprints/{id}/vector-index/status` does, and no screen calls it.)*

---

# 11. Background jobs — Celery & Redis

## 11.1 Why background processing

A single document can trigger **up to 31 AI calls** plus a full PDF parse — minutes
of wall-clock time. Gunicorn's timeout is 120 s. Doing this in-request would time
out, hold a worker, and give the user no progress feedback. Instead the API returns
`201` immediately with a job row the frontend polls.

## 11.2 Configuration

`config/celery.py` — `Celery('aios_backend')`,
`config_from_object('django.conf:settings', namespace='CELERY')`,
`autodiscover_tasks()`.

| Setting | Value |
|---|---|
| `CELERY_BROKER_URL` | `redis://redis:6379/0` (prod) / `redis://localhost:6379/0` (default) |
| `CELERY_RESULT_BACKEND` | same |
| `CELERY_ACCEPT_CONTENT` / serializers | `json` |
| `CELERY_TIMEZONE` | `UTC` |
| **`CELERY_TASK_IGNORE_RESULT`** | **`True`** |
| `CELERY_WORKER_CONCURRENCY` | **Derived from `AI_PROCESSING_MODE`** (single = 2, multi_router = routers × per-router limit = 8) unless set explicitly; compose no longer passes `--concurrency` |
| `CELERY_WORKER_POOL` | Optional; `threads` on Windows (the default prefork pool does not run there) |
| `CELERY_WORKER_PREFETCH_MULTIPLIER` | **1** — a worker never reserves more jobs than it has free slots |
| `CELERY_BROKER_TRANSPORT_OPTIONS.visibility_timeout` | **6 hours** — must outlast the slowest document, or `acks_late` would hand a long job to a second worker |
| Beat schedule | **One job, off by default** — `daily-source-watcher` at `WATCHER_HOUR_UTC:30`, added only when `WATCHER_ENABLED=true` |

`CELERY_TASK_IGNORE_RESULT = True` carries an unusually good comment: nothing in the
project calls `.get()`/`.result` — every outcome is tracked in its own DB row — and
without this, a `.delay()` against a **down Redis** triggers the result backend's
~20-attempt reconnect cascade (~100 s) *before* the broker-unreachable error the
code already handles gracefully ever gets a chance to raise.

**Celery Beat now has exactly one job** — the daily source watcher (§3.18). The
schedule is built in `config/settings.py` only when `WATCHER_ENABLED=true`, so a
development machine never contacts government sites on its own, and it needs a
separate `celery -A config beat` process (the `celery-beat` compose service). Every
other task is still triggered on demand from an API call. (`backend/README.md`
still says no Beat is needed — true unless the watcher is switched on.)

## 11.3 The seven tasks

| Task | Module | Trigger | Retries | Backoff | On exhaustion |
|---|---|---|---|---|---|
| `run_extraction_job(job_id)` | `apps/extraction/tasks.py` | `POST /sprints/{id}/extraction-jobs` | **3** (`EXTRACTION_MAX_RETRIES`), `acks_late=True` | `30 s × 2ⁿ` → 30/60/120 | `ExtractionJob.status=failed`, `Document.status=failed` |
| `run_drive_import_job(job_id)` | `apps/documents/tasks.py` | `POST /sprints/{id}/drive-import-jobs` | **3** (`GOOGLE_DRIVE_IMPORT_MAX_RETRIES`), `acks_late=True` | `15 s × 2ⁿ` → 15/30/60 | `DriveImportJob.status=failed` |
| `generate_report_task(report_id)` | `apps/reports/tasks.py` | `POST /sprints/{id}/reports` | **none, by design** | — | `Report.status=failed`, error stored in `report_data['error']` |
| `index_document_vectors(document_id, force)` | `apps/vector_store/tasks.py` | End of a successful extraction, **or** `POST /sprints/{id}/vector-index` | **3** (`VECTOR_INDEX_MAX_RETRIES`), `acks_late=True` | `20 s × 2ⁿ` → 20/40/80 | `VectorDocumentIndex.status=failed` + the reason on the row |
| `index_sprint_vectors(sprint_id, force)` | `apps/vector_store/tasks.py` | Fan-out helper | — | — | Queues one task per document and returns the count |
| `draft_source_requirements(version_id)` | `apps/benchmarks/tasks.py` | *Draft requirements* in Studio › Sources | none — `acks_late=True`; claims `queued → running` atomically so a duplicate message does nothing | — | `SourceVersion.extraction_status=failed` + the error in `extraction_note`; takes and releases a router lease in multi_router mode |
| `run_source_watcher(trigger)` | `apps/benchmarks/tasks.py` | **Celery Beat** (daily) or *Check all now* | none | — | `WatcherRun` records complete / partial failure / failed with per-feed errors; a cache lock stops two runs overlapping |

**Extraction task hardening** (uncommitted work): the task first **claims** the job
(only `pending` / `retrying` / `running` may start, so a finished job is never
re-run), skips a stale queue message whose `celery_task_id` no longer matches the
job (it was re-processed since), acquires the router lease *inside* the `try` so a
failure always releases it, and logs mode, worker, router and duration.

`generate_report_task`'s docstring explains the asymmetry: unlike extraction (an
inherently flaky pipeline over external documents), report generation reads
already-validated data, so *"a failure here is a real bug to surface immediately,
not a transient condition worth retrying blindly."*

The two vector tasks follow extraction's policy exactly — recoverable errors back
off, permanent and *unrecognised* ones fail immediately rather than hiding a real
bug behind a retry loop. `index_sprint_vectors` fans out **one task per document**
rather than running one long task per sprint, so a single bad document costs one
document and each gets its own retry budget.

**Extraction never fails because of indexing.** The hand-off in
`apps/extraction/tasks.py` is wrapped whole:

```python
def _queue_vector_indexing(document):
    try:
        from apps.vector_store.services import indexer
        indexer.queue_document(document)
    except Exception as exc:
        logger.error('extraction.task.vector_queue_failed document_id=%s error=%s', document.id, exc)
```

A missing `pinecone` package, an unconfigured index, or a down broker is logged and
dropped — the extraction result is already committed and stands on its own.

## 11.4 Job status tracking

There is **no polling of Celery's own result backend**. Each task owns a DB row:

| Job | Status values | Progress signal |
|---|---|---|
| `ExtractionJob` | pending → running → retrying → completed / failed / cancelled | `current_step` (7 stages) + `progress_percentage` (15/30/45/60/75/90/100), `ai_router` |
| `DriveImportJob` | pending → scanning → downloading → completed / failed / cancelled | `files_scanned`, `files_imported`, `results.progress` |
| `SourceVersion` (drafting) | idle → queued → running → done / failed | `extraction_note` |
| `WatcherRun` | running → complete / partial_failure / failed | `feeds_checked`, `changes_detected`, `failure_detail` |
| `Report` | draft → generating → ready / failed | `status` alone |
| `VectorDocumentIndex` | pending → processing → indexed / failed | `vector_count`, `embedding_model`, `indexed_at`, `error_message` |

`celery_task_id` is stored on the first two so `SprintExtractionCancelView` can call
`current_app.control.revoke(task_id, terminate=True)`.

## 11.5 Failure handling when Redis is down

Every dispatch site wraps `.delay()` in `try/except Exception`:

```python
except Exception as exc:
    logger.error('…broker_unreachable job_id=%s error=%s', job.id, exc)
    job.status = FAILED
    job.error_message = f'Could not reach the Celery broker: {exc}'
    job.save(...)
```

The API still returns `201`/`202` with a job row whose `error_message` explains the
problem — **no 500, no hang**. The frontend's `humanizeExtractionError()` then
renders it readably.

Each dispatch site also catches `celery.exceptions.Retry`, which is only reachable
under `CELERY_TASK_ALWAYS_EAGER` (tests / a synchronous worker), where `.delay()`
runs the task inline; the code `refresh_from_db()`s so the response reflects what
actually happened rather than the stale in-memory row.

## 11.6 The queue flow

```mermaid
sequenceDiagram
    actor U as User
    participant API as Django (gunicorn)
    participant DB as PostgreSQL
    participant R as Redis (broker)
    participant W as Celery worker (2 or 8 slots, by mode)
    participant EXT as AI provider / Drive

    U->>API: POST /sprints/{id}/extraction-jobs
    API->>DB: INSERT ExtractionJob(status=pending)
    API->>R: run_extraction_job.delay(job_id)
    alt broker reachable
        R-->>API: AsyncResult(id)
        API->>DB: UPDATE job.celery_task_id
    else broker DOWN
        API->>DB: UPDATE job → failed + "Could not reach the Celery broker: …"
    end
    API-->>U: 201 [ExtractionJob]   (immediate)

    R->>W: deliver (acks_late — redelivered if the worker dies)
    W->>DB: claim: pending/retrying → running (skip if finished or stale)
    opt multi_router
        W->>R: lease a slot on the least-busy healthy router
    end
    loop 7 stages
        W->>DB: UPDATE current_step, progress_percentage
        W->>EXT: AI / Drive calls
    end
    alt success
        W->>DB: job → completed; document → processed
        W->>DB: if no active jobs left → sprint → reviewing + sprint-wide gap pass
    else RecoverableExtractionError, attempt ≤ 3
        W->>DB: job → retrying, retry_count, error_message
        W->>R: retry with countdown 30·2ⁿ
    else Permanent / unknown / retries exhausted
        W->>DB: job → failed; document → failed
    end

    loop every 3 s
        U->>API: GET /sprints/{id}/extraction-jobs
        API->>DB: SELECT
        API-->>U: current_step + progress_percentage
    end
```

---

# 12. External services

| Service | Purpose | Where used | Authentication | Data sent | Data received |
|---|---|---|---|---|---|
| **OpenAI API** (`chat.completions`) | Document classification, fact extraction, conflict adjudication | `apps/extraction/services/openai_client.py` via `ai_service.get_ai_service()` | `AI_API_KEY` / `OPENAI_API_KEY` bearer (SDK) | System prompt + extracted document text (≤12 000 chars/chunk) + a JSON schema | Schema-constrained JSON: facts / classification / conflict verdict |
| **Anthropic API** (`messages`) | Same three call sites | `apps/extraction/services/anthropic_client.py` | `AI_API_KEY` (SDK) | Same, as a forced tool call with `input_schema` | The tool call's `.input` |
| **OpenAI-compatible endpoint** | Local router / self-hosted gateway / multi-provider proxy | Same `OpenAIExtractionService`, with `base_url` | `AI_API_KEY` | Same | Same — **requires genuine `response_format=json_schema` support**; the `.env` comment records that a previously-configured router returned prose instead of JSON |
| **AI routers** *(multi_router mode)* | Spread extraction across several OpenAI-compatible endpoints (e.g. four local 9router instances) | `router_pool.py` + `OpenAIExtractionService` | `AI_ROUTER_API_KEYS` (one per router, or one for all) | Same as above | Same; the JSON-in-prompt + lenient-parse + one-retry handling (§9.1) exists for these |
| **Google Drive REST v3** | Import a shared folder of institutional documents; **also** fetch Source Library files by Drive link (`ingest_source_files`) | `apps/documents/drive_import.py`, `apps/benchmarks/services/file_intake.py` | **Single server-side API key** (`GOOGLE_DRIVE_API_KEY`) as a query param | Folder id, page tokens, file ids | File metadata (`id,name,mimeType,size`) and raw/exported bytes |
| **Official source websites** *(watcher, off by default)* | Daily check of switched-on regulator / framework pages | `apps/benchmarks/services/watcher.py` | None — public pages; honest User-Agent; robots.txt respected | One GET per page per day (plus `robots.txt`) | Page HTML or file bytes, stored as snapshots |
| **PaddleOCR model hosts** | OCR models download **on first use** | `paddle_ocr.py` (via PaddleX) | None | — | Model files, cached in `~/.paddlex` (`paddle_models` volume) |
| **Redis 7** | Celery broker (and nominal result backend) | `config/celery.py` | none (container network only) | Task name + `job_id` | Task delivery |
| **PostgreSQL 16** | Primary datastore | `dj-database-url` | `POSTGRES_USER`/`POSTGRES_PASSWORD` | All application data | — |
| **Pinecone** *(optional)* | Vector index for college-evidence retrieval | `apps/vector_store/services/pinecone_client.py` — **the only module that imports the SDK, and lazily** | `PINECONE_API_KEY` (SDK) | Chunk text (≤1 200 chars) + 9 metadata keys, or a raw embedding vector; queries carry text/vector + the metadata filter | Matches: id, score, metadata. **Never the original file** |
| **OpenAI embeddings** *(optional)* | Vector generation, **manual mode only** | `apps/vector_store/services/embeddings.py` | `EMBEDDING_API_KEY`, falling back to `OPENAI_API_KEY` / `AI_API_KEY` | Chunk text | Float vectors (`text-embedding-3-small` = 1 536 d by default) |
| **GitHub Container Registry** | Image hosting | `.github/workflows/ci-cd.yml`, `docker-compose.yml` | `GITHUB_TOKEN` | Built images | Pulled images |

Neither Pinecone row is reached unless it is configured. In **integrated** mode
Pinecone embeds server-side and the OpenAI embeddings row does not apply at all.

**Not present:** S3/GCS/object storage, any email/SMTP provider, SMS, payment
gateway, analytics/telemetry, error tracking (Sentry), or feature flags — all
**Not found in the codebase**.

**OCR runs locally.** PaddleOCR executes inside the Celery container on CPU, so
scanned pages are **not** sent to any third party for OCR — only the resulting
text goes to the AI provider, as before.

**Data-privacy note.** Institutional document text is sent to a third-party AI
provider. There is no PII redaction step, no per-institution consent record, and no
configurable data-residency control in the code. **Enabling the vector store widens
this**: the same text is also sent to Pinecone (and, in manual mode, to an embedding
provider), and the chunk text is *stored* there rather than merely passed through.
`PINECONE_CLOUD` / `PINECONE_REGION` give an operator control over where the index
lives, which is the only data-residency lever in the codebase. Whether any of this is
acceptable is a contractual question, but it is worth stating explicitly.
---

# 13. Configuration & environment variables

All configuration is read via `os.getenv` in `config/settings.py`, loaded from
`.env` by `python-dotenv`. **No values are reproduced here.**

## 13.1 Full variable table

| Variable | Purpose | Required? | Used where | Sensitive? |
|---|---|---|---|---|
| `SECRET_KEY` | Django cryptographic signing | **Yes in prod** — but has an insecure fallback | `settings.py`; also the JWT fallback key | **Yes** |
| `JWT_SECRET_KEY` | Signs access/refresh tokens | **Yes in prod** — falls back to `SECRET_KEY` | `SIMPLE_JWT['SIGNING_KEY']` | **Yes** |
| `DEBUG` | Debug mode; **`!DEBUG` switches on all production hardening** | No (default `False`) | `settings.py` | No |
| `ALLOWED_HOSTS` | Host allowlist, comma-separated | **Yes in prod** | `settings.py` | No |
| `CORS_ALLOWED_ORIGINS` | Browser origins allowed to call the API | **Yes in prod** | `corsheaders` | No |
| `DATABASE_URL` | Postgres DSN; **unset ⇒ SQLite fallback** | **Yes in prod** | `dj_database_url.config()` | **Yes** (embeds the password) |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Postgres container init | **Yes in prod** | `docker-compose.yml` | **Yes** (password) |
| `REDIS_URL` | Redis DSN (informational) | No | `.env` | No |
| `CELERY_BROKER_URL` | Task broker | **Yes** | `config/celery.py` | No |
| `CELERY_RESULT_BACKEND` | Result backend (unused — `IGNORE_RESULT=True`) | No | same | No |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | Access TTL (default **60**) | No | `SIMPLE_JWT` | No |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | Refresh TTL (default **1**) | No | `SIMPLE_JWT` | No |
| **`AI_API_KEY`** | The AI provider key; **provider is auto-detected from its prefix** | **Yes, for extraction** | `ai_service.get_ai_service()` | **Yes** |
| `AI_MODEL` | Model override; **mandatory when `AI_BASE_URL` is set** | No | same | No |
| `AI_BASE_URL` | OpenAI-compatible endpoint; **wins over key detection** | No | same | No |
| `OPENAI_API_KEY` | Legacy key (pre-multi-provider) | No | same | **Yes** |
| `OPENAI_EXTRACTION_MODEL` | Legacy model; **only honoured for OpenAI keys** | No | `_resolve_model` | No |
| `AI_PRICING_JSON` | Extra / overriding AI prices, USD per 1 M tokens, as JSON (e.g. a router combo at 0) | No | `extraction/pricing.py` | No |
| **`AI_PROCESSING_MODE`** | `single` (default) or `multi_router`; **an invalid value stops startup** | No | `config/ai_processing_mode.py`, `router_pool`, `ai_service` | No |
| `AI_ROUTER_URLS` | Comma-separated router base URLs (`/v1` added if missing) — multi_router only | In multi_router | `router_pool.py` | No |
| `AI_ROUTER_API_KEYS` | One key per router, or one for all (empty = `AI_API_KEY`) | In multi_router | same | **Yes** |
| `AI_ROUTER_MODEL` | Model every router serves (empty = `AI_MODEL`) | No | `ai_service.py` | No |
| `AI_ROUTER_MAX_CONCURRENT` | Documents per router at once (**2**) | No | `router_pool.py`, worker count | No |
| `AI_ROUTER_COOLDOWN_SECONDS` / `AI_ROUTER_WAIT_SECONDS` / `AI_ROUTER_LEASE_SECONDS` | Failed-router cool-down (**60**), wait for a free slot (**300**), lease TTL (**1 800**, kept alive by the job) | No | same | No |
| `AI_ROUTER_REDIS_URL` | Redis for leases (empty = `CELERY_BROKER_URL`) | No | same | No |
| `CELERY_WORKER_CONCURRENCY` | Override the mode-derived worker count | No | `settings.py` | No |
| `CELERY_WORKER_POOL` | e.g. `threads` on Windows | No | same | No |
| `CELERY_WORKER_PREFETCH_MULTIPLIER` | Jobs reserved per slot (**1**) | No | same | No |
| `CELERY_VISIBILITY_TIMEOUT_SECONDS` | Broker redelivery timeout (**21 600** = 6 h) | No | same | No |
| `OCR_PROVIDER` | `paddle` (default; `none` under `manage.py test`) or `none` | No | `pdf_reader.default_ocr_provider` | No |
| `OCR_LANG` / `OCR_DPI` / `OCR_MIN_CONFIDENCE` | Language (**en**), render resolution (**200**), drop lines below (**0.5**) | No | `paddle_ocr.py`, `pdf_reader.py` | No |
| `OCR_ENABLE_MKLDNN` / `OCR_DET_MODEL` | oneDNN CPU acceleration (**true**; broken in paddlepaddle 3.3 on Windows, hence the `<3.3` pin) / detection model (**`PP-OCRv5_mobile_det`**) | No | `paddle_ocr.py` | No |
| `GOOGLE_DRIVE_IMPORT_CONCURRENCY` | Parallel Drive requests (**6**) | No | `documents/tasks.py`, `drive_import.py` | No |
| **`WATCHER_ENABLED`** | Adds the daily watcher to the Beat schedule (**false**) | No | `settings.py` | No |
| `WATCHER_HOUR_UTC` | Hour of the daily run (**20** → 20:30 UTC = 02:00 IST) | No | same | No |
| `GOOGLE_DRIVE_API_KEY` | Drive REST v3 key | **Yes, for Drive import** | `documents/tasks.py` | **Yes** |
| `OPENAI_CLASSIFICATION_SAMPLE_PAGES` | Pages sampled for classification (**3**) | No | `openai_classifier.py` | No |
| `PDF_MIN_TEXT_CHARS_PER_PAGE` | OCR-required threshold (**40**) | No | `pdf_reader.py` | No |
| `OPENAI_FACT_EXTRACTION_MAX_CHUNK_CHARS` | Chunk size (**12 000**) | No | `openai_fact_extractor.py` | No |
| `OPENAI_FACT_EXTRACTION_MAX_CHUNKS` | **Hard AI-call cap per document (20)** | No | same | No |
| `GAP_CONFLICT_CHECK_MAX_PAIRS` | AI conflict calls per document (**10**) | No | `conflict_checker.py` | No |
| `EXTRACTION_MAX_RETRIES` | Retry count (**3**) | No | `extraction/tasks.py` | No |
| `EXTRACTION_RETRY_BACKOFF_SECONDS` | Base backoff (**30**) | No | same | No |
| `GOOGLE_DRIVE_IMPORT_MAX_FILES` | Files per import (**200**) | No | `drive_import.py` | No |
| `GOOGLE_DRIVE_IMPORT_MAX_FOLDERS` | Folders walked (**200**) | No | same | No |
| `GOOGLE_DRIVE_IMPORT_MAX_RETRIES` / `..._RETRY_BACKOFF_SECONDS` | Drive retry policy (**3** / **15**) | No | `documents/tasks.py` | No |
| `GAP_LOW_CONFIDENCE_THRESHOLD` | Low-confidence gap trigger (**0.7**) | No | `gaps`, `gap_detector` | No |
| `GAP_VERY_LOW_CONFIDENCE_THRESHOLD` | Escalate to `high` (**0.5**) | No | same | No |
| `GAP_STALE_DATA_DAYS` | Stale-document age (**365**) | No | same | No |
| `MAX_DOCUMENT_UPLOAD_SIZE` | Business size cap (**50 MB**) | No | `documents/serializers.py` | No |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` | Django parse limits (**50 MB**) | No | `settings.py` | No |
| `SECURE_SSL_REDIRECT` | Force HTTPS when `DEBUG=False` (**default `True`**) | No | `settings.py` | No |
| `DJANGO_LOG_LEVEL` / `APP_LOG_LEVEL` / `CELERY_LOG_LEVEL` | Log levels (all default `INFO`) | No | `LOGGING` | No |
| `RUN_OPENAI_INTEGRATION_TESTS` | Enables the opt-in **real-API** test (spends quota) | No | `extraction/tests.py` | No |
| **`PINECONE_API_KEY`** | Pinecone auth. **Unset ⇒ the whole vector store is off** | No — optional feature | `vector_store/services/pinecone_client.py` | **Yes** |
| **`PINECONE_INDEX_NAME`** | Which index to read/write. Also required to enable | No | same | No |
| `PINECONE_CLOUD` / `PINECONE_REGION` | Recorded for the operator who **creates** the index (`aws` / `us-east-1`); the SDK resolves the index by name at runtime | No | same | No |
| `PINECONE_NAMESPACE` | Optional namespace (default `''`). Isolation does **not** depend on it — metadata filtering does | No | same | No |
| `PINECONE_EMBEDDING_MODE` | `auto` (default) / `integrated` / `manual` — who generates the embedding, and therefore which Pinecone API is used | No | same | No |
| **`EMBEDDING_API_KEY`** | Embedding provider key, **manual mode only**. Separate from `AI_API_KEY` because Anthropic has no embedding endpoint; falls back to `OPENAI_API_KEY` / `AI_API_KEY` | No | `vector_store/services/embeddings.py` | **Yes** |
| `EMBEDDING_MODEL` | Embedding model (**`text-embedding-3-small`**) | No | same | No |
| `EMBEDDING_DIMENSIONS` | Override only for a model whose width this app does not know; blank ⇒ derived | No | same | No |
| `EMBEDDING_BASE_URL` | Point at any OpenAI-compatible embedding endpoint | No | same | No |
| `VECTOR_CHUNK_MAX_CHARS` / `..._OVERLAP_CHARS` / `..._MIN_CHARS` | Chunking (**1 200** / **150** / **40**). Overlap must stay below max or chunking cannot terminate — enforced in `chunking.py` | No | `vector_store/services/chunking.py` | No |
| `VECTOR_INDEX_MAX_RETRIES` / `..._RETRY_BACKOFF_SECONDS` | Indexing retry policy (**3** / **20**) | No | `vector_store/tasks.py` | No |
| `VECTOR_SEARCH_DEFAULT_TOP_K` / `VECTOR_SEARCH_MAX_TOP_K` | Result count (**5**) and its hard ceiling (**50**), so a caller cannot ask for an unbounded set | No | `vector_store/services/search.py` | No |

> Integer vector settings go through a `_int_env()` helper rather than bare `int()`,
> so an env var that is *present but empty* (`EMBEDDING_DIMENSIONS=`) falls back to
> the default instead of crashing Django at import time.

## 13.2 Configuration by environment

| Concern | Local development | CI (GitHub Actions) | Production |
|---|---|---|---|
| Settings module | `config.settings` (single module) | same | same |
| `DEBUG` | `True` | `True` | `False` |
| Database | **SQLite** `db.sqlite3` (no `DATABASE_URL`) | SQLite | **Postgres 16** container via `DATABASE_URL` |
| Redis / Celery | Redis **in WSL on port 6380**, reached at `127.0.0.1` (not `localhost`, which costs ~20 s per connection through IPv6); `start-dev.ps1` keeps WSL alive and starts it | Not started — Celery paths run eagerly / are mocked | `redis:7-alpine` container |
| Worker on Windows | `CELERY_WORKER_POOL=threads` (prefork does not work); slot count from `AI_PROCESSING_MODE`; started by `start-dev.ps1` in its own window | — | Default pool; slot count from `AI_PROCESSING_MODE` |
| AI endpoint | `single`: a local 9router on 20128; `multi_router`: four WSL routers on 20228–20231 (`switch-ai-mode.ps1`) | Mocked | Whatever `.env` names |
| OCR | PaddleOCR installed locally (`requirements/ocr.txt`) | `OCR_PROVIDER=none` automatically under `manage.py test` | In the image (own Docker layer) |
| Beat / watcher | Off (`WATCHER_ENABLED` unset) | — | `celery-beat` service runs; the watcher job exists only if `WATCHER_ENABLED=true` |
| Secrets | `backend/.env` (**git-ignored**) | `SECRET_KEY`/`JWT_SECRET_KEY` injected as literal CI values | `/opt/ai-ready/.env` next to `docker-compose.yml` |
| AI calls | Real, if `AI_API_KEY` is set | **Mocked**, unless `RUN_OPENAI_INTEGRATION_TESTS=true` | Real |
| Security hardening | Off (`DEBUG=True`) | Off | **On** — SSL redirect, secure cookies, HSTS 1 year + preload, nosniff, XSS filter, `SECURE_PROXY_SSL_HEADER` |
| Static files | Served by Django | — | `collectstatic` at container start → `static_data` volume → nginx |
| API docs | `/api/docs` open | disabled in test settings | **still enabled** (`SERVE_INCLUDE_SCHEMA: False` only hides the schema endpoint from itself) |

---

# 14. Deployment architecture

## 14.1 The pipeline

```mermaid
flowchart LR
    DEV["Developer"] -->|"git push main"| GH["GitHub repo"]
    GH --> CI["GitHub Actions — .github/workflows/ci-cd.yml"]

    subgraph CI["CI/CD"]
        direction TB
        T1["backend-test<br/>python 3.12 · pip install development.txt<br/>python manage.py test (779 tests)"]
        T2["frontend-build<br/>node 20 · npm ci · npm run build"]
        T3["build-and-push<br/>buildx → GHCR<br/>tags: latest + git SHA<br/>cache-from/to: type=gha"]
        T4["deploy<br/>appleboy/ssh-action → GCP VM"]
        T1 --> T3
        T2 --> T3
        T3 --> T4
    end

    T3 -->|"push"| GHCR[("ghcr.io/jagadesh-alpha8/<br/>ai-ready-backend & -frontend")]
    T4 -->|"ssh"| VM

    subgraph VM["GCP VM — /opt/ai-ready"]
        direction TB
        CMD["docker login ghcr.io<br/>git fetch with the run's token + merge --ff-only<br/>prune images + build cache (never volumes)<br/>refuse if < 6 GB free<br/>docker compose pull<br/>docker compose up -d --remove-orphans<br/>docker image prune -af"]
        NGX["frontend :80<br/>nginx 1.27-alpine"]
        BE["backend :8000<br/>gunicorn ×3"]
        CEL["celery<br/>slots by AI mode"]
        BT["celery-beat"]
        PG[("db — postgres:16-alpine")]
        RD[("redis — redis:7-alpine")]
    end

    GHCR -.->|"pull"| VM
    NGX --> BE
    BE --> PG
    BE --> RD
    RD --> CEL
    BT --> RD
    CEL --> PG
```

## 14.2 The six services

| Service | Image | Restart | Ports | Depends on | Command |
|---|---|---|---|---|---|
| `db` | `postgres:16-alpine` | `unless-stopped` | internal | — | default; **healthcheck `pg_isready`** every 10 s ×5 |
| `redis` | `redis:7-alpine` | `unless-stopped` | internal | — | default |
| `backend` | `ghcr.io/…/ai-ready-backend:latest` | `unless-stopped` | internal `:8000` | `db` (healthy), `redis` | `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120` |
| `celery` | **same image** | `unless-stopped` | — | `db` (healthy), `redis`, `backend` | `celery -A config worker -l info` — **no `--concurrency`**, so `AI_PROCESSING_MODE` decides |
| `celery-beat` | **same image** | `unless-stopped` | — | `redis`, `celery` | `celery -A config beat -l info -s /tmp/celerybeat-schedule` — sends the daily watcher job only when `WATCHER_ENABLED=true`. **Exactly one beat must run** |
| `frontend` | `ghcr.io/…/ai-ready-frontend:latest` | `unless-stopped` | **`80:80`** | `backend` | nginx |

All services share a `json-file` logging anchor capped at 10 MB × 3 files.

**Volumes:** `postgres_data`, `redis_data`, `media_data` (shared **backend + celery**
— essential, since the worker reads uploaded PDFs, source files and evidence, and
writes reports and snapshots), `static_data` (shared **backend + frontend**,
read-only on the nginx side), and **`paddle_models`** (celery only — OCR models,
downloaded once).

**The backend image is large** since OCR: the Dockerfile installs `libgl1`,
`libglib2.0-0`, `libgomp1` (needed by OpenCV / PaddlePaddle) and installs
`requirements/ocr.txt` (> 1 GB) **in its own layer before everything else**, so a
normal deploy reuses that layer and only downloads the small ones above it.

## 14.3 Migration safety

`backend/docker-entrypoint.sh`:

```sh
if [ "$1" = "gunicorn" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
fi
exec "$@"
```

Only the **web** process migrates. The `celery` service shares the same image but
its command starts with `celery`, so it does not race the web container's migration
on every deploy. This is a correct and deliberate design.

## 14.4 nginx (`frontend/nginx.conf`)

| Location | Behaviour |
|---|---|
| `/static/` | `alias /usr/share/nginx/html/static/` — the shared `static_data` volume; `access_log off`, `expires 30d` |
| `/api/` | `proxy_pass http://backend:8000/api/` with `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` |
| `/admin/` | same proxy to the Django admin |
| `/` | `try_files $uri $uri/ /index.html` — React Router SPA fallback |
| global | `client_max_body_size 100m` — the 1 MB nginx default would reject 50 MB uploads before they reached Django |

## 14.5 Infrastructure inventory

| Layer | Choice |
|---|---|
| Cloud provider | **GCP** (`GCP_HOST` / `GCP_SSH_USER` / `GCP_SSH_KEY` / `GCP_SSH_PORT` secrets) |
| Server | A single VM, deploy root `/opt/ai-ready` |
| OS | Linux with Docker + Compose v2 (`docker compose`). Exact distro: **Not found in the codebase** |
| Orchestration | **Docker Compose** — no Kubernetes |
| Web server | nginx 1.27-alpine (SPA + reverse proxy) |
| App server | Gunicorn, 3 sync workers, 120 s timeout |
| Database | PostgreSQL 16 in a container, `postgres_data` volume |
| Object storage | **None** — local `media_data` volume |
| Cache / broker | Redis 7 in a container |
| Worker | Celery, 2 slots (`single`) or routers × 2 (`multi_router`) |
| Scheduler | `celery-beat`, one optional job |
| Domain / DNS | **`http://ai.ingageedutech.com`** — an A record to the VM (35.188.110.20), managed outside the repo. The deploy job (`APP_DOMAIN` in `ci-cd.yml`) adds the domain to `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` in the VM's `.env` if missing, keeping a one-time `.env.before-domain` backup, and recreates `backend`/`celery` when it changed (commit `c588b0e`) |
| SSL/TLS | **Not found in the codebase** — no certbot, no TLS listener, port 80 only. But `SECURE_SSL_REDIRECT` defaults to `True` when `DEBUG=False` ⇒ see §17 |
| Firewall / security groups | **Not found in the codebase** — configured outside the repo |
| CI/CD | GitHub Actions → GHCR → SSH |
| Registry | GitHub Container Registry |
| Backups | **On the VM, outside the repo (since 15 Oct):** `/usr/local/sbin/ai-ready-backup.sh` via `/etc/cron.d/ai-ready-backup` at 01:30 UTC — daily PostgreSQL dump (kept 14), weekly uploaded-files archive (kept 4), daily `.env` copy (kept 14), in `/opt/ai-ready/backups/`. **Same disk as the server** — copy them off the VM regularly |
| Monitoring / alerting | No monitoring service. The deploy job now fails (and GitHub emails) when `https://ai.ingageedutech.com/api/v1/health` is not healthy within 5 minutes; the 9Router instances have a once-a-minute watchdog on the VM (`~/9router/watchdog.sh`, user crontab) that restarts any that stop |
| Healthcheck | `db` (`pg_isready`) and **`backend`** (`/api/v1/health`: database + cache, every 30 s); post-deploy check in the workflow. Still none on `celery` or `frontend` |

## 14.6 Deployment concerns worth flagging

1. **The VM still holds a full git checkout** purely to get `docker-compose.yml`.
   The deploy now fetches with the run's short-lived GitHub token (no SSH key kept
   on the VM) and merges `--ff-only`, so an edit made on the server still fails the
   deploy. It also prunes images and build cache first and **refuses to pull with
   less than 6 GB free** — the OCR layers made disk space the most likely deploy
   failure. A single-file fetch or a baked-in compose file would still be simpler.
2. **`docker compose up -d` with no healthcheck on `backend`** means the deploy job
   reports success as soon as containers start — even if Django then fails to boot
   (bad migration, missing env var). Nothing verifies the app actually serves.
3. **No rollback path.** Images are tagged with the SHA, so a rollback is possible
   manually, but the workflow only ever pulls `:latest`.
4. **`SECURE_SSL_REDIRECT` + port 80 only.** With `DEBUG=False` and no TLS
   terminator in front, Django will 301 every HTTP request to HTTPS, which nothing
   is listening on. Either set `SECURE_SSL_REDIRECT=False` in `.env` or put TLS in
   front. This is the single most likely "it deployed but the site is broken" trap.

---

# 15. Complete user journeys

## Workflow 1 — Consultant signs in and opens the dashboard

1. **User:** opens the app, is redirected `/` → `/dashboard` → (no session) `/login`.
2. **Frontend:** `Login.tsx`. Types `consultant@ingage.ai` + password, or clicks the
   "InGage Lead Consultant" quick-login tile.
3. **API:** `POST /api/v1/auth/login` `{email, password}` — **no auth required**.
4. **Backend:** `LoginView` → `LoginSerializer.validate()` → Django `authenticate()`
   with `username=email` → checks `is_active`.
5. **DB:** `SELECT … FROM accounts_user WHERE email = …`; PBKDF2 verify.
6. **Response:** `200 {access_token, refresh_token, user}`.
7. **Frontend:** `AuthContext.login()` writes `aios_token` + `aios_refresh_token` to
   `localStorage`, sets `token`, which fires the effect → `GET /auth/me` →
   `setUser`. `LoginRoute` sees a user and `<Navigate to="/dashboard">`.
8. **Dashboard:** `useApiResource(() => getDashboard(), [])` → `GET /api/v1/dashboard`.
9. **Backend:** `get_accessible_institution_ids(user)` returns `None` (consultant is
   cross-institution) → **no filtering** → seven metric queries + the annotated,
   prefetched sprint list.
10. **User sees:** platform-wide tiles (active sprints, avg completion, reports
    ready, pending confirmations, high-priority gaps, sprint count, institution
    count) and every sprint, newest-updated first.
11. **60 minutes later** the access token expires; the next call 401s, the axios
    interceptor silently refreshes and replays it. The user notices nothing.

## Workflow 2 — Main business operation: documents → CRI score

1. **Screen 1 (`/sprint/setup`):** the consultant picks *M. Kumarasamy College of
   Engineering*, mode `verified_cri`, academic year `2026-27`.
   → `POST /sprints` → `201`, `sprint_code = SPR-…`, `status=draft`.
2. **Screen 2 (`/sprint/{id}/upload`):** uploads NAAC SSR, AQAR, AICTE approval,
   faculty list, student strength, placement report.
   → six `POST /sprints/{id}/upload-file` calls. Each validates size/extension/
   checksum, writes to `media/`, and the first one flips `draft → collecting`.
   *(Alternative: paste one Drive folder link → `POST /drive-import-jobs` → Celery
   walks the folder, keyword-matches filenames, and imports through the same path.)*
3. **Screen 3 (`/sprint/{id}/monitor`):** clicks **Start AI Processing**.
   → `POST /sprints/{id}/extraction-jobs` → sprint `collecting → processing`, six
   `ExtractionJob` rows, six `.delay()` publishes, `201` returned immediately.
   The screen polls every 3 s and shows a 7-stage bar per document.
4. **Worker (per document):** classify (1 AI call) → PyMuPDF reads pages (OCR for scans) →
   chunk + extract facts (≤20 AI calls) → persist `ExtractedFact` rows → rule-based
   gaps → AI conflict adjudication (≤10 calls) → `document → processed`.
   When the last job finishes: sprint `processing → reviewing` and the sprint-wide
   gap pass adds `missing_document` gaps for absent required types.
5. **Screen 4 (`/sprint/{id}/facts`):** the IQAC Coordinator reviews. For each fact
   they see the value, the pillar, the confidence, and **the exact source snippet
   and page**. They confirm most, correct one ("Total faculty" 312 → 318).
   → `POST /facts/{id}/confirm` and `POST /facts/{id}/correct {corrected_value}`.
   Each writes a `FactReviewHistory` row capturing the **previous** value first.
6. **Screen 5 (`/sprint/{id}/gaps`):** works the gap list — resolves what they can,
   marks genuinely-unavailable items `unavailable`, skips the rest.
7. **Screen 6 (`/sprint/{id}/confirmation`):** the owner-role queue — the Registrar
   confirms enrolment facts, the HR Officer confirms faculty facts, and so on.
8. **Screen 7 (`/sprint/{id}/score`):** `POST /sprints/{id}/score`.
   → the nine-step engine reads only `confirmed`/`corrected` facts and
   `open`/`in_progress` gaps, evaluates 8 pillars against their criteria, subtracts
   the gap penalties, writes 8 `PillarScore` rows + 1 `ScoringRun`, denormalises
   `overall_cri`/`confidence_score` onto the sprint, and moves `reviewing → scoring`.
9. **User sees:** e.g. **CRI 63.4 / 100, confidence 71%**, with
   *Infrastructure & Digital Capability* `strong` and *Research & Innovation*
   `at_risk`, plus the live evidence metrics and any unresolved blocking gaps.

## Workflow 3 — Data/file processing: one Drive folder to a downloadable report

1. **Paste** `https://drive.google.com/drive/folders/1AbC…` on Screen 2.
   `DriveImportJobCreateSerializer` parses the folder id **immediately** — a
   malformed link is a `400` before any job is created.
2. **`DriveImportJob(status=pending)`** created; `run_drive_import_job.delay()`.
3. **Worker:** checks `GOOGLE_DRIVE_API_KEY` (missing ⇒ job fails with a clear
   admin-facing message) → `status=scanning` → BFS walk of the folder tree, paging
   each folder, capped at 200 files / 200 folders, cycle-guarded.
4. **No files?** → job fails with *"check the link, and make sure the folder is
   shared as 'Anyone with the link — Viewer'."*
5. **Classification:** each filename is lowercased and keyword-matched against
   `DRIVE_IMPORT_CHECKLIST`; the first match claims a slot; the rest go to
   `results['unmatched_files']`.
6. **`status=downloading`:** per claimed slot, `download_drive_file()` — a
   Google-native Doc is **exported** to PDF, a Sheet to XLSX, Slides to PDF; a raw
   file is fetched with `alt=media`.
7. **Import:** wrapped in `SimpleUploadedFile` and pushed through
   **`create_document_from_file()` — the same validation as a manual upload**. A
   per-file failure is recorded in `results['skipped_files']` with a reason and the
   job continues.
8. **Completion:** `results` now maps every checklist slot to `found`/`missing`;
   the UI ticks the checklist. Extraction then runs exactly as in Workflow 2.
9. **Screen 8 — approval:** `GET /sprints/{id}/baseline` bootstraps a `PENDING`
   Baseline pinned to the latest `ScoringRun` and moves the sprint to
   `baseline_pending`. If any blocking gap is open, `can_approve` is `false` and
   full approval is refused server-side; the consultant either resolves them,
   approves **provisionally**, or **returns for correction** with a mandatory reason
   (sending the sprint back to `reviewing`).
10. **Screen 9 — recommendations:** `POST /recommendations/generate` runs three
    idempotent generators (open blocking/high gaps; confirmed-but-low-confidence
    facts; at-risk/not-started pillars). Each recommendation states the exact data
    point that triggered it and an `expected_cri_lift`. A consultant may `PATCH`
    the wording — **no other role can**.
11. **Screen 10 — report:** `POST /sprints/{id}/reports` → new version row →
    `generate_report_task.delay()` → `202`. The worker assembles the 11 sections,
    renders a PDF with fpdf2 (Latin-1-sanitised) and a DOCX with python-docx, saves
    both to `media/`, sets `status=ready`, and moves the sprint
    `baseline_approved → report_ready`.
12. **Download:** the page polls every 3 s until `ready`, then
    `GET /reports/{id}/download?file=pdf` streams the file as an attachment through
    the authenticated endpoint.

**The 11 report sections** (`reports/services.py::build_report_data`):
institution · sprint · baseline status · executive summary · overall CRI &
confidence · 8 pillar scorecards · strengths · areas for improvement ·
missing-data appendix · recommendations · 90-day action plan · 12-month roadmap ·
how InGage can help · evidence metrics.

Every one is derived from real rows; the module docstring is explicit that an empty
source produces an honest empty section, never placeholder text.

## Workflow 4 — Benchmark library to a college's benchmark scorecard

*Not yet possible end to end on the dev database — no release is published — so
this traces what the code does once the content exists.*

1. **Register sources (staff, command line).**
   `python manage.py import_source_register <workbook> --report report.csv` is a
   dry run (everything inside a rolled-back transaction) that lists every row's
   errors and warnings; with `--commit` it creates `Authority` / `Framework` /
   `SourceDocument` / draft `SourceVersion` rows and disabled `SourceFeed`s. `python manage.py ingest_source_files` fetches each
   file from its Drive link, stores it content-addressed and verifies the SHA-256.
2. **Approve a source (Studio › Sources).** `POST /benchmarks/versions/{id}/approve`
   — refused unless the file is verified; the version becomes `active` and its file
   fields freeze.
3. **Draft requirements.** *Draft requirements* → `draft_source_requirements`
   (Celery). The AI proposes candidates per section; any whose quote is not in the
   text is dropped. The expert accepts or rejects each one.
4. **Build benchmarks (Studio › Catalogue / Requirements / Levels / Applicability).**
   `import_benchmark_catalogue <workbook> --commit` loads the Source Pack (draft benchmarks, placeholder
   levels). Experts link approved requirements, write L3/L2/L1 and non-examples,
   add evidence rules per level, and write applicability rules — the preview shows
   any profile's result with reasons. The readiness checklist turns green.
5. **Release (Studio › Releases).** Create *Release 1.0*, add the benchmarks, submit
   (readiness checked), a **second person** approves, publish: each benchmark's
   snapshot and hash are frozen and they become `active`.
6. **Watch (Studio › Watcher).** Staff switch on the official listing pages; each
   night the watcher records snapshots, raises change events with impact, and a
   person reviews them. Nothing changes on its own.
7. **Assess a college (Benchmark Assessment).** Staff set the college profile, start
   a cycle on *Release 1.0* (applicability decided per benchmark, with reasons),
   and ask for evidence. The college's IQAC coordinator uploads files per evidence
   request and submits.
8. **Review and score.** Staff review each item (five scores + decision), enter
   outcome scores, approve weights per benchmark, calculate, and **finalize**.
9. **The college sees its scorecard:** per benchmark, the level reached against the
   target, compliance, maturity, evidence confidence, outcome and — where weights
   are approved — a composite, each with its reason, stamped with the release label,
   its hash and the scoring model.
---

# 16. Error handling

## 16.1 By layer

| Layer | Mechanism | Behaviour |
|---|---|---|
| **Frontend — network/API** | `utils/errors.ts::getErrorMessage()` | Normalises DRF's three shapes (`{detail}`, `{non_field_errors:[…]}`, `{field:[msg]}`) into one string; falls back to `err.message` |
| **Frontend — extraction** | `humanizeExtractionError(message, willRetry)` | Rewrites known backend errors (rate limit/quota, timeout, unreachable, corrupt PDF, no file, unconfigured key, server error) into user guidance; correctly **suppresses "will retry automatically" once retries are exhausted**; unknown messages pass through untouched |
| **Frontend — 401** | axios response interceptor | Silent single-flight refresh + replay; on failure, clears tokens and redirects to `/login` |
| **Frontend — render** | `components/ApiStates.tsx` + `useApiResource`'s `error` | Shared loading / error-with-retry / empty states |
| **Backend — validation** | DRF serializers | `400 {"field": ["message"]}` |
| **Backend — auth** | `JWTAuthentication` | `401 {"detail": …}` |
| **Backend — permission** | permission classes / `require_institution_access` | `403 {"detail": <class .message>}` |
| **Backend — missing** | `get_object_or_404` | `404 {"detail": "Not found."}` |
| **Backend — business rules** | `raise ValidationError(...)` in views/services | `400` with an explanatory message |
| **Celery — extraction** | typed exception taxonomy | Recoverable → retry ×3 with exponential backoff; permanent/unknown → fail immediately; **all state recorded on the job row** |
| **Celery — Drive import** | same shape | Per-file failures are **recorded and skipped**, not fatal to the job |
| **Celery — reports** | broad `except Exception` | `status=failed`, error stored in `report_data['error']`; **no retry, deliberately** |
| **Celery — extraction stop** | `ExtractionCancelled` (not an `ExtractionError`) | Raised at the next checkpoint after Stop; the job keeps its `cancelled` status, nothing is retried, the sprint leaves `processing` when nothing is left running |
| **Benchmark / assessment rules** | `ReleaseError`, `AssessmentError`, `ApplicabilityError`, `EvidenceRuleError`, … | `400 {"detail", "problems": [...]}` — every unmet rule listed, shown as bullets in Studio and on the assessment page |
| **Watcher** | `FetchError` per feed | One broken feed never stops the run; it is recorded in `WatcherRun.failure_detail`, and a page that *starts* failing raises a single change event |
| **Celery — vector indexing** | typed taxonomy mirroring extraction's | Recoverable → retry ×3 at 20/40/80 s; permanent/unknown → fail immediately, reason written to `VectorDocumentIndex.error_message`. **Classification is by HTTP status code**, not by string-matching the exception text — an earlier keyword approach misread a `400`'s header dump as transient |
| **Broker down** | `try/except` around every `.delay()` | Job marked failed with `"Could not reach the Celery broker: …"`; **API still returns 201/202** |
| **Logging** | `LOGGING` in settings | Console handler, `{asctime} {levelname} {name} {message}`; `django`/`apps`/`celery` loggers at INFO, root at WARNING. The comment notes that without this block, `apps.*` module loggers would silently vanish into Python's last-resort handler |

## 16.2 What happens when each thing fails

| Failure | Result |
|---|---|
| **Wrong password** | `400 {"non_field_errors": ["Invalid login credentials"]}` — inline on the login form |
| **Disabled account** | `400 ["This account has been disabled"]` |
| **Access token expired** | Transparent refresh + replay; user sees nothing |
| **Refresh token expired/blacklisted** | Tokens cleared, hard redirect to `/login` |
| **Wrong institution** | `403 "You do not have access to this institution."` |
| **Wrong role for a write** | `403` with the gate's own message, e.g. *"Only InGage consultants can edit recommendations."* |
| **Upload too large / wrong type / duplicate** | `400` with a specific, human message naming the size or the existing document |
| **Corrupt or password-protected PDF** | `PermanentExtractionError("Could not parse PDF: …")` → job fails immediately (no wasted retries) → frontend shows *"This document could not be read — it may be corrupted, password-protected, or not a valid PDF."* |
| **Word / Excel / CSV / image** | Read into sections / sheets / OCR text and extracted like a PDF |
| **Old .doc / .xls, or .zip** | Marked `unsupported_format`; the upload page shows *"Can't read this file type"* with what to do (save as .docx/.xlsx/PDF, or unzip) |
| **Scanned PDF page** | Rendered and read by PaddleOCR; if OCR is off or still cannot read it, an `ocr_warning` is recorded and the page is flagged — the rest of the document continues |
| **User presses Stop mid-document** | The worker stops at the next step or AI call; facts already written stay, the job shows *Cancelled*, and *Process* runs it again from the start |
| **A router fails (multi_router)** | Recoverable error → that router is used last for 60 s and the retry leases another one; a call without a lease is refused rather than sent to `AI_BASE_URL` |
| **Router replies in prose instead of JSON** | Lenient parse, then one corrective retry; a second failure fails the job as before |
| **No published release** | Starting an assessment returns `400` "No benchmark release has been published yet" |
| **College opens the scorecard before finalize** | `403` "The scorecard is shared once InGage finalizes the assessment" |
| **AI rate limit / timeout / 5xx** | Recoverable → 3 retries at 30/60/120 s → then failed; UI: *"The AI service is temporarily unavailable…"* |
| **AI 4xx (bad key)** | Permanent → immediate failure; UI: *"The AI service is not configured on the server. Contact your administrator."* |
| **AI returns malformed/truncated JSON** | `AIResponseError` (permanent) — retrying identical input cannot help |
| **AI returns one bad fact** | **That fact only** is dropped with a warning; the chunk and document continue |
| **AI invents a page number** | The fact is rejected by `_validate_fact` |
| **Redis down** | Job row created + marked failed with a clear message; API returns normally |
| **Drive folder not shared** | Job fails with explicit guidance to share as "Anyone with the link — Viewer" |
| **One Drive file fails to export** | Recorded in `results['skipped_files']` with a reason; the rest import |
| **Report render fails** | `Report.status=failed`, exception text in `report_data['error']`; the polling page stops |
| **Approve with blocking gaps open** | `400` naming the count and pointing at approve-provisionally |
| **Recalculate a locked baseline** | `400` explaining the baseline must be returned for correction first |
| **Delete an active sprint** | `400` *"Archive it first (or delete it while still a draft)."* |
| **Delete a non-failed extraction job** | `400` *"Only failed jobs can be deleted."* |
| **Delete an institution** | Hard cascade inside a transaction. `Baseline` rows are cleared first to avoid a `ProtectedError` from the `PROTECT`-vs-`CASCADE` collector interaction on `Baseline.scoring_run` |
| **Pinecone unconfigured (or the SDK not installed)** | No task is queued and no row is written — the rest of the platform is unaffected. The three vector endpoints return `503` naming the missing variables, so *"not configured"* is never mistaken for *"no results"* |
| **Pinecone rate-limited / timing out / down** | Indexing retries; a *search* returns `503 "Evidence search is temporarily unavailable: …"` so the caller knows to retry rather than assuming the college has no evidence |
| **A document re-indexed with unchanged text** | No-op — the content hash matches, so nothing is re-embedded and no cost is incurred |
| **Indexing fails for one document** | That document alone is marked `failed` with its reason; the sprint's other documents index normally, each having its own task and retry budget |

## 16.3 Missing error handling

| Gap | Impact |
|---|---|
| **No global frontend `ErrorBoundary`** | A render-time exception in any page blanks the whole SPA |
| **No dead-letter / stuck-job sweeper** | A job whose worker is killed mid-run stays `running` until its message is redelivered (`acks_late`, after the 6-hour visibility timeout) and the claim lets it continue. Nothing reconciles a row whose message is lost. Beat now exists, but no sweeper is scheduled on it |
| **No structured/centralised error reporting** | Console logs only; no Sentry or equivalent |
| **`_advance_sprint_if_all_jobs_done` is not transactional** | Two workers finishing simultaneously could both see "nothing active" and both run `generate_gaps_for_sprint` — the gap constraints prevent duplicate rows, so it is wasted work rather than corruption |
| **Classification result is discarded** | Stage 1 spends a full AI call, logs the answer, and writes nothing but `processing_status='classified'` |
| **Requirement drafting is untested against a real model** | Its quote check is tested with a fake AI; how many genuine drafts a live model's paraphrasing loses has not been measured |

---

# 17. Security analysis

## Good

| # | Finding |
|---|---|
| 1 | **Secrets are not committed.** `git ls-files` shows only `.env.example` files tracked; `backend/.env`, `db.sqlite3`, and `media/` are all correctly git-ignored. |
| 2 | **`DEFAULT_PERMISSION_CLASSES = (IsAuthenticated,)`** — endpoints are private by default; only `LoginView` opts out. |
| 3 | **Two-layer authorization**, consistently applied: a role gate plus an institution check, with the nested-route helper (`get_authorized_sprint`) ensuring sub-resources are not missed. |
| 4 | **Media is never served statically**, even under `DEBUG` — `config/urls.py` documents the reason. Downloads go through an authenticated `FileResponse` endpoint. |
| 5 | **Upload hardening:** extension allowlist, 50 MB business cap plus Django parse limits, SHA-256 dedupe, and `document_type` constrained by regex. |
| 6 | **AI secrets never logged.** Both clients log only model + duration + outcome, explicitly *not* the key, prompt, or response body. The Drive module keeps the API key out of exception messages. |
| 7 | **Every AI field is re-validated in Python** — the model cannot inject an out-of-range confidence, an unknown pillar, an unknown owner role, or a fabricated page citation. |
| 8 | **Refresh-token blacklisting is real** — `token_blacklist` is installed and `logout` uses it. |
| 9 | **Production hardening is automatic** when `DEBUG=False`: SSL redirect, secure session/CSRF cookies, HSTS 1 year + subdomains + preload, nosniff, XSS filter, `SECURE_PROXY_SSL_HEADER`. |
| 10 | **SQL injection is structurally prevented** — every query goes through the Django ORM; there is no `raw()`, no `extra()`, no string-built SQL anywhere. |
| 11 | **XSS is structurally low-risk** — React escapes by default and there is **no `dangerouslySetInnerHTML`** anywhere in the frontend. |
| 12 | **Password validation** uses Django's four validators on change-password. |
| 13 | **CORS is explicitly allowlisted** (`CORS_ALLOWED_ORIGINS`), not `CORS_ALLOW_ALL_ORIGINS`. |
| 14 | **Immutable audit trails** — `FactReviewHistory`, `BaselineDecisionHistory`, `ScoringRun.pillar_snapshot`, `Report.version`, and the `PROTECT` FK on `Baseline.scoring_run`. |
| 15 | **Only failed extraction jobs are deletable**, and only draft/completed/archived sprints — history cannot be quietly destroyed. |
| 16 | **779 tests** across 14 apps, including permission and institution-scoping tests. |
| 17 | **Cross-institution vector retrieval is structurally prevented.** The `college_id` filter is built server-side in `search.build_filter()`, never accepted from the caller; the institution comes from the URL's sprint, not the request body; and `pinecone_client._require_filter()` refuses to issue an unfiltered query at all. Filtering happens **inside Pinecone**, not by discarding rows after retrieval. |
| 18 | **Pinecone internals never reach the client** — no index name, host, key or raw match object is serialized. Unconfigured deployments get a `503` with a stated reason, not a `500` stack trace. |
| 19 | **User administration cannot be used to escalate.** Institution admins are confined to their own college, cannot mint platform roles or move users between colleges, and nobody can deactivate or re-role themselves (§3.16). "Delete" is deactivation, so audit trails keep resolving. |
| 20 | **The benchmark library is server-side staff-only.** `IsInGageStaff` gates reads as well as writes on every `/benchmarks/*` route — not just the Studio page, which was the earlier gap (Benchmark Studio used to be reachable by anyone with a session). |
| 21 | **Four-eyes where it matters:** a release's approver must differ from its submitter; an evidence reviewer must differ from its uploader. |
| 22 | **Tamper-evident benchmark history:** append-only audit events, frozen source-version files, hashed release snapshots, append-only evidence reviews, and `PROTECT` from assessments to the release they used. |
| 23 | **The watcher is polite by construction:** robots.txt honoured, one request per page per day, a pause per host, an honest User-Agent, and every feed off until a person switches it on. |
| 24 | **Router and AI keys stay out of logs and status output.** `ai_mode_status`, the worker's start-up line and the Django system check describe the configuration without printing keys. |

## Needs improvement

| # | Finding | Detail |
|---|---|---|
| 1 | ~~No rate limiting~~ **Fixed 15 Oct** | Login: 10/min per client address and 20/hour per email (`429`); admin login 10/min; change-password 10/hour. Counters live in Redis in production so all workers share them. Other endpoints are still unthrottled. |
| 2 | **No account lockout** | Combined with #1, credential stuffing is unimpeded. |
| 3 | **Tokens in `localStorage`** | Standard SPA trade-off, but XSS-readable. The 60-minute access TTL limits the window; the 1-day refresh token does not. |
| 4 | **Refresh tokens are not rotated** | `ROTATE_REFRESH_TOKENS: False` and `BLACKLIST_AFTER_ROTATION: False` — a stolen refresh token is valid for its full day and is only revoked by an explicit logout. |
| 5 | **`viewer` can read everything in its institution** | Every role gate returns `True` for `SAFE_METHODS`, so a "Trustee Board" viewer can read raw facts, gaps, and unpublished reports — not only approved ones, as the persona description implies. |
| 6 | **No frontend role gating** | `ProtectedLayout` checks only for a session; every screen is reachable by every role, failing only on the action. |
| 7 | **Uploaded file content is never inspected** | Only the extension is checked. A renamed executable, a zip bomb, or a malicious PDF is accepted (though only PDFs are ever parsed, by PyMuPDF and PaddleOCR, in the worker). `.zip` is allowed but never processed. |
| 8 | **No PII redaction before AI calls** | Full document text — potentially containing student and staff personal data — is sent to a third-party provider with no consent record or residency control. |
| 9 | **Drive import requires public link-sharing** | An API-key-only integration cannot read a private folder, so institutions must expose the folder to anyone with the link for the duration. A service account would remove this. |
| 10 | ~~API docs enabled in production~~ **Fixed 15 Oct** | `/api/docs`, `/api/redoc`, `/api/schema` are only registered when `API_DOCS_ENABLED=true` (default off when `DEBUG=False`). |
| 11 | **`GOOGLE_DRIVE_API_KEY` travels as a URL query parameter** | Inherent to the Drive REST API-key flow; it is kept out of logs and exceptions, but it will appear in any intermediary's request logs. |
| 12 | **No database encryption at rest / no backups in the repo** | `postgres_data` and `media_data` are plain Docker volumes. |
| 13 | **No `SECURE_REFERRER_POLICY` or CSP** | Neither is set; `X-Frame-Options` is on via middleware. |
| 14 | **`ALLOWED_HOSTS` defaults to `localhost,127.0.0.1`** | Safe by default, but a misconfigured deploy fails confusingly rather than loudly. |
| 15 | **Assessment evidence is not content-inspected** | Same as #7: extension and size are checked, the bytes are not. Evidence is only ever opened by a person, never parsed, which limits the exposure |
| 16 | **Watcher fetches arbitrary URLs from feed rows** | Feeds come from the staff-imported register and must be switched on by staff, so this is not user-controlled SSRF — but nothing restricts a feed to public hosts either |
| 17 | **Imported source workbooks are parsed with `openpyxl`** | Staff-only, but an untrusted workbook is still parsed server-side |

## High priority

| # | Finding | Why it matters | Where |
|---|---|---|---|
| **H1** | **`SECRET_KEY` has an insecure fallback and never fails fast.** `SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key-change-me')` — and `JWT_SECRET_KEY` falls back to `SECRET_KEY`. A deployment that forgets both env vars boots happily and **signs every JWT with a key published in this repository**, letting anyone mint a `super_admin` token. | Total authentication bypass | `backend/config/settings.py` |
| **H2** | **PARTLY FIXED 15 Oct: the login page no longer pre-fills or contains the password** (only a developer build with `VITE_SHOW_DEMO_PERSONAS=true` does). **STILL OPEN: all 12 active production accounts, including both super admins, still use `Password123!`** (checked on the server; counts only) — they must be changed. Original finding: **The production login page ships 11 real account emails and a hardcoded password.** `frontend/src/pages/auth/Login.tsx` defines `SEEDED_ROLES` with quick-login buttons that call `login(email, 'Password123!')`, and the email/password fields are **pre-filled** with `superadmin@ingage.ai` / `Password123!`. `AuthContext.login()` also *defaults* its password parameter to `'Password123!'`. This is in the built bundle. If `seed_demo_users` was ever run against production, anyone visiting the site is one click from super-admin. | Full account takeover | `Login.tsx`, `AuthContext.tsx`, `seed_demo_users.py` |
| **H3** | **FIXED 13 Oct: HTTPS with a Let's Encrypt certificate on ai.ingageedutech.com** (and on the router ports); the redirect is now correct. Original finding: **`SECURE_SSL_REDIRECT` is on by default with no TLS anywhere.** With `DEBUG=False`, Django 301-redirects every request to `https://`, but compose exposes only `80:80` and there is no certificate, no certbot, and no TLS terminator in the repo. Either the site is unreachable, or `SECURE_SSL_REDIRECT=False` is set and **all traffic — including JWTs — is plaintext HTTP**. | Credential/token interception, or an unusable deploy | `settings.py`, `docker-compose.yml`, `nginx.conf` |
| **H4** | **FIXED 15 Oct** (see Needs improvement #1). Original finding: **No throttling on authentication.** With H2's known emails, an unthrottled `POST /auth/login` is a ready-made credential-stuffing target. | Brute force | `settings.py` (REST_FRAMEWORK) |
| **H5** | **Django admin is exposed at `/admin/` over the same nginx** with session auth, no IP restriction, and no 2FA. Combined with H1/H3 this is the highest-value target on the box. | Privilege escalation | `nginx.conf`, `config/urls.py` |

> **Also worth naming (correctness, not security):** the `DRIVE_IMPORT_CHECKLIST`
> slugs (`aqar_report`, `faculty_master`, `research_publications`) do **not** match
> `REQUIRED_DOCUMENT_TYPES` (`aqar`, `faculty_master_list`, …). A Drive-imported
> AQAR therefore does **not** satisfy the `missing_document` gap check, so a sprint
> that imported everything correctly can still show blocking gaps and be refused
> full baseline approval. The divergence is documented in `constants.py` as
> pre-existing and out of scope, but it is a live functional defect.

---

# 18. Performance analysis

## 18.1 Database

| # | Issue | Location | Impact |
|---|---|---|---|
| P1 | **N+1 in the conflict pre-filter.** `_candidate_pairs()` loops over every fact of the document and runs a **separate query per fact**. With 97 facts that is 98 queries — and the pair list can grow to O(n²) before being sliced to `max_pairs`. | `extraction/services/conflict_checker.py` | Slow, per document |
| P2 | **N+1 in gap generation.** `_detect_low_confidence_facts` and `_detect_unconfirmed_facts` call `create_gap_if_new()` per fact, each doing an `exists()` then an `INSERT`. ~200 queries for 100 facts. | `gaps/services.py` | Slow at the end of every sprint |
| P3 | **N+1 in recommendation generation.** `_derive_gap_owner_role(gap)` touches `gap.source_fact.owner_role` / `gap.related_document.owner_role` with **no `select_related`** on the gaps queryset. | `recommendations/services.py` | One extra query per gap |
| P4 | **~32 queries per scoring run.** `_evaluate_pillar` runs `count()`, `count()`, and `aggregate()` on the gaps queryset **separately** — three round trips × 8 pillars — plus the per-criterion fact reads. | `scoring/services/cri_engine.py` | Moderate; every recalculation |
| P5 | **~20 `count()` queries in one request.** `SprintViewSet.overview` counts documents (7 buckets), facts (6), gaps (5), recommendations (3), reports (1) individually, then serialises every document, recommendation, and the scorecard. | `sprints/views.py` | The heaviest single endpoint |
| P6 | **Almost no composite indexes.** The hot filters — `facts(sprint_id, status)`, `gaps(sprint_id, status, priority)`, `documents(sprint_id, status)`, `extraction_jobs(sprint_id, status)` — rely on single-column FK indexes only. `vector_store` is the one app that declares the index for its own filter (`ix_vecidx_sprint_status`), which is the pattern the others should follow. | all migrations | Grows with data volume |
| P7 | **`_detect_conflicting_facts` loads every fact into memory** and groups in Python. | `gaps/services.py` | Memory + time on large sprints |

**Recommendations:** batch P1 into one `field_key__in=[…]` query; use `bulk_create`
with `ignore_conflicts=True` (backed by the existing partial unique constraints) for
P2; add `.select_related('source_fact','related_document')` for P3; collapse P4's
three gap queries into one `.aggregate(Count(...), Count(..., filter=...), Sum(...))`;
replace P5's counts with a single `.aggregate()` of conditional `Count`s (carefully —
the dashboard's own comment warns about fanning out reverse-FK joins); add the
composite indexes in P6.

## 18.2 AI cost and latency

| Metric | Value |
|---|---|
| Calls per document | 1 (classify) + ≤20 (extract) + ≤10 (conflicts) = **≤31** |
| Repeated system prompt | **~1 500 tokens × up to 20 chunks** per document, uncached |
| Timeout per call | 60 s |
| Worker concurrency | **2** (`single`) or **8** (`multi_router`, 4 routers × 2) |
| Serial worst case, 6 documents | 6 × 31 = 186 calls; at ~3 s each ≈ **5 minutes** with 2 slots, well under 2 minutes with 8 |
| OCR | **CPU-bound and serialised** (one PaddleOCR inference at a time per worker process, by design); a scanned page costs seconds, not milliseconds, on top of the AI time |
| Measured cost | No longer an estimate — `AIUsage` records the real tokens and cost per call (§3.15) |

**Biggest wins, in order:** (1) prompt caching on the fact-extraction system block;
(2) batch the conflict checker into one multi-pair request; (3) reuse stage 2's page
read for stage 1 instead of re-parsing the PDF; (4) consider a cheaper model for
classification. All four are behaviour-preserving. See §9.5.

### Indexing cost, when the vector store is enabled

| Metric | Value |
|---|---|
| Chunks per document | Roughly `chars / 1 050` per page (1 200 max less 150 overlap), rounded up at each sentence boundary — a 180-page PDF runs to a few hundred |
| Embedding calls | Batched: **96** records per `upsert_records` (integrated) or **100** vectors per `upsert` (manual). ~300 chunks → 3–4 calls |
| Re-index cost when nothing changed | **Zero.** The SHA-256 content-hash check short-circuits before any embedding, which is what makes "re-index this sprint" safe to press repeatedly |
| Search | One embedding call (manual mode only) + one filtered `query`; `top_k` is capped at 50 |
| Effect on the user's request | **None** — all indexing is on Celery; only search is synchronous, and it is a single round trip |

The batch caps are not cosmetic: `upsert_records` rejects a batch above **96**
outright, which is why the integrated store carries a different constant from the
manual one.

## 18.3 Frontend

| # | Issue |
|---|---|
| F1 | **No code splitting.** Every page is a static top-level import in `App.tsx` — now including Benchmark Studio's ten tabs and the assessment pages, all InGage-internal or rarely used, yet shipped to every college user in the one bundle. `React.lazy` + `Suspense` per route would materially cut the initial bundle. |
| F2 | **3-second polling with no backoff.** Both `AIProcessingMonitor` and `ReportPreviewExport` poll unconditionally. A 20-minute extraction is ~400 requests per open tab. Exponential backoff, or stopping once every job is terminal, would cut this by an order of magnitude. |
| F3 | **No request caching or deduplication.** Every mount refetches; `useApiResource` has no cache. React Query/SWR would remove most redundant calls. |
| F4 | **Full list refetch after every single action.** Confirming one fact refetches the whole fact list. |
| F5 | **No virtualisation.** A sprint with a thousand facts renders a thousand DOM rows; pagination exists on the API but the frontend never passes `?page`. |

## 18.4 Infrastructure

| # | Issue |
|---|---|
| I1 | **Gunicorn: 3 sync workers.** Every request occupies a worker for its full duration; the heavy `overview` endpoint can starve the pool. Consider `gthread` or more workers. |
| I2 | **Worker slots follow the AI mode** — 2 in `single`, 8 in `multi_router`. The router leases keep each router at 2 documents, so more slots only help when more routers (or a provider with higher limits) exist. |
| I2a | **OCR serialisation.** `paddle_ocr._infer_lock` makes OCR one-at-a-time inside a worker process, so on a scan-heavy sprint the 8 slots contend for it. A separate OCR queue/worker would remove the contention. |
| I2b | **The backend image grew past 1 GB with OCR**, which makes pulls slower and is why the deploy now checks free disk. The OCR layer is cached separately so ordinary deploys stay small. |
| I3 | **`conn_max_age=600`** persistent connections × (3 gunicorn + 2 celery) processes — well within Postgres defaults, but worth watching if worker counts rise. |
| I4 | **No caching layer.** Redis is present but used **only** as a Celery broker. `GET /dashboard`, `GET /sprints/{id}/overview`, and `GET /scoring/config` are all excellent cache candidates. |
| I5 | **`media_data` is a local volume** — no CDN, no offload; every report download streams through Django and Gunicorn. |

---

# 19. Project folder structure

```text
D:\AI READY\
├── .github/workflows/ci-cd.yml     # test → build → push to GHCR → SSH deploy
├── docker-compose.yml              # PRODUCTION compose: db, redis, backend, celery, celery-beat, frontend
├── .env.production.example         # template for /opt/ai-ready/.env on the VM
├── .gitignore                      # ignores dump.rdb, *.rdb, .env, .env.production, transfer/
├── start-dev.ps1                   # Windows dev start: WSL Redis, routers (multi_router), worker, health check
├── switch-ai-mode.ps1              # change AI_PROCESSING_MODE + warm-restart the worker
├── source_library_work/            # interns' Source Register / QA workbooks + import reports (data, not code)
├── dump.rdb                        # stray local Redis snapshot (untracked, ignorable)
│
├── backend/                        # Django 5 + DRF + Celery
│   ├── manage.py
│   ├── Dockerfile                  # python:3.12-slim + libpq5 + OCR system libs; OCR deps in their own layer
│   ├── docker-entrypoint.sh        # migrate + collectstatic ONLY for the gunicorn process
│   ├── .env / .env.example         # .env is git-ignored
│   ├── db.sqlite3                  # local dev database (git-ignored)
│   ├── media/                      # uploads, reports, source_library/, source_snapshots/, assessment_evidence/ (git-ignored)
│   ├── requirements/
│   │   ├── base.txt                # runtime packages (pulls in ocr.txt)
│   │   ├── ocr.txt                 # paddlepaddle <3.3 + paddleocr — >1 GB, own Docker layer
│   │   ├── development.txt         # + pytest-django, black, flake8
│   │   └── production.txt          # + gunicorn, uvicorn
│   ├── docs/
│   │   ├── API_CONTRACT.md         # hand-written contract — last updated 1 Sep 2026 (stale, §7)
│   │   ├── VECTOR_STORE.md         # vector-store architecture + operator setup
│   │   ├── AI_PROCESSING_MODES.md  # single vs multi_router, switching, health check
│   │   ├── SOURCE_LIBRARY.md       # benchmark library stages 1–4: every rule + endpoint
│   │   ├── BENCHMARK_ASSESSMENTS.md # stage 5
│   │   └── openapi.yaml            # stale like API_CONTRACT.md
│   ├── config/                     # PROJECT configuration (not an app)
│   │   ├── settings.py             # single settings module, heavily commented
│   │   ├── ai_processing_mode.py   # the AI mode switch + derived worker count
│   │   ├── urls.py                 # root router + spectacular; deliberately no media serving
│   │   ├── celery.py               # Celery('aios_backend') + worker_ready mode log
│   │   ├── pagination.py           # OptionalPageNumberPagination
│   │   └── wsgi.py / asgi.py       # gunicorn uses wsgi; asgi is unused
│   └── apps/                       # FOURTEEN domain apps
│       ├── accounts/               # User (11 roles) · permissions.py · user_admin.py · tokens · seed_demo_users
│       ├── institutions/           # the tenant + Institution DNA (leaders, departments, IT systems)
│       ├── sprints/                # state machine · overview · access.py · composes nested URLs
│       ├── documents/              # upload validation · Drive import · secure download
│       │   ├── services.py         #   create_document_from_file() — the ONE ingestion path
│       │   ├── tasks.py            #   run_drive_import_job
│       │   ├── drive_import.py     #   Drive REST v3 client
│       │   └── constants.py        #   DOCUMENT_TYPES · REQUIRED_… · DRIVE_IMPORT_CHECKLIST
│       ├── extraction/             # THE AI PIPELINE
│       │   ├── models.py           #   ExtractionJob · AIUsage
│       │   ├── tasks.py            #   run_extraction_job: claim, router lease, retry policy, Stop
│       │   ├── exceptions.py       #   Recoverable / Permanent / AIResponseError / ExtractionCancelled
│       │   ├── usage.py · pricing.py  # AI usage recording + call-time pricing
│       │   ├── checks.py           #   Django system check for the AI mode
│       │   ├── management/commands/   # ai_mode_status · ai_usage_report · import_ai_usage
│       │   └── services/
│       │       ├── base.py         #     7 ABCs — every stage is swappable
│       │       ├── ai_service.py   #     provider factory (mode, lease, key-prefix / base-URL detection)
│       │       ├── router_pool.py  #     multi_router: Redis-leased router slots, cooldown
│       │       ├── processing_status.py  # mode summary + configuration problems (no keys)
│       │       ├── openai_client.py / anthropic_client.py
│       │       ├── pipeline.py     #     the 7-stage orchestrator + Stop checkpoints
│       │       ├── pdf_reader.py   #     PyMuPDF text layer → OCR fallback → cleanup
│       │       ├── paddle_ocr.py   #     PaddleOCR provider (lazy engine, inference lock)
│       │       ├── text_cleaning.py #    "is meaningful?", header/footer removal
│       │       ├── openai_classifier.py
│       │       ├── openai_fact_extractor.py   # prompt + schema + Python validation
│       │       ├── gap_detector.py #     deterministic, NO AI
│       │       ├── conflict_checker.py        # deterministic pre-filter + AI verdict
│       │       └── stub.py         #     honest no-op defaults
│       ├── facts/                  # 4 review actions + append-only history
│       ├── gaps/                   # 5 detectors + create_gap_if_new + 3 partial constraints
│       ├── scoring/                # Pillar/Criterion/PillarScore/ScoringRun/Baseline
│       │   └── services/
│       │       ├── cri_engine.py   #   the 9-step deterministic engine
│       │       └── baseline.py     #   approve / approve-provisional / return
│       ├── recommendations/        # 3 idempotent generators
│       ├── reports/                # 11-section builder + fpdf2 PDF + python-docx DOCX
│       ├── dashboard/              # aggregation only — OWNS NO MODELS
│       ├── vector_store/           # OPTIONAL — Pinecone evidence retrieval
│       │   ├── models.py           #   VectorDocumentIndex (tracking only, no vectors)
│       │   ├── tasks.py            #   index_document_vectors + index_sprint_vectors
│       │   ├── exceptions.py       #   Recoverable / Permanent, mirroring extraction's
│       │   ├── urls.py             #   DELIBERATELY EMPTY — routes live in sprints/urls.py
│       │   └── services/
│       │       ├── chunking.py     #     page-aware, sentence-aware splitting
│       │       ├── embeddings.py   #     EmbeddingService ABC + OpenAI implementation
│       │       ├── pinecone_client.py  # THE ONLY MODULE THAT IMPORTS THE SDK (lazily)
│       │       ├── indexer.py      #     read → hash → chunk → embed → upsert
│       │       └── search.py       #     build_filter() — the isolation boundary
│       ├── benchmarks/             # BENCHMARK LIBRARY — InGage staff only
│       │   ├── models.py           #   24 models: sources → requirements → catalogue → releases → watcher
│       │   ├── tasks.py            #   draft_source_requirements · run_source_watcher
│       │   ├── management/commands/   # import_source_register · ingest_source_files ·
│       │   │                       #   import_benchmark_catalogue · run_source_watcher
│       │   └── services/           #   register/catalogue import · file_intake · approval ·
│       │                           #   requirement_drafting · linking · authoring · evidence_rules ·
│       │                           #   applicability · releases · release_lock · watcher
│       └── assessments/            # BENCHMARK ASSESSMENT of a college (stage 5)
│           ├── models.py           #   profile · programmes · scoring model/rules · cycle · applicable
│           │                       #   benchmark · evidence item/review · benchmark assessment
│           └── services.py         #   every rule + the four-score compute()
│
└── frontend/                       # React 18 + TypeScript + Vite
    ├── Dockerfile                  # node:20 build → nginx:1.27-alpine
    ├── nginx.conf                  # SPA fallback + /api and /admin proxy + 100m body
    ├── vite.config.ts              # dev proxy /api → localhost:8000
    ├── tailwind.config.js / postcss.config.js
    └── src/
        ├── main.tsx / App.tsx      # bootstrap + all 30 route entries (no lazy loading)
        ├── api/                    # 19 axios modules; client.ts holds the interceptors
        ├── context/                # AuthContext (the only global state) · ThemeContext
        ├── hooks/useApiResource.ts # the single fetch hook
        ├── layouts/AppShell.tsx
        ├── components/             # Navbar · Sidebar (15 modules) · PageHeader · ApiStates
        │   ├── TableFilters.tsx · ScrollableTable.tsx · ScrollToTop.tsx
        │   └── DemoDataNotice.tsx  #   no longer rendered anywhere
        ├── data/                   # prototype content — only 3 Benchmark Studio tabs read it
        │   ├── benchmark/          #   types (455 L) · seed (267 L) · scoring (342 L)
        │   └── workspaceDemo.ts    #   imported by nothing (dead)
        ├── pages/                  # 38 screens / panels in 19 folders
        │   ├── institutions/       #   Institution DNA — list + create + delete, 3-tab detail
        │   ├── status/             #   Project Status Dashboard — no API, outside the app shell
        │   ├── benchmark/          #   Benchmark Studio + 8 real tabs/panels · CRI & Benchmark Intelligence
        │   ├── assessments/        #   Benchmark Assessment (stage 5)
        │   ├── admin/              #   Admin / Settings · Users · AI Usage & Billing
        │   ├── evidence/ chat/ compliance/ workspace/   # rewired to real data
        │   ├── previews/           #   design write-ups; unlinked from the menu
        │   └── …                   #   auth · dashboard · sprints · documents · facts · gaps
        │                           #   · scoring · recommendations · reports
        ├── types/                  # 13 type modules
        └── utils/                  # errors.ts · extractionTiming.ts
```

### Purpose of each important folder

| Folder | Why it exists |
|---|---|
| `backend/config/` | Project-level wiring only — settings, root URLs, Celery app, shared pagination. No business logic. |
| `backend/apps/<domain>/` | One bounded context each: its own models, serializers, views, filters, services. |
| `backend/apps/<domain>/services/` | Business logic kept out of views so it can be unit-tested without HTTP — used by `extraction`, `scoring`, `gaps`, `documents`, `recommendations`, `reports`, `benchmarks`, and (as one `services.py`) `assessments`. |
| `source_library_work/` | The interns' workbooks and the import / QA reports — inputs to the benchmark library, not code. |
| `backend/apps/extraction/services/base.py` | The seam that makes every pipeline stage replaceable without touching orchestration or retry logic. |
| `backend/apps/sprints/urls.py` | Composes every nested `/sprints/<id>/…` route by importing views from their owning app — the URL shape the frontend expects without collapsing logic into one app. |
| `backend/apps/dashboard/` | Deliberately model-free: a read-only aggregation view over other apps. |
| `frontend/src/api/` | One module per backend domain; all share `client.ts`, so auth and refresh live in exactly one place. |
| `frontend/src/pages/` | One folder per wizard stage, mirroring the sidebar's numbering. |
| `frontend/src/types/` | Mirrors the backend serializers; `types/index.ts` re-exports everything. |

---

# 20. Architecture diagrams

*(The high-level architecture is in §1, the request/data flow in §2.2, the sprint
state machine in §2.1, the ERD in §6.2, the auth flows in §8.2–8.5, the AI provider
selection and pipeline in §9.1–9.2, the upload and Drive flows in §10.2/10.4, the
queue flow in §11.6, and the deployment pipeline in §14.1. The remaining two are
below.)*

## 20.1 Layered component view

```mermaid
graph TB
    subgraph P["Presentation — React 18 SPA"]
        PG["38 screens / panels<br/>audit wizard · Studio · assessment"]
        CTX["AuthContext · ThemeContext"]
        HK["useApiResource"]
        AXI["axios client<br/>token attach + silent refresh"]
    end

    subgraph T["Transport"]
        NG["nginx — SPA fallback · /api · /admin · 100m body"]
    end

    subgraph A["API — Django REST Framework"]
        URL["config.urls → apps.*.urls<br/>dual slash registration"]
        AUTH["JWTAuthentication"]
        PERM["Role gates + institution scoping"]
        SER["Serializers — validation"]
        VW["ViewSets / APIViews"]
    end

    subgraph B["Domain services"]
        DSVC["documents.services<br/>create_document_from_file"]
        GSVC["gaps.services<br/>create_gap_if_new + 5 detectors"]
        CRI["scoring.cri_engine<br/>9 deterministic steps"]
        BASE["scoring.baseline"]
        RSVC["recommendations.services<br/>3 generators"]
        REPS["reports.services<br/>11 sections"]
        BSVC["benchmarks.services<br/>import · approval · drafting · authoring ·<br/>applicability · releases · watcher"]
        ASVC["assessments.services<br/>cycles · evidence · compute()"]
    end

    subgraph W["Async — Celery (+ Beat)"]
        T1["run_extraction_job<br/>claim · lease · 3 retries · Stop"]
        T2["run_drive_import_job<br/>3 retries · 15·2ⁿ s · Stop"]
        T3["generate_report_task<br/>no retries"]
        T4["draft_source_requirements"]
        T5["run_source_watcher<br/>(Beat, daily, optional)"]
        PIPE["ExtractionPipeline — 7 stages"]
    end

    subgraph I["Integration"]
        AIF["ai_service.get_ai_service()<br/>+ router_pool (multi_router)"]
        OAI["OpenAIExtractionService"]
        ANT["AnthropicExtractionService"]
        USG["usage + pricing → AIUsage"]
        DRV["drive_import"]
        PDF["pdf_reader — PyMuPDF + PaddleOCR"]
        RND["rendering — fpdf2 + python-docx"]
        WEB["official source sites"]
    end

    subgraph D["Data"]
        PGDB[("PostgreSQL 16")]
        RDS[("Redis 7 — broker")]
        FS[["media volume"]]
    end

    PG --> HK --> AXI --> NG --> URL --> AUTH --> PERM --> SER --> VW
    VW --> DSVC & GSVC & CRI & BASE & RSVC & REPS & BSVC & ASVC
    VW -->|".delay()"| RDS --> T1 & T2 & T3 & T4 & T5
    T1 --> PIPE --> PDF & AIF
    T4 --> PDF & AIF
    T5 --> WEB
    AIF --> OAI & ANT
    OAI & ANT --> USG
    T2 --> DRV
    T3 --> REPS --> RND --> FS
    DSVC --> FS
    CRI & GSVC & BASE & RSVC --> PGDB
    VW --> PGDB
    PIPE --> PGDB
    CTX -.-> AXI
```

## 20.2 The AI pipeline in detail

```mermaid
flowchart TD
    START(["run_extraction_job(job_id)"]) --> LOAD["claim ExtractionJob → running, started_at<br/>(skip if finished / stale message)<br/>multi_router: lease a router slot"]
    LOAD --> S1["① classifying_documents — 15%"]
    S1 --> S1a["PDFPageReader: first 3 pages"]
    S1a --> S1b["🤖 get_ai_service().extract_structured_data<br/>CLASSIFICATION_SCHEMA"]
    S1b --> S1c["_validate(): confidence ∈ [0,1],<br/>nullable strings are strings-or-null"]
    S1c --> S2["② reading_pages — 30%"]
    S2 --> S2a{"extension == .pdf?"}
    S2a -->|no| S2b["format_supported=False — honest, not empty"]
    S2a -->|yes| S2c["PyMuPDF text layer per page<br/>meaningful? (≥ 40 chars, mostly letters/digits)"]
    S2c -->|no| S2d["render at 200 DPI → PaddleOCR<br/>(lines < 0.5 confidence dropped;<br/>still unreadable ⇒ requires_ocr + warning)"]
    S2c -->|yes| S2x
    S2d --> S2x["drop repeated headers/footers,<br/>normalise text"]
    S2x --> S2e["correct Document.ocr_required + ocr_warnings"]
    S2b --> S3
    S2e --> S3["③ extracting_facts — 45%"]
    S3 --> S3a["_build_chunks: ≤12 000 chars,<br/>never split a page, skip empty pages"]
    S3a --> S3b{"chunks > 20?"}
    S3b -->|yes| S3c["warn + truncate to 20"]
    S3b -->|no| S3d
    S3c --> S3d["per chunk: 🤖 FACT_EXTRACTION_SCHEMA"]
    S3d --> S3e["_validate_fact per fact<br/>types · enums · page citation · confidence"]
    S3e --> S3f["_merge_fact by field_key — keep highest confidence"]
    S3f --> S4["④ mapping_audit_fields — 60%<br/>IdentityAuditFieldMapper (pass-through)"]
    S4 --> S4a["INSERT ExtractedFact rows"]
    S4a --> S5["⑤ detecting_gaps — 75%<br/>RuleBasedGapDetector — NO AI"]
    S5 --> S5a["low_confidence / unconfirmed_fact per fact<br/>+ stale_data per document"]
    S5a --> S5b["create_gap_if_new — dedup + IntegrityError guard"]
    S5b --> S6["⑥ checking_conflicts — 90%"]
    S6 --> S6a["deterministic pre-filter:<br/>same field_key, different normalized_value"]
    S6a --> S6b{"pairs > 10?"}
    S6b -->|yes| S6c["warn + truncate to 10"]
    S6b -->|no| S6d
    S6c --> S6d["🤖 CONFLICT_SCHEMA per pair<br/>{is_conflict, confidence, explanation}"]
    S6d --> S6e["is_conflict=false ⇒ discard<br/>true ⇒ GapItem with immutable value snapshots"]
    S6e --> S7["⑦ preparing_review_workspace — 100%<br/>Document → processed"]
    S7 --> DONE["job → completed"]
    DONE --> ADV{"any job still active in this sprint?"}
    ADV -->|no| ADV1["sprint processing → reviewing<br/>+ generate_gaps_for_sprint()<br/>(adds missing_document gaps)"]
    ADV -->|yes| END(["end"])
    ADV1 --> END

    S1b -.->|"RecoverableExtractionError"| RETRY["retry ×3 — 30/60/120 s<br/>job status = retrying"]
    S3d -.->|"Recoverable"| RETRY
    S6d -.->|"Recoverable"| RETRY
    RETRY -.->|"exhausted"| FAIL["job → failed<br/>document → failed"]
    S1b -.->|"Permanent / unknown"| FAIL
    S3d -.->|"user pressed Stop<br/>(checked per step and per AI call)"| CANCEL["ExtractionCancelled<br/>job stays cancelled — no retry"]
```
---

# 21. Technology stack

| Layer | Technology | Version (as pinned) | Purpose |
|---|---|---|---|
| **Frontend** | React | `^18.2.0` | UI library |
| | TypeScript | `^5.2.2` | Type safety; `npm run build` runs `tsc` before Vite |
| | Vite | `^5.1.0` | Dev server (port 3000, `/api` proxy) + production bundler |
| | React Router DOM | `^6.22.0` | Client-side routing, 30 route entries |
| | Axios | `^1.6.7` | HTTP client + auth/refresh interceptors |
| | Tailwind CSS | `^3.4.1` | Styling (with `postcss` + `autoprefixer`) |
| | lucide-react | `^0.330.0` | Icon set |
| **Backend** | Python | 3.12 (Docker base + CI) | Runtime |
| | Django | `>=5.0,<5.1` | Web framework, ORM, admin, migrations |
| | Django REST Framework | `>=3.15.0` | API layer, serializers, permissions |
| | djangorestframework-simplejwt | `>=5.3.0` | JWT issue/verify + **token blacklist** |
| | django-cors-headers | `>=4.3.0` | CORS allowlist |
| | django-filter | `>=24.2` | Query filtering on list endpoints |
| | drf-spectacular | `>=0.27.0` | OpenAPI 3 schema, Swagger UI, ReDoc |
| | python-dotenv | `>=1.0.0` | `.env` loading |
| **Database** | PostgreSQL | 16 (`postgres:16-alpine`) | Primary datastore |
| | SQLite | bundled | Local-dev fallback when `DATABASE_URL` is unset |
| | psycopg2-binary | `>=2.9.0` | Postgres driver |
| | dj-database-url | `>=2.1.0` | DSN parsing, `conn_max_age=600` |
| **AI** | openai | `>=1.50.0,<2.0.0` | OpenAI + any OpenAI-compatible endpoint |
| | anthropic | `>=0.40.0,<1.0.0` | Claude, via forced tool call |
| | *default models* | `gpt-4o-mini` / `claude-haiku-4-5-20251001` | Per-provider defaults when no `AI_MODEL` is set |
| **Documents** | PyMuPDF (`pymupdf`) | `>=1.24.0` | PDF text layer + page rendering for OCR |
| | PaddleOCR + PaddlePaddle | `paddleocr>=3.0.0`, `paddlepaddle>=3.0.0,<3.3` (`requirements/ocr.txt`) | OCR of scanned pages, on CPU, models downloaded on first use. `<3.3` because 3.3.x crashes with oneDNN on Windows |
| | numpy | `>=1.26` | Page images handed to OCR |
| | pdfplumber | `>=0.11.0,<0.12.0` | **Still listed, no longer imported** by the app (§25) |
| | beautifulsoup4 | `>=4.12` | Watcher: document links and visible text from official pages |
| | openpyxl | `>=3.1` | Source Register / Source Pack workbook imports |
| | fpdf2 | `>=2.7.0` | PDF report rendering |
| | python-docx | `>=1.1.0` | DOCX report rendering |
| | Pillow | `>=10.2.0` | Image handling (Django `ImageField` support) |
| | requests | `>=2.31.0` | Google Drive REST v3 calls |
| **Vector search** | pinecone | `>=5.0.0,<7.0.0` | Vector index for college-evidence retrieval. **Optional at runtime** — imported lazily, only when configured |
| | *embedding model* | `text-embedding-3-small` (manual mode) | Default embedding model; integrated indexes embed server-side instead (e.g. `llama-text-embed-v2`) |
| **Storage** | Local filesystem | — | `MEDIA_ROOT`, mounted as the `media_data` Docker volume. **No S3/GCS.** |
| **Queue** | Celery | `>=5.3.0` | Async task execution; **Beat** for the one daily watcher job |
| | Redis | 7 (`redis:7-alpine`); client `>=5.0.0` | Broker, and the **router-slot leases** in multi_router mode (result backend nominally configured but ignored) |
| **Web server** | nginx | `1.27-alpine` | SPA serving, `/api` + `/admin` reverse proxy, static |
| **App server** | Gunicorn | `>=21.2.0` | WSGI, 3 workers, 120 s timeout |
| | uvicorn | `>=0.27.0` | Present in production requirements but **not used** — compose runs WSGI |
| **Deployment** | Docker + Compose v2 | — | Six services |
| **Dev tooling (Windows)** | PowerShell `start-dev.ps1` / `switch-ai-mode.ps1`; WSL for Redis and the AI routers | — | One-command local start and AI-mode switch |
| | GitHub Actions | — | test → build → push → SSH deploy |
| | GHCR | — | Image registry |
| | GCP VM | — | Single host, `/opt/ai-ready` |
| **Dev tooling** | pytest-django `>=4.7.0`, black `>=24.1.0`, flake8 `>=7.0.0` | — | In `development.txt`; **CI runs `manage.py test`, not pytest, and never runs black/flake8** |

---

# 22. Dependencies

## 22.1 Backend (`requirements/base.txt` — 23 packages + `ocr.txt`)

| Package | Why it is here |
|---|---|
| `Django>=5.0,<5.1` | Framework. Minor-pinned to 5.0.x — a deliberate, conservative range |
| `djangorestframework>=3.15.0` | The entire API layer |
| `django-cors-headers>=4.3.0` | The SPA is served from a different origin in dev |
| `djangorestframework-simplejwt>=5.3.0` | JWT + the blacklist app that makes logout real |
| `python-dotenv>=1.0.0` | `.env` loading in `settings.py` |
| `Pillow>=10.2.0` | Required by Django for image fields; images are in the upload allowlist |
| `celery>=5.3.0` | The seven async tasks, and Beat for the watcher |
| `redis>=5.0.0` | Celery's broker transport, and the router-slot leases |
| `drf-spectacular>=0.27.0` | OpenAPI schema + Swagger/ReDoc |
| `psycopg2-binary>=2.9.0` | Postgres driver (binary wheel — fine here; `psycopg2` source is preferred by some for production) |
| `dj-database-url>=2.1.0` | Single-variable DB config, with the SQLite fallback |
| `django-filter>=24.2` | `filterset_class` on facts, gaps, sprints, institutions, scoring config |
| `fpdf2>=2.7.0` | PDF rendering. Chosen over WeasyPrint/wkhtmltopdf because it needs **no system binaries** — the trade is Latin-1-only core fonts, handled by `_latin1()` |
| `python-docx>=1.1.0` | DOCX rendering (full UTF-8, unlike the PDF path) |
| `openai>=1.50.0,<2.0.0` | OpenAI SDK; **major-pinned** — sensible, the v1→v2 boundary is breaking |
| `anthropic>=0.40.0,<1.0.0` | Anthropic SDK; **major-pinned** for the same reason |
| `pdfplumber>=0.11.0,<0.12.0` | **No longer imported** — `pdf_reader.py` moved to PyMuPDF in `e35fdc4`; only test docstrings still mention it. Removable |
| `pymupdf>=1.24.0` | PDF text layer and page rendering for OCR |
| `numpy>=1.26` | Page images for OCR (used to arrive only as a PaddleOCR dependency) |
| `-r ocr.txt` → `paddlepaddle>=3.0.0,<3.3`, `paddleocr>=3.0.0` | OCR of scanned pages; > 1 GB installed, so the Dockerfile installs `ocr.txt` in its own cached layer |
| `requests>=2.31.0` | Google Drive REST calls, Source Library file intake, the watcher |
| `beautifulsoup4>=4.12` | Watcher: parse official pages |
| `openpyxl>=3.1` | Source Register / Source Pack workbook imports. **Added to `base.txt` on 13 Oct 2026** — before that it was used but undeclared, so a clean CI or Docker install would have failed the benchmark imports and tests |
| `pinecone>=5.0.0,<7.0.0` | Vector store; **major-bounded**. Listed as a runtime requirement but imported **lazily**, only when Pinecone is actually configured — the project boots, migrates and passes its full suite with the package absent |

**Development adds:** `pytest-django`, `black`, `flake8`.
**Production adds:** `gunicorn`, `uvicorn`.

## 22.2 Frontend (`package.json` — 5 runtime, 9 dev)

Runtime: `react`, `react-dom`, `react-router-dom`, `axios`, `lucide-react`.
Dev: `@vitejs/plugin-react`, `vite`, `typescript`, `@types/react`, `@types/react-dom`,
`tailwindcss`, `postcss`, `autoprefixer`.

**This is an unusually lean dependency set** — no UI kit, no state library, no form
library, no date library, no chart library. Everything is hand-rolled on Tailwind.

## 22.3 Assessment

| Observation | Detail |
|---|---|
| **Well-pinned where it matters** | The volatile packages (`openai`, `anthropic`, `pinecone`, `paddlepaddle`) carry upper bounds; Django is minor-bounded. `pymupdf` and `paddleocr` have no ceiling |
| **Two dependencies are optional at runtime** | `pinecone` (lazy import behind a configuration check) and `paddleocr` (checked by `paddleocr_available()`, falling back to no OCR). Everything else is imported unconditionally |
| **Loosely pinned elsewhere** | Most packages are `>=` with no ceiling, and there is **no lockfile for Python** (no `requirements.lock`, no Poetry/uv/pip-tools). Two builds a month apart can resolve differently — the CI image and the deployed image may not match |
| **Frontend is locked** | `package-lock.json` is committed and CI uses `npm ci` — reproducible |
| **`uvicorn` is unused** | Listed in `production.txt`; compose runs `gunicorn config.wsgi`. `config/asgi.py` exists but nothing routes to it. Dead weight |
| **Dev tools are never enforced** | `black` and `flake8` are installed in CI (via `development.txt`) but no workflow step runs them |
| **`pytest-django` is installed but unused** | CI runs `python manage.py test`; there is no `pytest.ini`/`setup.cfg`/`pyproject.toml` configuring pytest |
| **`redis` (Python client) is a direct dependency** | Correct — Celery needs it for the Redis transport |
| **`Pillow`** | Justified by the image extensions in the upload allowlist, though no `ImageField` is actually declared |
| **No security scanning** | No `pip-audit`, `safety`, `npm audit`, or Dependabot config in the repo |

---

# 23. Important files

| File | Why it matters |
|---|---|
| `backend/config/settings.py` | **The single most informative file in the repo.** Every tunable, plus long comments explaining *why* each default was chosen (`APPEND_SLASH`, `CELERY_TASK_IGNORE_RESULT`, the AI provider strategy, the two upload limits, the production hardening block) |
| `backend/apps/accounts/models.py` | The `User` model, the 11 roles, and `CROSS_INSTITUTION_ROLES` — the root of the whole authorization model |
| `backend/apps/accounts/permissions.py` | Every reusable permission class and the institution-scoping helpers. Read this to understand who can do what |
| `backend/apps/sprints/models.py` | `ALLOWED_TRANSITIONS`, `BASELINE_LOCKED_STATUSES`, `STATUS_COMPLETION_MILESTONES` — the workflow's rulebook |
| `backend/apps/sprints/urls.py` | The full nested URL surface in one place |
| `backend/apps/extraction/services/ai_service.py` | Provider selection. Change this to add a provider |
| `backend/apps/extraction/services/pipeline.py` | The 7-stage orchestrator |
| `backend/apps/extraction/services/base.py` | The 7 ABCs that make every stage swappable |
| `backend/apps/extraction/services/openai_fact_extractor.py` | **The prompt, the JSON schema, the chunking, and the Python validation** — the highest-risk, highest-value file |
| `backend/apps/extraction/services/conflict_checker.py` | The "deterministic pre-filter, AI only for judgement" pattern |
| `backend/apps/extraction/tasks.py` | The retry policy and the sprint-advance trigger |
| `backend/apps/scoring/services/cri_engine.py` | The 9-step CRI calculation — the product's core intellectual property |
| `backend/apps/scoring/services/baseline.py` | The approval workflow and its locking rules |
| `backend/apps/scoring/constants.py` | The 8 pillar keys, engine version, and status thresholds |
| `backend/apps/gaps/services.py` | `create_gap_if_new` — the shared idempotency primitive |
| `backend/apps/gaps/models.py` | The three partial unique constraints |
| `backend/apps/documents/services.py` | `create_document_from_file()` — **the single ingestion path** for both upload and Drive import |
| `backend/apps/documents/constants.py` | Document types, required types, and the Drive checklist — **including the documented slug divergence** |
| `backend/apps/institutions/models.py` | Institution + the three DNA models, and the comment explaining which counts are stored vs. derived |
| `backend/apps/institutions/views.py` | `InstitutionScopedMixin` and the two institution permission classes — why DELETE differs between an institution and its sub-resources |
| `backend/apps/institutions/constants.py` | The five digital-maturity level descriptions |
| `backend/apps/reports/services.py` | The 11-section report builder |
| `backend/apps/vector_store/services/search.py` | `build_filter()` — the vector-side tenant boundary. **Read this to understand why one college cannot retrieve another's documents** |
| `backend/apps/vector_store/services/pinecone_client.py` | The only module importing the Pinecone SDK; both store classes, the deterministic id scheme, the metadata contract, and the error taxonomy |
| `backend/apps/vector_store/services/indexer.py` | read → hash → chunk → embed → upsert, and the content-hash short-circuit that makes re-indexing cheap |
| `backend/apps/vector_store/models.py` | Why the tracking row exists and why it holds no vectors |
| `backend/docs/VECTOR_STORE.md` | The vector store's own architecture document and operator setup guide |
| `backend/config/ai_processing_mode.py` + `apps/extraction/services/router_pool.py` | The AI mode switch and the Redis-leased router pool (§3.14) |
| `backend/apps/extraction/services/pdf_reader.py` + `paddle_ocr.py` + `text_cleaning.py` | How a page becomes text: PyMuPDF, OCR fallback, cleanup |
| `backend/apps/extraction/usage.py` + `pricing.py` | Where every AI call's tokens and cost are recorded |
| `backend/apps/accounts/user_admin.py` | User administration and its three anti-escalation rules |
| `backend/apps/benchmarks/models.py` | The whole benchmark library schema, each model naming its `schema.sql` table |
| `backend/apps/benchmarks/services/releases.py` + `release_lock.py` | Readiness, four-eyes, snapshot + hash on publish, the review lock |
| `backend/apps/benchmarks/services/requirement_drafting.py` | The benchmark side's AI call and its quote-verification guard |
| `backend/apps/benchmarks/services/applicability.py` | Applicability rules with a reason for every result; `evaluate_snapshot()` for frozen releases |
| `backend/apps/benchmarks/services/watcher.py` | The daily watcher: fetch, normalise, compare, events, impact |
| `backend/apps/assessments/services.py` | Every assessment rule and `compute()` — the four scores |
| `backend/docs/SOURCE_LIBRARY.md`, `BENCHMARK_ASSESSMENTS.md`, `AI_PROCESSING_MODES.md` | The operator / developer guides for the newer subsystems — more current than `API_CONTRACT.md` |
| `start-dev.ps1`, `switch-ai-mode.ps1` | Local Windows start-up and AI-mode switching |
| `backend/config/urls.py` | Root routing, **and the comment explaining why media is never served** |
| `backend/docs/API_CONTRACT.md` | A hand-written, frontend-audited contract; the best single reference for the API |
| `backend/apps/accounts/management/commands/seed_demo_users.py` | The 11 demo personas and the shared demo password |
| `frontend/src/api/client.ts` | Token attachment + the single-flight silent-refresh interceptor |
| `frontend/src/context/AuthContext.tsx` | The only global state |
| `frontend/src/App.tsx` | All routes + the session guard |
| `frontend/src/components/Sidebar.tsx` | The whole product plan in one file — every module, which one is staff-only, and the 10 audit steps |
| `frontend/src/api/benchmarks.ts`, `api/assessments.ts` | Every benchmark-library and assessment call and type |
| `frontend/src/pages/benchmark/BenchmarkStudio.tsx` | The staff gate and the 10 tabs — including which 3 still read seed data |
| `frontend/src/pages/assessments/BenchmarkAssessments.tsx` | The college-facing assessment page and the scorecard |
| `frontend/src/pages/institutions/InstitutionList.tsx` | The Institution DNA landing page: the list, the create form, and per-row hard delete — plus the two role sets mirroring the backend's |
| `frontend/src/pages/institutions/InstitutionDetail.tsx` | One institution's workspace: 3 tabs, the derived-vs-stored count distinction, all editing |
| `frontend/src/pages/status/StatusDashboard.tsx` | Build-progress report. **Hand-maintained constants, no API** — read §25 before trusting its numbers |
| `frontend/src/utils/errors.ts` | DRF error normalisation + extraction-error humanisation |
| `frontend/src/pages/documents/UploadDataPack.tsx` | The largest screen; holds the frontend twin of the Drive checklist |
| `docker-compose.yml` | The six production services and their volumes |
| `.github/workflows/ci-cd.yml` | The full pipeline |
| `backend/docker-entrypoint.sh` | Why only the web process migrates |
| `frontend/nginx.conf` | SPA fallback, proxy rules, and the 100 MB body limit |
| `.env.production.example` | The complete production variable list |

---

# 24. Project execution guide

> Every command below is taken from `backend/README.md`, `docker-compose.yml`,
> `.github/workflows/ci-cd.yml`, `package.json`, or `backend/.env.example`.
> Nothing here is invented.

## Prerequisites

- **Python 3.12+**
- **Node.js 20+** (CI uses 20; the Dockerfile uses `node:20-alpine`)
- **Redis** (for Celery) — a local install or `docker run --rm -p 6379:6379 redis:7`
- **PostgreSQL 16** — *optional locally*; without `DATABASE_URL` the project falls
  back to SQLite
- **Docker + Docker Compose v2** — only for the production-shaped run
- **Disk space for OCR** — `requirements/base.txt` pulls in `requirements/ocr.txt`
  (PaddlePaddle + PaddleOCR, > 1 GB installed); OCR models download on first use.
  To run without OCR, set `OCR_PROVIDER=none`
- **Windows:** WSL, for Redis (port 6380) and — in `multi_router` mode — the four
  AI routers. `start-dev.ps1` drives both

## Installation — backend

```bash
cd backend
python -m venv .venv
```

```bash
source .venv/bin/activate
```

On Windows use `.venv\Scripts\activate` instead.

```bash
pip install -r requirements/development.txt
```

## Environment setup

```bash
cp .env.example .env
```

Then edit `backend/.env`. The minimum for the app to boot is nothing at all (every
value has a default), but for a *useful* local run set:

- `SECRET_KEY` and `JWT_SECRET_KEY` — long random values
- `DEBUG=True`
- `ALLOWED_HOSTS=localhost,127.0.0.1`
- `CORS_ALLOWED_ORIGINS=http://localhost:3000`
- `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` — point at your Redis
- `AI_API_KEY` — an OpenAI (`sk-…`) **or** Anthropic (`sk-ant-…`) key; the provider
  is auto-detected. Without it, extraction jobs fail with a clear configuration error
- `GOOGLE_DRIVE_API_KEY` — only if you want the Drive import path (and Source
  Library file intake)
- `AI_PROCESSING_MODE` — `single` (default) or `multi_router` with
  `AI_ROUTER_URLS` / `AI_ROUTER_API_KEYS` / `AI_ROUTER_MODEL`; see
  `backend/docs/AI_PROCESSING_MODES.md`
- `AI_PRICING_JSON` — only to put a price on a model that has none (e.g. a router
  combo), so the usage pages show a cost
- `WATCHER_ENABLED` — leave unset unless you want the nightly watcher to contact
  official sites

**The vector store needs nothing here.** Leave `PINECONE_*` and `EMBEDDING_*` unset
and the app runs exactly as it did before that app existed. To switch it on you need
`PINECONE_API_KEY` and `PINECONE_INDEX_NAME` (create the index yourself first — this
app reads an index, it never creates one), plus `EMBEDDING_API_KEY` **only** if your
index does not embed server-side. `pip install -r requirements/base.txt` brings in
`pinecone`; without it the app still boots, and the endpoints answer `503`. Full
setup, including how to choose a dimension and metric, is in
`backend/docs/VECTOR_STORE.md`.

## Database setup

```bash
python manage.py migrate
```

This creates the schema **and** runs the data migrations: the eight CRI pillars
(without them, scoring produces zeros), the institution / programme types for
applicability, and the `BM-SCORE-1` scoring model.

**Benchmark library content (optional, staff):**

```bash
python manage.py import_source_register "path/to/Source Register.xlsx" --report report.csv
```

That is a dry run; add `--commit` to save. Then `python manage.py
ingest_source_files` fetches and verifies the source files, and `python manage.py
import_benchmark_catalogue "path/to/Source Pack.xlsx" --commit` loads the
benchmark catalogue.

Then create a login. Either a superuser:

```bash
python manage.py createsuperuser
```

or the full 11-persona demo set (institution + one user per role):

```bash
python manage.py seed_demo_users
```

## Backend startup

```bash
python manage.py runserver
```

The API is at `http://localhost:8000/api/v1/…`; Swagger at `http://localhost:8000/api/docs`.

## Redis startup

```bash
redis-server
```

Or, containerised:

```bash
docker run --rm -p 6379:6379 redis:7
```

## Celery startup

In a second terminal, from `backend/` with the same environment:

```bash
celery -A config worker -l info
```

The worker's slot count comes from `AI_PROCESSING_MODE` (2 or 8); its first log
line states the mode. **On Windows the default prefork pool does not work** — set
`CELERY_WORKER_POOL=threads` in `.env`.

**On this Windows dev machine, one command does Redis, routers and the worker:**

```bash
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
```

and switching AI mode (warm-stops the worker so running jobs finish) is:

```bash
powershell -ExecutionPolicy Bypass -File .\switch-ai-mode.ps1 -Mode multi_router
```

Check the AI setup at any time (no keys printed):

```bash
python manage.py ai_mode_status --workers
```

**Celery Beat is only needed for the daily watcher**, and only does anything with
`WATCHER_ENABLED=true`:

```bash
celery -A config beat -l info
```

If Redis or the worker is down, `POST /sprints/<id>/extraction-jobs` still
returns normally; the job row is marked `failed` with a clear `error_message`.

## Frontend startup

```bash
cd frontend
```

```bash
npm install
```

```bash
npm run dev
```

Runs on `http://localhost:3000` with `/api` proxied to `http://localhost:8000`.

## Build process

Frontend production bundle (type-check then build):

```bash
npm run build
```

Backend container image:

```bash
docker build -t ai-ready-backend ./backend
```

## Testing

```bash
python manage.py test
```

**779 tests** across 14 apps — `Ran 779 tests … OK (skipped=1)` (13 Oct 2026), the
single skip being the opt-in real-API test below. **The AI, the embedding provider,
Pinecone, OCR and the watcher's web fetches are all mocked throughout**
(`OCR_PROVIDER` defaults to `none` under `manage.py test`); no test makes a network
call by default. To additionally
run the opt-in test that makes a **real, quota-spending API call**, set
`RUN_OPENAI_INTEGRATION_TESTS=true` first.

The suite takes roughly **18 minutes** on a developer machine against SQLite.
`python manage.py test apps.benchmarks apps.assessments` (110 tests) runs in under
two minutes.

CI runs exactly this with `SECRET_KEY`, `JWT_SECRET_KEY`, `DEBUG=True`, and
`ALLOWED_HOSTS=localhost,127.0.0.1` set.

> There are **no frontend tests** — no test runner is configured in `package.json`.

## Production startup

On the deploy host (`/opt/ai-ready`), with a filled-in `.env` beside the compose file:

```bash
docker compose pull
```

```bash
docker compose up -d --remove-orphans
```

The backend container's entrypoint runs `migrate` and `collectstatic` automatically
(only for the gunicorn process — the celery and celery-beat containers skip both).
The app is served on port **80** by the frontend container. Pulling the OCR-sized
backend image needs about **6 GB free** on the VM; the CI deploy step checks this
and stops before touching the running site if there is not enough.

To create the first production account:

```bash
docker compose exec backend python manage.py createsuperuser
```

> **Do not run `seed_demo_users` in production** — it creates eleven accounts with a
> shared, publicly-known password (see §17 H2).

---

# 25. Dead / unused / scaffold code

| Item | Location | Assessment |
|---|---|---|
| `uvicorn` dependency + `config/asgi.py` | `requirements/production.txt`, `config/asgi.py` | **Unused.** Compose runs `gunicorn config.wsgi`. Django generates `asgi.py` by default, so it is scaffold rather than a mistake |
| `debug_task` | `config/celery.py` | **Unused.** Celery's standard scaffold task; harmless |
| `CELERY_RESULT_BACKEND` | `settings.py` | **Configured but deliberately inert** — `CELERY_TASK_IGNORE_RESULT = True` and nothing reads a result |
| `services/stub.py` classes | `apps/extraction/services/stub.py` | **Fallbacks.** `NullOCRProvider` is now used only when `OCR_PROVIDER=none` or PaddleOCR is not installed; the other stubs (`KnownMetadataClassifier`, `NullAuditFieldMapper`, …) are superseded by the real implementations and remain as documented fallbacks/test doubles |
| `OCRProvider` implementations | `services/base.py`, `services/paddle_ocr.py` | **`[IMPLEMENTED]`** — `PaddleOCRProvider` is the default |
| `pdfplumber` dependency | `requirements/base.txt` | **Unused since `e35fdc4`** — the reader moved to PyMuPDF; only test docstrings mention it. Safe to remove |
| Classification result | `pipeline.py` stage 1 | **Computed and discarded.** A full AI call produces `{document_type, document_title, reporting_year, institution_name, confidence, reasoning}`; only `processing_status='classified'` is saved. `Document.quality_score` is never written either |
| `Document.quality_score` | `documents/models.py` | **Never populated** by any code path |
| `page['tables']` | `pdf_reader.py` | **Always `[]` now** — the key is kept for the page-dict shape; nothing fills or reads it |
| `pytest-django` | `requirements/development.txt` | **Installed, never used** — CI runs `manage.py test` and there is no pytest config file |
| `black`, `flake8` | `requirements/development.txt` | **Installed, never run** — no CI step, no pre-commit config |
| `IsInstitutionAdmin`, `IsReadOnly` | `accounts/permissions.py` | **Defined but not referenced** by any view. (`IsSuperAdmin` and `IsConsultant` are now used, by the AI usage report.) Reasonable to keep as a toolkit |
| **Status Dashboard data** | `pages/status/StatusDashboard.tsx` | **Hand-maintained, not measured.** `PLAN_MODULES`, `AUDIT_STEPS`, `OPS_READINESS`, `ACTIVITY` and `BUILD_QUEUE` are module-level constants; the page makes **no API call**. Nothing in the backend computes a "% complete", and the file says so. The headline figures (modules live, plan coverage, modules not started) *are* derived from `PLAN_MODULES` rather than typed, so they cannot contradict the list beneath them — but the per-step percentages are engineering judgement and go stale unless someone updates them. Treat it as a status *report*, not a metric |
| `SprintMode` enum + `Sprint.mode` column | `sprints/models.py` | **No longer reachable from the UI.** The setup screen's mode picker was removed; every new sprint takes the model default. The column and enum remain, so reviving the choice is a UI change only |
| `Institution.is_active` | `institutions/models.py` | **Effectively vestigial.** DELETE is now a hard cascade, so nothing sets it `False` any more; it only lingers on rows removed before that change. Still read by the list page, which hides its Status column when no inactive row exists |
| `apps/vector_store/urls.py` | `vector_store/` | **Empty by design**, and says so — every route lives in `sprints/urls.py` with the other nested sub-resources. The module exists so the app owns a URLConf if a non-nested route is ever needed |
| **Design preview system** | `pages/previews/` (~1 000 L), `/preview/:moduleKey` | **Unreachable from the UI.** Every module it described is now a real screen, so no menu row links here. The route still resolves by URL. Keep or delete is a live decision |
| `SourceSnapshot.extraction_status` | `benchmarks/models.py` | Always `complete` — snapshots are compared, never text-extracted |
| **Vector store indexing endpoints** | `vector_store/views.py` | **Implemented and tested; no screen calls them.** Evidence search *is* now used (AI Copilot), but nothing in the SPA triggers indexing or shows its status |
| `index_sprint_vectors` | `vector_store/tasks.py` | **Not triggered by any endpoint** — `POST /vector-index` queues per-document tasks directly. It exists as the fan-out entry point for a scheduled or management-command re-index |
| `PineconeVectorStore` (manual mode) + `OpenAIEmbeddingService` | `vector_store/services/pinecone_client.py`, `services/embeddings.py` | **Implemented and unit-tested, but only one of the two modes runs in any given deployment.** Against an *integrated* index this whole path — and the embedding provider with it — is never entered. Not dead: the mode is a real deployment choice, selected by `PINECONE_EMBEDDING_MODE` |
| `dump.rdb` (root and `backend/`) | repo root, `backend/` | **Stray local Redis snapshots.** Correctly git-ignored (`dump.rdb`, `*.rdb`); safe to delete |
| `.e2e_sprint2`, `.e2e_token2` | `backend/` | **Leftover local scratch files** from manual end-to-end testing. Untracked; safe to delete |
| `celery_worker.log` | `backend/` | **Leftover local log file** |
| `db.sqlite3` (2.1 MB) | `backend/` | **Local dev database.** Correctly git-ignored |
| Trailing-slash duplicate routes | every `urls.py` | **Intentional, not dead** — documented as accommodating the frontend's inconsistent calls with `APPEND_SLASH=False` |
| `Recommendation.consultant_notes` | `recommendations/models.py` | Declared and serialised, but no generator writes it — it exists for consultant editing via `PATCH` |
| `DriveImportJob.Status.PENDING` | `documents/models.py` | Set at creation but the task immediately moves to `SCANNING`; effectively transient |

**Genuinely dead code is still small**, but it grew with the rewiring: the
prototype's demo data and banner component, and its in-browser CRI engine, are now
unreferenced, and `pdfplumber` is installed but unused. The one real inefficiency
left in the pipeline is the **discarded classification result** (table extraction
was removed with the PyMuPDF rewrite).

## Implementation-status summary

| Status | Items |
|---|---|
| **Implemented** | Auth, **user administration**, institutions, **Institution DNA**, sprints + state machine, uploads, **whole-folder Drive import with Stop**, the full 7-stage AI pipeline with **Stop / Process**, multi-provider AI, **AI processing modes + router pool**, **PyMuPDF + PaddleOCR reading**, **AI usage & cost tracking**, fact review + history, 5 gap detectors + AI conflicts, the 9-step CRI engine, baseline approval, 3 recommendation generators, versioned PDF/DOCX reports, dashboard, **Admin / Settings**, the eight rewired modules (Evidence Intelligence, CRI & Benchmark Intelligence, Transformation Plan, Goals & Tasks, AI Copilot, Reminders, Compliance Mapping, UAT Readiness), **the benchmark library (stages 1–3.6)**, **the daily watcher (off by default)**, **benchmark assessment (stage 5)**, the Pinecone vector store, OpenAPI docs, 779 tests, Docker/CI/CD |
| **UI-only / demo data** | Three Benchmark Studio tabs — **Editor, Approvals, AI candidates** — on the prototype's seed benchmarks, labelled as such (§3.12) |
| **Built, but no content yet** | The benchmark library and assessment: AI-QIF v1.0 imported (9 criteria, 36 key indicators, weights, NAAC crosswalk) with template L3/L2/L1 awaiting expert confirmation, no evidence or applicability rules, no approved requirements, no published release, all 48 watcher feeds off — **no college can be assessed until experts fill it in** (§2.4) |
| **Partial** | Non-PDF documents (accepted and stored, but unreadable and unexplained to the user); classification (called, validated, then discarded); vector store (search used by AI Copilot, indexing not triggered from any screen); Goals & Tasks / Reminders / Compliance Mapping / UAT Readiness (real data, but no task model, no sending, no criteria lists, no sign-off record) |
| **Planned / absent** | Self-registration, password reset, email/notifications, object storage, caching, monitoring, TLS, backups, frontend tests, rate limiting; on the benchmark side: **benchmark candidates from watcher changes**, **gaps / transformation plans from an assessment**, AI evidence claims, linking sprint documents to benchmark evidence |
| **Dead / stray** | `uvicorn`, `debug_task`, `IsInstitutionAdmin` / `IsReadOnly`, `pdfplumber`, `data/workspaceDemo.ts`, `DemoDataNotice`, `calculateCRI`, `dump.rdb`, `.e2e_*`, `celery_worker.log` |
---

# 26. "How the project works" — presentation script

*A 5–10 minute explanation for a manager or a new team member. Read it top to bottom.*

---

### What is this project?

This is the **AIOS AI Readiness Discovery Sprint Platform**, built by InGage
Technologies. It answers one question for a college or university: *"How ready is
this institution to adopt AI?"* — and it produces a number, an explanation, and a
plan.

The output is a **Campus Readiness Index**: a score out of 100 across eight areas,
backed by a separate confidence figure that says how much real evidence sits behind
that score.

---

### Why was it built?

Because doing this by hand takes weeks. A consultant reads hundreds of pages of
accreditation paperwork — NAAC self-study reports, AQAR returns, AICTE approvals,
faculty lists, placement reports — pulls numbers out, chases the right person on
campus to confirm each one, and writes a bespoke report.

This platform compresses that to **24 to 48 hours**, and — importantly — makes the
result *traceable*. Every number in the final report can be followed back to the
exact sentence, on the exact page, of the exact document it came from.

---

### Who uses it?

Two groups.

**InGage's own staff** — consultants and super admins — who can see across every
institution on the platform.

**Campus staff** at the institution being assessed — the Principal, the IQAC
Coordinator, the Registrar, HODs, the HR Officer, the Lab Admin, the Placement
Officer, faculty, and a read-only Trustee viewer. They can only ever see their own
institution's data; that boundary is enforced on every single request.

The reason there are so many campus roles is that **data ownership is distributed**.
The person who can confirm "how many faculty hold AI certifications" is the HR
Officer, not whoever happened to upload the file. The platform routes each fact to
the role that can actually vouch for it.

---

### What happens when a user starts?

They sign in and land on a dashboard showing every sprint they can see. Then they
walk a **ten-step wizard** — literally numbered 1 to 10 in the sidebar:

1. **Sprint Setup** — pick the institution, name the engagement.
2. **Upload Data Pack** — drag in documents, *or* paste one Google Drive folder link
   and let the system fetch everything.
3. **AI Processing Monitor** — click start, then watch a live progress bar.
4. **Extracted Facts Review** — check what the AI found.
5. **Gap Dashboard** — work through what's missing or contradictory.
6. **Owner Workspace** — each campus role confirms their own facts.
7. **Live CRI Preview** — see the score.
8. **Baseline Approval** — a consultant signs it off.
9. **Recommendations** — the system proposes actions with expected score gains.
10. **Report & Export** — download the PDF or Word document.

---

### What are the major modules?

On the backend, **fourteen Django apps**, each owning one part of the domain:
accounts (people and permissions), institutions, sprints, documents, extraction,
facts, gaps, scoring, recommendations, reports, dashboard, the optional vector
store — and the two newest, **benchmarks** (InGage's benchmark library) and
**assessments** (scoring a college against it).

On the frontend, a **React single-page app**. Every module in its navigation is
now real; the ten-step audit wizard is the deepest of them, and Benchmark Studio is
the InGage-only workspace.

The three that matter most:

- **`extraction`** — the AI pipeline. This is where the intelligence lives.
- **`scoring`** — the CRI engine. This is the product's core intellectual property.
- **`accounts`** — the permission model. This is what keeps institutions apart.

---

### How does data move through the system?

Start to finish:

A user uploads a PDF. The API validates it — size, file type, and a checksum so the
same file can't be uploaded twice — and saves it.

The user clicks "Start AI Processing." The API creates a **job record**, hands the
job to a **background queue**, and returns immediately. It does not wait — a single
document can take minutes.

A **background worker** picks the job up and runs seven stages: classify the
document, read every page, extract facts, map them, detect gaps, check for
conflicts, and finish. It updates the job's progress after each stage, so the
browser — which polls every three seconds — can show a live bar.

When the facts land in the database, campus staff confirm or correct them. **Only
confirmed or corrected facts count toward the score** — an unreviewed AI guess
scores nothing.

Then the scoring engine reads those confirmed facts, weighs them against eight
configurable pillars, subtracts points for unresolved gaps, and produces the CRI.
A consultant approves it, recommendations are generated from the same data, and a
report is rendered as PDF and Word.

---

### And the second half — the benchmark library

The audit tells a college how ready it is. The newer half tells it **against
what**. InGage staff register the official documents — UGC, AICTE, NAAC, NBA and
the rest — and the AI drafts the requirements they contain, each tied to a quoted
sentence and a page. Experts turn those into **benchmarks**, each with three levels
(Foundational, Operating, Advanced), the evidence each level needs, and the kinds of
college it applies to. Two different people must approve a **release** before it can
be used, and publishing it freezes it.

A college is then assessed against that frozen release: it uploads evidence for
each request, InGage reviews every item, and four separate scores come out —
compliance, maturity, evidence confidence and outcome — each with its reason. A
nightly watcher keeps an eye on the official sites, but it only *tells* people what
changed; it never changes a benchmark by itself.

Today the machinery is complete and tested; what it still needs is the expert
content — real levels, approved requirements and a first published release.

---

### Where is the database used?

Everywhere — it is the system's memory and its audit trail. PostgreSQL holds the
institutions, users, sprints, documents, every extracted fact, every gap, every
score, every approval, and every report.

Two things are worth pointing out.

First, **history is never overwritten.** Every time someone corrects a fact, the old
value is written to a history table first. Every scoring run is a new row, never an
update. Every report is a new version. When a baseline is approved, it is pinned to
one specific scoring run, and the database physically prevents that run from being
deleted.

Second, **the rules are in the database, not just the code.** "A student can't have
two active gaps of the same type for the same fact" isn't a check in Python that
could be raced — it's a constraint the database enforces.

---

### Where is AI used?

In exactly **four places**, and deliberately nowhere else.

1. **Classifying a document** — one call, reading the first three pages.
2. **Extracting facts** — the main event. The document is split into chunks and each
   chunk is sent with a strict schema the model must fill in.
3. **Deciding whether two facts genuinely contradict each other** — and only after
   plain code has already found that they disagree.
4. **Drafting requirements from an official source** for the benchmark library —
   and any draft whose quote is not found word for word in the source is thrown away
   before a person ever sees it.

Every one of those calls is now **metered**: its tokens and cost are recorded, so
InGage can see what each college's audit costs.

Everything else — gap detection, both scoring engines, recommendations, the
watcher — is **deterministic business logic with no AI at all**. (Reading scanned
pages uses OCR, which runs on our own server; it is pattern recognition, not a
language model.) That's a stated design principle in the code:
don't replace a rule with a model unless the task actually needs judgement.

Two more things about the AI worth telling anyone technical:

**The provider is swappable by changing one environment variable.** Paste an OpenAI
key and it uses OpenAI; paste an Anthropic key and it uses Claude. The system reads
the key's format and picks. No code change.

**The AI is not trusted.** The prompt tells it never to invent a number and always
to quote its source — but then Python re-checks every single field it returns. If it
cites a page that wasn't in the text we sent it, that fact is thrown away. If its
confidence score isn't between 0 and 1, thrown away. If it names a pillar that
doesn't exist, thrown away. One bad fact is dropped; the rest of the document
continues.

---

### Where are files stored?

On the server's own disk, in a Docker volume shared between the web process and the
background worker. Uploaded documents and generated reports live there.

Critically, **that folder is never exposed to the web.** There's a comment in the
code explaining why: these are confidential institutional documents, and serving the
folder directly would mean no authentication at all. Every download goes through an
API endpoint that checks who you are and whether you belong to that institution.

---

### What happens in the background?

The main jobs run on a queue, using Redis as the message broker and Celery as the
worker:

1. **Document extraction** — the AI pipeline. Retries three times with increasing
   delays if the AI service is rate-limited or times out.
2. **Google Drive import** — walks the folder, matches filenames against a
   checklist, downloads and imports. If one file fails, it's recorded with a reason
   and the rest continue.
3. **Report generation** — builds the eleven sections and renders PDF and Word.
   Deliberately does *not* retry, because it only reads data that's already been
   validated — a failure there is a real bug worth surfacing, not a hiccup.

Two more belong to the benchmark side: **drafting requirements** from a source,
and the **daily watcher** — the only scheduled job in the system, switched off by
default, which checks official pages once a night and records what changed for a
person to review. Everything else is triggered by a user action.

The worker's size is one setting: one AI endpoint and two documents at a time, or
four AI routers and eight at a time.

And if the queue is down entirely, the API doesn't crash — it creates the job
record, marks it failed with a clear message, and returns normally.

---

### How is the project deployed?

Push to `main` on GitHub. GitHub Actions runs the full backend test suite — 779
tests — and builds the frontend. If both pass, it builds two Docker images, pushes
them to GitHub's container registry, then SSHes into a Google Cloud VM and pulls
them.

Six containers run there: the database, Redis, the Django API, the Celery worker,
the scheduler for the nightly watcher, and nginx serving the React app and proxying
the API.

Database migrations run automatically when the web container starts — and only the
web container, so the worker can't race it.

---

### If you remember three things

1. **Every number is traceable.** Fact → snippet → page → document → upload → person
   who confirmed it. Nothing in the final report is unsourced.
2. **AI proposes; humans decide; code scores.** The AI never sets a score, never
   picks a winner in a conflict, and never has its output trusted without
   re-validation.
3. **History is append-only.** Corrections, approvals, scoring runs, and reports all
   accumulate rather than overwrite — which is what makes an approved baseline
   defensible months later.

---

# 27. Final project summary

## Architecture summary

A **containerised, monolithic Django REST API** with a **React SPA** and a **Celery
worker sharing the same image**, on **PostgreSQL** and **Redis**, behind **nginx**,
deployed to a single **GCP VM** via **GitHub Actions → GHCR → SSH**.

The backend is organised as **fourteen domain apps**, with business logic pushed into
`services/` modules that are independent of HTTP and Celery — so the CRI engine, the
gap detectors, the report builder and the vector indexer can all be unit-tested
directly. The **extraction pipeline is built on seven abstract interfaces**, making
each stage individually replaceable without touching orchestration or retry logic;
the vector store follows the same pattern with `EmbeddingService` and its two
Pinecone store classes.

`vector_store` is **strictly additive**: unconfigured, it queues nothing, writes
nothing, and changes no other subsystem's behaviour. The same is true of the
watcher (off until `WATCHER_ENABLED` and a feed is switched on) and of
`multi_router` mode (off until `AI_PROCESSING_MODE` says so).

**The product now has two halves on one platform.** The AI Readiness Audit and
every module around it read real data — the prototype screens that used to run on
hardcoded content were rewired, and the in-browser second CRI engine is no longer
used (§3.12). Beside it, `benchmarks` and `assessments` implement the manager's
benchmark database design: versioned sources, quote-checked requirements,
benchmarks with levels, evidence and applicability rules, four-eyes releases frozen
by hash, a daily watcher, and assessments scored against the frozen release. The
two halves share only the institution; they are not yet connected (§3.13).

## Main workflows

1. **Intake** — upload files or import a Google Drive folder, through one shared,
   validated ingestion path.
2. **Extraction** — a 7-stage async pipeline: classify → read → extract → map →
   detect gaps → check conflicts → prepare workspace.
3. **Review** — confirm/correct/reject facts and resolve gaps, all append-only.
4. **Scoring** — a deterministic 9-step engine over 8 configurable pillars.
5. **Approval** — baseline sign-off that locks the score against further drift.
6. **Delivery** — data-derived recommendations and a versioned PDF/DOCX report.

7. **Benchmark library** — register and verify official sources, draft and
   approve requirements, author benchmarks, publish an approved release.
8. **Benchmark assessment** — profile a college, collect and review evidence, score
   four dimensions against the frozen release, finalize.

*Optional, off the main line:* **indexing** — a processed document's text is chunked
and embedded into Pinecone, and **evidence search** (used by the AI Copilot) returns
the college's own passages for a natural-language query, each cited to a document
and page; and the **daily watcher** of official sites. Nothing in workflows 1–8
depends on either.

## Key technologies

Python 3.12 · Django 5 · DRF · SimpleJWT · Celery (+ Beat) · Redis · PostgreSQL 16 ·
OpenAI + Anthropic SDKs · Pinecone (optional) · PyMuPDF · PaddleOCR · BeautifulSoup ·
openpyxl · fpdf2 · python-docx ·
React 18 · TypeScript · Vite · Tailwind · Axios · Docker Compose · nginx · Gunicorn ·
GitHub Actions.

## Critical components

| Component | Why critical |
|---|---|
| `extraction/services/openai_fact_extractor.py` | Prompt, schema, chunking, and validation — the product's accuracy lives here |
| `scoring/services/cri_engine.py` | The scoring IP; deterministic and version-fingerprinted |
| `accounts/permissions.py` | The entire multi-tenant boundary |
| `documents/services.py` | The single ingestion path for both upload routes |
| `gaps/services.py::create_gap_if_new` | The shared idempotency primitive |
| `extraction/services/ai_service.py` | Provider swappability |
| `vector_store/services/search.py::build_filter` | The vector-side tenant boundary — the `college_id` filter no call site can omit |
| `extraction/services/router_pool.py` + `ai_service.py` | Which AI endpoint every call reaches, and the guarantee that multi_router never silently falls back |
| `benchmarks/services/releases.py` | What makes a published benchmark trustworthy: readiness, four-eyes, frozen hashed snapshots |
| `assessments/services.py::compute` | The benchmark scores a college is shown |
| `frontend/src/api/client.ts` | Auth and silent refresh in one place |
| `docker-entrypoint.sh` | Migration safety across two containers sharing an image |

## External dependencies

An AI provider (OpenAI, Anthropic, an OpenAI-compatible endpoint, or several
routers), Google Drive REST v3, Redis, PostgreSQL, GHCR, and PaddleOCR's model
download on first use — plus **Pinecone and an embedding provider, both optional**,
and **the official source websites**, contacted only by the watcher when it is
switched on. **No email, no object storage, no
payment, no analytics, no error-tracking service.**

## Current strengths

1. **Exceptional in-code documentation.** Nearly every non-obvious decision carries
   a comment explaining *why*, including the alternatives rejected. This is rare and
   genuinely valuable.
2. **A serious anti-hallucination posture.** Strict schemas, "prefer null over
   guessing", mandatory source snippets, verified page citations, and full Python
   re-validation of every AI field.
3. **AI used surgically.** Deterministic rules everywhere they suffice; AI only for
   the one judgement that needs it.
4. **Append-only audit trails throughout**, including a `PROTECT` FK that makes an
   approved baseline's scoring run undeletable.
5. **Invariants enforced in the database**, not only in services — three partial
   unique constraints on gaps, checksum uniqueness on documents, version uniqueness
   on reports.
6. **779 backend tests**, covering permissions, institution scoping, the AI paths
   (mocked), OCR (with a fake provider), the watcher (with a fake fetcher), and the
   benchmark and assessment rules, plus an opt-in real-API integration test.
7. **Graceful degradation.** Broker down, Drive misconfigured, AI unconfigured,
   Pinecone unconfigured, SDK not even installed, non-PDF document — each produces a
   clear, actionable message rather than a 500.
8. **A configurable scoring rubric** whose version fingerprint changes automatically
   when an admin retunes a weight.
9. **A clean, lean frontend** with a correctly-implemented single-flight token
   refresh.
10. **New subsystems were added without disturbing the old ones.** The vector
    store, the watcher and multi_router mode are all off by default and change
    nothing until configured.
11. **The benchmark side is built for audit:** append-only history, frozen source
    files, quote-verified requirements, a reason on every applicability decision,
    four-eyes releases with hashed snapshots, and assessments pinned to the exact
    release they used.
12. **AI cost is measured per call**, priced at the time of the call, and visible
    per sprint and per institution.
13. **Scanned documents are now readable** — OCR on the server, with no extra third
    party.

## Current weaknesses

1. **No TLS anywhere in the repo**, combined with `SECURE_SSL_REDIRECT` defaulting on.
2. **Demo credentials shipped in the production login bundle.**
3. **No rate limiting, no account lockout, no monitoring, no backups.**
4. **Insecure `SECRET_KEY` fallback** with no fail-fast.
5. **No frontend tests at all**, and no code splitting.
6. **Checklist slug divergence** between Drive import and required document types —
   a live functional defect that can block baseline approval.
7. **Old .doc / .xls and .zip are still not read** (the user is now told why).
8. **The backend image is now > 1 GB** (OCR), and OCR is CPU-bound and one page at a
   time per worker process.
9. **N+1 query patterns** in conflict checking, gap generation, and recommendations.
10. **Aggressive 3-second polling** with no backoff.
11. **No Python lockfile** — builds are not reproducible.
12. **Institutional document text is sent to a third-party AI provider** with no
    redaction or consent record.
13. **The benchmark library has no real content yet** — placeholder levels, no
    approved requirements, no published release — so the assessment cannot be used
    with a college until the experts' work is entered.
14. **The two halves are only loosely connected.** Audit documents can now be reused
    as benchmark evidence, but confirmed facts are not, and the pillar CRI and the
    benchmark scores are separate numbers with no stated relationship.
15. **All 12 live accounts still use the published demo password** (§17 H2) — the
    single most urgent item.

## Technical debt

| Item | Cost |
|---|---|
| `DRIVE_IMPORT_CHECKLIST` ↔ `DOCUMENT_TYPES` slug divergence, kept in sync by hand across two repos' worth of files | Silent functional breakage |
| Classification result computed then discarded | A wasted AI call per document |
| `page.extract_tables()` computed then discarded | Wasted parse time and memory |
| `uvicorn` + `asgi.py` shipped but unused | Confusion |
| `pytest-django`, `black`, `flake8` installed but never run | False assurance |
| Dual slash-registration on every route | Doubles the URL surface; a frontend cleanup would remove it |
| Single 300-line `settings.py` with no environment split | Harder to reason about as environments diverge |
| No lockfile for Python dependencies | Build drift |
| `IsInstitutionAdmin`/`IsReadOnly` unused | Dead API surface |
| `pdfplumber` installed but unused | Dead weight from earlier stages |

## Security risks

| Rank | Risk |
|---|---|
| 1 | Insecure `SECRET_KEY`/`JWT_SECRET_KEY` fallback → forgeable admin tokens |
| 2 | Demo emails + hardcoded `Password123!` with one-click login in the shipped bundle |
| 3 | No TLS; `SECURE_SSL_REDIRECT` on by default with nothing listening on 443 |
| 4 | No login throttling or lockout |
| 5 | Django admin publicly exposed, no IP restriction, no 2FA |
| 6 | Non-rotating 1-day refresh tokens in `localStorage` |
| 7 | API docs (`/api/docs`, `/api/schema`) unauthenticated in production |
| 8 | Drive import requires public link-sharing of institutional folders |
| 9 | No content inspection of uploads (`.zip` accepted, never processed) |
| 10 | No PII redaction before third-party AI calls |
| 11 | No encryption at rest, no backups |
| 12 | `viewer` role can read all raw facts, gaps, and unpublished reports |
| 13 | Assessment evidence and imported workbooks are not content-inspected (staff-only / human-read, which limits it) |

## Performance risks

| Rank | Risk |
|---|---|
| 1 | Uncached ~1 500-token system prompt resent up to 20× per document |
| 2 | N+1 in `conflict_checker._candidate_pairs` (one query per fact) |
| 3 | N+1 in gap generation (two queries per fact) |
| 4 | `~20 count()` queries in `GET /sprints/{id}/overview` |
| 5 | 3-second polling with no backoff or termination |
| 6 | No composite indexes on the hot filter columns (except `vector_store`'s own) |
| 7 | Worker slots (2 or 8 by mode) and per-router limits cap throughput; OCR is serialised inside each worker process |
| 8 | Gunicorn's 3 sync workers can be starved by the heavy overview endpoint |
| 9 | No caching layer, despite Redis already being deployed |
| 10 | No frontend code splitting; every page in the initial bundle |
| 11 | Unvirtualised lists; the API supports pagination the frontend never requests |

## Recommended improvements

### P0 — Critical (do before, or immediately after, any real deployment)

1. **Remove the `SECRET_KEY` fallback and fail fast.** Raise `ImproperlyConfigured`
   when `SECRET_KEY` or `JWT_SECRET_KEY` is missing and `DEBUG` is off. A refused
   boot is far better than a live app signing tokens with a published key.
2. ~~Strip the demo credentials from the production bundle.~~ **Done 15 Oct** (the
   accounts' passwords still need changing — 4a). Original text: **Strip the demo credentials from the production bundle.** Remove `SEEDED_ROLES`
   and the quick-login buttons (or gate them behind `import.meta.env.DEV`), clear the
   pre-filled email/password, and delete the `password = 'Password123!'` default in
   `AuthContext.login`. Then rotate every seeded account's password on any host where
   `seed_demo_users` has run.
3. ~~Terminate TLS.~~ **Done 13 Oct** (Let's Encrypt, auto-renewal).
4. ~~Add DRF throttling.~~ **Done 15 Oct** for login, admin login and password change.
4a. **Change the passwords of all 12 live accounts** (they use the published demo
    password) — or deactivate the demo persona accounts.
5. **Restrict `/admin/`** by IP at the nginx layer, or remove the proxy block
   entirely and reach it over an SSH tunnel.
6. **Fix the checklist slug divergence** so Drive-imported required documents
   actually satisfy the `missing_document` gap check.

### P1 — High

7. **Enable prompt caching** on the fact-extraction system prompt — the single
   largest cost reduction available, with no behaviour change.
8. **Disable `/api/docs` and `/api/schema` when `DEBUG=False`**, or put them behind
   authentication.
9. **Rotate refresh tokens** (`ROTATE_REFRESH_TOKENS=True` +
   `BLACKLIST_AFTER_ROTATION=True`).
10. **Fix the three N+1 patterns** (conflict pre-filter, gap generation,
    recommendation owner-role derivation).
11. **Add database backups** — a scheduled `pg_dump` off the VM at minimum.
12. **Add error tracking** (Sentry or equivalent) and container healthchecks for
    `backend`, `celery`, and `frontend`, plus a post-deploy verification step in the
    workflow.
13. ~~Tell the user when a file type cannot be read.~~ **Done 15 Oct** (and Word,
    Excel, CSV and images are now read).
14. **Add a stuck-job sweeper** — Beat now exists (for the watcher), so a periodic
    sweeper is one schedule entry away.
14a. ~~Commit the working tree.~~ **Done** (committed and deployed).
14b. **Enter the benchmark content and publish Release 1.0** — real levels for the
    pilot benchmarks, approved requirements, evidence and applicability rules,
    expert owners and approved composite weights. Until then no college can be
    assessed (§2.4).
14c. ~~Bring `API_CONTRACT.md` / `openapi.yaml` up to date.~~ **Done 15 Oct**
    (`openapi.yaml` regenerated; `API_CONTRACT.md` lists every newer endpoint).

### P2 — Medium

15. **Batch the conflict checker** into one multi-pair AI call.
16. **Reuse stage 2's page read in stage 1**, saving a redundant PDF parse per document.
17. **Persist the classification result** (or drop the call) — currently a full AI
    call is spent and thrown away.
18. **Add composite indexes** on `facts(sprint_id, status)`,
    `gaps(sprint_id, status, priority)`, `documents(sprint_id, status)`.
19. **Cache `GET /dashboard`, `/sprints/{id}/overview`, and `/scoring/config`** in
    the Redis that is already deployed.
20. **Add code splitting** (`React.lazy` per route) and an `ErrorBoundary`.
21. **Add polling backoff** and stop polling once every job is terminal.
22. **Pin Python dependencies** with a lockfile (pip-tools, uv, or Poetry).
23. **Run `black` and `flake8` in CI**, since they are already installed.
24. **Add frontend tests** — Vitest + Testing Library, starting with the auth
    interceptor and the wizard guards.
25. **Add role-aware frontend routing** so a `viewer` isn't shown actions that will 403.
25a. ~~Remove Benchmark Studio's seeded tabs.~~ **Done 15 Oct.**
25b. ~~Back the watcher's run lock with Redis.~~ **Done 15 Oct** (`DJANGO_CACHE_URL`).
25c. **Connect the two halves further:** audit documents are now reusable as
    evidence; still to decide how the pillar CRI and the benchmark scores relate on a
    client report.
25d. ~~Build the next benchmark stages.~~ **Done 15 Oct:** benchmark candidates
    (§3.20) and the improvement plan (§3.21).

### P3 — Low

26. Remove `uvicorn`, `asgi.py`, `debug_task`, and the unused permission classes.
27. Delete the stray `dump.rdb`, `.e2e_sprint2`, `.e2e_token2`, and `celery_worker.log`.
28. Stop extracting `page.tables` until something consumes it.
29. Consolidate the dual slash-registered routes once the frontend calls are
    normalised.
30. Split `settings.py` into `base/dev/prod` modules.
31. Set an explicit AI `temperature` for reproducible extraction.
32. Add a `README.md` at the repository root — there currently isn't one; only
    `backend/README.md` exists.
33. Consider a Google **service account** for Drive import, so institutions no longer
    have to share folders publicly.
34. Remove `pdfplumber` from `requirements/base.txt` (the demo files, the stale
    comment and the README note were cleaned up on 15 Oct).

---

*End of report.*
