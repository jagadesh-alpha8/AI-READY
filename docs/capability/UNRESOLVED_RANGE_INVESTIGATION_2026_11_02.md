# Why the earlier assessment returned 0–100 everywhere

2 November 2026. Independent investigation while the SWE obtains a fresh A1 export.
Code baseline: A1 after PR #6 (`02ab72f640668a2239ccea96185d0ed3b58ca322`).
Evidence baseline: the earlier saved capability JSON exported at 05:41 UTC today, not the user's
new assessment. No finding here is asserted to describe the fresh run until that export is compared.

## Finding

The earlier range is exactly reproducible from its saved decisions. This is not an arithmetic bug.
The main unresolved issue is what the present capability rubric demands and why the evaluator
could establish only one of its 72 foundational requirements from the passages it received.

Five response/validation defects are real, but correcting those alone cannot resolve the broad
ranges. Even an intentionally optimistic arithmetic sensitivity check that sets all five affected
decisions to `met` still returns 0–100: other foundational requirements remain unknown in every
indicator. This is a diagnostic counterfactual, not admissible evidence or a revised institutional
score. It is not saved as an assessment or plan scenario.

## Verified facts from the saved export

| Observation | Verified value | What it establishes |
|---|---|---|
| Active source manifest | One SSR; 187 page records, all marked `ok` | This run was a one-document baseline. Page flags do not establish perfect extraction accuracy or a complete Drive import. |
| Model execution | 36 reserved requests and 36 response-received outcomes | The earlier case was not a blanket no-response/provider-failure run. |
| Recorded output usage | Largest completion 1,026 tokens; configured ceiling 3,000 | No evidence of hitting this configured output ceiling. This does not prove an upstream router had no undisclosed limit. |
| Model identity | Configured/recorded response model `gemma4:31b` | Identity is known. No claim that this model is or is not adequate follows from its name. |
| Condition decisions | 1 met, 215 unknown, 0 not-met, 0 conflicting | Missing evidence was not converted into institutional absence. |
| Foundation decisions | 1 met, 71 unknown | No indicator established both foundational conditions. |
| Recorded response defects | Four missing/duplicated condition decisions; one unmatched quotation | Five technical validation problems, distinct from substantive unknown judgements. |
| Other unknowns | 210 without a recorded validator failure | These are saved model abstentions, not proof that the entire PDFs lack the evidence. Their correctness still requires review. |
| Retrieval | Every indicator used bounded context; 50 unique page IDs appear across saved excerpts | The model did not inspect every page for every requirement. This is not a measured semantic-recall result, and unavailable pages cannot be re-searched from this export alone. |
| Deterministic replay | Saved result exactly matches engine replay | The arithmetic is consistent with the recorded inputs and methodology. It does not validate those decisions or the rubric. |

The earlier publisher erased some `validation_issue` fields while preserving their fixed reason
strings. PR #3 already repaired that publication path. This investigation's read-only diagnosis
also recognises those exact legacy reason strings, so old exports no longer look free of errors.

## What the model actually objected to

The saved passages describe general academic systems, computing/cloud/business-analytics labs,
an AI centre, and innovation/incubation support. The current requirements ask for more specific
claims, for example:

- C3.1 foundations: mapped AI learning outcomes and discipline-specific content, plus curriculum
  approval and an AI delivery plan identifying responsible faculty.
- C6.1 foundations: capacity mapped to approved AI uses/intended users, plus assigned access,
  support and security responsibilities.
- C6.4 foundations: an accessible environment supporting planned AI learning, plus documented
  access, support and safe-data arrangements.
- C7.3 foundations: an AI funding/translation pathway naming owners and selection rules, plus
  active-project access to funding/IP/incubation support.

A generic lab or innovation-unit statement cannot automatically demonstrate every part of those
requirements. Conversely, a model saying “not found” in selected passages cannot establish that
the full source collection lacks it. The one positive judgement also needs semantic/currency
review; a matching quotation is not a gold-standard label.

A1 still runs **AIQIF-CAP-0.2**, the experimental cumulative capability rubric. The reviewed
candidate readiness revisions were deliberately not activated. Reports, default scope and plan
features did not replace those requirements or add partial-capacity credit. This is a central
product-fit issue: expecting useful readiness differentiation from ordinary NAAC material while
requiring detailed AI capability evidence can yield very broad ranges even with correct code.

