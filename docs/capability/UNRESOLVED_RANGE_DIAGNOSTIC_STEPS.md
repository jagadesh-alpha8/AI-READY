# Focused diagnosis of a fresh 0–100 assessment

Use this addendum alongside `SWE_TEST_HANDOFF_2026_11_02.md`. It targets the numerical-range issue,
not general plan-feature acceptance. The earlier export investigation is in
`UNRESOLVED_RANGE_INVESTIGATION_2026_11_02.md`.

## Collect one complete affected run

Return its full assessment JSON, the run ID and deployed frontend/API/worker SHAs. Include the
actual source manifest, frozen scope, condition reasons/validation issues, traces and model usage.
Identify whether this is a completed assessment, not a failed/partial job or an old saved result.
Use the A1 build actually deployed for testing; merging a branch does not deploy it automatically.

The new diagnosis tooling is on `a1-unresolved-assessment-diagnosis`; until merged/deployed, the
current A1 API will not expose these extra trace fields. You can run its offline command against
an existing export without rerunning inference:

```bash
# From backend/, with the normal project dependencies installed:
python manage.py audit_capability_export /path/to/assessment.json --output /path/to/new-diagnosis.json
```

This performs no model calls or database writes. Choose a new output path. Arithmetic replay
checks numerical consistency, not the truth of evidence interpretations or file authenticity.

## Compare these values

| Value | Diagnostic interpretation |
|---|---|
| Included document/page counts versus full import inventory | Determines whether the expected PDFs actually entered this assessment. |
| All 216 condition states; both foundation conditions for each area | Shows exactly why the lower bound remains zero. One met foundation alone earns no stage under the current method. |
| Validation failures versus other unknowns | Distinguishes model output/citation defects from model judgements about insufficient evidence. |
| Reserved/successful requests, usage and actual model | Helps identify execution/budget/provider issues; do not treat a provider error as an institutional shortfall. |
| Selected passages and bounded-context counts | Shows what the model actually saw. It does not establish that unselected pages lack evidence. |
| Protocol and rubric versions | Current rubric remains AIQIF-CAP-0.2. The new exact-ID/schema diagnostics use evaluation protocol 0.5. Completed older runs keep their original protocol/results. |

## Trace three requirements manually

Start with curriculum, computing/access and research/incubation, using the actual rubric's
foundation text. For each, fill one row:

| Requirement ID/text | Full-PDF page and exact passage | Population/activity/effective dates | Expected met/not-met/unknown/conflicting and why | Frozen extraction includes it? | Selected context includes it? | Model proposal | Validator result |
|---|---|---|---|---|---|---|---|
| Complete in test evidence | | | | | | | |

Use a knowledgeable reviewer for the expected decision. A title or named lab alone does not
establish delivery, competence, scope, current availability or every part of a compound criterion.
A document-generation date alone is not the activity period. If the available evidence really is
insufficient, record that honestly and identify which requirement needs methodology review.

For new protocol-0.5 runs, `assessment.traces[].response_audit` retains the structured model
proposal and missing/duplicate/unexpected IDs. It explains an invalid quote without admitting it
as evidence. Old exports cannot reconstruct proposals that were never saved.

If the expected passage is absent from the snapshot, investigate import/extraction/lineage first.
If present but unselected, investigate retrieval. If selected but misread, evaluate the mapper/model
on that fixed case. If correctly rejected but the criterion is unsuitable for a NAAC-based readiness
product, propose a versioned rubric change with reviewed examples; do not patch points in the UI.

## Required return

The fresh full JSON plus this three-row trace is more useful for the 0–100 issue than a generic
“all tests passed.” Keep ordinary implementation failures, insufficient source evidence, retrieval
errors, model interpretation errors and methodology-design concerns separate. Do not change the
baseline, rubric or prompts during the comparison without recording the new version and run.
