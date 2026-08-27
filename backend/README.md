# AIOS Discovery Sprint — Backend

Production-ready Django REST API for the AIOS AI Readiness Discovery Sprint platform. It implements
the exact API contract already called by the existing React frontend (`frontend/src/api/client.ts`,
`AuthContext.tsx`, and `src/pages/*.tsx`) — no part of the frontend was modified to build this.

## Stack

- Python 3.12+, Django 5.x, Django REST Framework
- JWT auth via `djangorestframework-simplejwt`
- PostgreSQL-ready via `dj-database-url` (`DATABASE_URL`), SQLite fallback for local dev
- `django-cors-headers`, `Pillow`, `Celery` + `Redis`, `drf-spectacular` (OpenAPI docs)
- Every model uses a UUID primary key

## Project layout

```
backend/
├── manage.py
├── config/                  # settings, root urls, celery app, wsgi/asgi
│   └── settings.py
├── apps/
│   ├── accounts/            # custom User model, JWT login/me, permissions
│   ├── institutions/        # Institution ModelViewSet (CRUD, soft delete)
│   ├── sprints/              # Sprint ModelViewSet (CRUD, state machine, overview) + nested sub-resources
│   ├── documents/           # Document uploads: validation, checksums, secure download
│   ├── extraction/          # ExtractionJob model, Celery task, services/ pipeline (see below)
│   ├── facts/                # ExtractedFact review (confirm/correct/reject/request-evidence) + audit trail
│   ├── gaps/                 # Data-gap tracking (resolve)
│   ├── scoring/              # 8-pillar CRI rubric, PillarScore/ScoreCard, recalculation service
│   ├── recommendations/     # Gap-driven recommendation generation
│   └── reports/              # Snapshot report generation/publishing
└── requirements/{base,development,production}.txt
```

Each domain lives in its own app; `apps/sprints/urls.py` composes the nested
`/sprints/<id>/...` endpoints by importing the views from their owning app, so the URL shape the
frontend expects doesn't force all that logic into one app.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements/development.txt
cp .env.example .env                                 # edit as needed
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The API is served at `http://localhost:8000/api/v1/...`. The Vite frontend's dev proxy (or your own
reverse proxy in production) should point `/api` at this server.

### Background workers (extraction jobs)

Document extraction is asynchronous and runs on Celery, which needs Redis as both broker and result
backend (`REDIS_URL`/`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` in `.env`):

```bash
# 1. Start Redis (pick whichever you have installed)
redis-server
# or: docker run --rm -p 6379:6379 redis:7

# 2. Start a Celery worker (from backend/, same env as the Django app)
celery -A config worker -l info
# Windows: the default 'prefork' pool doesn't work there -- add a pool flag:
celery -A config worker -l info --pool=solo
```

**Celery Beat is not required** — every task in this project (`run_extraction_job`) is triggered
on-demand from an API call, not on a schedule. There are no periodic tasks, so there's nothing for
Beat to schedule; don't start it unless a recurring job is introduced later (e.g. re-queuing stuck
jobs on a timer), at which point add a `CELERY_BEAT_SCHEDULE` in `config/settings/base.py` and run
`celery -A config beat -l info` alongside the worker.

If Redis/the worker aren't running, `POST /sprints/<id>/extraction-jobs/` still creates the job
record but marks it `failed` with a clear `error_message` (`Could not reach the Celery broker: ...`)
instead of raising a 500 or hanging — the API stays usable while you bring the worker up.

## Environment variables (`.env`)

All secrets/config are read from the environment (via `python-dotenv`) — nothing is hardcoded:

| Variable | Purpose |
|---|---|
| `SECRET_KEY`, `JWT_SECRET_KEY` | Django/JWT signing secrets |
| `DEBUG`, `ALLOWED_HOSTS` | standard Django settings |
| `DATABASE_URL` | Postgres DSN; **unset → falls back to local SQLite** |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Celery/Redis |
| `CORS_ALLOWED_ORIGINS` | frontend origin(s), e.g. `http://localhost:5173` |

There's a single `config/settings.py`: with `DEBUG=False` (the default — set it explicitly per
environment via `.env`), it automatically also turns on HSTS/SSL-redirect/secure-cookie hardening
for deployment.

## API contract notes

- **No trailing slashes** (except the `/auth/*` endpoints, see below). The frontend's axios client
  calls every other endpoint without one (e.g. `/api/v1/sprints`). Django's default `APPEND_SLASH`
  redirect turns `POST` bodies into dropped `GET`s on redirect, so `APPEND_SLASH = False` is set and
  every URL is defined to match exactly.
- **Pagination is opt-in.** Institutions and sprints support real pagination
  (`config.pagination.OptionalPageNumberPagination`), but only activates when the client sends
  `?page=` or `?page_size=` — with no pagination params, the response is still a plain JSON array,
  so `sprints.map(...)` in the current frontend keeps working unmodified. Every other list endpoint
  in this project is simply unpaginated (no `pagination_class` set).
- **Nested sprint resources**: `/api/v1/sprints/<id>/{documents,upload-file,extraction-jobs,facts,
  gaps,score,recommendations,reports}` — matches `pages/*.tsx` exactly.
- **Action endpoints**: `POST /api/v1/facts/<id>/{confirm,correct}`,
  `POST /api/v1/gaps/<id>/resolve`, `PATCH /api/v1/recommendations/<id>`.

## Institution & Sprint domain (`apps/institutions`, `apps/sprints`)

