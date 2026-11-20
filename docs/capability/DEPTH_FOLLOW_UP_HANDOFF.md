# Follow-up questions about the depth of evidence: skeleton handoff

Branch `depth-follow-up-skeleton` (built on `a1-fair-standard`, PR 41). Written 11–13 Nov 2026 by Siddharth Chundru
before handing the project over. The proposal behind it, with the decisions still open, is the document
"AI-READY: Follow-up questions to assess the depth of evidence — proposal" (shared with Harsha).

**Nothing in this branch changes an assessment, its score or its reports.** The stage runs only through the four
`depth_*` commands below and writes only to its own four tables.

## 21 Nov 2026: depth counts, every indicator is asked about (questions-0.2, depth-reserve-v1)

From the test 13 audit (project doc "AI-READY: follow-up questions audit"). Decisions taken by us on Siddharth's
instruction; all are settings and can be changed back.

- **Depth decision 2 = reserve, share 0.25** (`DEPTH_CREDIT_MODE=reserve`, `DEPTH_CREDIT_SHARE=0.25`,
  `capability/reserve.py`). The headline counts each credited requirement at credit x (0.75 + 0.25 x depth): evidenced
  (also "don't know" and no answer) 0.75, substantiated 0.875, strong 1. The judge's credit on the record is unchanged.
  The share is frozen into each new run (`inputs.depth_policy`) and stamped on each record (`depth_share`,
  `depth_level`); runs from before keep their scores. `result.depth_reserve` gives the evidence score, what is held,
  what was earned back. Reports say so in one sentence; each requirement's explanation gets a `follow_up` line.
