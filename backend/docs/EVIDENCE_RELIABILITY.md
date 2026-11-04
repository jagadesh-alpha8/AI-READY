# Evidence reliability after PR14

## Current facts and re-extraction

A complete successful extraction reconciles observations for that document. An absent unreviewed or system-confirmed observation is retired from active facts, tag queues, coverage and assessment review context. It remains available through `ExtractedFact.all_objects` (and mappings through `FactAIQIFMapping.all_objects`) for provenance; it is not a second current observation. Reappearance reactivates the same scoped machine observation when the existing identity rules match it.

Partial, failed, cancelled and interrupted processing does not retire absent observations. Final reconciliation is transactional and locks the document and job. Human-confirmed/corrected/rejected decisions retain their recorded values and dispositions. If the cited source in the reprocessed document no longer supports a retained decision, `source_review_required` is set and exposed in the API/UI. Reverification can clear it only when the verification result is verified. It is excluded from coverage and grounded retrieval hints while flagged. Independently supported new evidence can still establish a requirement.

Retired observation tasks are resolved with an audit event. A linked conflict is kept and pointed at current alternatives if a same-scope contradiction remains. The full active corpus is also reconciled by the existing assessment ledger.

Migration: `python manage.py migrate` applies `facts.0019_fact_extraction_lifecycle`. No historical-report conversion or data backfill is included.

## Bounded conflict context

The frozen ledger remains complete. Each model packet contains at most 20 selected/representative claim records, 8 conflict summaries and 8 review answers, under a 24,000-character JSON ceiling. Each conflict reports how many alternatives are omitted. Narrative fields are clipped for context; they are not quotations.

All rejected/corrected/source-review and unresolved-conflict controls are checked against the full frozen ledger by the citation validator, even when their details are omitted from the model packet. Omission never resolves a disagreement. The 200-document tests now verify a bounded request instead of pinning expected failures.

## Citation fragments

Separate exact citations remain preferred. A joined citation can be normalized only when every fragment is at least 20 characters and all fragments occur in the supplied order within one supplied window. Fragments may not span separate windows, even if they have the same source ID. Each accepted fragment becomes a separate exact citation, then passes the full review-control validator. Original model responses remain in the audit record. These rules apply to assessment decisions and recommendation factual bases.

## Local hybrid retrieval

The default is always BM25, including when an operator provisions a local embedding model. No weights or institutional embeddings are committed to this repository. Provision on the worker host:

```sh
pip install -r requirements/semantic.txt
python manage.py prepare_capability_embeddings --cache-dir /absolute/model-cache --download
```

The command prints `CAPABILITY_EMBEDDING_PATH`. Set that directory in the web and worker environment. Installing a model does not activate hybrid. Keep `CAPABILITY_RETRIEVAL_MODE=bm25` for normal assessments. Set `CAPABILITY_RETRIEVAL_MODE=hybrid` only for an explicitly enabled candidate run after private evaluation. Restart the web/worker processes and start a fresh assessment.

Model: `BAAI/bge-small-en-v1.5`, CPU through FastEmbed 0.9.1. Only the explicit preparation command downloads public model files. Workers use the provisioned directory with `local_files_only=True`, never hosted embeddings. Freeze an immutable model directory and do not replace its files while workers are running.

Each run freezes the model identity, artifact SHA256 and library version. Workers reject mismatches or unavailable hybrid artifacts; they do not silently downgrade to BM25. Embeddings of source text and queries are cached in memory per run, not in a cross-institution/global source index.

