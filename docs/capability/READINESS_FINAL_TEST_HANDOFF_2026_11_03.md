# A1 readiness final test handoff

The primary acceptance test is evidence → supported decisions → informative bounds → useful next actions. A successful execution with every requirement unknown is an incomplete baseline and needs investigation.

## Concrete fixes

- Same-page evidence loss: retrieval previously retained only one selected window per canonical page ID. Different assertions could select different windows on the same long page, yet the later window disappeared. Retrieval now retains distinct `(page ID, offset)` windows within the unchanged 18,000-character budget. A regression proves recovered faculty skill evidence can establish an assertion and move the actual default assessment lower bound.
- Citation validation: multiple supplied windows may share a page ID. Each quotation must match wholly within one supplied window; stitching omitted gaps is rejected. Two distinct scoped quotations on the same page may establish a conflict. Repeating one quotation cannot. Conflicts require the relevant scope and period.
- Recommendation context: bounded, cited verified strengths now support tailored evidence checks. Unknown remains unknown and its action remains an evidence check. Only explicit shortfalls authorize development advice.
- Useful planning: the current-method pathway groups remaining work into six proposed foundation goals: safeguards, resources, faculty, students, operations and review. Verified requirements are removed and existing strengths reused. Three illustrative paces have the same remaining outcomes. Unknown prerequisites need verification before conditional implementation. These are pilot proposals, not calibrated Silver gates, prices, guaranteed timelines or automatic score gains.
- Deployment guard: web output identifies an older protocol even if rubric versions match. A worker with a different retrieval protocol fails before provider use, with a restart/new-run instruction.
- Incomplete baseline: entirely unresolved assessments explicitly require evidence review. Mathematical uncertainty remains visible; no narrower scores are fabricated.

## Deploy and probe first

Deploy the same A1 revision to web and Celery workers and restart both. No migration or dependency is added. In the deployed worker environment:

```bash
python manage.py readiness_smoke_test
```

Expected: `AIQIF-CAP-0.3`, `capability-engine-0.3.0`, `AIQIF-EVAL-0.7`, `assertion-balanced-windows-0.3`. This default command makes no provider call.

Then explicitly probe the actual configured provider with synthetic evidence:

```bash
python manage.py readiness_smoke_test --live-provider
```

This opt-in probe uses model credits: at most four SDK requests and USD 0.05 reserved under configured pricing, or lower configured limits. Production telemetry, pricing, timeout, output and retry controls apply. No institutional assessment is created. Router lease bookkeeping may occur. Investigate configuration, quota, pricing or budget failures before full documents.

The synthetic source states dated computing access and an explicit technical suitability shortfall. Expected: C6.1.F1 met and C6.1.F2 not_met. If these are the only resolved assertions, bounds are 16.67–83.33. Failure prints synthetic decision/validation reasons and exits nonzero. Passing checks the provider contract, not semantic quality across real PDFs.

## Fresh PDF acceptance test

1. Start a new assessment with a fresh idempotency key after deployment. Refreshing a saved assessment preserves its original protocol/results.
2. Use source-reported default scope unless deliberately testing a particular current population/period. Confirm the institution declared in the source when requested. Upload/report dates do not prove activity dates or current operation.
3. Retain the new export privately. Verify protocol versions above and actual provider/model telemetry. Never publish institutional quotations or exports in a public PR.
4. Inspect plainly supported enabling assertions in original PDFs and their exact supplied windows. Each genuine met assertion independently contributes 16.67 at indicator level; each not_met reduces its upper bound. Unknown counts as neither.
5. If every bound remains 0–100, classify the retained records: unavailable pages, omitted windows, identity/period mismatch, provider abstention or validation rejection. Compare original page → selected window → raw decision audit → validated decision. Do not change arithmetic to hide unresolved evidence.
6. Check the foundation pathway reuses strengths, omits verified work, separates conditional proposals from established shortfalls, and retains equal outcomes at every pace. Evidence-check answers/task completion do not change scores; reassessment does.
7. Check HTML/PDF and workspace agree, history remains immutable and repeated GET/download never dispatches paid work.

## Verification limits

Regression tests cover retrieval through actual scoring, same-page grounding, scoped conflicts, strength-grounded advice validation, immutable recommendations, protocol mismatch, report escaping and the rendered foundation pathway. Provider SDK tests use synthetic responses. The dry probe runs locally; this environment has not performed a fresh real-provider institutional PDF run. Bounded lexical retrieval and model accuracy require the deployed test above. These checks do not establish that every earlier product issue has been resolved.
