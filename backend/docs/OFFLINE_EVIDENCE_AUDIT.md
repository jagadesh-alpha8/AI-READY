# Offline evidence selection and consumption checks

These commands prepare or replay private diagnostics. They do not call an evaluator,
change the active retrieval mode, write assessment records, or establish semantic
assessment accuracy. Keep inputs, outputs, source excerpts and labels outside Git.

## Matched candidate selection

With the local encoder and cross-encoder already provisioned, run from `backend`:

```bash
HF_HUB_OFFLINE=1 PYTHON_DOTENV_DISABLED=1 ORT_DISABLE_TELEMETRY=1 \
CAPABILITY_EMBEDDING_PATH=/private/provisioned-encoder \
python manage.py capability_selection_experiment \
  --replay-inputs /private/frozen-replay.json \
  --evidence-cases /private/reviewed-cases.json \
  --reranker-path /private/provisioned-reranker \
  --output /private/new-selection-result.json \
  --budget 18000 --depth 60 --max-pairs 30000 --max-seconds 1200
```

The supported diagnostic scorer is the previously investigated
`Xenova/ms-marco-MiniLM-L-6-v2`, loaded locally with downloads disabled. This is
an experimental comparator, not a recommended production reranker. The experiment
records model artifact hashes and rejects query/passage pairs exceeding 512 tokens.
The time allowance is checked between scoring batches; an in-flight local batch
can exceed it. No global runtime limit is changed.

Three arms are reported:

- Corrected plain BM25 at the specified final character budget.
- Profiled lexical candidates on token-aware passages, reranked locally.
- The union of those lexical and semantic candidates, using the same scorer.

The latter arms share full-indicator requirement queries, source representations,
per-requirement scores, round-robin packing and final budget. All companion
requirements participate, including unlabelled conditions. Their candidate pools
are indicator-wide unions of each requirement's eligible top-depth routes.
Semantic additions cannot silently use a larger packet. Heading spans pay for
context; same-source overlap merges; identical text from different source IDs
retains independent provenance. Production baseline protection is deliberately
not applied to these replacement-selector experiments.

The union is scored once and scores are reused for the lexical subset. Actual
shared pair count and latency, equivalent arm pair counts, candidate provenance,
queries, rankings, packing attempts and exact final excerpts are recorded. Shared
latency is not separately timed lexical-only performance. Quotation gains over
the lexical arm are diagnostic; review their source and bundle significance before
calling them a semantic benefit. Positive support coverage, quotation recall and
model interpretation remain distinct. Inspected labels cannot demonstrate
held-out generalization.

## Prepared packets and recorded decisions

```bash
python manage.py capability_evidence_audit /private/probe-input.json \
  --output /private/new-consumption-audit.json
```

Input has `rubric`, the complete frozen `reviewed_evidence` ledger, and a
`requests` list. Each request has `id` and its exact `payload` containing
`indicator`, `sources`, and `reviewed_evidence`. An optional `payload_hash` is
verified. Frozen condition objects must match the rubric exactly. Optional
`response` and `advice` are recorded replay inputs; neither proves a provider call.

Without a response the result is explicitly `prepared_unexecuted`; no decision,
score or synthetic model outcome is created. With a response, the exact packet
and full ledger drive production `validate_decisions` and `response_audit`.
Rebuilt review projection must match the prepared packet before a response can
be replayed. Results preserve raw and validated decisions, citation and
scope/period failures, deterministic scoring with all companion requirements
explicitly unknown, and expected recommendation kind/operation. Supplied advice
is preserved for inspection, not regenerated or semantically certified. The score
is a packet diagnostic, not an institutional assessment or an additive allocation
across independently replayed packets.

Attachment diagnostics distinguish source quotation overlap, original correction
quotation overlap, off-window conflict context, bounded-packet omission, conflict
alternative limits and no overlap. They preserve source lifecycle, dispositions,
scopes, original/current quotations and references. These reasons explain review
control selection, not relevance to an assertion. Resolved issues without current
claim IDs cannot serve as resolved-alternative tests. Use explicit synthetic
contract tests for that lifecycle until a real reviewed case is available.

Production evaluation traces additionally retain the actual bounded review packet
and attachment audit. This increases private trace/export size; it does not enlarge
model input, select additional evidence or grant credit for confirmation. Existing
raw/correction response audits remain the decision authority.

## Multi-year table scope

A table header listing multiple academic years cannot deterministically date every
cell to its first year. A date explicitly named in the fact field is preferred;
otherwise an unambiguous quotation date is used. Multiple header years leave the
deterministic period unknown. A stated extracted cell period may distinguish
claims and remains labelled `extraction`; it does not establish activity currency.
Re-freeze evidence after this change to obtain new scope projections. Existing
frozen ledgers and saved conflict resolutions are never silently rewritten.
