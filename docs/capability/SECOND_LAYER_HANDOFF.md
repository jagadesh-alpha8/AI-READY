# Second assessment layer: handoff (skeleton, 12 Nov 2026)

What happens after the provisional score: the institution answers the second line of questions one at a time
(depth questions about credited requirements, "nothing found" questions about uncredited ones), may answer one
follow-up per question, and may add evidence it thinks was missed. Design: claude.ai doc "AI-READY: second assessment
layer — architecture for follow-ups and new evidence". Code: `apps/scoring/capability/layer2.py` (logic),
`layer2_service.py` (database), `layer2_views.py` (API), `second_layer_jobs.py` (background jobs, metered), tests in
`apps/scoring/test_layer2.py` and `test_second_layer_jobs.py`.

## Rules the code keeps

- **Search with the institution's words.** Records are worded differently from the rubric, so the query is the
  answer (or the note), never rubric wording. For a depth answer the quotations that earned the credit are added: they
  are the institution's own records, and they keep a short answer ("yes, 300 hours") from being an empty query. With
  no text at all, a large document is ranked with the requirements' records-language retrieval profiles. Attached
  documents first, sent whole up to 8,000 characters, then the run's corpus with its own 4,000-character share,
  because answers often point at something already submitted. The requirement's provisional packet is left out of the
  search, and so are passages that mostly repeat text already taken, so the corpus share goes to text the first pass
  did not see. The run's own ranker is used (keyword and embedding ranks fused when the run used hybrid retrieval;
  each check records which); attachments get their own ranker on the same model so the corpus index is kept.
- **The depth check reads the credited evidence.** The windows that earned the credit are shown to the check beside
  what the search found, so a reply is read against what it is about. A reply with documents and no text is judged on
  the documents. `SECOND_LAYER_CORPUS_SUPPORT` (default true) decides whether support found only in documents
  already submitted counts; false means only documents attached to the reply count.
- **Peer-reviewer standard.** A submitted record is evidence of what it states; several passages can support a claim
  together; nothing is rejected for not repeating a dimension word for word.
- **Typed text is the query and the claim, never evidence.** An answer counts only when the search finds something
  that supports it (Harsha, 12 Nov). If nothing is found there is no model call; the follow-up asks for a document.
- **Credit rises only on evidence the first pass didn't see.** Requirements are re-judged on their provisional packet
  (from the run trace) plus the new passages and the pages extraction tagged for the indicator in the documents sent
  for it. New is decided by content: a passage that mostly repeats the packet is not added, and a quotation whose text
  the packet already held, under any page, is not new. Part by part, a rise is taken only when the part cites, in
  either judging pass, a new quotation. One exception: when a gate part (the subject) was missing and now rests on new
  evidence, the condition's other parts that rose count even when they cite the packet (`unlocked_parts`). Other parts
  keep their provisional result and the credit is recomputed. Untouched requirements are copied. Windows take each key
  indicator's 12,000 characters in this order: "nothing found" documents, additional evidence, tagged pages, depth
  answers.
- **One scale.** `layer2_rejudge` refuses an export scored under a different part rule (f5919156 was scored with
  related evidence at 0.5 and the subject as a share): re-judge on an export from a run on the current rule.
- **Depth answers can raise credit too.** A depth answer the check found support for also goes to the credit path, so a
  partly credited requirement can rise on it (decided 12 Nov).
- **Contradictions are flagged, not applied** (depth decision 1 is still open): `rejudge_credit` lists them and the
  command prints them; feeding them to the review queue waits for the refining run.

## Flow

| Step | Code | Model calls |
| --- | --- | --- |
| Questions for the run | `depth_questions export.json --commit` (existing) | one per credited condition tried |
| Next item (a follow-up first) | `GET .../questions`, `layer2_service.next_item` | none |
| Answer, attach, or skip | `POST .../questions/{id}/responses`, `submit` | none |
| Search and check | `check_response` (on submit if `SECOND_LAYER_CHECK_ON_SUBMIT`, else `layer2_check_pending RUN_ID`) | one per depth answer with passages found; none for "nothing found" answers |
| One follow-up answer | `POST .../responses/{id}/follow-up` | as above, never followed up again |
| Additional evidence | `POST .../additional-evidence` (`picked` = areas, key indicators or requirements; required) | none; routed with extraction's tags at check time, capped at 8 key indicators |
| Depth | `depth_judge export.json` (existing) now reads checked answers and their passages; a condition with an answer still waiting for its check is held (`awaiting_check`) | one per credited condition answered |
| Credit | `layer2_rejudge export.json --run --out result.json` | two passes + tie-break per key indicator re-judged |

## Background jobs (13 Nov)

With `SECOND_LAYER_JOBS_ENABLED=true` the steps above run in Celery instead of from the commands, through
`POST .../second-layer/jobs {operation, options}` (Idempotency-Key header; `GET` lists the run's jobs and its budget,
`POST .../second-layer/jobs/{id}/cancel` stops one):

| Operation | Does | Options |
| --- | --- | --- |
| `questions` | plans and saves the follow-up questions | `replace` (refused once the college has answered) |
| `checks` | checks waiting answers and additional evidence | none |
| `depth` | judges depth from checked answers (saves judgments and pending past cases) | none |
| `rejudge` | re-judges credit and publishes the final result as a run refining the provisional one | `publish` (default true; false reports only) |

- **Metered.** Every model call is reserved against the job (it must still be running, within its deadline) and the
  run's `SecondLayerBudget`, which all of the run's jobs share. The budget is frozen when the first job starts:
  `SECOND_LAYER_MAX_HTTP_CALLS` / `SECOND_LAYER_MAX_COST_USD`, or, when unset, the limits the run's own assessment had.
  `manage.py layer2_budget RUN_ID [--max-calls N --max-cost X]` shows and raises it (logged on the ledger). Per-request
  settings (output tokens, timeout, reasoning effort, input bound) are the assessment's. The ledger is
  `SecondLayerEvent`; the final run's inference carries the rejudge job's calls (`second_layer_metered: true`).
- **One active job per run**, and nothing saved after a cancel or a spent budget: each job writes its result in one
  transaction that first checks the job is still running. The re-judgment runs with `strict_errors`, so a spent
  budget stops it instead of becoming a "re-judgment failed" requirement. A job past its deadline plus 15 minutes is
  taken to have lost its worker when the next job starts.
- **Checks start on their own.** A submitted answer or additional evidence requests a checks job (quietly skipped when
  another job is active); a checks job that finds items submitted while it ran queues another; the beat task
  `sweep_second_layer_checks` (every `SECOND_LAYER_SWEEP_SECONDS`) starts one when a waiting item's documents finished
  extraction since the run's last checks job. An item a job tried and left waiting (a malformed reply) is not retried
  until something about it changes; start a checks job to retry it.
- With jobs on, `SECOND_LAYER_CHECK_ON_SUBMIT` is ignored. The commands still work, unmetered, for consultants on a
  frozen export. A rejected document now counts as failed, not as still being extracted.
- Who may start jobs: `CanManageSprint`, like starting a run, so the college's coordinator can publish the final
  result. Restrict `rejudge` to staff if Harsha prefers.

`evaluate()` gained `fixed_contexts`: the credit path calls the main judge on a cut-down rubric with given packets
instead of retrieval.

## Not built

- Who may answer, and who may start jobs: the views use `CanManageSprint`, like the run views.
- Front-end screens for the jobs (start, progress, cancel, budget).
- Contradictions into the review queue and the report.
- Depth judging for requirements newly credited in the credit path; a second round of questions.
- Not run against a real model or the VISTAS export yet.
