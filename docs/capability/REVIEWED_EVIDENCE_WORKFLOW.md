# Reviewed evidence and bounded review release

## Result

Capability assessments freeze every sprint claim (including context/enabling claims), its current disposition, original/current citation, verification result, review actor/time/rationale and conflict history alongside the current raw pages. The worker sends relevant ledger records through the actual evaluation payload. Publication independently rechecks rejected/superseded citation precedence. New comparable contradictions explicitly reopen uncertainty. Confirmation never maps directly to rubric points.

Rubric `AIQIF-CAP-0.3`, engine `capability-engine-0.3.0` and retrieval `assertion-balanced-windows-0.3` are unchanged. Prompt `AIQIF-EVAL-0.9` adds the review contract while preserving required decisions, scoped quotation checks and bounded correction. There are 216 rubric requirements, not 216 prescribed facts. Additional relevant facts may support an exact requirement, a contextual finding or advice; they cannot supply discretionary points to narrow the unresolved bounds.

## Review journey

Evidence & Review → Review exceptions prepares one persisted initial batch per sprint via explicit POST. Identity mismatches share this batch. Scoped equivalent claims share one question; independent departments, programmes, populations, units and periods remain separate. Relevance uses category links and conservative lexical matches against actual assertions, not legacy CRI weights or invented expected uplift. Links indicate potential relevance, not proven effect on a score.

At most 25 initial questions are frozen, with overflow retained. Answers never refill this initial set. Administrators may finish early, declare uncertainty/unavailability or defer. Optional overflow actions require explicit follow-up intent. Changed/new evidence can be prepared as an additional optional batch, retaining the original questions and answers. Stale questions fail closed rather than applying old decisions to changed claims.

Preparing the initial batch runs existing verification and policy. Shadow mode stays shadow; enforce accepts only already eligible evidence. One deterministic source repair attempt can recover a unique exact line on the cited page when its value and at least two attribute words match. It never changes values or accepts claims. Failed/ambiguous quotation repairs remain system recovery detail, not primary human parsing work. All original check results and repaired snippets remain auditable.

Each question offers supported confirmation/alternative choice, a correction with a basis, evidence upload, cannot establish and defer. Unsupported corrections are explicitly declarations: no invented PDF quote or numerical credit. Current work is separate from historical verification outcomes. Legacy gap penalties are labelled as evidence uncertainty in the main journey; legacy APIs remain compatible and do not gate the capability path.

## Frozen boundary and limits

PostgreSQL uses brief SHARE locks on the evidence/review tables while copying the boundary; no provider work occurs under these locks. This conservatively blocks evidence writes across sprints for the duration of the copy. SQLite uses its transaction snapshot. The production concurrency regression checks a writer paused between review history and claim update: a new assessment must wait and capture both.

Provider ledger context is restricted to selected source pages and compact decision history. Above 32,000 ledger characters for an indicator, evaluation remains unknown without a provider call. Raw frozen history remains complete. This conservative guard can limit findings on exceptionally dense pages; it never discards rejected alternatives to obtain credit. Citation overlap guards may withhold an entire broad quotation containing a rejected claim; independently supported quotations remain usable.

Legacy institution-confirmation request fields remain compatible. The current interface routes essential source identity questions through the shared review budget. Population/period refinement remains optional after the baseline. Claim scope is always required for substantive credit.

## Deployment and fresh acceptance run

1. Check out the merged A1 revision. Apply `python manage.py migrate` (facts migrations 0017 and 0018). Rebuild frontend and restart API and Celery workers at the same revision; mixed prompt versions fail closed.
2. Preserve the existing `FACT_VERIFICATION_MODE`. Inspect the verification summary, exclusion reasons and shadow report before enabling enforce; this release does not change deployment automation mode or calibration.
3. Use a fresh synthetic sprint first. Upload two same-scope documents that disagree, process extraction and select **Prepare review questions**. Confirm grouped duplicate claims and the total initial budget; inspect overflow explicitly.
4. Resolve the scoped discrepancy. Start a **new** capability assessment; pre-existing reports intentionally do not change. Verify the run detail and JSON evidence export include the review ledger, chosen value and rejected alternative, then inspect the corresponding actual provider decision/citation.
5. Generate tailored advice explicitly if desired, and export a leadership report. Downloads, history and queue GETs never dispatch model work. A deterministic fallback is not a test of tailored advice.
6. Add materially contradictory evidence. Verify a new assessment lists the reopened uncertainty and that optional follow-up leaves the original initial batch intact. Compare the old report's frozen assessment hash and decisions.

Synthetic automated coverage exercises the real file upload, PDF page reading, extraction orchestration, verification, grouped human choice, metered scoring worker, recommendation input assembly and report export. Only extraction interpretation and provider responses are fixture-controlled. This is integration validation, not evidence of live-provider semantic quality. Inspect a fresh deployed provider result before claiming that the institution's unresolved range has meaningfully improved.