Full `ModelViewSet` CRUD (`InstitutionViewSet`, `SprintViewSet`), each registered both with and
without a trailing slash for the same reason as `/auth/*` above.

| Method | Path | Notes |
|---|---|---|
| GET/POST | `/api/v1/institutions/` | filter, order, paginate (opt-in) |
| GET/PATCH/DELETE | `/api/v1/institutions/{id}/` | `DELETE` is a soft delete (`is_active=False`) |
| GET/POST | `/api/v1/sprints/` | filter, order, paginate (opt-in) |
| GET/PATCH/DELETE | `/api/v1/sprints/{id}/` | `DELETE` only allowed while `draft` or `archived` |
| GET | `/api/v1/sprints/{id}/overview/` | dashboard summary — see below |

**Institution** fields: `id`, `name`, `short_name`, `institution_type`, `university_affiliation`,
`location`, `city`, `state`, `country`, `accreditation_details`, `contact_email`, `contact_phone`,
`created_by`, `created_at`, `updated_at`, `is_active` (+ read-only `sprint_count`). Filterable by
`is_active`, `institution_type`, `state`, `country`, `created_by`; orderable by `name`, `city`,
`state`, `created_at`, `updated_at`. Create/update require `super_admin`/`consultant`/
`institution_admin`; delete requires `super_admin`/`consultant` (an institution admin can edit their
own institution but not remove it).

**Sprint** fields: `id`, `institution`, `name`, `sprint_code` (server-generated, e.g. `SPR-69F7A2C0`,
unless supplied), `mode`, `status`, `description`, `start_date`, `target_completion_date`,
`completion_percentage`, `overall_cri`, `confidence_score` (the latter two are `null` until first
scored — mirrored from `ScoreCard` by `apps/scoring/services.recalculate_sprint_score` so the
dashboard can read them without a join), `created_by`, `created_at`, `updated_at`. Filterable by
`status`, `mode`, `institution`, `created_by`; orderable by `created_at`, `updated_at`, `start_date`,
`target_completion_date`, `completion_percentage`, `overall_cri`, `name`. Modes:
`quick_cri` / `verified_cri` / `full_digital_twin`.

**Sprint status state machine** — a linear pipeline plus an "archive" escape hatch from any active
state; `archived` is terminal. Enforced in `SprintSerializer.validate()`, so an invalid `PATCH`
(e.g. `draft` → `scoring`, skipping stages) is rejected with a `400` naming the allowed next
statuses, not silently accepted or best-guessed:

```
draft → collecting → processing → reviewing → scoring → report_ready → completed
  ↓          ↓            ↓           ↓          ↓            ↓
  └──────────┴────────────┴───────────┴──────────┴────────────┴──→ archived
```

A status change also advances `completion_percentage` to that stage's real milestone
(`Sprint.STATUS_COMPLETION_MILESTONES`) *unless* the same request explicitly sets
`completion_percentage` itself. New sprints must be created in `draft` — any other initial `status`
is rejected. The other domain apps' own status-advancing logic (document upload → `collecting`,
extraction start → `processing`, extraction complete → `reviewing`, score computed → `scoring`,
report generated → `report_ready`) was updated to match this same graph, so the pipeline can't be
skipped from either the API or internal event-driven transitions.

**`GET /sprints/{id}/overview/`** returns everything the dashboard/sprint-overview screen needs in
one call, computed from real related records (not cached/fabricated): the sprint and its institution,
document counts by status, fact counts by status, gap counts (including `blocking_open`), the current
scorecard (`null` if never scored), recommendation counts + items, the latest report, and the most
recent extraction job.

**Known frontend impact**: this rebuild renames/replaces several fields the current frontend still
sends/reads on institutions and sprints — `sprint_mode`→`mode`, `academic_year` (dropped), `affiliation`
→`university_affiliation`, `accreditation_status`→`accreditation_details`, `website_url` (dropped).
Per this task's scope the frontend itself wasn't touched, so `SprintSetup.tsx`'s create calls still
succeed (the old field names are just ignored, and `mode`/`name` fall back to their model defaults)
but no longer capture that data under the old keys — the frontend needs a follow-up pass to match the
new schema and to switch its `/institutions`/`/sprints` calls to trailing-slash URLs.

## Document management (`apps/documents`)

