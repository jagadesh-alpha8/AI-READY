# Step 6 live acceptance runbook — outstanding

Automated mocks, replay and synthetic browser checks are complete. This runbook lists the remaining
acceptance work; it is not a record of live tests having passed. No production deployment is authorized.

1. Choose one approved institution corpus and reference period. Record file checksums, lineage, page
   extraction/OCR status and the population being assessed. Confirm permission for the existing provider.
   Retain source failures and missing pages; do not treat them as demonstrated capability failures.
2. In a development environment, review/apply earlier migrations; exercise actual PostgreSQL and the
   configured Redis/Celery worker. Keep assessment/recommendation inference flags off until pricing,
   per-run limits and provider-side spend controls are configured and an experiment budget is approved.
3. Have qualified reviewers label condition IDs against frozen quoted sources, including unknown,
   conflicting and affirmative not-met cases. Record disagreements and adjudication separately.
   A small label subset is allowed, but report its coverage and selection limitations.
4. Explicitly start one assessment with a unique idempotency key. Record returned run ID, inputs hash,
   actual provider/model identity, request attempts, tokens and reserved/actual billing. Check all 36
   indicators and 216 conditions; framework coverage is not evidence completeness.
5. Export JSON and run `validate_capability` for exact replay and human-label metrics. Inspect unsupported
   met claims, missing-source handling, scope/period mismatches and contradictions individually. Domain
   owners must agree on acceptance thresholds before interpreting results; none are invented here.
6. With separate explicit spending authorization, repeat from identical frozen inputs. Confirm hashes
   before using `--repeat`; changes in source pages/profile/policy are not a cold-run agreement test.
   Report state agreement separately from numerical replay and semantic accuracy.
7. Explicitly request one recommendation version. Review all selected actions for factual support,
   feasible suggested roles/effort, bounded dependencies and appropriate completion evidence. Missing
   evidence should request records; it must not prescribe capability development. Both sides of a conflict
   should remain visible. Reject unsupported institutional facts or implied guaranteed score uplifts.
8. Exercise source replacement/renaming with explicit lineage, a partial-OCR document, unreadable/failed
   pages, an unsupported format and contradictory/scoped/outdated evidence. Old run/report/advice stays
   pinned; a new run must reassess all requirements, not only previously cited ones.
9. Test concurrent repeated/different keys in PostgreSQL, duplicate task delivery, queued and in-flight
   cancellation, provider failure/missing usage, exhausted budgets, broker failure and killed workers.
   Account for in-flight billing. Killed workers must not silently replay potentially billable work.
10. Use two institutions to check history/detail/evidence/recommendation/workflow/export access. View and
    refresh every new UI screen without POST/model calls. Mark an action completed and verify unchanged
    assessment scores. Export without legacy baseline approval. Recheck mobile and print layouts on actual
    sources, including long filenames, multilingual quotations and large evidence sets.

Record each case as PASS/FAIL/NOT RUN with run/version IDs, hashes, reviewer, environment and billing
reference. Resolve failures before a separate deployment decision. No automatic model judge substitutes
for the human-labelled condition and recommendation review.
