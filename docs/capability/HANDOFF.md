# Working handoff: continue capability assessment on A1

Continue implementation rather than restart the audit. Work only on A1. Never push main, merge to main,
or deploy production without explicit authorization. A1 (letter A, digit 1) is the user's confirmed branch.

Read `IMPLEMENTATION_PLAN.md` in this folder first, then inspect the branch diff/log and current tests.
The initial foundation is under `backend/apps/scoring/capability/`; it is not connected to the UI or DB yet.
Finish persistence/evidence adapter, async API, grounded LLM recommendation tailoring, administrator UI,
exports and update handling. Tests must cover all 36 indicators. Do not narrow implementation to a pilot.

The product is an automatic AI readiness assessment for colleges, using NAAC and supplementary evidence.
Required outputs: current capability, next improvements and Silver/Gold/Platinum pathways. LLMs perform
substantive evidence interpretation and contextual recommendations; code calculates scores and tiers.
No consultant approval gate. Preserve historical facts, sources, reviews, scores and rubric versions.
Unknown evidence is not failure. Confidence is not capability. General NAAC compliance is not AI capability.

The branch's engine uses 0/L3/L2/L1 = 0/100/3/200/3/100 with exact Fraction comparisons. Missing/conflicting
requirements permit bounded uncertainty. Headline incomplete assessment is a minimum/range, never an
assessed-only average. Tiers have proposed thresholds 40/65/85 plus pillar floors and gates. Related
indicator lists are soft links, not prerequisites (the old lists have cycles).

The audit and discussion documents are in ChatGPT Library:
- AI_Readiness_MVP_Rubrics_v0_1.md: libfile_04ccc8ddeab0819186870b5f8d6ae116
- AI_Readiness_Spec_Audit_v0_1.md: libfile_384c99b2bfd48191bdea1e5eb18f2bcf
- AI_Readiness_Product_Change_Brief.pdf: libfile_04f044cae71c819197f982ee30058e5c

Relevant existing components: scoring/services/cri_engine.py (legacy confidence-based CRI),
assessments/services.py (staff-reviewed evidence-count maturity), assessments/plan.py (staff-finalized plans),
extraction/services/pipeline.py, chunk_store.py, openai_fact_extractor.py (field-key merge),
facts/verification/, documents/services.py (same-filename lineage), and frontend/pages/scoring/LiveCRIPreview.tsx.

Real inference and deployed behaviour are unverified. Use mocks for integration tests; don't send institution
documents to a different provider or incur significant costs without authorization. Reuse configured routing,
usage tracking, authentication and tenant-scoped source downloads. Do not show hidden credentials in outputs.

Avoid another broad planning loop. Implement the next coherent stage, test it, and report concrete progress
and remaining gaps candidly. The user has authorized starting changes and pushing the work to A1.

Validation at this checkpoint: 23 new pure tests pass, including exhaustive indicator-state comparisons.
The Django scoring suite passes all 117 tests with `SECURE_SSL_REDIRECT=False` for local HTTP clients.
`manage.py check` reports only the expected unconfigured AI-key warning. No model inference, production
requests or production migrations were executed. A1 has a dedicated dependency-free foundation-test workflow;
the existing main deployment workflow was not changed.