Documents are created **exclusively** through the multipart upload endpoint — the nested
`/documents/` list is read-only, so a checksum/type/size-validated real file always backs every
`Document` record (no metadata-only placeholder rows).

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/sprints/{sprint_id}/upload-file/` | multipart; the only way to create a document |
| GET | `/api/v1/sprints/{sprint_id}/documents/` | list, scoped to the sprint's institution |
| GET/PATCH/DELETE | `/api/v1/documents/{id}/` | see permissions below |
| GET | `/api/v1/documents/{id}/download` | streams the file — see "Secure download" below |

All four registered both with and without a trailing slash, as elsewhere in this project.

**Fields**: `id`, `sprint`, `document_type`, `title`, `file`, `original_filename`, `mime_type`,
`file_size`, `checksum` (SHA-256 hex), `uploaded_by`, `owner_role`, `status`, `page_count`,
`quality_score`, `ocr_required`, `ocr_warnings`, `processing_status`, `uploaded_at`, `processed_at`,
`created_at`, `updated_at`. `mime_type`/`file_size`/`checksum` are computed from the real uploaded
bytes at upload time (never client-supplied) and are read-only afterwards, same as
`original_filename`/`uploaded_by`/`uploaded_at` — a client can edit a document's metadata
(`title`, `document_type`, `owner_role`, `status`, ...) but can't rewrite what was actually uploaded.
`page_count`/`quality_score`/`ocr_warnings`/`processing_status`/`processed_at` stay `null`/empty until
the (separate, not-yet-built) extraction pipeline populates them — per "no fake data," nothing here
is guessed.

**`document_type` is deliberately not a `choices=` enum** — it's a validated lowercase-slug
`CharField` (`apps/documents/models.py:document_type_validator`), so a brand-new document type needs
no migration or code change. `apps/documents/constants.py` lists the 12 types the current AIOS
workflow already knows (`naac_ssr`, `aqar`, `aicte_approval`, `faculty_master_list`,
`student_strength`, `placement_report`, `research_publication_report`, `lab_inventory`,
`mou_industry_engagement`, `certification_summary`, `ai_faculty_certifications`,
`ai_software_licenses`) purely to supply a human label (`document_type_label` in the serializer);
anything else gets a readable label derived from the slug instead of an error.

**Statuses** (`Document.Status`): `pending` (record exists, no file yet — not reachable through the
upload endpoint, which always attaches a real file and sets `uploaded`), `uploaded`, `processing`,
`processed`, `failed`, `rejected`. No transition graph is enforced here (unlike `Sprint.status`) —
this task didn't ask for one, and the realistic use (an admin marking a bad upload `rejected`, or the
future pipeline moving `uploaded → processing → processed`) doesn't need one yet.

**Upload validation** (`DocumentUploadSerializer`): file extension against
`ALLOWED_UPLOAD_EXTENSIONS` (`.pdf .doc .docx .xls .xlsx .csv .zip .png .jpg .jpeg`), size against
`settings.MAX_DOCUMENT_UPLOAD_SIZE` (50MB default, env-configurable), and a real SHA-256 checksum of
the file's bytes checked against every other document already uploaded **to the same sprint** —
uploading the exact same file twice to one sprint is rejected with a `400` naming the existing
document; the same file uploaded to a *different* sprint is fine. A DB-level partial unique
constraint (`sprint`, `checksum`) backs this up against a race between two simultaneous uploads.
Sprint ownership is checked the same way as every other nested sprint endpoint
(`apps/sprints/access.get_authorized_sprint` → `403` for another institution's sprint).

**Storage**: `apps/documents/utils.document_upload_path` writes every file to
`media/sprints/<sprint_id>/documents/<uuid>_<original-filename>` — `os.path.basename()` strips any
directory components a crafted filename might carry, and the uuid prefix means two uploads can never
collide. Nothing about that path is derived from user-controlled data beyond the display filename.

**Secure download**: the raw `MEDIA_URL` is **not** served at all (removed from `config/urls.py`,
even in `DEBUG`) — there is no unauthenticated way to fetch a file by guessing or reading its storage
path. `GET /documents/{id}/download` is the only way to fetch content: it re-runs the same
institution-membership check as everything else, then streams the file through Django's storage
backend via `FileResponse` with `Content-Disposition: attachment; filename="<original name>"` — the
client gets the human filename back, never the internal `<uuid>_...` storage name. The serializer
only ever exposes a `download_url` pointing at this endpoint, never a direct media path.

**Permissions**: viewing is governed by `IsInstitutionMember` like every other sprint-scoped resource.
Editing (`PATCH`) is open to the document's uploader or anyone whose role isn't `viewer`; deleting
is tighter — the uploader themselves, or `super_admin`/`consultant`/`institution_admin`/
`iqac_coordinator` (`apps/documents/views.py:CanManageDocument`) — so e.g. one `hod` can't delete
another department's upload, but an institution admin cleaning up the data pack can. Deleting a
document also deletes its file from storage (`instance.file.delete(save=False)`), so nothing is
orphaned on disk.

Uploading the first document also advances the sprint from `draft` to `collecting`, same as before.

**Known frontend impact**: `UploadDataPack.tsx`'s "Instant Demo Pack Generator" button posts JSON
metadata (`document_type`, `original_filename`, `file_uri`) with no real file directly to
`/sprints/{id}/documents` to fake a populated data pack. That path is gone — `/documents/` is
read-only now, so that button will get a `405`. This is intentional: this task's spec lists no JSON
creation endpoint, only the validated multipart upload, and "no dummy data" cuts both ways —
this backend shouldn't keep a shortcut that creates `Document` rows with no real file behind them.
The button needs a follow-up frontend pass to either drive real file picks through `upload-file` or
be removed; every other document field the frontend already reads (`id`, `original_filename`,
`document_type`, `owner_role`, `status`, `created_at`) is unchanged.

## Document extraction pipeline (`apps/extraction`)

Replaces the frontend's simulated processing screen (`AIProcessingMonitor.tsx`'s hardcoded step
list) with a real, database-backed, asynchronous Celery pipeline. One `ExtractionJob` tracks one
document through seven fixed stages — not one job per sprint — so a single flaky/corrupt file's
retries or failure never blocks or restarts the rest of the sprint's documents.

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/sprints/{sprint_id}/extraction-jobs/` | body optional; see below |
| GET | `/api/v1/sprints/{sprint_id}/extraction-jobs/` | list, scoped to the sprint's institution |
| GET | `/api/v1/extraction-jobs/{id}/` | single job's full status |

All three registered both with and without a trailing slash, as elsewhere in this project. Note the
top-level path is `/api/v1/extraction-jobs/`, not `/api/v1/extraction/` — matching the task spec.

