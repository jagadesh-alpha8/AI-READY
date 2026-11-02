# Readiness rubric and maturity ladder review — 2026-11-02

Status: **experimental candidate, not an activated methodology**. Guidance: user-supplied *AIFRC AI Readiness Maturity Ladder Blueprint v0.1*. Scope: all 72 foundational requirements, aggregation and badge separation. This does not implement the blueprint's full programme-management platform.

## Finding

The current release combines an advanced, mostly institution-wide AI maturity rubric with cumulative numerical gates. Each indicator has two foundational, two adoption and two outcome requirements. One unsupported foundational requirement holds its lower bound at zero even when another requirement is met. With no explicit negative finding, its upper bound can remain 100. That is correct arithmetic for the current rules, but a poor way to communicate partial readiness.

The earlier export has 71 unknown foundations and one met foundation. Original arithmetic reproduces its saved 0–100 exactly. Independent equal-assertion arithmetic exposes **1.39–100 in foundations**, while adoption and outcomes remain **0–100**. This is an arithmetic sensitivity result using original wording and original decisions, not a revised assessment or an institutional readiness score. Changing arithmetic alone cannot supply the 215 unresolved findings.

The evidence investigation also found bounded context, output-validation failures, and a possible institution/scope mismatch. These remain separate causes. Neither this review nor the arithmetic experiment proves that the full PDFs lack evidence, or that every abstention was justified. The new A1 assessment still needs its own export; the earlier export is not evidence about that run.

## What changes in this candidate

- Each of the 72 foundations has an explicit replacement assertion, source mapping, scope/date/evidence rule and re-adjudication requirement. Machine-readable detail: `ladder_foundations_candidate_v0_1.json`; readable table: `LADDER_FOUNDATION_REVIEW.md`.
- A companion assertion no longer acts as an implicit prerequisite for numerical credit. Critical safeguards can still be mandatory achievement gates in a calibrated profile.
- Basic digital governance, resources and support count as enabling capacity where appropriate. They do not establish AI implementation. AI-specific curriculum, services, practice and research still need AI-specific evidence.
- Evidence for a programme, cohort or service can establish capability in that stated scope. Institution-wide reach requires separate coverage evidence; a pilot does not establish Silver.
- The period follows the assertion: effective policy interval, applicable curriculum regulation or actual activity period. A current policy need not be newly published each academic year. A report footer does not date an activity.
- Unknown and conflicting findings retain uncertainty. Explicit scoped negative evidence can establish not_met. Plans support planning assertions only; attendance establishes participation, not competence; generic MoUs do not establish delivered partnerships.
- Candidate IDs differ from source IDs. Old met findings cannot be copied to revised requirements. Existing assessments, hashes and active rubric remain unchanged.

The previous draft's source-specific counterexamples are retained as review context, not mandatory evidence formats or extra pass conditions. For example, a governance minute is an evidence example, not the only accepted document type. The newly stated assertion controls adjudication.

## Blueprint reconciliation

| Blueprint idea | Decision for this work |
|---|---|
| Verified baseline, evidence confidence and coverage | Keep capability findings and evidence uncertainty visible; do not multiply capability by document completeness. Confidence is not a score substitute. |
| Silver foundational and operational | Treat as a destination requiring operational and safety evidence. It is not the minimum threshold for any readiness credit. |
| Gold scaled/integrated; Platinum sustained leadership | Separate calibrated achievement packs. F/A/O are evidence stages, not aliases for the three badges. |
| Profile-specific thresholds, applicability and weights | Do not fabricate thresholds or silently exclude research/other requirements for an ITI. Version profile alternatives and their denominators before activation. |
| No unresolved critical risks; current, sufficient evidence | Candidate badge gates, distinct from arithmetic. A high partial-capability component cannot override a critical safety blocker. No badge is awarded by this experiment. |
| Review/approval | Formal achievement attestation may be added separately. No consultant approval is required to run assessments, reports, recommendations or hypothetical plan evaluations. |
| Next unachieved level and three delivery paces | Subsequent planning should target the next calibrated destination, reuse verified work and vary timing/resources while keeping required outcomes stable. Do not treat illustrative durations as promises. |
| Investment and resource planning | Use declared capacity and optional budgets. Do not invent prices, require a new budgeting step or promise equally priced routes. |
| Several proposed screens | Preserve the previously agreed merged navigation; conceptual programme entities do not require separate pages. |

