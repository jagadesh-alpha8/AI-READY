# Benchmark Assessments (stage 5)

Menu: **Benchmark Assessment** (`/benchmark-assessment`). App: `apps/assessments`.
Connects colleges to the benchmark library: a college is assessed against the **current published
release** -- never against draft benchmarks -- and gets four separate scores per benchmark.

Schema tables (manager's `db/schema.sql`): `institutions` + `programmes` (stored as a benchmark profile next to
the existing Institution), `assessment_cycles`, `applicable_benchmarks`, `evidence_items`, `evidence_reviews`,
`scoring_models`, `benchmark_score_rules`, `benchmark_assessments`.

## Steps

| Step | Who | What happens |
|---|---|---|
| Profile | InGage staff | Institution type, autonomous status, approvals (AICTE, NBA, ...), programmes. Decides which benchmarks apply |
| Start | InGage staff | Picks the current published release; every benchmark is checked against the release's frozen applicability rules, each with a reason. "Requires review" ones must be decided before evidence is requested. Going against the rules needs a note |
| Ask for evidence | InGage staff | Status -> collecting evidence |
| Upload | College (any role except viewer) | For each evidence request from the release: a file (PDF, Office, CSV, image; 25 MB) or a link, with issue date. File SHA-256 recorded |
| Submit | College | Status -> submitted; uploads stop (InGage can send it back with a note) |
| Review | InGage staff | Five scores 0-100 (relevance, completeness, currency, authenticity, scope) + accept / ask for more / reject; the reviewer can't be the uploader; a note is required unless accepted. Reviews are append-only |
| Score | InGage staff | Needs every piece of evidence reviewed. Calculates the four scores; the assessor can add the outcome score and, with a reason, set the level |
| Finalize | InGage staff | Needs fresh scores (no review after scoring) and any "manual review" level confirmed. Everything is frozen; the college can now see the scorecard |

## Scores (method `stage5-v1`)

| Score | How |
|---|---|
| Compliance | Share of the mandatory foundational (L3 or any-level) evidence requests met. Empty for InGage-proposed benchmarks (nothing legal to comply with) |
| Maturity | Level reached: none 0, L3 33.33, L2 66.67, L1 100. A level counts only when every mandatory request for it and the levels below is met |
| Evidence confidence | Average of the reviewers' five quality scores over accepted, current evidence; 0 when there is none |
| Outcome | Entered by the assessor from a measured result (note required); empty until then |
| Composite | Only with weights approved for that benchmark under the active scoring model (`BM-SCORE-1`, seeded with no weights); the weights must add up to 1. Empty while any weighted score is empty. The weights used are copied into the assessment |

A request is met when at least `minimum_count` accepted items count for it. An item does not count if it is not
accepted, expired (`valid_until` before the assessment's start date), or older than the request's
`minimum_currency_months` (an issue date is then required). Every score carries its reason (`detail`), shown on
hover in the scorecard. Empty is shown as "—", never as 0.

## Access

InGage staff (super_admin, consultant): everything. College users: only their own college; upload and submit
(not viewers); the scorecard only after finalize. Every change is written to the audit log
(`SourceAuditEvent`, actions `assessment.*`).

## Reusing audit documents as evidence

When uploading evidence, a college can pick a document it already uploaded in an AI Readiness Audit sprint
(`sprint_document`) instead of uploading it again. Only that college's own documents are offered; the file is
served from the audit document, and its checksum is recorded on the evidence.

## Improvement plan (stage 6)

After **finalize**, staff generate the plan (`apps/assessments/plan.py`; schema: `gaps`,
`transformation_templates`, `initiatives`, `tasks`). Nothing is guessed: gaps come from the frozen scores.

| Gap | When | Severity |
|---|---|---|
| Capability | Level reached below the target level | none reached on a mandatory benchmark: critical; 2+ levels short: high; 1 short: medium |
| Compliance | Compliance score below 100 | mandatory benchmark: critical (< 50) / high; recommended: medium; else low |
| Evidence | Confidence below 60 although evidence was accepted (weak, partial or old proof) | medium |
| Outcome | Outcome score below 70 | high (< 50) / medium |
| Dependency | Added by staff | — |

Each gap gets an initiative due by severity (critical 30 days, high 60, medium 90, low 180 after finalize):
from the benchmark's **transformation template** for that gap type when the experts wrote one (title,
intervention, expected evidence and outcome, task list), otherwise one task per unmet mandatory evidence request
up to the target level. The college (not viewers) runs initiatives and tasks: owner, dates, status, extra tasks.

**A gap is only validated by accepted evidence** for the same benchmark at the same college (from this or a
later assessment), with a note; only a validated gap can be closed, and it cannot be reopened afterwards.
Templates are edited per benchmark on the assessment page (staff) and apply to plans generated afterwards.

## Not built yet

AI-suggested evidence claims (`evidence_claims`); comparing assessments across releases; a combined view of the
pillar CRI and benchmark scores (how the two relate on a client report is a product decision).

## API (`/api/v1/assessments`)

```
GET  /reference
GET  /institutions
GET/PUT /institutions/<id>/profile             {institution_type, autonomous_status, approval_bodies, programmes[]}
GET/POST /cycles?institution=                  {institution, name, opens_on, closes_on}
GET  /cycles/<id>
POST /cycles/<id>/open | submit | return | score | finalize   {note}
GET/PATCH /cycles/<id>/benchmarks/<code>       {included, target_level, note}
POST /cycles/<id>/benchmarks/<code>/evidence   multipart {rule_key, title, file | source_url, issued_on, valid_until}
POST /cycles/<id>/benchmarks/<code>/assessment {outcome_score, outcome_note, level_override, override_note}
GET  /evidence/<id>/file
POST /evidence/<id>/review                     {decision, relevance_score, completeness_score, currency_score,
                                                authenticity_score, scope_score, notes}
GET  /cycles/<id>/scorecard
GET  /score-rules   PUT /score-rules/<code>    {compliance_weight, maturity_weight, evidence_weight, outcome_weight, note}
```
