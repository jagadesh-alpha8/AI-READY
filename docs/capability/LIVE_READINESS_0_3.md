# Live A1 readiness scoring 0.3

This change activates AIQIF-CAP-0.3 for **new capability assessments**, rather than adding another offline candidate. The worker, default release, retrieval, publication, recommendations and conditional plan arithmetic use the revised method. Main is not the deployment target.

## Behavior

- Each of an indicator's six assertions contributes independently. Its lower bound is `100 × met / 6`; its upper bound is `100 × (6 − not_met) / 6`. Unknown/conflicting findings retain uncertainty. Missing foundations do not erase supported activity or results.
- One met assertion therefore establishes 16.67/100 at indicator level even when its companion is unknown. One explicit negative reduces that indicator's upper bound to 83.33. No assertion is automatically adjudicated by the arithmetic engine.
- The 32 shared capability groups have equal provisional budgets. The four overlapping pairs split one budget each; remaining indicators receive one. This is equivalent to equal F/A/O component contributions within the reviewed grouping. These are experimental A1 pilot weights, not empirical calibration or an impact guarantee.
- Silver/Gold/Platinum are not awarded. Their numeric thresholds and floors are null in this release; numerical readiness and achievement are distinct. Badge roadmaps explicitly return not calibrated.
- All 216 requirement texts, constructs, scope/date rules and AI-specific context rules come from the reviewed candidate. Generic computing, digital-service and institutional-review evidence can establish the corresponding enabling assertions; it never establishes AI deployment or learning competence.

## Evidence selection and period

Retrieval selects exact, assertion-diverse windows with capability-specific vocabulary, rather than predominantly weighting the old AI indicator titles. The same 18,000-character and 36-indicator request budgets remain; context is still bounded and its semantic recall is not guaranteed. Exact windows, offsets and protocol hashes remain frozen.

Default assessment uses supported source-local scope/periods. For static enabling provision, a report's own explicitly labelled date or standard SSR printed footer timestamp may date its **reported claim**. This is never an activity date or proof of current operation. The scope adapter preserves that distinction. Generic event timestamps, filesystem timestamps and upload dates are not report dates. Custom current-period requests still need compatible evidence.

## Source institution confirmation

A detected source/profile name mismatch now returns a specific review response **before creating an execution or calling a provider**. The workspace offers an explicit source-institution confirmation. The confirmed name must be declared in the current source pages; an arbitrary name is rejected. The confirmation is included in the idempotency intent and immutable scope, and does not rename the institution profile, establish a capability or prove source authenticity.

This removes a known source of blanket abstention without guessing document ownership. It is a run-specific identity assertion by the authenticated user. Each finding still needs its own actual scope and period. Matching names do not prove authenticity; unconfirmed identity remains an evidence issue.

## Compatibility and presentation

Old 0.2 rubric files and cumulative arithmetic remain available through their frozen snapshots. Old results are not remapped, recomputed on GET or overwritten. Legacy-specific tests explicitly select 0.2; current-path tests select the new default. Stable condition labels are scoped by the run's rubric version/hash and require fresh evaluation under 0.3.

New numerical results expose independent aggregation and badge policy. Fractional compatibility credit units are not presented as discrete maturity levels. The workspace marks an older saved method and explains that a fresh assessment is required. Report descriptions and diagnostics reflect the actual recorded method. Readiness threshold suggestions are rescored using exact assertion arithmetic; conditional plan gains preserve paired uncertainty and do not change the baseline.

## Deployment and fresh test

1. Deploy the updated A1 commit to both the web process and assessment worker; restart both so their engine/prompt protocols agree. No database migration or new dependency is introduced.
2. Open the scoring workspace and **start a new assessment**. Refreshing or selecting an old 0.2 result cannot test this fix. A new start uses a new idempotency key; ordinary request retries remain idempotent.
3. If prompted, confirm the correct source institution or correct the uploaded documents/profile. The preflight rejection spends no model credits.
4. Verify that the new run's `rubric_version` is `AIQIF-CAP-0.3`, result engine is `capability-engine-0.3.0`, prompt is `AIQIF-EVAL-0.7` and retrieval is `assertion-balanced-windows-0.3`.
5. Inspect supported enabling assertions, actual source periods, validation failures and per-indicator bounds. A supported assertion must move its lower bound. A fully unresolved assertion set must stay unresolved. Quote/provenance/identity/period failures still cannot receive automatic credit.

Tests exercise the actual default evaluator and publication path with synthetic evidence, identity confirmation before dispatch, fresh/legacy method behavior, exact windows, numerical extremes, plan deltas and unchanged history. They are not a fresh live-provider assessment of institutional PDFs. The SWE must run that final provider/deployment test and retain its new export; a historical export is not evidence of this version's behavior.

See [the final test handoff](READINESS_FINAL_TEST_HANDOFF_2026_11_03.md) for the latest retrieval and recommendation fixes and deployed-provider smoke test.