## Executable numerical experiment

`backend/apps/scoring/capability/experimental_ladder.py` is deliberately isolated from live services, models, prompts and reports. For each F/A/O component independently, met contributes [1,1], not_met [0,0], and unknown/conflicting [0,1]. Summing and dividing by the number of assertions gives exact rational percentage bounds. There are no cross-stage prerequisites. Resolution counts remain separate. The output explicitly has no headline score and no badge assessment.

Equal assertion weighting is a sensitivity convention, not a validated policy. It changes both gating and weight structure relative to the current engine. The component result must not be marketed as an improved institutional score. Foundation is also not synonymous with capacity: some foundation rows describe observed participation or practice. An eventual capacity/activity/results headline requires construct mapping of all 216 requirements, overlap control and calibrated weights.

Run the read-only comparison from `backend`:

```sh
python manage.py compare_capability_aggregation /path/to/assessment-export.json
```

It accepts complete, unique original decision sets, replays the original engine, reports whether it matches the saved result, and computes original-wording component sensitivity. It performs no inference, database writes or automatic translation into the revised rubric. It prints no source passages. Revised-wording findings must be adjudicated separately against the candidate IDs and version.

## Remaining design risks and activation boundary

1. **Double counting:** C3.2 and C5.1 both address literacy provision; C3.4 and C5.3 overlap project opportunities; C6.1 and C6.4 overlap resource/environment access. These should become shared evidence/capability contributions or receive calibrated weights before any single headline. Keeping 72 traceable rows does not justify counting the same capability twice.
2. **Remaining compound A/O requirements:** the 144 adoption/outcome conditions are not rewritten here. Their scope, measurement and repeated-cycle requirements need the same assertion-level review before a complete release. No claim is made that the entire rubric is now atomic.
3. **Safety and coverage:** simplification must not remove controls. Owner, appeal, safeguards, measured reach and currency need explicit gate definitions for each badge/profile, with missing evidence reported unresolved. Do not infer coverage from the existence of one course or policy.
4. **Evidence adjudication:** use the same available evidence and retrieval boundaries for source/candidate comparisons; separately compare improved retrieval. Record supported assertions, scope, period, provenance, failures and expert disagreements. Do not change wording and retrieval simultaneously and attribute all change to the rubric.
5. **Calibration:** first test Silver packs for Engineering, Polytechnic, Arts & Science and ITI with representative institutions and expert-reviewed sparse/negative/conflicting cases. Then set applicability, shared-capability weights, materiality and safety gates. Gold/Platinum follow validated Silver work. Do not activate illustrative thresholds or target dates.
6. **Plans:** neither generated plans nor completed task checkboxes establish delivered capability. Proposed changes remain conditional scenarios; only fresh evidence can change the verified baseline. The existing plan engine is not automatically migrated by this review.

A complete future release needs versioned requirements, profile rules, construct/overlap mapping, headline arithmetic, badge gates, evidence contract and migration policy together. This PR prepares a reviewable candidate and reproducible arithmetic comparison. It does not silently switch current users to uncalibrated scoring.

## Verification

Nine pure tests cover independent partial credit, observed activity with missing foundations, unresolved/conflicting evidence, exhaustive possible-world bounds, invalid/N/A rejection, deterministic input identity, all 72 source mappings, unchanged source arithmetic, and incomplete/duplicate export rejection. The earlier export replays exactly; the experiment's foundation lower bound is 25/18 percent (1.39 rounded), with upper bound 100. No fresh model evaluation was performed and no raw institutional source documents are included in the repository.
