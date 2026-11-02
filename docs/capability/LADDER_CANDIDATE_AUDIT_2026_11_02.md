# Candidate audit and corrections — 2026-11-02

Audited PR #8 at `2ecff334cf7a3c4cf199a74003ac6ad6a48c6c50`. Corrections introduce **LADDER-CANDIDATE-0.3**, **LADDER-PROFILES-0.2** and `grouped-candidate-bounds-0.2`. The candidate remains offline and uncalibrated. No active scoring, assessment history, API or production plan engine changes.

## Reproduced findings and fixes

| Finding before correction | Reproduction / consequence | Correction |
|---|---|---|
| Proposed Silver minimum omitted student attainment and operational ownership/lifecycle evidence | The old fixture satisfied the checklist while C5.1.O1, the AI-service inventory and service owners were unknown. | Add student attainment, inventory, owners, an applied lifecycle evaluation, service ownership and an AI-related security test to the proposed minimum. These are candidate controls, not validated badge thresholds. |
| Consequential-use oversight was absent from the gate | A declaration of clear critical risks could coexist with unassessed oversight and appeals. | Require an explicit adjudicated consequential-use flag. True requires C2.4.F1/F2/A1/A2; unknown leaves the checklist unresolved. False waives only this conditional block and must refer to the assessed inventory. |
| Credit-group membership was accepted without checking the declared 32-group structure | Changing one row to `extra-budget` increased the F denominator from 32 to 33 without changing the declared release version. | Validate each row's source ID, candidate ID, stage, parent indicator and exact group membership. A future grouping policy needs a corresponding engine/release revision. |
| Returned alternative IDs referenced the input profile's lists | Appending to an output list changed the input profile and its hash. | Copy alternative and conditional ID lists; output mutation no longer affects the input profile or gate context. |
| Malformed structures could escape as AttributeError | Passing `[]` for decisions reached `.values()` rather than a controlled validation error. | Validate object/list/ID/state/context/gate shapes before arithmetic. The command returns CommandError for malformed input or stale hashes. |
| AI specificity was implicit in some adoption assertions | Repeated use of a generic digital service could be misread as AI adoption if the indicator title was ignored. | All 216 candidate rows now carry an explicit context rule. AI-specific activity needs a substantive AI use/content/project; enabling practice is labelled separately. |
| One source-stage outcome was mislabelled as a measured result | C4.2.O1 is an academic work sample showing skill application, not by itself a measured outcome. | Label it observed AI activity. F/A/O remain source stages and are not constructs or badge levels. Resource/support activity is likewise separated from AI deployment. |

## Versioning and execution

Earlier candidate/profile/case files are preserved as historical artifacts. Current files:

- `ladder_candidate_v0_3.json`: all 216 source mappings, new LADDER03 identities and context rules.
- `ladder_profiles_candidate_v0_2.json`: four draft profiles and revised proposed Silver rules.
- `ladder_candidate_acceptance_cases_v0_3.json`: seven synthetic hand-adjudicated cases, including a consequential use with missing oversight.

The evaluator accepts only this candidate/profile contract. No old finding is automatically mapped to a new ID. The offline command additionally checks the canonical-JSON hashes of the entire candidate and profile release. These hashes are not just filenames or version labels.

```sh
# From backend, with the project's Python environment:
python -m unittest apps.scoring.test_experimental_ladder \
  apps.scoring.test_experimental_candidate \
  apps.scoring.test_experimental_candidate_command

python manage.py evaluate_ladder_candidate \
  ../docs/capability/ladder_candidate_v0_3.json \
  ../docs/capability/ladder_profiles_candidate_v0_2.json \
  /path/to/newly-adjudicated-candidate-snapshot.json
```

Snapshot fields: `methodology`, `candidate_hash`, `profile_release_hash`, `profile`, `decisions`, `gate_context`. Required context is `scope_verified`, `currency_verified`, `coverage_verified`, `critical_risks` and `consequential_ai_use`. Verification flags and consequential-use status take true/false/null; critical risks takes clear/open/unknown. A false verification or open critical risk blocks; missing verification or consequential-use classification leaves uncertainty. No badge is awarded even when the proposed checklist is satisfied.

All context flags and condition decisions are **adjudicated inputs**. The arithmetic engine does not prove coverage, discover the deployment inventory, establish absence of consequential uses or validate quotations. Do not infer those flags from a high component value or a task checkbox. The candidate command is a test harness, not the live evidence bridge.

## Validation and limits

32 focused tests pass, including actual command execution over all seven cases, malformed input and stale-release rejection, unchanged command input files, mandatory gate omissions, conditional oversight, denominator integrity, output detachment, source arithmetic and all 216 mappings. A separate audit check confirms all 216 original source texts are preserved in the review mapping. No database, inference or institutional assessment writes are performed by these tests.

Focused tests use the listed modules and a minimal Django runtime. Broad discovery also imports unrelated production services and needs the full project dependencies; it is not a substitute for running the documented focused command. Full project-suite validation remains in CI.

Full GitHub CI must finish on the updated commit; earlier-commit results are not evidence for this revision. There are no new migration or frontend changes. No fresh PDF/model-quality evaluation or empirical calibration is claimed.

Remaining work is substantive rather than a hidden activation step: representative institutional evidence, disagreement review, profile coverage/materiality definitions, causal/positive-impact standards, headline weights and complete Gold/Platinum achievement packs. A first evaluation may establish measurement capability without demonstrating positive impact. The revised minimum is still not an exhaustive or calibrated Silver standard. Unknown evidence still produces uncertainty, so these fixes do not promise that an unsupported assessment will stop showing 0–100.
