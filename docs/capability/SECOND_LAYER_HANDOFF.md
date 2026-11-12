# Second assessment layer: handoff (skeleton, 12 Nov 2026)

What happens after the provisional score: the institution answers the second line of questions one at a time
(depth questions about credited requirements, "nothing found" questions about uncredited ones), may answer one
follow-up per question, and may add evidence it thinks was missed. Design: claude.ai doc "AI-READY: second assessment
layer — architecture for follow-ups and new evidence". Code: `apps/scoring/capability/layer2.py` (logic),
`layer2_service.py` (database), `layer2_views.py` (API), tests in `apps/scoring/test_layer2.py`.

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
