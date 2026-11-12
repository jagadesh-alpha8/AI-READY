# Second assessment layer: handoff (skeleton, 12 Nov 2026)

What happens after the provisional score: the institution answers the second line of questions one at a time
(depth questions about credited requirements, "nothing found" questions about uncredited ones), may answer one
follow-up per question, and may add evidence it thinks was missed. Design: claude.ai doc "AI-READY: second assessment
layer — architecture for follow-ups and new evidence". Code: `apps/scoring/capability/layer2.py` (logic),
`layer2_service.py` (database), `layer2_views.py` (API), tests in `apps/scoring/test_layer2.py`.

## Rules the code keeps

- **Search with the institution's words.** Records are worded differently from the rubric, so the query is the
  answer (or the note), never rubric wording. Attached documents first, sent whole up to 8,000 characters, then the
  run's corpus with its own 4,000-character share, because answers often point at something already submitted. The
  run's own ranker is used (keyword and embedding ranks fused when the run used hybrid retrieval; each check records
  which). Passages that mostly repeat text already taken are skipped.
- **Peer-reviewer standard.** A submitted record is evidence of what it states; several passages can support a claim
  together; nothing is rejected for not repeating a dimension word for word.
- **Typed text is the query and the claim, never evidence.** An answer counts only when the search finds something
  that supports it (Harsha, 12 Nov). If nothing is found there is no model call; the follow-up asks for a document.
- **Credit rises only on evidence the first pass didn't see.** Requirements are re-judged on their provisional packet
  (from the run trace) plus the new passages and the new documents' pages extraction tagged for the indicator. Part by
  part, a rise is taken only when the part cites, in either judging pass, a passage that was not in that packet;
  other parts keep their provisional result and the credit is recomputed. Untouched requirements are copied.
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
| Depth | `depth_judge export.json` (existing) now reads checked answers and their passages | one per credited condition answered |
| Credit | `layer2_rejudge export.json --run --out result.json` | two passes + tie-break per key indicator re-judged |

`evaluate()` gained `fixed_contexts`: the credit path calls the main judge on a cut-down rubric with given packets
instead of retrieval.

## Not built

- Publishing the credit path's result as a run that refines the provisional run (`refines_run_id`); today it returns
  merged records and the final score.
- Metering of second-layer model calls against the run budget (they use the extraction client directly).
- A Celery task for checks (answers wait for the command unless `SECOND_LAYER_CHECK_ON_SUBMIT` is on, which checks in
  the request).
- Who may answer: the views use `CanManageSprint`, like the run views.
- Contradictions into the review queue and the report.
- Depth judging for requirements newly credited in the credit path; a second round of questions.
- Not run against a real model or the VISTAS export yet.
