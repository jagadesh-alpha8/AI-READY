# Capability assessment diagnostics

Offline tools and tests for finding where a capability assessment loses evidence. Nothing here calls a model provider, writes run history or changes a score.

## Reading a wide score range

Under the current rubric each requirement is scored independently. The **lower bound** credits only `met` requirements. The **upper bound** credits every requirement except explicit `not_met` decisions. The evaluator is told that silence never establishes absence, so `not_met` is rare and the upper bound is usually 100. A range such as 7.1–100 therefore means "7.1 points demonstrated; the rest unresolved". The width is the weight of unknown and conflicting requirements, and the question is which pipeline stage left each one unresolved.

## Running the report

```bash
python manage.py capability_context_report <export.json> --database --output-dir <new folder outside the repository>
```

- `<export.json>`: the JSON export of a completed assessment (report → JSON).
- `--database` reads that run's frozen page text, stored tables and AI-QIF tags from the configured database, read-only. Without it, only the request-size and scoring checks run.
- `--gold <file.json>` adds the labelled-evidence funnel (below). It needs `--database`.
- The command refuses to write inside the repository: reports contain institutional text.

Outputs:
- `pipeline.md`: where evidence is lost, stage by stage, and how many points of the range each cause accounts for.
- `batches.md` / `batches.csv`: per-indicator request sizes, limits, token figures (actual, estimated and bound kept separate), and what the current code would send for the same windows.
- `diagnostics.json`: everything, including three traced requirements.

## Stages checked (`pipeline_diagnostics.py`)

| Stage | Question | Signal |
|---|---|---|
| Ingestion | Does the page text that assessment freezes contain the document's content? | Table placeholders (`AIOSTABLEMARKER…`; none since tables are rendered into evidence), characters missing against the canonical rendering (`evidence_text.evidence_pages`), pages under 300 characters. |
| Extraction | Do claim quotations occur in the page text they cite? | Quotation found in frozen text, only with tables, nowhere, or on a page outside the sources. Only quotations in frozen text can anchor a claim in a review packet. |
| Retrieval | Do the selected windows contain labelled evidence, and reach the pages the extraction layer tagged? | `retrieval_recall`: labelled quotations inside a selected window, by prose/table, with window count and duplicated text. Tagged pages selected, and a budget sweep against the chance expectation for selecting that share of text at random. |
| Context | Was the batch sent? | Pre-request limit, packet size and composition (`context_diagnostics.py`). |
| Model and validation | Did the model leave it unknown, and did validation downgrade it? | Cause per requirement: `model_unknown:*`, `validation_rejected`, `provider_failure`, `not_evaluated:*`. |
| Scoring | Do the saved decisions reproduce the reported range? | Engine replay, and width attributed to causes and to F/A/O levels. |

AI-QIF tags are the extraction layer's own, mostly automatic labels. They are a strong signal, not ground truth.

## Labelled evidence (gold file)

The most direct diagnosis is a short list of things you know the documents show. Copy each quotation from the PDF:

```json
[
  {"condition_id": "AIQIF-C1.3.F1", "page": 42, "quote": "exact words copied from the PDF", "document": "file name.pdf", "note": "why this is evidence"}
]
```

`document` can be omitted when the run has one document. For each item, the report gives the first stage that loses it:

`page_missing` → `quote_not_in_any_text` → `quote_only_in_tables` → `not_retrieved` (with the selection budget that would have reached it) → `batch_blocked` → `provider_failure` → `model_unknown` / `model_not_met` / `model_conflicting` → `validation_downgraded` → `credited`.

Twenty to forty items across several indicators, including some from tables, are enough to separate the stages. Keep gold files with the exports, outside the repository.

An item can name an `indicator` instead of a `condition_id` when you know the passage is evidence for the indicator but not for which requirement. It counts as credited when any of that indicator's requirements is met. `pipeline_diagnostics.provisional_gold` drafts such indicator-level items from the extraction layer's accepted direct and supporting AI-QIF tags whose quotations occur in the page text. Treat that draft as a starting point for people to review, not ground truth.

## Extraction fidelity gate

`extraction_fidelity` reports the share of claim quotations that occur verbatim in the text assessment reads, against a 90% threshold, and the same share once tables are rendered. Below the threshold, most reviewed claims can't anchor in a review packet however good retrieval is.

## Re-check with labelled pages supplied (oracle context)

```bash
python manage.py capability_oracle_check <export.json> --gold <file.json> --output-dir <new folder outside the repository>
```

This re-evaluates each indicator in the gold file with the production `evaluate()`, changing only page selection. Each batch receives the run's own selected passages plus a window around each labelled quotation, taken from table-rendered text. If a requirement is credited then but not in the saved run, retrieval or ingestion lost it; if it's still unknown, the model's judgement or the requirement's scope and period are the next place to look.

Without `--send` it is a dry run: it builds every request and reports the request count and estimated tokens, and contacts no provider. With `--send` it uses the configured provider (`AI_BASE_URL` / `AI_MODEL`), so check cost and data-handling terms first. Nothing is written to the database either way.

## Tests

- `apps.scoring.test_pipeline_diagnostics`: each stage on synthetic data, the labelled-evidence funnel, and score-range attribution.
- `apps.scoring.test_context_diagnostics`: request construction, review-semantics preservation, a 200-PDF scale simulation, production-path mirrors, and export safety.
- Reference run: set `CAPABILITY_REFERENCE_EXPORT=<private export.json>` to also replay a real saved run (hashes, blocked batches, score bounds, width attribution).

Saved runs replay with the construction that produced them: `context_diagnostics` keeps frozen copies of the page-projection packet (prompt AIQIF-EVAL-0.9) and of retrieval `assertion-balanced-windows-0.3` (`balanced_windows_0_3`), which also serves as the baseline when measuring retrieval changes.

Tests marked `expectedFailure` pin open defects. When a fix lands, the test passes unexpectedly and the suite fails until the marker is removed.

| Expected failure | Defect |
|---|---|
| `test_claim_quotations_occur_in_the_text_assessment_reads` (reference run only) | Under 90% of the reference run's stored claims are grounded in the page text assessment reads. |
| `test_cross_document_conflict_does_not_block_batches_at_200_pdfs` and two related growth tests | Every alternative of an applicable conflict joins the packet, so conflicts spanning many documents grow requests. |
| `test_every_advice_item_declares_whether_it_is_deterministic_or_model_tailored` | Model-tailored advice carries no origin label. |
| `test_unevaluated_requirement_is_not_advised_as_missing_institutional_evidence` | A requirement that was never evaluated is advised as missing evidence. |