**Creating jobs**: `POST` with no body creates one `ExtractionJob` per document in the sprint that's
`uploaded` or previously `failed` and doesn't already have an active (`pending`/`running`/`retrying`)
job — i.e. "process everything that's ready and not already in flight," which is what the frontend's
"Start AI Extraction Run" button expects. Pass `{"document_id": "<uuid>"}` to target one specific
document instead (e.g. to explicitly retry a single failed upload). The response is always an array
of the jobs created (possibly empty, if nothing was eligible) — each dispatched to
`run_extraction_job.delay(...)` immediately after being created. The sprint moves from `collecting`
to `processing` the moment jobs are created, and from `processing` to `reviewing` once every job
belonging to it has left the active states (see `_advance_sprint_if_all_jobs_done` in `tasks.py`).

**`ExtractionJob` fields**: `id`, `sprint`, `document`, `status`, `current_step`,
`progress_percentage`, `started_at`, `completed_at`, `error_message`, `retry_count`, `created_at`,
`updated_at`. `status` is `pending → running → completed`, or `running → retrying → running → ...`
before landing on `completed`/`failed`. `current_step` is one of the seven fixed stages, each with a
real progress milestone (15/30/45/60/75/90/100 — tied to genuine stage completion, not a guessed
estimate):

```
classifying_documents → reading_pages → extracting_facts → mapping_audit_fields
    → detecting_gaps → checking_conflicts → preparing_review_workspace
```

**No artificial delays** — the task does exactly the real work each stage currently has (see
"Service layer" below) and moves on; nothing sleeps to simulate processing time. A job with the
default stub services genuinely completes in milliseconds because there's genuinely nothing yet to
wait on.

**Retries**: `apps/extraction/exceptions.py` defines `RecoverableExtractionError` (transient —
retried with exponential backoff: attempt *N* waits `EXTRACTION_RETRY_BACKOFF_SECONDS * 2^(N-1)`
seconds, both env-configurable) and `PermanentExtractionError` (won't be fixed by retrying — failed
immediately). Any *other*, unrecognized exception is also failed immediately rather than retried —
retrying blindly on an error the pipeline didn't classify risks masking a real bug behind a retry
loop instead of surfacing it. After `EXTRACTION_MAX_RETRIES` (default 3) recoverable attempts, the
job stops retrying and is marked `failed` — permanent failures are never retried endlessly, and
recoverable ones aren't either past the configured bound. A failed job also marks its `Document`
`failed`, distinctly from the successful `processed` status set on completion.

**Service layer** (`apps/extraction/services/`) — the actual point of this task, per "create clean
interfaces/services rather than fake AI output":

- `base.py` — one small ABC per stage: `DocumentClassifier`, `PageReader`, `FactExtractor`,
  `AuditFieldMapper`, `GapDetector`, `ConflictChecker`. Each takes plain data in, returns plain data
  out — no dependency on Celery, DRF, or `ExtractionJob`, so a real implementation can be built and
  unit tested on its own.
- `stub.py` — the *current, active* implementation of each interface. Per "no fake data," these do
  whatever's honestly possible without AI (classification just reports what's already known from
  upload — no AI needed for that) and return **empty** results everywhere real extraction would be
  needed, rather than fabricating facts, gaps, or conflicts. A job completes today having found zero
  facts, which is the truth.
- `pipeline.py` — `ExtractionPipeline` orchestrates the seven stages against whichever services it's
  given (defaulting to the stubs), advancing `current_step`/`progress_percentage` and persisting any
  facts/gaps a real implementation returns.

Swapping in OCR, an LLM-based extractor, a document classifier, or table extraction later means
implementing the matching interface in `base.py` and passing it to
`ExtractionPipeline(fact_extractor=MyLLMExtractor(), ...)` in `tasks.py` — the retry/logging/state
machinery around it doesn't change.

**Logging**: every stage transition and task-level outcome is logged (`apps.extraction.tasks`,
`apps.extraction.services.pipeline`) via plain `logging.getLogger(__name__)` calls, e.g.
`extraction.task.running job_id=... attempt=...`, `extraction.pipeline.step job_id=... step=...`,
`extraction.task.retrying job_id=... attempt=... error=...`. `config/settings/base.py` adds a real
`LOGGING` config (console handler, INFO by default, env-overridable via `APP_LOG_LEVEL`) — without it
these calls would silently go nowhere, since Python's logging module has no visible output configured
by default.

## Extracted fact review (`apps/facts`)

