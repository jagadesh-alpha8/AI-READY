# ADR: source-grounded passage retrieval for A1

Status: implemented as an explicitly selected experimental hybrid. BM25 remains the operational default.

## Findings and limits

The supplied private reference report demonstrates lower gold recall for the previous hybrid than BM25; its detailed institutional results remain outside the repository. It does not establish which encoder/ranking stage caused each loss. No private reference corpus or gold file is available in this workspace. PR16 improves fusion and recommendation isolation, but still embeds character windows and treats passage construction as part of indicator selection.

Code inspection establishes several structural limitations: character counts do not bound encoder tokens; windows can separate a rendered table's header from its rows; window generation/ranking repeats per indicator; broad indicator terms influence every condition; and rubric assertions such as "that priority" are not self-contained semantic queries. None of those observations proves a particular reference label's loss. Planned versus operational, scope, period and contradiction require assessment of evidence, not a cosine threshold.

## Alternatives

- A larger encoder alone leaves broken passage boundaries, missing headings and packing unchanged. Retain provisioned BGE-small initially; diagnose its actual inputs before a model replacement.
- More weighted RRF alone addresses neither representation nor independent requirement coverage.
- A cross-encoder adds another artifact and inference stage. Defer until candidate recall and selection diagnostics show a useful candidate set that it could improve.
- A vector database adds operations and persistence without a scale/concurrency requirement. A deterministic per-execution passage store and matrix cache suffice for the current corpus.
- Hosted embeddings expose institutional evidence to another service. They are not introduced.

## Selected architecture

Keep deployed BM25 unchanged as the operational control. Explicit hybrid uses a separate source-grounded pipeline:

1. Construct a reusable page-local passage store independent of indicators. Split prose at paragraph/sentence boundaries; group table rows under their actual rendered header. Use the provisioned tokenizer with padding/truncation disabled for construction, targeting 240 tokens and enforcing the model's actual input limit with a 32-token safety margin. Split oversized units by real token offsets with bounded overlap. Preserve every body span as an exact original page slice.
2. Keep retrieval text separate from citable text. Embeddings may prepend the actual local section/table heading. Each heading carries its own source offset; a table also carries its preceding page-local section/period heading. Final packets include those original heading spans, charged to the same budget; synthetic embedding strings are never citable quotations. Page-local headings do not fabricate cross-page context.
3. Generate a small deterministic query set per requirement. Preserve the assertion; resolve demonstrative/pronominal references with the immediately preceding assertion. Every one of the 216 current requirements has a reviewed evidence-record description in retrieval_profiles_v1.json. Pair that description with the assertion (contextualised where needed); both receive a query slot. The profiles list alternative source record types and aliases, never additional pass criteria. Validate exact coverage and assertion text, freeze the profile version/checksum and reject mismatches. Use profile vocabulary with a modest separate lexical weight, while keeping assertion terms primary. Do not prepend the broad indicator title to every assertion. No hosted query generation. For English BGE v1.5, add its documented retrieval-query instruction only to queries. FastEmbed 0.9.1's generic ONNX adapter does not add that instruction. The [official model card](https://huggingface.co/BAAI/bge-small-en-v1.5) also says v1.5 can work without it: omission is not proof of the reference regression. Freeze and expose the actual encoder query strings. Other model families retain their native FastEmbed query encoding.
4. Rank the same passage store lexically and semantically. Lexical scoring separates assertion/context terms, low-weight curated indicator terms and bounded extraction hints. Diagnostics expose raw and boosted scores/ranks. Encode every passage once per execution; normalized matrix multiplication ranks all passages for each cached query. Same-page exact/contained-span consolidation precedes fusion; partially overlapping passages keep their unique tails, while final merging charges only unique characters. Cross-page copies retain independent provenance because their scopes or periods may differ. Semantic ranking finds relevance, not truth or readiness credit.
5. Form diversified lexical and semantic shortlists; fuse with fixed lexical-favouring RRF (2:1, k=60), retaining lexical candidates independently. Select per requirement in rounds, with a lexical protection allocation, semantic expansion and remaining fused candidates. Account for exact unique body/heading spans in a shared 18,000-character budget. Clip neither evidence bodies nor headers merely to fill the last few characters. Record rejection/coverage/budget decisions.
6. Expand small retrieved bodies to their construction unit, not arbitrary neighbouring text; heading spans preserve interpretive context. Exact source IDs/offsets pass unchanged to current citation/review validators and the evaluator. Semantic component failure fails the frozen hybrid execution; it never silently substitutes BM25.

