# A1 retrieval and recommendation verification

This change incorporates PR16 recommendation repair and redesigns experimental hybrid retrieval around token-bounded source passages. Read ADR_EVIDENCE_RETRIEVAL.md before reviewing the retrieval changes. Target A1 only. Do not change main. It does not install a different embedding model, configure Gemini credentials, or claim improved institutional recall from synthetic tests.

## Review and merge

1. Review the PR against current A1, including any concurrent provider configuration work. Require backend, PostgreSQL and frontend CI checks to pass. Resolve code issues on the PR branch. Merge only into A1.
2. Back up the development database and environment. Use a database copy for reference-document assessments and recommendation calls. No new migration is introduced by this PR; run `python manage.py migrate --check` to confirm the checkout and database agree.
3. Keep `CAPABILITY_RETRIEVAL_MODE=bm25` in web and worker environments and restart both after pulling A1. Installing embeddings no longer activates hybrid. New assessments must record `inputs.retrieval_policy.mode=bm25`.
4. If the provider is being switched to Gemini, verify the actual supported model ID, credentials, structured output, pricing and usage metering first. Configure extraction, capability assessment and recommendations consistently. The local embedding model is separate. Do not introduce model-comparison experiments or silently fall back to another provider.

## Automated checks

From `backend`, in the project virtual environment and the same test configuration as CI (`DEBUG=True` locally). Clear a local `AI_PRICING_JSON` override for the tests, then restore deliberate development pricing afterward:

```sh
python manage.py test apps.scoring.test_passage_architecture apps.scoring.test_retrieval_advice_repair apps.scoring.test_evidence_reliability apps.scoring.test_recommendations apps.scoring.test_context_diagnostics apps.scoring.test_report_projection --parallel 4
python manage.py test --parallel 4
```

Also run the real local model test with `CAPABILITY_TEST_EMBEDDING_PATH` pointing to the provisioned immutable directory and `HF_HUB_OFFLINE=1`. A skipped test is not proof that the local model works. The real-model suite also tests dense numeric passages against the actual tokenizer limit and verifies execution-local embedding reuse. PostgreSQL CI is required; SQLite does not verify its locking behavior.

## Offline private retrieval diagnostic

Use the existing table-inclusive frozen reference run and the manually checked development/held-out gold files. Resolve its full run UUID; an abbreviated UUID is not accepted. The application may stay on BM25 throughout this command:

```sh
python manage.py capability_retrieval_compare RUN_UUID \
  --gold /private/gold-development.json \
  --holdout-gold /private/gold-held-out.json \
  --output /private/new-retrieval-comparison.json
```

Use actual absolute paths for the machine. Output must be a new file outside the repository. This command reads frozen evidence, performs local embeddings and writes the private report; it makes no evaluator requests or database writes.

Report the three methods at the same 18,000-character budget: BM25/1,800, BM25/1,200 and candidate token-bounded hybrid passages. Include retrieved item counts, prose/table groups, character totals and overlap. Compare item identities as well as totals: improved aggregate recall can hide lost evidence.

For every missed label, inspect `gold_traces`: its query, matching candidate text, lexical/semantic/fused ranks, packing attempts, tokenizer truncation and the five nearest semantic passages. Determine whether the evidence is absent from candidate windows, ranked poorly, or excluded by requirement allocation or the whole-passage budget. Look at table headings in the actual embedding input. A tokenizer probe does not establish whether a table is meaningful. If tokenizer inspection is unavailable, report it explicitly.

The command writes both JSON and a readable Markdown report. Check raw versus contextual/term/hint-boosted lexical scores, gain/loss item IDs, per-method time and model-load time. `vector_bytes` measures the vector matrix only; measure worker peak RSS separately on the reference run. Inspect per-query similarities and cache statistics. Check whether table/section headings are clipped and whether any oversized row is split. Gold traces explain the candidate implementation, not an exact reconstruction of the previous hybrid algorithm. Keep the previous saved comparison as the historical baseline. Existing labels already inspected during tuning are a regression set, not a fresh independent validity study. Do not enable hybrid merely because CI or a paraphrase smoke test passes. Keep BM25 active if the candidate fails to improve grounded retrieval or loses important evidence.

## Fresh assessment and recommendation checks

Run one fresh reference assessment on the database copy using BM25 and the agreed provider, then explicitly generate a new recommendation version. Existing saved outputs are not regenerated by changing settings. Confirm:

- Table-inclusive evidence is still present, quotation fidelity remains intact, and no batches are context-blocked.
- Selected gold evidence and credited decisions are counted separately. Unknown requirements are not counted as missing passages. Audit unknown causes using existing per-batch/pipeline reports; distinguish model/validation failures, conflicts, scope/period limitations and insufficient evidence in supplied passages. Do not infer absence from retrieval misses.
- The recommendation execution completes and contains exactly one item per planned action, without foreign or duplicate requirement IDs.
- `tailoring.validation` reports `initial_invalid_items`, `repair_attempted_batches`, `repaired_items`, `fallback_items` and per-indicator details. Good initial recommendations survive; correction requests contain only failed actions. At most one corrective generation occurs per batch, with all actual provider requests subject to frozen caps and metering.
- Unsupported citations never survive. Each basis is an allowed exact action/strength citation or a validated quotation from supplied text. Dependencies reference batch actions and are acyclic after merging.
- Unknown actions remain evidence-gathering requests; conflicts request reconciliation; documented shortfalls may receive capability improvements. Conditional foundation proposals remain clearly separate, with no automatic score credit.
- Only `origin=model_tailored` is presented as tailored in API/HTML/PDF. Fallback or processing follow-up must not receive that label. Inspect a mixed batch and an all-fallback example through automated tests; do not deliberately corrupt the reference database to produce failures.
- Manually inspect at least ten recommendations across indicators: direct successes, repaired items and fallbacks where present; include evidence requests and conditional improvement advice. Check specificity, useful steps, feasible suggested roles, completion evidence and whether existing documented assets are reused. Passing validation alone does not establish usefulness.
- Export JSON and leadership HTML/PDF; check the displayed advice, origin labels and evidence/development distinction. Record provider/model, requests and total cost.

If hybrid shows a clear offline improvement and no material evidence regression, a separate explicitly enabled hybrid assessment on the copy can validate downstream decisions. Do not spend evaluator calls testing a hybrid candidate that already loses evidence offline. Do not change score-bound rules to make the score higher.

## Return report

Return the merge SHA, CI and local test results (including skips), retrieval counts by split/type and gained/lost label IDs, explanations for representative semantic failures, recommendation validation/repair/fallback counts, a short qualitative recommendation audit, remaining unknown causes, and total cost. Identify unresolved defects explicitly. Keep all institutional quotations, labels, database copies and reports outside the repository and PR discussion; share them privately.
