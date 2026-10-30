# Steps 5–6: capability experience and validation

Branch: `a1-step5-6-experience`, from merged A1 `9f1211d107c5f4c3e78279934ec77d249c056511`.
Target a new PR into **A1**. No direct A1/main push, merge, production migration or deployment.
The engineer's separate work is not overwritten. The Step 4 web-upload commits are already in the base.

## Step 5 implemented

The dashboard now shows the selected institution's capability, not average CRI/confidence headlines.
Score, recommendation, transformation plan, goals/tasks, capability intelligence and report routes read
capability-run snapshots. All 36 indicators and 216 condition decisions remain available, including
unknown/contradictory evidence and frozen source quotes/version labels. Capability, evidence resolution
and experimental tier eligibility are separate. A failed/cancelled/incomplete run has no headline score;
older completed runs are accessible by selecting history explicitly.

Assessment and recommendation history are paginated. The run and recommendation version selections are
carried in URL queries. Component keys and stale-response guards prevent earlier selections from updating
the current display. Active jobs poll GET only, show progress/reservations/stalled status, and can be cancelled.
Explicit POST controls disclose model-credit use and respect enabled flags. Ambiguous start failures keep
idempotency keys for retries of the same inputs. Intentional successful new starts receive fresh keys.
Mutable action ownership, feasibility and status stay separate from historical advice and scores.

The main onboarding guide projects capability progress when `workflow=capability` is requested. Human
fact review, legacy gaps and baseline approval are not gates on this path. Guide defaults for older clients
remain unchanged. Contextual tours and navigation labels are updated. Historical CRI, its advice, approval,
reports and other legacy workflow consumers remain accessible under explicit Legacy labels. Backend legacy
score/report APIs and their records are retained for compatibility; new primary routes do not use them.

### Deterministic plans without model spending

A completed run detail now includes `deterministic_plan`, derived solely from its frozen assessment with
the explicit versioned next-threshold policy. This includes all next-level, next-overall and tier-selected
actions even when tailoring is disabled. It does not append events or change scores. The derivation policy
is visible and included in the response/export; a recommendation generation pins it immutably in its own
snapshot. Historical assessment results themselves are never reinterpreted or rewritten.

### Report export

Authenticated GET `/api/v1/sprints/{sprint_id}/capability-runs/{run_id}/report` supports `file=html|json`.
Optional `recommendation_id` must belong to this exact run; invalid/foreign versions are rejected.
Only completed assessments export. No legacy baseline approval or model call is required.

HTML includes current standing/uncertainty, all indicators and requirements/reasons/quotes, sufficient tier
pathways, next overall policy, canonical action evidence and optional selected advice. Source filenames,
versions/checksums, run/event identity and input hash are included. All model/source text is escaped.
Current workflow at export is labelled separately. Headers disable caching and active content.

JSON includes the pinned rubric, full stored assessment and selected recommendation version, allowing
replay. HTML can be opened in a browser and printed to PDF. Native server-generated PDF/Word for the new
capability path are not implemented in this revision; their legacy exports remain on legacy routes.

No schema migration is added. Install updated frontend dev dependencies (`npm ci`); jsdom 26 is used for
DOM tests and remains compatible with the existing Node 20 build image. Builds still carry the existing
large-bundle advisory; code splitting is separate work.

## Step 6: implemented validation, not live acceptance

- Full scoring/extraction/accounts regression: **579 tests ran; OK, 1 skipped** (578 passed).
- Frontend tests: **155 passed**. New tests cover full indicator presentation, no POSTs on view, export
  without approval, late-response isolation, zero versus uncertainty, and retry-key reuse.
- TypeScript/Vite production build passes. Model checks pass with only expected unconfigured-key warning;
  migrations show no changes. Whitespace check is clean.
- Chromium smoke checks the actual app with synthetic intercepted API responses: score → recommendations
  → report navigation, all 36 indicators, 390px mobile layout, no runtime errors and no POSTs.
  A mobile history-button overflow found during this check was fixed.
- Export API tests cover exact snapshot identity, tenant/run boundaries, no inference or assessment-history
  writes, changed institution profile not rewriting the report, untrusted HTML escaping, and optional
  workflow data not changing the assessment. Guide projection is covered while legacy semantics remain.

### Offline accuracy and agreement command

```bash
python backend/manage.py validate_capability /path/to/exported-assessment.json
python backend/manage.py validate_capability /path/to/exported-assessment.json --gold /path/to/human-labels.json --repeat /path/to/independent-repeat.json
```

The command does no inference. It checks every deterministic result field, reports human-label coverage,
exact state accuracy, unsupported-met count, unknown recall and a confusion matrix, and separately reports
agreement between independent runs. Missing gold/repeat leaves those metrics null. Labels and repeats
must match frozen input and rubric hashes; duplicate, invalid or incomplete prediction sets are rejected.
Partial human labels are allowed but their coverage is reported, never represented as full-corpus accuracy.
Human-label file shape:

```json
{"inputs_hash":"COPY_FROM_EXPORT","rubric_hash":"COPY_FROM_EXPORT.assessment.result.rubric_hash","records":[{"condition_id":"AIQIF-C1.1.F1","state":"unknown"}]}
```

The example state is illustrative, not a gold label for any real institution. Use a qualified reviewer to
supply actual labels. Do not use the UI synthetic fixture as a quality benchmark.

### Reproduce the browser smoke

With frontend dependencies and a local Playwright Chromium installation available:

```bash
python scripts/create_capability_ui_fixture.py /tmp/capability-ui-fixture.json
npm --prefix frontend run dev -- --port 3015 --host 127.0.0.1
# In a second terminal (Playwright available under frontend/node_modules):
node scripts/capability_ui_smoke.cjs /tmp/capability-ui-fixture.json
```

The script accepts local hosts only, supplies synthetic auth/API fixtures, and asserts no writes occur.
`CAPABILITY_UI_URL` selects a different local port. `CAPABILITY_CHROMIUM_EXECUTABLE` supports an existing
local Chromium executable; `CAPABILITY_UI_SCREENSHOTS` optionally selects an existing scratch screenshot
directory. Screenshot outputs are not included in this code package. The execution environment used an
isolated temporary Chromium install because its default browser download was unavailable.

## Still required to finish Step 6

Actual institution corpus/approved provider, independently reviewed condition labels, a budgeted cold-run
repeat, recommendation feasibility/semantic review, OCR/format/update cases on real files, PostgreSQL
concurrent starts and cancellation, real Redis/Celery dispatch, and worker termination/billing checks.
No live model calls or quality claims were made here. See STEP_6_ACCEPTANCE.md for the concrete runbook.
