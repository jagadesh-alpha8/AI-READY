# Preserve evidence identity and diagnose unresolved scores

Baseline: A1 `d468458410b438282efe1796905392c9d19cff05`.
Branch: `a1-evidence-ingestion-audit`. No change to active scoring conditions or main.

## Problem and behavior

An imported `criteria 3/a.pdf` could be superseded by an unrelated `criteria 4/a.pdf`, because
the upload service used case-insensitive basenames as version identity. Imports now persist
Drive file IDs and original source paths. Different IDs remain independent, even with identical
basenames; changed content with the same ID creates a new version even after a rename.
Exact-content duplicates still use the existing per-sprint checksum deduplication.
Manual filename versioning is retained for manual/legacy documents and cannot supersede a
new Drive-identified source by name alone.

The importer previously truncated folder scans at a configured cap. Production import jobs now
require a complete scan and fail visibly BEFORE downloading any files if file/folder limits are
exceeded. Existing bounded-list callers keep their previous behavior. The default file limit
increases from 200 to 1000; an explicit deployment environment value still overrides it.
Folder scans completing exactly at the file cap still check pending child folders.
They also follow empty provider pages, reject Google's `incompleteSearch` flag before
downloading, and stop repeated-page-token loops with a recoverable scan error. Import results
retain Drive IDs and source paths for successful files and skips, including checksum rejects.
Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list

Capability manifests include source identity/path. Publication revalidation preserves previously
recorded evaluator validation errors instead of blanking them when already-unknown decisions
are checked again. Old immutable reports are not rewritten.

## Deployment and recovery

1. Coordinate branch merge with the engineer. Apply the included additive documents 0007
   migration and restart the API and workers on the same commit. This is not a deployment script.
2. Check deployed file and folder limits. At least 350 files are needed for the observed folder;
   leave headroom for future uploads. Confirm storage/processing budgets separately.
3. Use a NEW test sprint for a clean reimport and extraction. Adding source identity does not
   reconstruct old IDs, repair old supersession chains or undo skipped checksum duplicates.
   Do not blanket-reactivate superseded documents: some may be genuine old versions.
4. Wait for import and document processing to finish. Compare discovered/imported/skipped,
   current/superseded, readable pages and the capability run's frozen input count. A completed
   import is not equivalent to completed extraction. Inspect per-file failures.
5. Match the institution and assessment period to the documents. Keep genuine historical
   evidence labelled historical; do not relabel old activities as current.
6. Export the resulting capability JSON before changing methodology. Review targeted evidence
   against `NAAC_RUBRIC_REVISION_DRAFT.md`; the draft is not activated by this patch.

## Read-only diagnostic command

From `backend/` after applying the migration:

```bash
python manage.py audit_evidence --sprint REPLACE_WITH_ACTUAL_SPRINT_UUID > evidence-inventory.json
```

Replace the labelled UUID placeholder with the actual test sprint ID. The output includes the
checkout commit, limits, document/source identity, version lineage, page status counts, import
job results and the last five runs' frozen input counts. Inventory format 0.2 exports a bounded
set of import-result fields and fixed skip-reason codes, plus an `error_present` flag. It omits
raw stored exception messages and provider response bodies, which can contain credential-bearing
URLs. Legacy skip reasons are labelled `legacy_unspecified`; inspect detailed errors locally if
needed. It makes no AI calls and does not change records. Filenames and source paths may contain
institutional information; send the output only within the existing project team.
A checkout SHA is not proof the API/worker processes were restarted on that SHA.

## Work that can proceed independently

`EVIDENCE_TO_REPORT_CONTRACT.md` specifies the proposed reviewed-evidence boundary and 18
acceptance cases. `METHODOLOGY_REVIEW.md` adds six worked report fixtures and explains the
score-meaning decision. `methodology_review_matrix.json` inventories all 216 conditions with
candidate wording, scope/period rules and counterexamples; reproduce it with
`python scripts/build_methodology_review.py` from the repository root. These files are design
material only. The app does not load them and no scoring release is activated.

CI now includes pull requests targeting A1. Image publication and deployment remain restricted
to pushes on main by the existing workflow conditions. Merging this PR into A1 does not deploy it.

## Validation

Local SQLite and injected Drive/provider responses; no production inference or complete corpus
rescore. Targeted backend checks use DEBUG=True (HTTP test client); the initial production-default
invocation redirected requests to HTTPS and did not exercise the API tests. No deployment setting
was weakened.

Initial validation before the follow-up: **179 tests passed** across documents, source identity, capability engine/API/storage,
reports, recommendations and evidence diagnostics. `makemigrations --check --dry-run` reports no
pending changes; `manage.py check` reports only the expected unconfigured AI-key warning;
`git diff --check` is clean. The rubric draft contains exactly 36 distinct indicator rows.
No production database, worker, paid AI endpoint or full-folder assessment was exercised.

Follow-up checks: **37 focused ingestion/audit tests passed**, including incomplete-provider
searches, empty/exact-cap pagination, repeated tokens, pre-download retries and safe audit
exports. Migration drift, Django configuration and whitespace checks passed. The frontend
production build passed locally and on GitHub. The full backend suite and PostgreSQL CI results
are recorded in the PR description/checks; do not treat an in-progress check as a pass.

```bash
DEBUG=True python manage.py test apps.documents.tests apps.documents.test_source_identity apps.scoring.test_capability apps.scoring.test_capability_api apps.scoring.test_capability_storage apps.scoring.test_capability_reports apps.scoring.test_recommendations apps.scoring.test_evidence_diagnostics --verbosity 1
```
