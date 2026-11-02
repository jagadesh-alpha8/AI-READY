# Methodology review: capacity, AI activity and results

2 November 2026. Candidate design only; not an engine release.

## Product decision proposed

Use one eventual headline AI readiness score with visible contributions from enabling capacity,
demonstrated AI activity and results. Continue to navigate through nine pillars and 36 readable
subareas. Evidence completeness is a separate explanation, never a multiplier on readiness.

This updates the presentation direction in the earlier foundation draft, which suggested separate
scores. It does not supply validated component weights, finer stage credit, applicability rules or
Silver/Gold/Platinum thresholds. Those remain unresolved. No headline score is activated here.

The complete implementation contract is in `EVIDENCE_TO_REPORT_CONTRACT.md`. That contract and
this review are design inputs, not preconditions for merging the independent ingestion fixes.

## Full condition inventory

`methodology_review_matrix.json` inventories all 216 existing conditions and proposes treatment
for each. The 72 foundation candidates come from `NAAC_RUBRIC_REVISION_DRAFT.md`. The 144
adoption/outcome requirements retain their substantive text except the explicit measurement
revisions listed below. Each row carries scope, period, stage and counterexample rules.

An unchanged candidate text means retain its substantive requirement for review; it does not mean
the condition has passed empirical validation. The inventory has no production import path and
must not replace `rubric_v0_2.json`. Its original texts and source hash allow drift checking.

### Changes needed across the framework

| Issue | Proposed treatment | Reason |
|---|---|---|
| Capacity confused with adoption | Identify enabling foundations separately; require AI-specific activity for adoption | General IT can enable AI without demonstrating its use |
| Blanket institutional scope | Foundation existence may have a narrow evidenced scope; institutional reach is a separate requirement | One programme can establish an offer, not universal provision |
| Universal claims | Require an explicit applicable population, eligible denominator and evidence of reach | Narrowing the assessed cohort must not make an institutional universal claim true |
| Two academic years everywhere | Require relevant completed comparable cycles where sustained performance is claimed | Course, release and service review cycles need not equal academic years |
| Plans credited as delivery | Credit plans only against explicit planning requirements | Future intent cannot prove implementation or benefit |
| Activity reports credited as competence | Require assessed work for competence and a disclosed comparison for benefits | Attendance and equipment records support narrower findings |
| Product-specific measurement credit | Accept substantive institutional AI evaluation outside this product | Using this application must not award readiness points by itself |
| Duplicate indicators | Link shared evidence and initiatives; review overlapping weights before release | Project/portfolio and career/workforce areas can otherwise reward the same result repeatedly |
| No deployed consequential use | Define applicability before assigning a negative oversight decision | No deployment and poor oversight of an existing deployment are different states |
| Coarse cumulative stages | Compare candidate arithmetic on fixed examples before deciding to retain or replace it | Revised wording alone cannot justify score precision |

### Explicit adoption/outcome wording revisions

For C9.1, replace application-shaped scoring prerequisites with institutional evaluation:

- A1: Repeated reviews evaluate stated AI initiative objectives using traceable evidence and a disclosed method.
- A2: Reviews distinguish changes in institutional activity from changes in measurement definitions or methods.
- O1: Two comparable completed review cycles use evaluation findings to prioritise and assess improvements.
- O2: Recorded checks of measurement stability and validity lead to justified revisions, with limitations retained.

For C9.2, A1 should be: “Sampled institutional AI evaluation findings trace to stated criteria,
decisions and original evidence.” A numerical score is not mandatory evidence of traceability.

For C9.3, use AI-relevant monitoring rather than a requirement to operate this product's methodology:

- A1: Change reviews identify affected AI activities, applicable external requirements and evidence needing update.
- A2: Dated reviews explain changes to criteria, practice or evidence without rewriting earlier findings.
- O1: Two completed change-review cycles demonstrate timely identification and appropriate reassessment of material AI-related changes.
- O2: Review findings improve monitoring and reduce unnecessary reassessment, with the comparison method stated.

For C9.4, acceptance testing and outcome learning should concern actual AI initiatives. A general
feedback system is an enabling foundation; its existence does not establish AI-specific review.

All other adoption/outcome candidate texts remain explicit per-row requirements. The common rule
adds AI-specific evidence and limits claims to the actually assessed scope. The generic original
counterexample must be replaced at evaluation time by the stage-specific counterexamples in the
review matrix: a roadmap is legitimate planning evidence even though it cannot establish adoption.

## Worked report fixtures for substantive review

These six cases are synthetic. They specify expected findings and advice, not numerical ground
truth or successful application tests. None awards a new tier or assumes a budget.