`ExtractedFact` replaces the earlier `Fact` model with the fuller review-workflow schema this task
specifies, plus a `FactReviewHistory` model that makes every review action permanent and auditable.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/sprints/{sprint_id}/facts/` | list, scoped; filter/order/paginate (opt-in) |
| GET | `/api/v1/facts/{id}/` | single fact **with its full `review_history`** |
| POST | `/api/v1/facts/{id}/confirm/` | mark the current value correct |
| POST | `/api/v1/facts/{id}/correct/` | replace the value; requires `new_value` |
| POST | `/api/v1/facts/{id}/reject/` | mark the fact invalid; value untouched |
| POST | `/api/v1/facts/{id}/request-evidence/` | flag for more evidence; value untouched |

All six registered both with and without a trailing slash, as elsewhere in this project. As with
documents, the nested `/facts/` list is **read-only** — facts are only ever created by the extraction
pipeline (`apps/extraction/services/pipeline.py`), never by a generic client POST — and `/facts/{id}/`
has no generic `PATCH`: the *only* way to change a fact's value or status is through one of the four
action endpoints below, so every change is guaranteed to go through `FactReviewHistory`.

**`ExtractedFact` fields**: `id`, `sprint`, `document` (the document it was extracted from),
`field_name`, `field_key`, `value`, `normalized_value`, `data_type`, `pillar`, `owner_role`,
`source_document` (the document currently cited as evidence for the value — usually the same as
`document`, but a correction can cite different evidence without rewriting the extraction lineage),
`source_page`, `source_snippet`, `confidence_score`, `confidence_reason`, `extraction_method`,
`status`, `reviewed_by`, `reviewed_at`, `created_at`, `updated_at`. `data_type` is a closed enum
(`string`/`number`/`percentage`/`boolean`/`date`/`currency`/`list`); `pillar` reuses the same 8-pillar
rubric as scoring/sprints. Statuses: `extracted` (initial) → `confirmed` / `corrected` / `rejected` /
`evidence_requested`.

**Audit trail**: every action creates a `FactReviewHistory` row — `fact`, `action`, `original_value`
(the fact's value *immediately before* this action), `new_value` (only set for `correct`; `null` for
the other three, since they don't change the value), `user`, `reason`, `created_at`. Corrections never
overwrite anything destructively: `ExtractedFact.value` always holds the *current* value, but each
correction's `original_value` captures what it was replacing, so the full chain of history rows —
from the very first correction's `original_value` onward — reconstructs everything a fact has ever
been, all the way back to what was originally extracted. Nothing is ever discarded. Both `value` and
`original_value` are nullable: a correction can legitimately set a fact to "unknown" (JSON `null`,
distinct from "no value provided" — `POST .../correct/` with no `new_value`/`corrected_value` key at
all is still rejected with a `400`).

**Filtering**: `pillar`, `status`, `owner_role`, `document` (by id), and confidence — `confidence`
(exact), `confidence_min` / `confidence_max` (range, the practically useful form for a continuous
score). Orderable by `created_at`, `updated_at`, `confidence_score`, `reviewed_at`, `field_key`.
Pagination is opt-in, same as institutions/sprints/documents.

**Permissions**: reading is open to any authenticated member of the sprint's institution
(`IsInstitutionMember`); all four review actions require `CanReviewFacts` — every role except
`viewer` (the platform's one deliberately read-only persona) — combined with the same institution
check, so a `403` covers both "you can't review anything" (viewer) and "you can't touch this sprint"
(wrong institution).

**Known frontend impact**: `FactsReview.tsx`'s "Seed Sample Facts" button posts directly to
`/sprints/{id}/facts` with no real extraction behind it — gone for the same reason as documents'
equivalent button (`/facts/` is read-only now; no dummy rows). Its confirm/correct calls, however,
keep working unmodified: `POST /facts/{id}/confirm` with `{comment}` and
`POST /facts/{id}/correct` with `{corrected_value, comment}` are still accepted as aliases for
`reason` and `new_value` respectively (see `apps/facts/serializers.py:_ReasonSerializer`) — this one
was cheap to keep compatible, unlike the broader institution/sprint field renames earlier.

## Gap management (`apps/gaps`)

`GapItem` replaces the earlier `Gap` model. Gaps are never created by a client — they're raised
automatically by `apps/gaps/services.py` and then worked through the three action endpoints below.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/sprints/{sprint_id}/gaps/` | list, scoped; filter/order/paginate (opt-in) |
| GET | `/api/v1/gaps/{id}/` | single gap |
| POST | `/api/v1/gaps/{id}/resolve/` | mark resolved; accepts `resolution` (or legacy `value`) |
| POST | `/api/v1/gaps/{id}/mark-unavailable/` | mark the underlying data as unobtainable |
| POST | `/api/v1/gaps/{id}/skip/` | mark not relevant to this sprint |

All five registered both with and without a trailing slash, as elsewhere in this project. As with
facts and documents, the nested `/gaps/` list is **read-only** — there is no generic `POST`/`PATCH`;
a gap's status only ever changes through one of the three action endpoints, each of which stamps
`resolved_by`/`resolved_at` for a complete audit trail.

**`GapItem` fields**: `id`, `sprint`, `gap_type`, `title`, `description`, `pillar`, `priority`,
`source_fact` (nullable FK to `ExtractedFact`), `related_document` (nullable FK to `Document`),
`status`, `resolution`, `resolved_by`, `resolved_at`, `created_at`, `updated_at`. Gap types:
`missing_document`, `unconfirmed_fact`, `conflict`, `stale_data`, `low_confidence`. Priorities:
`blocking`, `high`, `medium`, `optional`. Statuses: `open` (initial) → `in_progress` / `resolved` /
`unavailable` / `skipped`. `source_fact`/`related_document` use `SET_NULL`, not `CASCADE`: a gap's
resolution history is worth keeping even if the fact or document it pointed at is later deleted.

