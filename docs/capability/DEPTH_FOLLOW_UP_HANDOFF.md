# Follow-up questions about the depth of evidence: skeleton handoff

Branch `depth-follow-up-skeleton` (built on `a1-fair-standard`, PR 41). Written 11–13 Nov 2026 by Siddharth Chundru
before handing the project over. The proposal behind it, with the decisions still open, is the document
"AI-READY: Follow-up questions to assess the depth of evidence — proposal" (shared with Harsha).

**Nothing in this branch changes an assessment, its score or its reports.** The stage runs only through the four
`depth_*` commands below and writes only to its own four tables.

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
   `depth_load_responses responses.json --commit` loads a file. An answer counts as **supported** only when a document
   backs it.
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
| 1. Can an answer lower a score? | `DEPTH_ANSWERS_CAN_LOWER` | `on_contradiction` (recommended) | `on_contradiction`: only an answer that contradicts the credited evidence, and then the credit is withdrawn · `never` |
| 2. How much credit does depth carry? | `DEPTH_CREDIT_MODE`, `DEPTH_CREDIT_SHARE` | unset: depth changes no credit | `separate`: depth index only · `reserve` + share s: evidenced keeps 1 − s of a condition's credit, substantiated 1 − s/2, strong all of it, so provisional scores fall until colleges answer |
| 3. What is an answer without a document worth? **Decided (Harsha, 12 Nov): nothing.** | `DEPTH_UNSUPPORTED_ANSWERS` | `ignore`: typed answers without a document never reach the judge; a condition with nothing else stays evidenced without a model call | `ignore` · `cap_one_level` · `same` (comparison runs only) |
| 4. Who approves past cases? | admin permission | anyone with admin access to the model | to be decided by Harsha and Vijay |
| 5. Rescoring earlier colleges when the spec changes | `spec_version` on every row | judgments only use past cases of their own spec version | rescoring is not automated |

Every judgment stores the policy it was judged under.

## Stubbed or missing (for the next owner)

- **Response screen in the web app.** Responses come from a file. The models and `load_responses` are what a screen
  or API would call; a consultant-entered response should set `submitted_via='consultant'`.
- **Cost metering.** Depth model calls use `get_ai_service()` directly; they are not reserved against a
  `CapabilityExecution` budget like assessment calls. The commands cap calls (`--max-calls`, default 60 for
  questions and 40 for judging). Wire them through `provider.MeteredService` before any production use.
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
