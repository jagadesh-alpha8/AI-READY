# Evidence workflow, extraction consistency and PDF export

Base: A1 `59a942dfbeb32807644032a4cb3f39c3005f95fc`.
Working branch: `a1-evidence-workflow-pdf`. Review and merge into A1 only.
This package is source code, not a deployment or a completed production acceptance test.

## Resulting client workflow

1. Sprint Setup
2. Upload & Processing (upload and operational monitor tabs)
3. Evidence & Review (documents, fact exceptions, missing evidence/conflicts, accreditation evidence)
4. Assessment
5. Recommendations & Action Plan
6. Reports

Remove the separate requests portal, Owner Workspace, duplicate transformation/tasks navigation, and legacy
CRI/approval client routes. Earlier facts, gaps, monitor, compliance and action-plan bookmarks redirect to their
canonical workspace. Existing backend records and APIs are retained because extraction/review/deletion still
share parts of them. No database data is deleted. An existing fact request can be explicitly withdrawn inline
by an authorized reviewer; new supporting evidence goes directly to upload. Recommendations link to upload
with the frozen requirement context. Uploads become sprint evidence; this is not a new requirement-assignment
workflow, and evaluating new evidence requires a new explicit assessment.

Accreditation evidence is an inventory of relevant documents, not a claim of criterion-level NAAC compliance.
The processing monitor retains progress/failure/retry information and per-document outputs; evidence-review
headline counts are no longer repeated there. Verification groups already explain why exceptions need review.
The default facts view now filters to unreviewed exceptions; All and Verified remain available.

## Verified acceptance

The normal batch action is "Accept verified facts". The server always requires a verified status, rechecks the
current value/citation against live sources, applies the existing risk/automation policy, and leaves high-risk
facts for individual review. `only_verified=false` cannot bypass those checks. Per-fact person audit history
is retained; this is an explicit batch decision, not invisible auto-confirmation. Evidence-request, ownership,
confidence-floor and open-conflict checks remain enforced. Shadow/enforce configuration is not changed.
Model confidence remains a self-report, not a calibrated probability. Capability scoring does not depend on
confirming every extracted fact.

## Assessment diagnostics and retrieval

Read-only diagnostics summarize frozen condition states, validation failures, unreadable/unavailable pages,
foundational requirements not demonstrated, and bounded retrieval. Zero lower bounds with unresolved evidence
are explicitly distinguished from an exact zero. No scoring weights, thresholds, prerequisite rules or past
results are changed. New assessments pin prompt/schema/retrieval identifiers in their inputs.

New lexical retrieval uses indicator and requirement wording, searches overlapping page windows beyond the
first 6,000 characters, and breaks ties by source text rather than database UUID. Each selected page contributes
one exact, offset-recorded window. Publication validates that window against the frozen source. It remains
bounded lexical retrieval (18,000 characters per indicator), not full-document semantic coverage. Evidence
outside the selected windows can still be missed. A relevant source can still be interpreted incorrectly.

The reported all-zero institution run has NOT been reproduced: its actual assessment JSON and documents
were not supplied. Inspect the new diagnostics/condition rationales before attributing it to document count,
loosening evidence rules or changing thresholds.

## Fact types and extraction snapshots

`apps/facts/catalogue.py` defines `institution-facts-0.1`: eight initial types with conservative exact aliases.
Unknown types remain additional observations. There is no quota or fabricated placeholder fact. Add aliases
or types only by a reviewed versioned code change, with evaluation fixtures. Model proposals never mutate
this catalogue or scoring criteria automatically. The initial catalogue is deliberately small, not exhaustive.

Extraction merge/persistence identity includes concept, stated scope, data type and value. Unscoped facts on
different pages are retained separately. Different periods, populations, units and conflicting values no longer
compete solely on field key or model confidence. Exact observation retries reuse rows; unambiguous updates
retain IDs, and person-reviewed values remain protected. Canonical aliases are also recognized by the shared
verification comparison. Field keys remain available for provenance and existing integrations.

Migration extraction 0016 adds append-only `ExtractionSnapshot` rows before mutable fact review. They retain
validated observations, source-text and protocol fingerprints, reader version, configured sampling and recorded
provider/model identities. Partial and complete attempts are distinct. Identical freezes are idempotent.
Historical jobs are not backfilled. Fact API responses identify the canonical type and whether their current
value is observed in the latest extraction snapshot, retained, or not recorded. Retained records are not deleted
merely because a fresh model response omitted them; that decision needs source/reviewer evidence.

Chunk reuse now includes the extraction protocol fingerprint, so a prompt/schema/catalogue/configuration change
cannot silently reuse old chunks. The first explicit reprocessing after this update may make fresh calls.
Temperature/seed still reduce variability, not guarantee identical independent outputs. Some providers reject
sampling controls; actual request settings remain the provider layer's responsibility. Mutable router backends
can also change behind a configured model name. Snapshot comparison is measurement, not an accuracy claim.

Read-only tooling, with no model calls:

```bash
python backend/manage.py extraction_observations --job JOB_UUID > first.json
python backend/manage.py extraction_observations --job OTHER_JOB_UUID > second.json
python backend/manage.py extraction_observations --compare first.json second.json
```

Use two independently processed identical files in isolated test sprints, or two separate completed jobs.
"Process again" reusing a job's saved chunks is not an independent extraction. Comparisons require different
job identities, complete outputs, and matching source-text/protocol fingerprints. Outputs report observation
Jaccard, unmatched observation identities, category counts and whether recorded models match. Empty outputs
produce no agreement score. Unmapped category candidates are included for human review in exports.

For capability judgment agreement and human accuracy, retain the existing `validate_capability` workflow.
Numerical replay, repeat agreement and correctness against human labels remain different measurements.

## PDF export

Authenticated `GET /api/v1/sprints/{sprint_id}/capability-runs/{run_id}/report?file=pdf` uses the same pinned
assessment and optional `recommendation_id` as HTML/JSON. It includes all 36 indicators/216 requirements,
reasons, source citations/versions, uncertainty, tier scenarios, deterministic actions, selected advice and
separately labelled current workflow. Reads do not generate a new assessment or spend model credits.

Uses existing fpdf2 dependency and bundled DejaVu Sans fonts with their licence. No network or external HTML
resources are used. Text unsupported by the font is represented with Unicode escapes, not silently dropped.
This is not a full Tamil/Hindi typography solution. Exports can be long because they retain the full audit trail.
JSON is still the machine-readable replay artifact. HTML also includes diagnostics.

## Integration

1. Compare the current A1 head with the base above. Reconcile intervening engineer edits before replacing files.
2. Review the diff, install existing dependencies, and apply `python backend/manage.py migrate` in development.
   New migration: extraction 0016 only. Do not rewrite already-applied migrations.
3. Restart API and workers together, then rebuild the frontend.
4. Exercise a real authorized institution corpus: check a known supported foundational requirement, a genuine
   shortfall, missing evidence, conflicting sources, two academic years of the same metric, and a known decimal.
5. Export pinned PDF/HTML/JSON, add evidence, reassess explicitly, and verify old reports remain unchanged.
6. Compare independent extractions and capability decisions against human-labelled evidence. Do not enable
   broad automatic verification merely because synthetic tests pass.

No live provider calls, production database migration, deployment, main update or remote merge was performed.
See VALIDATION_EVIDENCE_WORKFLOW.md for exact local validation and remaining limits.