There's no stored `owner_role` field — the API derives it per-gap from whichever of `source_fact` /
`related_document` is set (`GapItemSerializer.get_owner_role`), so it's never out of sync with the
fact/document it's actually describing. There's likewise no stored `score_impact`: each priority has
a fixed penalty in `apps/gaps/constants.py:GAP_PRIORITY_SCORE_PENALTY` (`blocking`=8, `high`=5,
`medium`=3, `optional`=1), used by both CRI scoring and recommendation generation (see "Business
logic" below) — one rubric, not a value that could drift from its priority.

**Automatic generation** (`apps/gaps/services.py:generate_gaps_for_sprint`): runs five detectors over
a sprint's real fact/document records — never fabricated content:

- **Missing document** — one of `apps/documents/constants.py:REQUIRED_DOCUMENT_TYPES` (the core
  verified-CRI checklist: SSR, AQAR, AICTE approval, faculty master list, student strength, placement
  report) hasn't been uploaded yet. Always `blocking`.
- **Low confidence** — an `extracted`-status fact below `GAP_LOW_CONFIDENCE_THRESHOLD` (default 0.7).
  `high` priority below `GAP_VERY_LOW_CONFIDENCE_THRESHOLD` (default 0.5), `medium` otherwise.
- **Unconfirmed fact** — an `extracted`-status fact at or above the low-confidence threshold (i.e. the
  extraction itself looks trustworthy, but no human has signed off on it yet). `medium` priority.
- **Conflict** — two or more non-`rejected` facts in the sprint share a `field_key` but disagree on
  `value`. `high` priority.
- **Stale data** — a document uploaded more than `GAP_STALE_DATA_DAYS` (default 365) days ago.
  `medium` priority.

All three thresholds are environment-configurable (`GAP_LOW_CONFIDENCE_THRESHOLD`,
`GAP_VERY_LOW_CONFIDENCE_THRESHOLD`, `GAP_STALE_DATA_DAYS` in `.env`). Generation is triggered
automatically at the point a sprint's extraction work finishes and it moves `processing → reviewing`
(`apps/extraction/tasks.py:_advance_sprint_if_all_jobs_done`) — there's no separate "generate gaps"
endpoint, consistent with gaps being populated by the pipeline rather than by client action.

**No duplicate gaps**, enforced at the database level with three partial unique constraints (active
statuses only — `open`/`in_progress` — so a resolved gap doesn't block the same issue from being
re-raised if it recurs):

- `(gap_type, source_fact)` — one active gap per fact per type (covers `low_confidence` and
  `unconfirmed_fact`).
- `(gap_type, related_document)` — one active gap per document per type (covers `stale_data`).
- `(sprint, gap_type, title)` — for gaps with no natural fact/document anchor (covers
  `missing_document`, and `conflict`, which is deduped by title rather than by its representative
  fact, since which fact is "most representative" of a conflict can change as more conflicting values
  arrive — the field's identity, reflected in the title, is the stable key).

The generation service is also idempotent above and beyond the DB constraint: it checks for an
existing active gap before attempting an insert, so re-running it after new documents/facts arrive
only creates gaps for genuinely new issues.

**Filtering**: `gap_type`, `status`, `priority`, `pillar`. Orderable by `created_at`, `updated_at`,
`priority`, `resolved_at`. Pagination is opt-in, same as the other list endpoints.

**Permissions**: reading is open to any authenticated member of the sprint's institution
(`IsInstitutionMember`); all three actions require `CanResolveGaps` — every role except `viewer` —
combined with the same institution check.

**Known frontend impact**: `GapDashboard.tsx`'s "Seed Sample Gaps" button posts directly to
`/sprints/{id}/gaps` with no real detection behind it — gone for the same reason as the documents/
facts equivalents (`/gaps/` is read-only now; gaps come from real detection, not seeding). Its
resolve/mark-unavailable/skip calls keep working unmodified: they send `{value}` rather than
`{resolution}`, and `value` is accepted as an alias (see `apps/gaps/serializers.py:_ResolutionSerializer`).

## Authentication & authorization

### User model (`apps/accounts`)

A custom, email-authenticated `User` (`AUTH_USER_MODEL = 'accounts.User'`, in place since the first
migration — nothing bolted on afterwards). Fields: `id` (UUID), `email` (login identifier, unique),
`username`, `first_name`, `last_name`, `phone`, `role`, `institution` (nullable FK), `department_name`,
`is_active`, `is_staff`, `is_superuser`, `date_joined`, `updated_at`.

Roles (`User.Role`): `super_admin`, `consultant`, `institution_admin`, `iqac_coordinator`, `registrar`,
`hod`, `hr_officer`, `lab_admin`, `placement_officer`, `faculty`, `viewer`. `super_admin` and
`consultant` are **cross-institution** — every other role is confined to the institution on their
profile (`user.institution`).

### Endpoints (`apps/accounts`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/v1/auth/login/` | none | `{ email, password }` → `{ access_token, refresh_token, user }` |
| POST | `/api/v1/auth/refresh/` | none | `{ refresh }` → `{ access }` (standard SimpleJWT) |
| POST | `/api/v1/auth/logout/` | Bearer | `{ refresh }` → blacklists that refresh token (205) |
| GET | `/api/v1/auth/me/` | Bearer | current user profile |
| POST | `/api/v1/auth/change-password/` | Bearer | `{ old_password, new_password }`, validated against `AUTH_PASSWORD_VALIDATORS` |

Every endpoint above is also registered **without** the trailing slash (`/auth/login`, `/auth/me`, ...)
because the existing frontend's `AuthContext.tsx`/`api/client.ts` already call it that way and
`APPEND_SLASH` is off project-wide — both forms hit the same view.

### JWTs

Access and refresh tokens carry `role`, `institution_id`, and `email` claims (set on the refresh token
in `apps/accounts/tokens.py`; SimpleJWT copies them onto every access token derived from it, including
ones minted by `/auth/refresh/`) so the frontend or any downstream service can make authorization
decisions from the token alone. Nothing sensitive (password hash, phone, etc.) is included. Logout
uses `rest_framework_simplejwt.token_blacklist` — a blacklisted refresh token, and any access token
later derived from it, is rejected.

### Permission classes (`apps/accounts/permissions.py`)

| Class | Grants |
|---|---|
| `IsSuperAdmin` / `IsConsultant` / `IsInstitutionAdmin` | request user has exactly that role |
| `IsReadOnly` | safe methods (`GET`/`HEAD`/`OPTIONS`) only |
| `IsInstitutionMember` | object-level: user belongs to the object's institution, or holds a cross-institution role |
| `CanManageSprint` | anyone can read; only `super_admin`/`consultant`/`institution_admin` can create/edit sprints |
| `CanReviewFacts` / `CanResolveGaps` | anyone can read; every role except `viewer` can confirm/correct facts or resolve gaps |
| `CanManageRecommendations` | anyone can read; only `super_admin`/`consultant`/`institution_admin`/`iqac_coordinator` can generate/edit recommendations |

`get_accessible_institution_ids(user)` / `user_can_access_institution(user, institution_id)` /
`require_institution_access(user, obj)` are the underlying helpers — used to scope list-endpoint
querysets (institutions, sprints) and to guard the nested `/sprints/<id>/...` sub-resource endpoints,
which look up their sprint from a URL kwarg rather than through DRF's generic object lookup and so
apply the same check manually via `apps/sprints/access.get_authorized_sprint`. A request for
institution/sprint data outside a user's own institution gets a `403`, not a silent redirect or an
information-leaking `404`.

### Demo users (development only)

```bash
python manage.py seed_demo_users
```

Creates one user per role against a demo institution ("M. Kumarasamy College of Engineering"),
reusing the frontend's existing quick-login emails (`src/pages/Login.tsx`) where a matching role
exists. **The command refuses to run unless `DEBUG=True`** (pass `--force` to override, which you
should never need outside a throwaway environment) — this is what keeps these accounts out of
production, not the password's obscurity.

> **Development credentials only — do not use in production.**
> Every seeded account shares the password `Password123!` (override via the `DEMO_USER_PASSWORD` env
> var or `--password`). Rotate or delete these accounts before any non-local deployment.

| Email | Role |
|---|---|
| `superadmin@ingage.ai` | `super_admin` |
| `consultant@ingage.ai` | `consultant` |
| `principal@mkce.ac.in` | `institution_admin` |
| `iqac@mkce.ac.in` | `iqac_coordinator` |
| `registrar@mkce.ac.in` | `registrar` |
| `hod_cs@mkce.ac.in` | `hod` |
| `hr@mkce.ac.in` | `hr_officer` |
| `labadmin@mkce.ac.in` | `lab_admin` |
| `placement@mkce.ac.in` | `placement_officer` |
| `faculty@mkce.ac.in` | `faculty` |
| `viewer@mkce.ac.in` | `viewer` |

## Tests

```bash
python manage.py test
```

- `apps/accounts/tests.py` — auth flow: login success, invalid password, inactive user, JWT refresh
  (success and garbage-token rejection), `/auth/me`, logout/blacklisting, change-password (success,
  wrong old password, weak new password).
- `apps/institutions/tests.py` — institution-scoped visibility, role-gated create/update, soft-delete
  role gating and behavior, filtering/ordering/opt-in pagination.
- `apps/sprints/tests.py` — role permissions (`CanManageSprint`), institution-scoped access to sprints
  and their nested resources (403, not 404, confirmed for both the ModelViewSet detail routes and the
  nested sub-resource routes), creation defaults (`draft` status, generated `sprint_code`, date-order
  validation), the full status state machine (valid/invalid transitions, archive-from-any-state,
  terminal `archived`, milestone auto-advance and explicit override), the delete guard, opt-in
  pagination, filtering (`status`/`mode`/`institution`/`created_by`), ordering, and the `overview`
  endpoint.
- `apps/documents/tests.py` — valid upload (real metadata populated, sprint advances to `collecting`,
  works without a trailing slash), invalid file (disallowed extension, oversized file, nothing
  persisted on rejection), duplicate checksum (rejected within a sprint, allowed across sprints),
  unauthorized upload (unauthenticated `401`, wrong institution `403`), document listing (scoped,
  read-only), deletion (owner allowed, unrelated non-manager forbidden, manager role allowed, file
  actually removed from storage), and permissions (retrieve/PATCH/DELETE role and ownership gating,
  future/unknown `document_type` accepted, invalid slug format rejected, file-integrity fields
  immutable via PATCH, secure download auth/ownership checks, raw media path confirmed unreachable).
- `apps/extraction/tests.py` — job creation (one job per eligible document, no duplicates for
  documents already in flight, explicit `document_id` targeting, 404 for a document outside the
  sprint), unauthorized job access (create/list/detail all 401 unauthenticated, 403 cross-institution),
  a full successful run through all seven steps with the real default (stub) pipeline (state
  transitions, `Document` marked `processed`, sprint `collecting → processing → reviewing`, and a
  check that **no** facts/gaps were fabricated), failed jobs (permanent and unrecognized errors both
  fail in one attempt, no retry burned), and the retry/backoff/exhaustion decision logic itself
  (unit-tested directly against `_handle_recoverable` — see the note in that test file on why, given
  Celery's eager test mode runs a task exactly once per call rather than looping through retries).
- `apps/facts/tests.py` — listing (scoped, read-only, opt-in pagination), filtering (`pillar`,
  `status`, `owner_role`, `document`, `confidence_min`/`confidence_max`), ordering, detail (includes
  `review_history`, no generic `PATCH`), and all four review actions: confirm, correct (value update,
  legacy `corrected_value`/`comment` aliases, explicit-`null`-is-a-real-value vs.
  no-value-provided-is-a-400, and the audit trail — original value never destroyed across single and
  multi-round corrections), reject, and request-evidence — each checked for the correct status/history
  side effects and the full permission matrix (owner-agnostic here: any non-`viewer` role in the same
  institution, `403` for `viewer` and for a different institution, `401` unauthenticated).
- `apps/gaps/tests.py` — DB-level duplicate prevention for all three partial unique constraints
  (fact-scoped, document-scoped, title-scoped) plus confirmation that a resolved gap doesn't block a
  fresh one of the same kind; each of the five auto-generation detectors (missing document, low
  confidence vs. unconfirmed at the threshold boundary, conflicting values, stale data) checked both
  for correctly firing and for *not* firing when the condition isn't met, plus an idempotency check
  that re-running generation creates no duplicates; listing (scoped, read-only, opt-in pagination,
  filter by `gap_type`/`status`/`priority`/`pillar`, derived `owner_role` from both `source_fact` and
  `related_document`); and all three actions (resolve, mark-unavailable, skip) checked for
  status/audit-field side effects, the legacy `value` field alias, and the full permission matrix.

196 tests, all passing.

## Business logic — what's real vs. what's an integration point

Per the "no fake data" requirement, everything the API returns is either a real database record a
client wrote, or a value computed deterministically from real records already in the database:

- **CRI scoring** (`apps/scoring/services.py`): each of the 8 pillars is scored from the average
  confidence of that pillar's confirmed/corrected `ExtractedFact`s, less the fixed per-priority
  penalty (`apps/gaps/constants.py:GAP_PRIORITY_SCORE_PENALTY`) of its open `GapItem`s, weighted by
  the fixed CRI rubric in `apps/scoring/constants.py`. With no facts/gaps tagged to a pillar, that
  pillar's score is honestly `0`, not a placeholder number.
- **Gap detection** (`apps/gaps/services.py`): five deterministic detectors (missing required
  document, low-confidence fact, unconfirmed fact, conflicting fact values, stale document) run
  against a sprint's real fact/document records — see "Gap management" above for the full design.
- **Recommendations** (`apps/recommendations/services.py`): one recommendation is generated per open,
  not-yet-covered `GapItem`, using that gap's own fields (title, description, priority, and its
  derived owner role) — not invented content.
- **Reports** (`apps/reports/services.py`): a report is a JSON snapshot of the sprint's real
  institution/scorecard/gaps/recommendations at generation time.
- **Extraction jobs** (`apps/extraction/services/`): the pipeline does the real, non-AI part of
  processing a document (stage/progress bookkeeping, marking it `processed`) and calls out to real,
  swappable service interfaces for the AI-dependent stages (classification, page reading, fact
  extraction, field mapping, gap detection, conflict checking). The active default implementation of
  each returns honest empty results rather than invented ones — see "Document extraction pipeline"
  above for the full design and how a real OCR/LLM backend plugs in later.

## Verified

```bash
python manage.py check     # System check identified no issues
python manage.py migrate   # applies cleanly to a fresh SQLite database
python manage.py test      # 196 tests, OK
```

The full sprint lifecycle (login → institution → sprint → document upload → extraction job → fact
confirm/correct → gap resolve → score recalculation → recommendation generation → report publish) was
smoke-tested end-to-end against a running server and matches the frontend's expected response shapes
exactly, as was the full auth/RBAC flow (login, refresh, logout/blacklist, change-password, role
rejection, cross-institution rejection), the institution/sprint domain (both slash forms, opt-in
pagination shape, filtering, the state machine's accept/reject paths, the `overview` endpoint, and
403-not-404 cross-institution access), document management (real file upload with a genuine PDF,
duplicate-checksum rejection, invalid-extension rejection, secure download returning byte-identical
content with the original filename, the raw media path confirmed unreachable, and the full
owner/manager/viewer PATCH-DELETE permission matrix), the extraction pipeline (job creation, listing,
and detail endpoints against a live server, both slash forms), and fact review (confirm/correct/
reject/request-evidence against a manually-seeded fact, the legacy `corrected_value`/`comment` field
aliases, the original value surviving a correction in `review_history`, viewer-role and
cross-institution rejection, and pillar/confidence filtering) — all using the seeded demo personas.

Three real bugs were found and fixed via this smoke testing (not just the automated suite) during the
fact review work: a `NOT NULL` `IntegrityError` when a correction's new value was legitimately `null`
(fixed by making `ExtractedFact.value` and `FactReviewHistory.original_value` nullable at the DB
level, not just accepted by the serializer), and two test-only false failures caused by Django REST
Framework's default test-client encoding (`multipart`) not JSON-parsing bare unquoted strings sent
through a `JSONField` — fixed by using `format='json'` explicitly in those tests, not by changing any
application code (the real frontend always sends `Content-Type: application/json`, so this only ever
affected the test client).

This last round of smoke testing is also how the `CELERY_TASK_IGNORE_RESULT` setting (see "Document
extraction pipeline" above) got found and fixed: without it, triggering extraction against a
Django dev server with no Redis running took **100+ seconds per request** (Celery's redis result
backend retrying its own reconnect ~20 times) before the already-correct broker-unreachable handling
ever got a chance to run — not a hang exactly, but a bad enough one to be worth catching before
calling it done. With it, the same request now fails in ~4s, the cost of one real, un-retried
connection attempt.