Hybrid v2 protects lexical passages first, targeting half the character budget (at least one window for small budgets), with a turn for each requirement. It then adds a semantic passage per requirement and fills remaining space with requirement-specific weighted reciprocal-rank fusion (k=60; lexical weight 2, semantic weight 1; top 60 diversified candidates per route). Near-duplicate windows with more than 50% overlap of the shorter span do not occupy multiple fusion slots. Semantic queries use the requirement text without a broad indicator-name prefix. These fixed choices are an experimental candidate, not a measured recall guarantee; protection cannot retain every BM25 passage within an unchanged budget. This is rank fusion, not a cross-encoder reranker. Local semantic windows use 1,200 characters; BM25-only windows retain 1,800 characters. Selected overlapping passages merge; source text is never rewritten. The overall budget stays 18,000 characters per indicator. Assessment traces and exports expose the frozen retrieval policy. Recommendation generation uses that same policy.

### Offline reference comparison

With a fresh table-inclusive frozen run in the local database:

```sh
python manage.py capability_retrieval_compare RUN_UUID \
  --gold /private/gold-development.json \
  --holdout-gold /private/gold-held-out.json \
  --output /private/new-retrieval-comparison.json
```

Use a new output path outside the repository. The command reads the database, runs local embeddings and writes a private comparison. It makes no evaluator requests or database changes. It explicitly constructs an offline hybrid policy even while the live setting remains BM25. It compares BM25 at 1,800 characters, BM25 at 1,200 characters (window-size ablation), and hybrid at 1,200 characters, all at the same total budget.

The private JSON also contains `gold_traces` per label: actual requirement query, best raw BM25/semantic/fused ranks of windows containing the quote, five nearest semantic passages, exact embedding inputs, tokenizer coverage when available, and passage-packing attempts. Candidate absence is reported separately from ranked-but-not-selected and budget/partial-passage losses. These are diagnostic observations, not proof that a document lacks evidence. Tokenizer probes report truncation; they do not establish that table headings are meaningful. Gold labels are used only after retrieval; they never select passages.

Each gold file is a list of `{condition_id, page, quote, document_id?, document?, evidence_type?}`. A document UUID or unique manifest filename is required when a page number is ambiguous. Every labelled quotation must occur on its frozen page. Development and held-out labels must not overlap. Gold tags are not generated from extraction tags. No institutional recall improvement is claimed until this command runs on the private reference corpus; a synthetic paraphrase smoke test is not a substitute.

## Recommendations

The foundation pathway now displays two separate tracks in the application and HTML/PDF reports:

- **Establish what exists**: evidence checks and assessment-specific follow-up.
- **Improve capability where needed**: actionable proposals, explicitly conditional where current capability is unresolved, with verified strengths retained as the basis for reuse.

Unknown is not absent. Evidence-gathering steps do not automatically become development tasks; conditional proposals do not change scores or award achievement levels. Existing owners and resources are not invented.

### Item-level validation and repair

The recommendation schema restricts requirement, operation, dependency and source IDs to the batch. Responses are validated per item; unsupported citations, duplicates, missing items and changed operations affect their own requirement rather than valid neighbours. A single metered corrective generation requests only failed requirements. It cannot overwrite accepted advice. Dependency cycles are checked again after merging; a repair that creates a cycle loses its new edge-bearing item before accepted neighbours. Unrepaired items use explicitly labelled deterministic fallback. Citation and operation checks remain strict.

Completed recommendation payloads expose `validation`: initially invalid item counts, repair-attempted batch counts, repaired item counts, final fallback item counts and per-indicator IDs/reasons. These counts measure validation and recovery, not prose quality. Only `origin=model_tailored` is labelled tailored in reports; deterministic fallback and processing follow-up remain basic guidance. Unknown actions remain evidence checks, and conditional development remains in the foundation pathway. No recommendation changes an assessment score.

## CI

The old PR14 PostgreSQL log shows the 22 targeted database tests passed. Its later full parallel suite failed on an extraction fixture, followed by a traceback-pickling error. Add `tblib` to preserve parallel worker exceptions. PostgreSQL CI now includes the new reliability contracts, is required rather than informational, and gates container builds alongside the other checks.

Run the real PostgreSQL job to verify production-database behavior; SQLite does not exercise its row locks. No local PostgreSQL result should be inferred from the SQLite suite.