- **A depth answer that contradicts the evidence no longer withdraws credit** (it did under `reserve` before, on one
  judge call): it is held at evidenced and listed (`depth_review`). Lowering credit stays with the re-judging path
  (two passes, each quoting the new document; #58).
- **Every key indicator is asked about** (`depth.plan_all`): one model call per key indicator; one or more depth
  questions per credited requirement (a fact two requirements need is asked once and counts for both); one
  missing-evidence question per key indicator with plain items for requirements with no or part credit, in the order
  starting capability, repeated use, results. Whatever the model leaves out or gets wrong gets fixed wording.
  `DEPTH_MAX_QUESTIONS` is 0 (no cap): the old 25 was a placeholder from the 11 Nov skeleton.
- **Ranked by points at stake** (`DepthQuestion.points_at_stake`, in the API): highest first; among equal ones,
  areas take turns (test 13 put all 15 depth questions in one area).
- **Judging:** "don't know" needs no model call; requirements whose own quotes show every dimension are judged on them
  (`DepthPlan.shown_by_evidence`, migration 0017). The re-judge job publishes a final result when depth answers
  earned anything back, even with no new evidence.
- **Answers:** a document the first assessment had already read for that key indicator is reported
  (`search.already_counted`) and the college is told, kindly; a follow-up that mostly repeats its question is replaced
  by one naming what is still not shown.

Test 13 replayed offline under these rules (no model calls): provisional 26.14 becomes 19.60 with 6.54 points held;
131 questions (95 depth, 36 missing-evidence) worth 61.9 points in all; the first 15 depth questions span 8 areas.
All substantiated would give 22.87, all strong 26.14.

## What problem it solves

The part judge decides whether evidence for a condition exists. It cannot tell a three-session workshop at a local
institute from a 300-hour accredited programme: both earn the same credit. A human auditor would ask follow-up
questions (how many hours, how many faculty out of how many, who ran it, what was the syllabus) before deciding how
much the evidence is worth. This stage does that after the provisional assessment.

## How it runs

1. `depth_questions export.json --commit` reads an assessment export (the same file `assessment_consistency` reads).
   - Credited conditions get **depth questions**: one model call per condition. The model sees the quotes that
     earned the credit and the quality dimensions for that condition, marks which dimensions the quotes already
     answer, and writes questions only for the rest. Its output is checked: unknown dimensions and questions about
     answered dimensions are dropped, and there is a per-condition cap by openness.
   - Uncredited conditions are grouped per key indicator into one **"do you have anything?" question**, built
     without a model call from the condition texts and their typical evidence forms.
   - At most `DEPTH_MAX_QUESTIONS` (25) in total, `DEPTH_MISSING_QUESTION_SLOTS` (10) of them reserved for missing
     evidence. Depth questions go to the credited conditions with the highest weight × credit first.
2. The institution responds: an answer, uploaded documents, or "don't know". There is no screen yet:
   `depth_load_responses responses.json --commit` loads a file (consultant-attested: rows are saved as checked). An
   answer counts as **supported** only when a document backs it: a row marked supported must name its `document_ids`.
   Through the API (second layer, `SECOND_LAYER_HANDOFF.md`) answers are searched for and checked instead.
3. `depth_judge export.json --commit` judges each credited condition with answered questions: one model call places it
   at **evidenced**, **substantiated** or **strong** against the indicator's level descriptions and any **approved
   past cases** for the same condition. Then the open decisions are applied in code (below). Each judgment is saved
   and proposed as a past case.
4. A person approves or rejects proposed past cases in the Django admin (Scoring › Depth past cases). Only approved
   cases are shown to later judgments, and only for the same spec version.
5. `depth_report export.json` prints the levels, a **depth index** (0–100: how deep the credited evidence is) and,
   only if decision 2 is set to `reserve`, the headline score with depth applied beside the provisional one.

## Files

| File | What it is |
| --- | --- |
| `backend/apps/scoring/capability/depth_spec.py` | Source of the depth spec. Edit this, then run `python -m apps.scoring.capability.depth_spec` |
| `backend/apps/scoring/capability/depth_spec_v0.json` | Generated spec: per key indicator, openness, quality dimensions, level descriptions; per condition, typical evidence forms and relevant dimensions |
| `backend/apps/scoring/capability/depth.py` | The logic: target selection, question prompts, judging prompt, policy, arithmetic. No database |
| `backend/apps/scoring/capability/depth_service.py` | Database side, working from an export |
| `backend/apps/scoring/models.py` (end) | `DepthQuestion`, `DepthResponse`, `DepthJudgment`, `DepthPastCase`; migration `0013_depth_follow_up` |
| `backend/apps/scoring/admin.py` (end) | Admin views, including approve and reject actions for past cases |
| `backend/apps/scoring/management/commands/depth_*.py` | The four commands |
| `backend/apps/scoring/test_depth.py` | 29 tests with a stand-in model |
| `docs/capability/depth_fixtures/` | A weak and a strong set of answers about faculty AI training, for a real-model check |

## The depth spec is a draft

`depth_spec_v0.json` covers all 36 key indicators and 216 conditions. **It was written by a model (Claude) from the
condition texts and has not been reviewed.** It is marked `status: draft-model-written`. Every openness level,
dimension, evidence form and level description is a starting point for the rubric reviewers to correct. Level
descriptions are in words on purpose: numeric thresholds wait until enough colleges have been assessed to see the
real spread. Faculty AI literacy (AIQIF-C4.1) is the worked example from the meeting with Vijay.

## Open decisions are settings, not code

| Decision | Setting | Default | Choices |
| --- | --- | --- | --- |
| 1. Can an answer lower a score? **Decided (Harsha, 12 Nov): yes.** | `DEPTH_ANSWERS_CAN_LOWER` (the depth level only) · `SECOND_LAYER_LOWERING` (the score) | `on_contradiction` · `apply` | Depth: `on_contradiction` (the level becomes withdrawn) · `never`. Score: `apply` (a document the institution sent that contradicts a credited part lowers it, with guards; see SECOND_LAYER_HANDOFF.md) · `flag`. How far "don't know" lowers is still Harsha's call. |
| 2. How much credit does depth carry? | `DEPTH_CREDIT_MODE`, `DEPTH_CREDIT_SHARE` | unset: depth changes no credit | `separate`: depth index only · `reserve` + share s: evidenced keeps 1 − s of a condition's credit, substantiated 1 − s/2, strong all of it, so provisional scores fall until colleges answer |
| 3. What is an answer without a document worth? **Decided (Harsha, 12 Nov): nothing.** | `DEPTH_UNSUPPORTED_ANSWERS` | `ignore`: typed answers without a document never reach the judge; a condition with nothing else stays evidenced without a model call | `ignore` · `cap_one_level` · `same` (comparison runs only) |
| 4. Who approves past cases? | admin permission | anyone with admin access to the model | to be decided by Harsha and Vijay |
| 5. Rescoring earlier colleges when the spec changes | `spec_version` on every row | judgments only use past cases of their own spec version | rescoring is not automated |

Every judgment stores the policy it was judged under.

## Stubbed or missing (for the next owner)

- **Response screen in the web app.** Responses come from a file. The models and `load_responses` are what a screen
  or API would call; a consultant-entered response should set `submitted_via='consultant'`.
- **Cost metering.** Done for the API (13 Nov): the `questions` and `depth` background jobs reserve every call
  against the run's second-layer budget (`second_layer_jobs.py`; see the second-layer handoff). The commands still
  call `get_ai_service()` directly and cap calls (`--max-calls`, default 60 for questions and 40 for judging).
- **Uploaded documents.** Uploads to missing-evidence questions are listed as "awaiting reassessment"; they still
  need extraction and a new assessment run. Uploads to depth questions count as supported answers, but their content
  is not read by the depth judge.
- **One judging pass.** The part judge runs two passes with a tie-break; the depth judge runs one. Add a second pass
  and agreement targets before relying on it.
- **Past-case retrieval** is exact: same condition, same spec version, newest three approved. Similar conditions in
  the same key indicator, or embedding similarity, would help once there are many cases.
- **Questions are per condition.** Two conditions about the same programme can produce overlapping questions; merging
  per key indicator would also cut model calls.
- **Reports.** Depth appears only in `depth_report`. Showing it in the leadership report waits on decision 2.

## Checking it with a real model (phase 2 in the proposal)

On the frozen VISTAS corpus export (sprint 5e19c078), with faculty AI literacy credited:

```
python manage.py depth_questions vistas.json --commit --out questions.json
python manage.py depth_load_responses docs/capability/depth_fixtures/faculty_training_weak.json --by-condition --run <run id> --commit
python manage.py depth_judge vistas.json --json > weak.json            # dry run, nothing saved
```

Then delete those responses (admin), load `faculty_training_strong.json` the same way and judge again. The strong set
must come out higher than the weak set on every condition it covers; the weak set should stay at evidenced. Read the
questions in `questions.json` too: each should name the college's own programme and ask about something the
documents do not already state.