### R1. Sparse NAAC evidence

Evidence: a general institutional report describes an ERP and ordinary computing facilities; it
contains no sufficient AI-specific activity records. Some relevant supplementary evidence is absent.

Finding: “Digital services and computing resources are described. Their suitability for the intended
AI work and the extent of current AI use are not established by this review.”

First initiative: “Check existing provision before choosing a small AI learning activity.” Ask the
relevant academic and IT leads to identify current AI courses/projects and test one introductory
workload using available access. Suggested owner: academic coordinator with IT support. Completion:
a scoped inventory and a practical access check. Do not recommend purchasing a GPU by default.

Reject: zero readiness from silence; asserted institution-wide absence; a 0–100 midpoint of 50.

### R2. Documented AI activity

Evidence: a dated AI module includes objectives, delivery records for an identified cohort and
assessed student work; an existing lab's access procedure covers that cohort. No repeated outcomes
comparison is supplied.

Finding: “The reviewed cohort received AI teaching and produced assessed work. The evidence does
not establish sustained improvement or access for other programmes.”

First initiative: “Use the assessed work to improve the next delivery.” The course lead reviews
common errors, selects an instructional change and uses comparable assessment criteria next time.
Completion: an error summary, teaching revision and next-cycle assessment plan. A plan does not
establish the eventual outcome. Link the initiative to curriculum, skills and learning support.

Reject: institution-wide literacy; repeated-benefit claims; duplicate projects for each linked area.

### R3. Approved plan, no delivery

Evidence: an approved AI module plan identifies the intended cohort, lead and practical task;
delivery has not started.

Finding: “An AI module is planned for the identified cohort. Delivery and student attainment have
not yet been established.”

First initiative: “Prepare a bounded first delivery.” The programme lead confirms access, a practical
assessment and responsible-use instructions before scheduling delivery. Completion evidence is the
actual teaching and assessed work, not just a completed task checkbox. Credit only planning
requirements actually satisfied by the approved plan.

Reject: adoption credit, forecast points presented as actual, or claims that students are competent.

### R4. Authorised absence declaration

Evidence: a programme coordinator states that their programme offered no AI learning activity during
the specified period. The rubric's candidate declaration policy permits this evidence for that
programme-level requirement. A relevant computing lab is documented.

Finding: “The programme coordinator reports that this programme offered no AI learning activity in
the stated period. This finding does not describe other programmes.”

First initiative: “Introduce a practical AI learning activity using existing access where suitable.”
Suggested owner: programme coordinator. First verify workload suitability and teaching support,
then design one assessed task with responsible-use guidance. Completion: delivery and assessed work
for the stated cohort. Do not infer a campus-wide deficit or promised numerical uplift.

### R5. Unresolved same-scope conflict

Evidence: two dated reports disagree about participant numbers for the same workshop, cohort and
period. Neither has been selected through a valid review decision.

Finding: “The workshop is documented, but its participation count is unresolved.”

First action: “Confirm the participation record.” Suggested owner: workshop coordinator. Compare
the attendance register and eligibility list; record which count is supported and why. Completion:
a scoped resolution tied to both source records. Do not design a low-participation intervention by
arbitrarily choosing the lower count. An existing resolution must survive the next assessment.

### R6. Mixed scope and periods

Evidence: an effective policy issued in 2024, a regulation-2024 BBA AI syllabus and faculty training
attendance from 2022–23. Current faculty competence and institution-wide delivery are not established.

Finding: “The policy remains applicable according to its effective-date evidence. The curriculum
documents an AI learning offer in BBA. Historical faculty attendance does not establish current
competence or campus-wide teaching.”

First initiative: “Connect the documented BBA offer with current delivery and support.” Suggested
owner: programme lead with relevant course teachers. Identify the current cohort, check teaching
and assessed work, then assess any support needs. Completion: scoped delivery evidence and a
practical assessment. Keep each finding's period visible in the evidence appendix.

Reject: a single current-year label for all three records; pooled denominators; universal reach.

## Numerical validation still required

Compare the active method and any candidate on the same frozen corpus. Include all six cases
above and the 18 contract cases. Inspect changes condition by condition, including negative and
uncertain cases. Check that missingness does not create a false exact score; one documented
strength cannot compensate for unrelated unknowns without an explicit aggregation rule.

Review overlapping credit in C3.2/C5.1, C3.4/C5.3, C5.4/C8.3, and C6.1/C6.4. Shared evidence can
support distinct constructs, but correlated constructs need a deliberate weighting decision.

Final weighting, tier thresholds, applicability and partial credit remain candidate-release work.
The ingestion PR can be merged independently; it neither validates nor activates these proposals.