There is also a source-identity mismatch in the earlier case: the saved profile uses a placeholder
institution while the selected SSR headers name another institution. That is an independent
provenance concern, not evidence that it caused all 215 abstentions. The old narrative reasons
mostly discuss criterion insufficiency rather than identity. The scope adapter now recognises
standard `Self Study Report of ...` headers as unverified identity claims and flags a mismatch;
it does not rename the profile or silently reassign sources.

## What was wrong in the implementation

1. The assessment response schema described a list of decisions but did not enforce an exact
   count or enumerate that indicator's six condition IDs. A compatible JSON endpoint could return
   valid JSON containing only some decisions. The code conservatively filled omitted decisions
   as unknown, but “completed” execution could conceal incomplete model coverage.
2. Invalid quotations were removed from canonical decisions for safety, but the model's proposed
   row was not retained in the trace. The earlier export cannot reveal whether the unmatched quote
   was paraphrased, misattributed or fabricated. It also cannot distinguish missing from duplicated
   rows in the four affected decisions.
3. Diagnostics did not separate technical validation problems, execution/context unavailability
   and unknown judgements without a validator error. Legacy erased flags made this worse.
4. Default identity parsing recognised labelled name fields but missed the standard SSR header
   visibly present in the available excerpts.
5. The user-facing range did not make its missing foundation requirements and reasons easy enough
   to inspect. Leadership limitations also needed an explicit bounded-context qualification.

## Changes prepared on `a1-unresolved-assessment-diagnosis`

- Per-indicator schemas require exactly the supplied condition count, enumerate known condition
  IDs and restrict cited source IDs to the supplied passages. Duplicate IDs are still checked
  in code; schema hints alone cannot guarantee that a compatible endpoint obeys them.
- Bounded structured model proposals are retained in the authenticated assessment trace with
  their hash, expected/returned counts, missing/duplicate/unexpected IDs and validation results.
  An invalid proposal never becomes evidence or earns points. SDK exceptions/credentials are
  not recorded. Oversized diagnostic snapshots are omitted with an explicit flag/hash.
- Read-only cause diagnostics separate response validation, unavailable evaluation and other
  unknowns; recover known legacy errors; expose foundation blockers with requirements/reasons;
  and report source/model/context counts without claiming full-corpus coverage.
- An offline `audit_capability_export` command diagnoses a JSON export and replays arithmetic
  without provider calls or database writes. It refuses to overwrite an existing output.
- The workspace explains the distinction between response problems and unresolved evidence,
  with the actual foundational reasons. Leadership limitations disclose bounded passage review.
- Standard SSR-header identity claims are captured with exact source spans and remain unverified.

No score weights, tier thresholds, stage arithmetic, applicability rules or criterion requirements
were relaxed. No extra model calls/retries were added, no actual assessment was changed, and no
live provider was called in this investigation. The schema/prompt protocol advances to 0.5;
old queued assessments with incompatible protocol pins require an explicit new run. Completed
history remains readable.

## What the fresh export must settle

Compare deployed API/worker SHAs and prompt protocol, then compare the new run to this baseline:
source document/page counts; actual populations/periods/identity; met/unknown counts; technical
errors; source excerpts; foundation reasons; and model usage. Do not assume identical PDFs imply
identical manifests, selected passages or model judgements.

For at least three foundations, manually establish an expected decision from the **actual full
source documents**, including scope and dates. Trace that passage into frozen source text and
selected model context. This distinguishes:

1. Not imported / unreadable / incorrectly superseded evidence.
2. Readable evidence omitted by retrieval.
3. Included evidence misinterpreted by the model.
4. Evidence that really does not satisfy the recorded requirement.
5. A requirement that needs a reviewed, versioned redesign for the intended readiness product.

Do not change all unknowns to zero, grant points for generic NAAC statements by fiat, pick a
midpoint of 50, or switch model/temperature merely to obtain narrower-looking numbers. Fix the
identified boundary and evaluate it against reviewed examples. A different model comparison, if
needed, must use the same frozen passages and adjudicated expected decisions.

## Verification checkpoint

- Full local scoring-module run: 221 tests passed. Final targeted report/contract follow-ups
  passed separately after the last diagnostic metadata/wording changes.
- All 162 frontend tests and the production build passed.
- Migration/configuration/whitespace checks passed (expected unconfigured AI-key warning for
  offline tests). No migration is introduced.
- The offline command was run against the actual earlier export and confirmed a complete
  216-record contract, the 1/215 state split, five technical issues and an exact arithmetic replay.
- Full repository SQLite/PostgreSQL CI on the new branch is still pending. No live-provider
  interpretation accuracy or repair of the user's new assessment is claimed.