## Flow

```mermaid
flowchart TD
    S["Frozen source pages"] --> P["Exact body and heading spans"]
    P --> L["Lexical index"]
    P --> E["Token-bounded embedding inputs"]
    Q["Requirement queries"] --> L
    Q --> E
    L --> C["Diversified candidate union"]
    E --> C
    C --> B["Requirement rounds and span budget"]
    P --> B
    B --> A["Assessment and exact citation validation"]
```

## Costs and constraints

This adds deterministic passage/tokenizer work and a per-execution vector matrix; corpus text and vectors stay local. The store is reused across all indicators and recommendation batches within that execution, not across institutions or mutable documents. There is no persistent index. Stable content hashes bind cache identity to source text and offsets.

Table rendering still depends on ingestion: absent/incorrect cells or headers cannot be recovered downstream. Oversized individual rows may need token splits; diagnostics expose that limitation. Source-period interpretation and relevance-versus-entailment remain evaluator responsibilities. The preceding-assertion anchor is an exposed retrieval heuristic, not a guaranteed pronoun-resolution result. The original rubric assertion still controls assessment. The fixed lexical allocation is a candidate policy, not a guarantee of retaining all baseline evidence. The existing labels are a debugging/regression set, not a fresh holdout.

## Verification and release

Test token-dense text, oversized units, row/header retention, reference-resolving queries, exact quotation provenance, independent requirement coverage, deduplication, bounded packing, input-change cache invalidation and explicit semantic failures. Run the real provisioned model offline, the scoring/recommendation suites and backend suite. Retain PR16's per-item recommendation repair and origin labels.

Extend private offline comparison with raw/boosted BM25 ranks, semantic similarities/query variants, exact encoder input/token counts, headings/body offsets, packing outcomes, candidate-vs-packet recall, gain/loss item identities and timing/cache statistics. Add readable per-item and aggregate traces. Report observed stages separately from hypotheses requiring manual relevance judgement.

The SWE must run reference comparisons on the private corpus under the same budget, inspect prose/table gains and losses and manually judge representative false semantic matches. Do not promote hybrid or claim institutional recall improvement from synthetic tests. Keep Gemini integration separate from encoder evaluation; it remains the agreed evaluator/extraction/recommendation provider choice, not a retrieval fix.

Verification results and exact test counts are recorded in the PR. The real-encoder dense-numeric test demonstrates that a 1,200-character string can exceed the encoder limit, while constructed inputs remain untruncated and reuse their vectors. These are implementation contracts, not private reference recall measurements. PostgreSQL and frontend CI remain merge requirements.

## Evidence-seeking profiles follow-up

The empty rubric evidence-query/example fields left assertion wording as the primary query language. A separate versioned profile pack now covers all 216 assertions, with descriptions of relevant source records (budgets, registers, computing access, curricula, governance decisions, outcome comparisons and follow-up checks). Each profile is bound to the exact assertion text. General enabling capacity remains general: computer access does not become AI adoption, and IQAC/academic reviews do not require this product. Source records are alternatives, not mandatory document titles.

The paired query design reserves one slot for the profile and one for the assertion; referential assertions cannot consume both slots and starve the profile. Lexical traces expose the profile contribution separately from contextual assertion scores, indicator terms and extraction hints. The frozen policy includes the profile checksum, and the retrieval protocol version changes with the new query policy. No scoring thresholds, rubric assertions, provider configuration or frontend contracts change.

These are manually authored retrieval descriptions, not a domain-trained relevance model. They can still retrieve plans or irrelevant topical matches; existing assessment/citation checks determine what the evidence establishes. The private regression run must inspect profile-versus-assertion rankings and gained/lost evidence before any hybrid promotion.

The offline comparison adds a single `profiled_bm25` ablation: new source passages and evidence profiles with no passage/query embedding inference. Comparing this with hybrid helps separate representation/query gains from the semantic route. It adds no live retrieval mode and makes no evaluator calls.
