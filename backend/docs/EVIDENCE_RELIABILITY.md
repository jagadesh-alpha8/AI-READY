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

Experimental hybrid uses a separate source-grounded passage pipeline; see [the architecture decision](ADR_EVIDENCE_RETRIEVAL.md). It constructs sentence/row-aware, overlapping source spans once per execution, targeting 240 tokenizer tokens while bounding the complete encoder input by the actual model allowance. Embeddings carry actual page-local section/table headings; citable bodies and heading spans retain original source offsets. Both consume the same 18,000-character final budget. Whole units are selected without truncating them to fill remaining space.

Queries now pair each of the 216 assertions with a versioned evidence-record description. Referencing assertions retain preceding-assertion context without consuming the profile slot. The paired queries remain bounded to two; profiles name alternative record types and aliases, not additional scoring requirements. Full coverage and exact assertion text are validated, and the profile version/checksum is frozen in each hybrid policy. English BGE v1.5 queries receive its documented query-only instruction. Other FastEmbed model families retain their native encoding. Raw lexical relevance, the modest evidence-profile contribution, low-weight indicator terms and extraction hints are separately recorded. Same-page exact/contained candidates are consolidated before fixed weighted RRF (2:1, k=60). Selection protects a lexical allocation, takes semantic turns per requirement and fills with fused candidates. These are experimental policy choices, not measured private recall guarantees.

The passage store and normalized vector matrix are reused across indicators within one execution and invalidated when source inputs change. No vector database or shared institutional embedding cache is added. The frozen policy identifies representation, query protocol, instruction, fusion, model artifact and package version. Semantic failures never silently change a frozen run to BM25. Recommendation generation uses the same retrieval policy and retains item-level repair.

### Offline reference comparison

With a fresh table-inclusive frozen run in the local database:

```sh
python manage.py capability_retrieval_compare RUN_UUID \
  --gold /private/gold-development.json \
  --holdout-gold /private/gold-held-out.json \
  --output /private/new-retrieval-comparison.json
```

Use a new output path outside the repository. The command reads the database, runs local embeddings and writes a private comparison. It makes no evaluator requests or database changes. It explicitly constructs a candidate hybrid policy while the application stays BM25. At the base budget (default 18,000) it compares BM25/1,800 windows, BM25/1,200, unprotected `profiled_bm25`, and baseline-protected `hybrid_passages`. At the expanded budget (default 24,000) it compares `bm25_expanded`, `protected_profiled_expanded` and `hybrid_expanded`. Check expanded hybrid against expanded BM25, not just the smaller baseline. Gold traces describe expanded hybrid; they expose baseline versus discovery retrieval, skipped instruction-only inputs and actual character totals. Any protected method losing baseline gold evidence fails the command.

Use `--expansion-budget 0` for a zero-expansion comparison, or the default 6,000 for the proposed production hybrid allowance. `--budget` is an explicit offline baseline override and does not change live settings. Add `--include-replay-inputs` to include the complete private frozen corpus and labels for independent offline replay. Never commit or publish that output. A report containing only selected excerpts cannot reproduce full-corpus rankings.

The private JSON also contains `gold_traces` per label: actual requirement query and actual encoder instruction, raw/contextual/boosted BM25 scores and ranks, per-query semantic similarities and fused ranks of windows containing the quote, five nearest semantic passages, exact embedding inputs, tokenizer coverage when available, and passage-packing attempts. Candidate absence is reported separately from ranking/allocation, duplicate consolidation and whole-unit budget exclusions. These are diagnostic observations, not proof that a document lacks evidence. Tokenizer probes report truncation; they do not establish that table headings are meaningful. Gold labels are used only after retrieval; they never select passages.

Each gold file is a list of `{condition_id, page, quote, document_id?, document?, evidence_type?}`. A document UUID or unique manifest filename is required when a page number is ambiguous. Missing labelled quotations are reported as source-text loss signals rather than rejected; a person must distinguish ingestion loss from an incorrect label. The command also writes a readable `.md` alongside its new `.json`, aggregate observed stages, gains/losses relative to BM25 and timing/cache statistics. Development and held-out labels must not overlap. Gold tags are not generated from extraction tags. No institutional recall improvement is claimed until this command runs on the private reference corpus; a synthetic paraphrase smoke test is not a substitute.

## Candidate audit and private replay

