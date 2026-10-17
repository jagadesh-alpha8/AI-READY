# AIOS Backend API Contract

Audited against the existing React/TypeScript frontend (`frontend/src`) on 2026-08-18.
Every endpoint below is implemented in `backend/apps/*` and covered by that app's `tests.py`.

## Conventions

- **Base URL**: `/api/v1` (the frontend's axios client, `frontend/src/api/client.ts`, is configured with this exact `baseURL`).
- **Trailing slashes**: `APPEND_SLASH = False` project-wide. Every resource collection/action below is registered **both** with and without a trailing slash (e.g. `/sprints` and `/sprints/` both work), because the frontend's existing calls are inconsistent about it. Path examples below omit the trailing slash for brevity; both forms are always valid.
- **IDs**: every resource's `id` is a UUID4, rendered as a lowercase hyphenated string (`"3fc78b7b-77d0-4b50-835f-4fd18efb3a37"`). No integer/auto-increment IDs are exposed anywhere.
- **Auth**: JWT via `djangorestframework-simplejwt`. Send `Authorization: Bearer <access_token>` (the frontend's request interceptor does this automatically from `localStorage['aios_token']`). Access tokens are short-lived; `POST /auth/refresh` exchanges a refresh token for a new access token (the frontend does not currently use this — see **Known Gaps**).
- **Pagination**: opt-in on every list endpoint (`config.pagination.OptionalPageNumberPagination`). Without `?page` or `?page_size`, the full result set is returned as a plain JSON array (what the existing frontend's `.map()`-based rendering expects). Adding `?page=N` and/or `?page_size=N` switches the response to `{"count": int, "next": str|null, "previous": str|null, "results": [...]}`. `page_size` defaults to 20, max 100.
- **Errors**:
  - `400 Bad Request` — serializer validation failure: `{"field_name": ["error message", ...], ...}`.
  - `401 Unauthorized` — missing/invalid/expired JWT: `{"detail": "..."}`.
  - `403 Forbidden` — authenticated but not permitted (wrong role, or wrong institution): `{"detail": "..."}`.
  - `404 Not Found` — object doesn't exist, or (deliberately) an object outside the caller's institution scope where returning 403 would leak existence: `{"detail": "Not found."}`.
  - `405 Method Not Allowed` — verb not implemented on that path (e.g. `POST` on a read-only list endpoint).
- **Role permissions**: `apps.accounts.permissions` defines the reusable gates referenced below (`CanManageSprint`, `CanManageRecommendations`, `CanEditRecommendation`, `CanReviewFacts`, `CanResolveGaps`, `IsInstitutionMember`, etc.). Unless noted otherwise, **every** endpoint requires authentication; GET is open to any authenticated user who can see the resource, writes are role-gated as documented per endpoint.
- **Institution scoping**: `super_admin` and `consultant` are cross-institution roles (see everything). Every other role only sees data belonging to the institution on their own user profile; a request against another institution's resource returns `403`.

---

## 1. Authentication (`/api/v1/auth`)

### `POST /auth/login`
- **Auth**: none (`AllowAny`).
- **Request body**: `{"email": str, "password": str}`
- **Response `200`**: `{"access_token": str, "refresh_token": str, "user": User}` — see **User object** below.
- **Errors**: `400` invalid credentials or inactive account (`{"non_field_errors": ["Invalid login credentials"]}` or `{"non_field_errors": ["This account has been disabled"]}`).

### `POST /auth/refresh`
- Standard `rest_framework_simplejwt` `TokenRefreshView`.
- **Request body**: `{"refresh": str}` → **Response `200`**: `{"access": str}`.

### `POST /auth/logout`
- **Auth**: required.
- **Request body**: `{"refresh": str}` — blacklists that refresh token.
- **Response**: `205 Reset Content`, empty body.
- **Errors**: `400` if the refresh token is invalid/already blacklisted.

### `GET /auth/me`
- **Auth**: required.
- **Response `200`**: the caller's own `User` object.

### `POST /auth/change-password`
- **Auth**: required.
- **Request body**: `{"old_password": str, "new_password": str}`
- **Response `200`**: `{"detail": "Password updated successfully."}`
- **Errors**: `400` wrong old password, or new password fails Django's validators.

### `POST /auth/password-reset`
- **Auth**: none. Rate-limited per client address (10/hour) and per email (3/hour); `429` beyond that.
- **Request body**: `{"email": str}`
- **Response `200`**: the same `{"detail": ...}` whether or not the email has an account. An active account gets an
  email with `{FRONTEND_BASE_URL}/reset-password?uid=...&token=...`; the link works once and expires after
  `PASSWORD_RESET_TIMEOUT` (1 hour).
- **Errors**: `400` email missing.

### `POST /auth/password-reset/confirm`
- **Auth**: none. Rate-limited per client address.
- **Request body**: `{"uid": str, "token": str, "new_password": str}`
- **Response `200`**: password changed; every refresh token of the user is blacklisted (signed out everywhere).
- **Errors**: `400` `token` (invalid, used or expired link) or `new_password` (fails Django's validators).

#### User object
```json
{
  "id": "uuid", "institution_id": "uuid|null", "username": str,
  "name": str,               // computed: first_name + last_name (get_full_name())
  "first_name": str, "last_name": str, "email": str, "phone": str,
  "role": "super_admin|consultant|institution_admin|iqac_coordinator|registrar|hod|hr_officer|lab_admin|placement_officer|faculty|viewer",
  "department_name": str, "is_active": bool, "is_staff": bool,
  "date_joined": "iso8601", "updated_at": "iso8601"
}
```
`name` and `institution_id` are **frontend-compatible aliases** — `AuthContext.tsx`'s `User` TypeScript type reads `user.name` and `user.institution_id` directly, not `first_name`/`last_name`/`institution`.

---

## 2. Institutions (`/api/v1/institutions`)

Standard `ModelViewSet` (list/create/retrieve/update/partial_update/destroy).

| Method | Path | Permission (write) | Notes |
|---|---|---|---|
| GET | `/institutions` | any authenticated | scoped to accessible institutions |
| POST | `/institutions` | super_admin, consultant, institution_admin | |
| GET | `/institutions/{id}` | any authenticated | `IsInstitutionMember` → 403 if out of scope |
| PATCH/PUT | `/institutions/{id}` | super_admin, consultant, institution_admin | |
| DELETE | `/institutions/{id}` | super_admin, consultant | **soft delete** (`is_active=False`), row is kept |

**Filters** (query params, list only): `is_active`, `institution_type` (+`_icontains`), `state` (+`_icontains`), `country` (+`_icontains`), `created_by`. **Ordering**: `?ordering=name|city|state|created_at|updated_at` (prefix `-` for descending).

**Response body** (Institution object):
```json
{
  "id": "uuid", "name": str, "short_name": str, "institution_type": str,
  "university_affiliation": str, "affiliation": str,      // affiliation = alias, same value
  "website_url": str, "location": str, "city": str, "state": str, "country": str,
  "accreditation_details": str, "accreditation_status": str,  // accreditation_status = alias, same value
  "contact_email": str, "contact_phone": str, "is_active": bool,
  "sprint_count": int,             // computed
  "created_by": "uuid|null", "created_at": "iso8601", "updated_at": "iso8601"
}
```

**Request body** (create/update) accepts either name for the two aliased fields (`affiliation` **or** `university_affiliation`; `accreditation_status` **or** `accreditation_details`) — `SprintSetup.tsx` posts the alias names. `website_url`, `name`, `institution_type`, `city`, `state` are also accepted as sent by that same form.

---

## 3. Sprints (`/api/v1/sprints`)

Standard `ModelViewSet`, plus a custom `overview` action.

| Method | Path | Permission (write) | Notes |
|---|---|---|---|
| GET | `/sprints` | any authenticated | scoped to accessible institutions |
| POST | `/sprints` | super_admin, consultant, institution_admin | new sprint always starts in `draft` |
| GET | `/sprints/{id}` | any authenticated | 403 if out of scope |
| PATCH/PUT | `/sprints/{id}` | super_admin, consultant, institution_admin | status transitions are validated (see below) |
| DELETE | `/sprints/{id}` | super_admin, consultant, institution_admin | only if status is `draft` or `archived` |
| GET | `/sprints/{id}/overview` | any authenticated | aggregate dashboard payload, see below |

**Filters**: `status`, `mode`, `institution` (UUID), `created_by` (UUID). **Ordering**: `created_at, updated_at, start_date, target_completion_date, completion_percentage, overall_cri, name`.

**Status pipeline** (`Sprint.ALLOWED_TRANSITIONS`): `draft → collecting → processing → reviewing → scoring → report_ready → completed`, with `archived` reachable from any non-terminal state. A `PATCH` that requests an illegal transition gets `400` listing the allowed next statuses.

**Response body** (Sprint object):
```json
{
  "id": "uuid", "institution_id": "uuid", "name": str, "sprint_code": str,  // auto-generated, e.g. "SPR-3FC78B7B"
  "mode": "quick_cri|verified_cri|full_digital_twin", "sprint_mode": str,   // sprint_mode = alias, same value
  "status": "draft|collecting|processing|reviewing|scoring|report_ready|completed|archived",
  "academic_year": str, "description": str,
  "start_date": "date|null", "target_completion_date": "date|null",
  "completion_percentage": int,        // 0-100, auto-set to a pipeline milestone on status change unless sent explicitly
  "overall_cri": float|null,           // null until first scored
  "confidence_score": float|null,      // null until first scored
  "created_by": "uuid|null", "created_at": "iso8601", "updated_at": "iso8601"
}
```

**Request body** (create) accepts `institution_id` (required), and either `mode` **or** `sprint_mode` (`SprintSetup.tsx` posts `sprint_mode`), plus `academic_year`, `name`, `description`, `start_date`, `target_completion_date`.

### `GET /sprints/{id}/overview`
Everything a sprint-detail dashboard screen needs in one call — avoids the frontend having to fan out to every sub-resource endpoint separately:
```json
{
  "sprint": Sprint, "institution": Institution,
  "documents": {"total": int, "pending": int, "uploaded": int, "processing": int, "processed": int, "failed": int, "rejected": int, "items": [Document, ...]},
  "facts": {"total": int, "extracted": int, "confirmed": int, "corrected": int, "rejected": int, "evidence_requested": int},
  "gaps": {"total": int, "open": int, "in_progress": int, "resolved": int, "blocking_open": int},
  "scorecard": SprintScore|null,       // null if never scored (bootstrap=False here, unlike GET .../score/)
  "recommendations": {"total": int, "accepted": int, "draft": int, "items": [Recommendation, ...]},
  "reports": {"total": int, "latest": Report|null},
  "latest_extraction_job": ExtractionJob|null
}
```

---

## 4. Documents (`/api/v1/sprints/{sprint_id}/documents`, `/api/v1/documents`)

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/sprints/{sprint_id}/documents` | any authenticated, institution-scoped | **read-only** — documents are only ever created via upload |
| POST | `/sprints/{sprint_id}/upload-file` | any authenticated, institution-scoped | multipart file upload |
| GET | `/documents/{id}` | any authenticated | 403 if out of scope |
| PATCH/PUT | `/documents/{id}` | uploader, or non-viewer role | |
| DELETE | `/documents/{id}` | uploader, or super_admin/consultant/institution_admin/iqac_coordinator | deletes the stored file too |
| GET | `/documents/{id}/download` | any authenticated, institution-scoped | streams the file (never a raw media URL) |
| POST | `/documents/{id}/confirm-category` | any role but viewer, institution-scoped | a person settles the AI category (below) |

### `POST /sprints/{sprint_id}/upload-file`
- **Content-Type**: `multipart/form-data`.
- **Request body**: `file` (required), `document_type` (required, lowercase snake_case, e.g. `naac_ssr`), `title` (optional), `owner_role` (optional). Matches `UploadDataPack.tsx` exactly.
- **Response `201`**: Document object.
- **Errors**: `400` — file too large (`MAX_DOCUMENT_UPLOAD_SIZE`), unsupported extension, or a duplicate (same checksum) already uploaded to this sprint.
- Uploading a sprint's first document flips its status `draft → collecting`.

**Response body** (Document object):
```json
{
  "id": "uuid", "sprint_id": "uuid", "document_type": str, "document_type_label": str,
  "title": str, "original_filename": str, "mime_type": str, "file_size": int|null,
  "file_size_display": str|null, "checksum": str,
  "download_url": str|null, "has_file": bool, "uploaded_by": "uuid|null", "owner_role": str,
  "status": "pending|uploaded|processing|processed|failed|rejected",
  "page_count": int|null, "quality_score": float|null, "ocr_required": bool, "ocr_warnings": [...],
  "processing_status": str, "uploaded_at": "iso8601|null", "processed_at": "iso8601|null",
  "document_type_source": "uploader|filename|none",
  "classification_status": "pending|classified|needs_review|unclassified",
  "ai_document_type": str, "ai_document_type_label": str|null, "ai_confidence": float|null,
  "ai_reasoning": str, "classified_at": "iso8601|null",
  "category_confirmed_by": "uuid|null", "category_confirmed_by_name": str|null,
  "category_confirmed_at": "iso8601|null",
  "created_at": "iso8601", "updated_at": "iso8601"
}
```

- `document_type` is the type assigned at upload/import and is never changed by the AI; `document_type_source` says who set it (the uploader, the Drive importer's filename keywords, or nobody — `unclassified`).
- The `ai_*` fields and `classification_status` are read-only, written by extraction's classification step from the document's content. `ai_document_type` is a checklist slug (`DRIVE_IMPORT_CHECKLIST`) or `""`. `classified` means confidence ≥ `AI_CLASSIFICATION_MIN_CONFIDENCE` (default 0.7) and is what the Upload Data Pack checklist counts; a lower-confidence checklist guess is `needs_review`; no or an unknown category is `unclassified`. Reprocessing overwrites them — unless a person confirmed the category (`category_confirmed_at` set), which reprocessing leaves exactly as it is.

### `POST /documents/{id}/confirm-category`
- **Request body**: `{"category": "<checklist slug>" | null}` — a `DRIVE_IMPORT_CHECKLIST` slug (aliases such as `aqar` accepted), or `null` for "not a checklist document". The key is required.
- **Effect**: `classification_status` → `classified` (or `unclassified` for `null`), `ai_document_type` → the slug (or `""`), `category_confirmed_by`/`category_confirmed_at` → the caller and now. `ai_confidence`/`ai_reasoning`/`classified_at` keep the AI's last verdict; `document_type` is untouched. Works on any status, including overriding a `classified` one.
- **Response `200`**: Document object.
- **Errors**: `400` — missing key, blank, or not a checklist category; `403` — viewer, or another institution.

---

## 4a. Google Drive Import Jobs (`/api/v1/sprints/{sprint_id}/drive-import-jobs`)

Screen 2 "Upload Data Pack"'s **Google Drive** data source. No OAuth: the server holds one Drive REST v3 API key (`GOOGLE_DRIVE_API_KEY`), so the institution must share the target folder as "Anyone with the link — Viewer". A job recursively scans the folder (including subfolders, breadth-first, bounded by `GOOGLE_DRIVE_IMPORT_MAX_FILES`/`GOOGLE_DRIVE_IMPORT_MAX_FOLDERS`), classifies filenames against `apps.documents.constants.DRIVE_IMPORT_CHECKLIST` (mirrors `UploadDataPack.tsx`'s `REQUIRED_CHECKLIST` slugs exactly), and imports every supported file through the same `create_document_from_file()` path as `POST /upload-file` — imported documents appear in the regular Documents list with no extra step. The filename match is only a hint: a matching file gets that `document_type` with `document_type_source: "filename"`, any other file `document_type: "unclassified"` with `document_type_source: "none"`; the checklist fills from the AI category saved during extraction.

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/sprints/{sprint_id}/drive-import-jobs` | any authenticated, institution-scoped | newest first |
| POST | `/sprints/{sprint_id}/drive-import-jobs` | any authenticated, institution-scoped | dispatches an async Celery job |

### `POST /sprints/{sprint_id}/drive-import-jobs`
- **Request body**: `{"drive_url": str}` — a Drive folder link (`.../drive/folders/<id>`, `.../drive/u/0/folders/<id>`, or a bare folder ID).
- **Response `201`**: DriveImportJob object, `status` still `pending`/`scanning`.
- **Errors**: `400` if the URL isn't a recognizable Drive folder link/ID.
- A single file's failure (unsupported type, validation reject) doesn't fail the job — it's recorded in `results.skipped_files` and the rest continue. A folder that isn't publicly link-shared, or that has no files, fails the whole job with an actionable `error_message`.

**Response body** (DriveImportJob object):
```json
{
  "id": "uuid", "sprint_id": "uuid", "drive_url": str,
  "status": "pending|scanning|downloading|completed|failed",
  "results": {
    "<checklist_type>": {"status": "found|missing", "filename": str|null, "document_id": "uuid|null"},
    "...": "...",
    "unmatched_files": [str, ...],
    "skipped_files": [{"filename": str, "reason": str}, ...]
  },
  "files_scanned": int, "files_imported": int, "error_message": str,
  "created_by": "uuid|null", "started_at": "iso8601|null", "completed_at": "iso8601|null",
  "created_at": "iso8601", "updated_at": "iso8601"
}
```

---

## 5. Extraction Jobs (`/api/v1/sprints/{sprint_id}/extraction-jobs`, `/api/v1/extraction-jobs`)

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/sprints/{sprint_id}/extraction-jobs` | any authenticated, institution-scoped | |
| POST | `/sprints/{sprint_id}/extraction-jobs` | any authenticated, institution-scoped | dispatches async Celery job(s) |
| GET | `/extraction-jobs/{id}` | any authenticated | 403 if out of scope |

### `POST /sprints/{sprint_id}/extraction-jobs`
- **Request body** (optional): `{"document_id": "uuid"}` — targets one document; omit to (re)process every eligible (`uploaded`/`failed`) document in the sprint. `UploadDataPack.tsx` sends no body (processes everything).
- **Response `201`**: `[ExtractionJob, ...]` — one row per document queued.
- Flips the sprint to `processing`. When every job finishes, the sprint auto-advances to `reviewing` and gap generation runs.

**Response body** (ExtractionJob object):
```json
{
  "id": "uuid", "sprint_id": "uuid", "document_id": "uuid", "document_filename": str,
  "status": "pending|running|retrying|completed|failed",
  "current_step": "classifying_documents|reading_pages|extracting_facts|mapping_audit_fields|detecting_gaps|checking_conflicts|preparing_review_workspace",
  "current_step_label": str, "progress_percentage": int,
  "started_at": "iso8601|null", "completed_at": "iso8601|null",
  "error_message": str, "retry_count": int, "created_at": "iso8601", "updated_at": "iso8601"
}
```
`AIProcessingMonitor.tsx` fetches this list but currently only uses its length for display, not individual fields — no compatibility risk there.

---

## 6. Facts (`/api/v1/sprints/{sprint_id}/facts`, `/api/v1/facts`)

Facts are **read-only via list** — only the extraction pipeline creates them. State changes go through four dedicated actions, each recording a `FactReviewHistory` row.

| Method | Path | Permission |
|---|---|---|
| GET | `/sprints/{sprint_id}/facts` | any authenticated, institution-scoped |
| GET | `/facts/{id}` | any authenticated, 403 if out of scope — includes `review_history` |
| POST | `/facts/{id}/confirm` | CanReviewFacts (every role except `viewer`) |
| POST | `/facts/{id}/correct` | CanReviewFacts |
| POST | `/facts/{id}/reject` | CanReviewFacts |
| POST | `/facts/{id}/request-evidence` | CanReviewFacts |
| POST | `/facts/{id}/aiqif-mappings/{indicator_code}/review` | CanReviewFacts -- `{decision: "confirm"\|"reject", note}`; returns the fact |

**Filters** (list): `pillar`, `status`, `owner_role` (case-insensitive), `document` (UUID), `confidence`/`confidence_min`/`confidence_max`. **Ordering**: `created_at, updated_at, confidence_score, reviewed_at, field_key`.

### `POST /facts/{id}/confirm` | `/reject` | `/request-evidence`
- **Request body**: `{"reason": str}` — `comment` is accepted as an alias (`FactsReview.tsx` sends `comment`).
- **Response `200`**: Fact detail object (with the new `review_history` entry included).

### `POST /facts/{id}/correct`
- **Request body**: `{"new_value": any}` — `corrected_value` is accepted as an alias (`FactsReview.tsx` sends `corrected_value`); also accepts `reason`/`comment`.
- **Response `200`**: Fact detail object, `status` now `corrected`.
- **Errors**: `400` if neither `new_value` nor `corrected_value` is present.

**Response body** (Fact object):
```json
{
  "id": "uuid", "sprint_id": "uuid", "document_id": "uuid|null",
  "field_name": str, "field_key": str, "audit_field_id": str,   // alias of field_key
  "value": any, "value_json": any,                              // alias of value
  "normalized_value": any, "data_type": "string|number|percentage|boolean|date|currency|list",
  "pillar": str, "pillar_label": str, "owner_role": str,
  "source_document_id": "uuid|null", "source_page": str, "source_snippet": str,
  "confidence_score": float, "confidence": float,                // alias of confidence_score
  "confidence_reason": str, "extraction_method": str,
  "status": "extracted|confirmed|corrected|rejected|evidence_requested",
  "aiqif_mapping_status": "pending|mapped|needs_review|unmapped",
  "aiqif_mappings": [{"criterion": "aiqif_c4", "criterion_code": "AIQIF-C4", "criterion_name": str,
                      "indicator_code": "AIQIF-C4.1", "indicator_name": str, "reason": str,
                      "confidence": float, "status": "mapped|needs_review"}, ...],
  "reviewed_by": "uuid|null", "reviewed_at": "iso8601|null",
  "created_at": "iso8601", "updated_at": "iso8601"
  // detail endpoint / action responses only:
  "review_history": [{"id": "uuid", "action": str, "original_value": any, "new_value": any, "user": "uuid|null", "user_name": str, "reason": str, "created_at": "iso8601"}, ...]
}
```
`audit_field_id`, `value_json`, `confidence` are **frontend-compatible aliases** — `FactsReview.tsx` reads exactly these three names.

**AI-QIF category tags** (`aiqif_mappings`, read-only): the AI-QIF key indicators (of the 36, `apps.scoring.constants.AIQIF_INDICATORS`) the fact extractor judged the fact to be evidence for, strongest first, at most 3 — each with its criterion, reason and confidence. A tag is `mapped` at confidence ≥ `AIQIF_MAPPING_MIN_CONFIDENCE` (default 0.7), else `needs_review`. `aiqif_mapping_status` summarizes them: `mapped` (≥1 confident tag), `needs_review` (only low-confidence ones), `unmapped` (the AI found no clear indicator — none is guessed), `pending` (extracted before tagging existed). Tags are categories only: the CRI scores `pillar` (+ `field_key`) and never reads them, and reprocessing replaces an unreviewed fact's tags but leaves a reviewed fact's alone. List filters: `?aiqif_criterion=aiqif_c4`, `?aiqif_indicator=AIQIF-C4.1`, `?aiqif_mapping_status=needs_review` (a fact matches if any of its tags does).

---

## 7. Gaps (`/api/v1/sprints/{sprint_id}/gaps`, `/api/v1/gaps`)

Read-only via list — gaps are only ever created by `apps.gaps.services` (during extraction). State changes go through three dedicated actions.

| Method | Path | Permission |
|---|---|---|
| GET | `/sprints/{sprint_id}/gaps` | any authenticated, institution-scoped |
| GET | `/gaps/{id}` | any authenticated, 403 if out of scope |
| POST | `/gaps/{id}/resolve` | CanResolveGaps (every role except `viewer`) |
| POST | `/gaps/{id}/mark-unavailable` | CanResolveGaps |
| POST | `/gaps/{id}/skip` | CanResolveGaps |

**Filters**: `gap_type`, `status`, `priority`, `pillar`. **Ordering**: `created_at, updated_at, priority, resolved_at`.

### `POST /gaps/{id}/resolve` | `/mark-unavailable` | `/skip`
- **Request body**: `{"resolution": str}` — `value` is accepted as an alias (`GapDashboard.tsx` sends `value`).
- **Response `200`**: Gap object, `status` now `resolved`/`unavailable`/`skipped`.

**Response body** (Gap object):
```json
{
  "id": "uuid", "sprint_id": "uuid",
  "gap_type": "missing_document|unconfirmed_fact|conflict|stale_data|low_confidence",
  "title": str, "description": str, "pillar": str, "pillar_label": str,
  "priority": "blocking|high|medium|optional",
  "audit_field_id": str,     // derived: source_fact.field_key, or "" if not fact-scoped
  "score_impact": float,     // derived: fixed per-priority penalty (blocking=8, high=5, medium=3, optional=1)
  "source_fact_id": "uuid|null", "related_document_id": "uuid|null", "owner_role": str,
  "status": "open|in_progress|resolved|unavailable|skipped", "resolution": str,
  "resolved_by": "uuid|null", "resolved_at": "iso8601|null",
  "created_at": "iso8601", "updated_at": "iso8601"
}
```
`audit_field_id` and `score_impact` are **frontend-compatible aliases** — `GapDashboard.tsx` reads these two names; neither is a stored column (`score_impact` was deliberately removed from the model in favor of deriving it from `priority`, so it can never drift out of sync with the scoring engine's own penalty table).

> **Known gap (not fixed)**: `GapDashboard.tsx` also reads `gap.requested_format`, which has no backend equivalent — GapItem has no concept of a "requested format." Left undocumented/blank rather than fabricated, consistent with this codebase's "never invent data" convention (see Reports/Recommendations below).

---

## 8. CRI Score (`/api/v1/sprints/{sprint_id}/score`, `/api/v1/scoring/config`)

| Method | Path | Permission |
|---|---|---|
| GET | `/sprints/{sprint_id}/score` | any authenticated, institution-scoped |
| POST | `/sprints/{sprint_id}/score` | super_admin, consultant, institution_admin |
| GET | `/sprints/{sprint_id}/score/history` | any authenticated, institution-scoped |
| GET | `/scoring/config` | any authenticated | live pillar/criteria weights, `?is_active=` filter |

- `GET` computes-and-persists a score on first access if the sprint has never been scored (never returns nulls for a sprint with real data just because nobody explicitly recalculated).
- `POST` forces a fresh recalculation from current fact/gap data and records a new `ScoringRun` audit row.

**Response body** (`SprintScore`, `LiveCRIPreview.tsx`'s `scorecard`):
```json
{
  "sprint_id": "uuid", "overall_cri": float, "overall_confidence": float,
  "cri_score": float, "cri_confidence": float,     // aliases of overall_cri/overall_confidence
  "raw_cri": float,                                 // = overall_cri (the CRI before coverage)
  "coverage_adjusted_cri": float|null,              // latest run; null before coverage / no applicable weight
  "evidence_coverage": {                            // latest run's frozen block; {} on older runs
    "formula_version": "AIQIF-COV-1", "formula": str,
    "status": "complete|incomplete|no_applicable_indicators", "ratio": float|null,
    "covered_count": int, "applicable_count": int, "excluded_count": int, "unresolved_applicability_count": int,
    "covered_weight": float, "applicable_weight": float,
    "weights_source": "release|equal_within_criterion", "weights_note": str,
    "release_label": str|null, "release_hash": str|null, "applicability_note": str,
    "mappings_awaiting_review": int,
    "indicators": [{"code", "criterion", "name", "applicability", "applicability_reason", "applicable",
                    "weight", "covered", "fact_ids"}]
  },
  "calculation_version": str, "calculated_at": "iso8601|null",
  "pillar_scores": [{
    "pillar": str, "label": str, "weight": float,
    "raw_score": float, "weighted_score": float, "confidence_score": float,
    "score": float, "confidence": float,           // aliases of raw_score/confidence_score
    "status": "not_started|at_risk|developing|strong",
    "evidence_count": int, "gap_count": int, "calculation_version": str, "calculated_at": "iso8601|null"
  }, ...],   // one per active pillar (the 9 AI-QIF criteria)
  "strengths": [{"pillar": str, "label": str, "raw_score": float, "status": str}, ...],
  "weaknesses": [{"pillar": str, "label": str, "raw_score": float, "status": str}, ...],
  "evidence_metrics": {"confirmed_facts": int, "corrected_facts": int, "total_extracted_facts": int, "documents_processed": int, "unresolved_gaps": int},
  "unresolved_blocking_gaps": [Gap, ...]
}
```

`score/history` rows and `GET .../baseline` (`baseline.coverage_adjusted_cri`, `baseline.evidence_coverage`)
carry the same two fields, frozen with their run. Reports add `report_data.raw_cri`,
`coverage_adjusted_cri` and `evidence_coverage` (`{available, summary, formula_version, ...}`).

### AI-QIF evidence coverage and the coverage-adjusted CRI (formula `AIQIF-COV-1`)

`overall_cri` is the **Raw CRI** (unchanged). Every scoring run also stores, next to it
(`apps/scoring/services/coverage.py`, `ScoringRun.coverage_adjusted_cri` / `evidence_coverage`):

```
coverage              = covered applicable indicator weight / total applicable indicator weight
coverage-adjusted CRI = Raw CRI x coverage
```

- **Indicators**: the 36 AI-QIF key indicators of the active CRI pillars.
- **Applicable**: all of them, except those the *published* benchmark release's applicability rules say
  explicitly do **not** apply to the college's benchmark profile. `requires_review` (no rules, no profile,
  no published release, indicator not in the release) stays applicable and is reported as unresolved;
  `optional` stays applicable.
- **Covered**: at least one *confirmed or corrected* fact whose AI-QIF tag a **reviewer confirmed**
  (`FactAIQIFMapping.review_status = confirmed`). Unreviewed, rejected or evidence-requested facts, and AI
  tags nobody confirmed, never count. Distinct indicators: two facts on one indicator count once; one fact
  may cover several indicators.
- **Weights**: the published release's approved key-indicator weights when it carries one for every
  indicator; otherwise equal weights within each criterion x the approved CRI pillar weight. No weight is
  invented. The source used is stored (`weights_source`, `weights_note`).
- Deterministic: no AI call; AI never confirms a fact or a tag or sets a score. Each run freezes its
  coverage (with `formula_version`, release label/hash and the per-indicator rows), so history and an
  approved baseline's pinned run never change. `SCORING_ENGINE_VERSION` is `2.1` for runs that include it;
  runs made before it have `coverage_adjusted_cri = null` and `evidence_coverage = {}`.
- Benchmark Assessment (cycles, evidence, maturity scoring) is separate and unchanged.

A reviewer confirms or rejects each AI-QIF tag in Facts Review
(`POST /facts/{id}/aiqif-mappings/{indicator_code}/review {decision: confirm|reject, note}`, every role
except `viewer`, institution-scoped). Reprocessing a document keeps reviewed tags.

---

## 9. Recommendations (`/api/v1/sprints/{sprint_id}/recommendations`, `/api/v1/recommendations`)

| Method | Path | Permission |
|---|---|---|
| GET | `/sprints/{sprint_id}/recommendations` | any authenticated, institution-scoped |
| POST | `/sprints/{sprint_id}/recommendations` | super_admin, consultant, institution_admin, iqac_coordinator |
| POST | `/sprints/{sprint_id}/recommendations/generate` | same as above (dedicated URL; the plain-list POST above is kept only for `RecommendationsReview.tsx`'s existing call) |
| GET | `/recommendations/{id}` | any authenticated, institution-scoped |
| PATCH | `/recommendations/{id}` | **super_admin, consultant only** — narrower than view/generate |

- `POST .../generate` runs three generators against real data (open high/blocking gaps, low-confidence confirmed facts, weak CRI pillars) and is idempotent — regenerating never duplicates a recommendation already raised for the same gap/fact/pillar.
- `PATCH` on a still-`draft` recommendation auto-advances its status to `edited` unless the caller explicitly sets `status` in the same request.

**Response body** (Recommendation object):
```json
{
  "id": "uuid", "sprint_id": "uuid", "title": str, "description": str,
  "trigger_gap": str,           // human-readable citation, e.g. "Missing Document: NAAC SSR"
  "source_gap": "uuid|null", "supporting_facts": [Fact, ...],
  "pillar": str, "pillar_label": str, "owner_role": str,
  "priority": "blocking|high|medium|optional", "timeline": str,
  "expected_cri_lift": float,          // 0-100, validated
  "support_offering": str, "consultant_notes": str,
  "status": "draft|accepted|edited|hidden|completed",
  "created_by": "uuid|null", "updated_by": "uuid|null",
  "created_at": "iso8601", "updated_at": "iso8601",
  "recommendation_text": str,   // alias of description
  "edited_text": "",            // always "" -- see note below
  "expected_score_lift": float  // alias of expected_cri_lift
}
```
`recommendation_text`, `edited_text`, `expected_score_lift` are **frontend-compatible aliases** — `RecommendationsReview.tsx` renders `rec.edited_text || rec.recommendation_text` and `rec.expected_score_lift`. `edited_text` is always `""` because this engine writes consultant edits directly into `description` (flipping `status` to `edited` instead of keeping a separate diff), so the frontend's `||` fallback always resolves to the current text.

**PATCH request body**: any of `title, description, priority, timeline, expected_cri_lift, support_offering, consultant_notes, status`. `expected_cri_lift` outside `[0, 100]` → `400`.

---

## 10. Reports (`/api/v1/sprints/{sprint_id}/reports`, `/api/v1/reports`)

| Method | Path | Permission |
|---|---|---|
| GET | `/sprints/{sprint_id}/reports` | any authenticated, institution-scoped — list, no `report_data` blob |
| POST | `/sprints/{sprint_id}/reports` | super_admin, consultant, institution_admin |
| POST | `/sprints/{sprint_id}/reports/generate` | same as above (dedicated URL; the plain-list POST is kept for `ReportPreviewExport.tsx`'s existing call) |
| GET | `/reports/{id}` | any authenticated, institution-scoped — full detail, includes `report_data` |
| GET | `/reports/{id}/download` | any authenticated, institution-scoped — streams the PDF (default) or `?file=docx` |

- Generation is **asynchronous** (Celery): the row is created immediately (`status=draft`) and `POST` returns `202 Accepted`; the task moves it through `generating → ready|failed`. Poll `GET /reports/{id}` for completion.
- **Versioned**: each `POST` creates a new row (`version` = previous max + 1 for that sprint); a historical version's data/files are never overwritten by a later regeneration.
- **Fresh CRI per report**: before building, the task runs the CRI engine (a new `ScoringRun` from the latest confirmed facts, open gaps and active scoring configuration) and builds the report from that run's frozen snapshot. The run is returned as `scoring_run_id`, and `report_data.cri_source` = `{scoring_run_id, calculation_version, calculated_at, recalculated, baseline_status, baseline_scoring_run_id, baseline_cri, differs_from_baseline, note}`; the PDF/DOCX show the note, flagged "RECALCULATED CRI" when it differs from the approved baseline. If scoring fails the report is `failed`, never `ready`.
- `POST /sprints/{id}/score` is allowed at any stage, including after a baseline decision; an approved baseline keeps its own pinned run (`GET .../baseline` returns its `overall_cri` and `pillar_snapshot`).
- **Errors**: `download` → `404` if the report isn't `ready` yet, or the requested file variant wasn't produced.

**Response body** (Report object, list vs. detail):
```json
{
  "id": "uuid", "sprint_id": "uuid", "version": int,
  "status": "draft|generating|ready|failed",
  "executive_summary": str, "overall_cri": float, "confidence_score": float,
  "generated_at": "iso8601|null", "generated_by": "uuid|null",
  "pdf_available": bool, "docx_available": bool,
  "created_at": "iso8601", "updated_at": "iso8601",
  "report_data": { /* detail endpoint only -- see below */ }
}
```

`report_data` (detail endpoint only) holds all 11 required report sections:
```json
{
  "institution": Institution, "sprint": {"id", "sprint_code", "name", "mode", "status"},
  "generated_at": "iso8601", "executive_summary": str,
  "overall_cri": float, "confidence_score": float,
  "pillar_scorecards": [ /* 8 entries, same shape as SprintScore.pillar_scores */ ],
  "strengths": [...], "areas_for_improvement": [...],
  "missing_data_appendix": [{"id", "gap_type", "title", "description", "pillar", "pillar_label", "priority", "created_at"}, ...],
  "recommendations": [Recommendation-summary, ...],
  "ninety_day_action_plan": [{"timeline": str, "items": [...]}, ...],
  "twelve_month_roadmap": [{"timeline": str, "items": [...]}, ...],
  "how_ingage_can_help": [{"offering": str, "recommendation_count": int, "pillars": [str, ...]}, ...],
  "evidence_metrics": {...}
}
```
`ReportPreviewExport.tsx` currently renders entirely static demo content and does not yet consume this shape (see **Known Gaps**), so there is no live-data compatibility risk today — this is the contract the frontend would need to switch to when it's wired up for real.

---

## 11. Dashboard (`/api/v1/dashboard`)

| Method | Path | Permission |
|---|---|---|
| GET | `/dashboard` | any authenticated — self-scoped, no separate object permission needed |

**Response body**:
```json
{
  "active_sprints": int, "completion_percentage": float, "reports_ready": int,
  "pending_confirmations": int, "high_priority_gaps": int,
  "sprint_count": int, "institution_count": int,
  "sprints": [
    {
      "id": "uuid", "institution": str,       // institution name
      "name": str, "status": str, "completion": int,
      "cri": float|null, "confidence": float|null,     // null if never scored -- never a fabricated 0
      "pending_gaps": int, "report_status": str|null,  // null if no report generated yet
      "updated_at": "iso8601"
    }, ...
  ]  // plain array by default; {count,next,previous,results} if ?page/?page_size given
}
```
Built with `select_related`, `annotate` (per-sprint gap count), `prefetch_related` (each sprint's latest report), and separate `aggregate()`/`count()` calls for the summary tiles — verified query-count-independent of row count (see `apps/dashboard/tests.py::DashboardQueryEfficiencyTests`).

`Dashboard.tsx` does not call this endpoint yet — it currently calls `GET /sprints` + `GET /institutions` directly and only uses their `.length` for the two working metric tiles (`sprints.length`, `institutions.length`); the "Average CRI Score" / "Data Confidence" tiles are hardcoded demo values (`57.5`, `82%`), and its sprint table reads `sprint.sprint_mode`/`sprint.academic_year` off the plain sprint list — both now real fields on `GET /sprints` (see §3), so that table no longer crashes on `undefined.replace()` once real sprint data exists. Switching the two hardcoded metric tiles and the summary counts over to `GET /dashboard` is a frontend change, out of scope here.

---

## Frontend-compatibility aliases — summary

Every alias below exists solely so the **existing, unmodified** frontend keeps working against real backend data. They were added/verified during this audit (2026-08-18):

| App | Alias field(s) | Real field | Why |
|---|---|---|---|
| accounts | `name` | `first_name`+`last_name` | `AuthContext.tsx` |
| accounts | `institution_id` | `institution` (FK) | `AuthContext.tsx` |
| institutions | `affiliation` (write+read) | `university_affiliation` | `SprintSetup.tsx` |
| institutions | `accreditation_status` (write+read) | `accreditation_details` | `SprintSetup.tsx` |
| institutions | `website_url` | *(new field, no prior column)* | `SprintSetup.tsx` |
| sprints | `sprint_mode` (write+read) | `mode` | `SprintSetup.tsx`, `Dashboard.tsx` |
| sprints | `academic_year` | *(new field, no prior column)* | `SprintSetup.tsx` |
| facts | `audit_field_id` | `field_key` | `FactsReview.tsx` |
| facts | `value_json` | `value` | `FactsReview.tsx` |
| facts | `confidence` | `confidence_score` | `FactsReview.tsx` |
| facts (actions) | `comment` | `reason` | `FactsReview.tsx` |
| facts (correct) | `corrected_value` | `new_value` | `FactsReview.tsx` |
| gaps | `audit_field_id` | derived from `source_fact.field_key` | `GapDashboard.tsx` |
| gaps | `score_impact` | derived from `priority` | `GapDashboard.tsx` |
| gaps (actions) | `value` | `resolution` | `GapDashboard.tsx` |
| scoring | `cri_score`, `cri_confidence` | `overall_cri`, `overall_confidence` | `LiveCRIPreview.tsx` |
| scoring (per pillar) | `score`, `confidence` | `raw_score`, `confidence_score` | `LiveCRIPreview.tsx` |
| recommendations | `recommendation_text`, `edited_text`, `expected_score_lift` | `description`, *(none — always `""`)*, `expected_cri_lift` | `RecommendationsReview.tsx` |

## Known gaps (deliberately not "fixed")

These are pre-existing frontend behaviors that don't map to any real backend action; fixing them would mean either changing the frontend (out of scope for this audit) or fabricating data (against this codebase's "never invent content" convention, enforced by tests like `apps.scoring.tests.EngineDeterminismTests.test_does_not_hardcode_the_frontend_demo_score`):

- **`GapDashboard.tsx`'s `gap.requested_format`** has no backend equivalent — left undocumented rather than fabricated.
- **Demo/seed buttons** ("Seed Demo Pack" in `UploadDataPack.tsx`, "Seed Sample Facts" in `FactsReview.tsx`, "Seed Sample Gaps" in `GapDashboard.tsx`) `POST` directly to `/sprints/{id}/documents`, `/sprints/{id}/facts`, `/sprints/{id}/gaps` with ad-hoc JSON payloads. All three list endpoints are **intentionally read-only** (`apps.documents`/`apps.facts`/`apps.gaps` explicitly document "only ever created by the extraction pipeline") — these buttons get `405 Method Not Allowed`. This is by design, not a bug: facts/gaps/documents are meant to be pipeline-derived, not manually POSTed with arbitrary field names. The real equivalents are `POST /sprints/{id}/upload-file` (documents) and `POST /sprints/{id}/extraction-jobs` (facts + gaps, via the extraction pipeline).
- **`ReportPreviewExport.tsx`** renders entirely static/hardcoded demo content (including the old fallback CRI of `57.5`) and doesn't call `GET /reports/{id}` for real `report_data` yet — see §10.
- **No client-side token refresh**: `AuthContext.tsx` stores only `access_token`; `POST /auth/refresh` exists and works, but nothing in the frontend calls it, so a session silently 401s once the access token expires (the frontend then `logout()`s on the next `/auth/me` failure). Backend-correct; a frontend concern.

---

## Endpoints added after 2026-09-01

The sections above describe the AI Readiness Audit API as audited on 2026-08-18. Everything below was added
later. Full request/response rules for the benchmark side live in `SOURCE_LIBRARY.md` and
`BENCHMARK_ASSESSMENTS.md`; `openapi.yaml` is regenerated from the code (`python manage.py spectacular --file
docs/openapi.yaml`). Conventions above (base URL, both slash forms, UUIDs, opt-in pagination, error shapes) apply.

### Platform

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/health` | anyone | `{"status":"ok","database":"ok","cache":"ok"}` or `503`. Used by the container healthcheck and the deploy job |
| POST | `/auth/login` | anyone | Now **rate-limited**: 10 attempts/minute per client address and 20/hour per email (`429` beyond). `/admin/login/` is limited to 10/minute too |
| — | `/api/docs`, `/api/redoc`, `/api/schema` | — | Only when `API_DOCS_ENABLED=true` (default: on with `DEBUG`, **off in production**) |

### Users — `/users` (super admin, institution admin)

`GET/POST /users`, `GET/PUT/PATCH/DELETE /users/{id}` — institution admins only manage their own college,
cannot grant platform roles, and nobody can change their own role or deactivate themselves. DELETE deactivates.

### Documents and extraction

| Method | Path | Notes |
|---|---|---|
| POST | `/sprints/{id}/drive-import-jobs/{job}/stop` | Stop a running Drive import; files already imported stay |
| POST | `/documents/{id}/confirm-category` | A person settles a document's AI category (`{"category": slug \| null}`); reprocessing keeps it |
| POST | `/sprints/{id}/extraction-jobs` | Body may now be `{"document_ids": [...]}` (the ticked documents) |
| POST | `/extraction-jobs/{id}/cancel`, `/extraction-jobs/{id}/process` | Stop / re-run one document |
| POST | `/extraction-jobs/sprints/{id}/cancel`, `/extraction-jobs/sprints/{id}/process-incomplete` | Stop all / re-run every unfinished document |
| GET | `/sprints/{id}/ai-usage` | Tokens and cost for the sprint (`?since=&until=`) |
| GET | `/extraction-jobs/usage-report` | Super admin / consultant: usage and cost per institution × sprint × month |

Word (.docx), Excel (.xlsx), CSV and images are now read by extraction; old .doc/.xls and .zip are marked
`processing_status: "unsupported_format"` with the reason in `ocr_warnings[0]`.

### Benchmark library — `/benchmarks/*` (InGage staff only, reads included)

Sources, versions, requirement candidates, requirements, catalogue, links, levels, readiness, evidence rules,
applicability, releases, the watcher — see `SOURCE_LIBRARY.md`. Added with stage 4b:

| Method | Path | Notes |
|---|---|---|
| GET/POST | `/benchmarks/benchmark-candidates` | `?status=open\|all\|research\|review\|approved\|rejected\|published`; POST `{candidate_type, title, source_rationale, benchmark_code?, source_code?}` |
| GET/PATCH | `/benchmarks/benchmark-candidates/{id}` | Edit while in research / review |
| POST | `/benchmarks/benchmark-candidates/{id}/submit` | research → review |
| POST | `/benchmarks/benchmark-candidates/{id}/review` | `{reviewer_role, decision: approve\|reject\|needs_research, notes}` — a different person per required role |
| POST | `/benchmarks/benchmark-candidates/{id}/open-revision` | Approved candidate → the active benchmark becomes a new draft |
| POST | `/benchmarks/watcher/events/{id}/propose` | Make a candidate from any watcher change |

### Benchmark assessment — `/assessments/*`

Profiles, cycles, evidence, reviews, scores, scorecard, weights — see `BENCHMARK_ASSESSMENTS.md`. Added with stage 6:

| Method | Path | Who | Notes |
|---|---|---|---|
| GET / POST | `/assessments/cycles/{id}/plan` | read: staff + the college · generate: staff, finalized cycles only | Gaps → initiatives → tasks |
| PATCH | `/assessments/gaps/{id}` | staff | `{status: open\|planned\|in_progress\|closed, root_cause}` — `closed` only after validation |
| POST | `/assessments/gaps/{id}/validate` | staff | `{evidence_item, note}` — accepted evidence, same college and benchmark |
| PATCH | `/assessments/initiatives/{id}` | staff + college (not viewers) | `{title, description, owner, status, target_date}` |
| POST | `/assessments/initiatives/{id}/tasks` | staff + college (not viewers) | `{title, owner?, due_date?, evidence_due?}` |
| PATCH | `/assessments/tasks/{id}` | staff + college (not viewers) | `{title, owner, status, due_date, evidence_due}` |
| GET/POST | `/assessments/templates?benchmark=` | staff | One template per benchmark × gap type |
| PATCH/DELETE | `/assessments/templates/{id}` | staff | |
| GET | `/assessments/cycles/{id}/sprint-documents` | staff + the college | Audit documents that can be reused as evidence (`sprint_document` on the evidence upload) |