The comparison accepts a previously exported private corpus directly:

```sh
ORT_DISABLE_TELEMETRY=1 PYTHON_DOTENV_DISABLED=1 HF_HUB_OFFLINE=1 \
python manage.py capability_retrieval_compare \
  --replay-inputs /private/comparison-with-replay.json \
  --output /private/new-candidate-audit.json
```

This route omits the run UUID and gold-file options, validates embedded labels,
and never reads the assessment database. Its replay-content hash identifies the
supplied corpus and labels; it does not independently verify the original run's
entire snapshot hash. Model files must already be provisioned locally.

Candidate recall is reported at 5, 10, 20, 60 and 100 candidates per route, both
for the labelled requirement's queries and the union of queries for its whole
indicator. Raw lexical/profile/semantic pools are distinguished from eligible
filtered/diversified pools. Pool sizes accompany hits: a large union can have
high recall without good ranking or affordable reranking. These label-aware
measurements never influence production selection.

The labelled-packet oracle chooses the shortest matching candidate per label
and counts unique body/header spans. It shows physical feasibility for these
labels only. It is not production retrieval, a global optimum, or a statement
that evidence for every requirement would fit. A `context_budget_excluded`
observation alone does not distinguish weak ranking from an inadequate budget.

Gold quotation inclusion is a relevance target. Degree titles, aggregate patent
counts, document upload lists and generic feedback claims can be useful leads
without establishing all parts of a scored assertion. Keep retrieval labels
separate from independently adjudicated expected assessment decisions. Do not
remove difficult retrieval targets to improve a benchmark or infer a met state
from a matching quotation alone.

### Requirement-level support cases

Add `--evidence-cases /private/requirement-evidence-cases.json` to the comparison
to measure known support-bundle coverage separately from exact quotation recall.
The private pack uses version `requirement-evidence-cases-1`, pins
`source_corpus_hash` and `rubric_hash` using the canonical snapshot digest, and
contains one case per requirement. Each case preserves the exact assertion,
lists `positive_bundles`, and lists `insufficient_controls`.

A positive bundle has an ID and source citations (`document_id`, `page`,
`quote`). All quotations in one bundle must be present; any alternative bundle
can satisfy the known-support check. Quotations are validated against their
frozen page before the encoder loads. A control includes its citations, reason,
and `expected_on_this_packet` of `unknown` or `adjudication_needed`. Controls
describe isolated evaluator test packets, not the expected state of a production
packet that might also contain positive evidence.

Cases with no verified positive bundle are excluded from the positive-coverage
denominator and reported explicitly. Their absence is not a not-met finding.
The result preserves the pack's review status and hash. Provisional
model-assisted bundles are not independently adjudicated gold; alternatives
may be incomplete, and a missing known bundle does not prove context is
inadequate. This diagnostic does not test evaluator decisions or award score.
Positive assertion support still requires matching population and period.

Keep institutional case packs and results outside the repository. Generic
synthetic contracts exercise alternative support, multi-citation bundles,
provenance, controls, hash binding and stale assertions.

ONNX Runtime telemetry is disabled before encoder import in application settings
and the model loader. Set `ORT_DISABLE_TELEMETRY=1` before starting an offline
process too: disabling events via the API after import alone can be too late for
an initialization event. This follows the installed runtime's Privacy.md and
https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md .

Rendered `[Table ... -- columns: ...]` lines can contain substantive narrative
cells. Discovery strips only the generated wrapper when classifying the payload;
source text and offsets are preserved. Caption-only narratives and long split
captions are covered by regression tests. The frozen filter policy is version 2.

## Lexical retrieval correction

Lexical retrieval retains `review` as a content term. Removing it as boilerplate
can erase the activity in an assertion and rank subject-only material above a
review of that subject. A synthetic regression distinguishes a review from a
catalogue that repeats the subject words, under the same character budget.
The source-passage protocol is version 4; protected hybrid's fusion identifier
is also version 4 because its protected lexical baseline changes. Budgets,
scoring assertions and the operational BM25 default are unchanged.

Case-pack corrections must change the data as well as reviewer notes. Move
disputed support into an `adjudication_needed` control rather than leaving it
in `positive_bundles`; otherwise it still inflates the positive denominator.
New alternative evidence found after inspecting retrieval is useful regression
coverage, not an independent held-out quality estimate.

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
