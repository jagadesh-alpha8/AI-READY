# Source Library (benchmark backend, stages 1-2)

App: `apps/benchmarks`. Tables follow the manager's foundation schema (`authorities`, `frameworks`,
`source_documents`, `source_versions`, `source_feeds`, audit log) plus stage 2 (`source_sections`,
`requirement_candidates`, `requirements`). UI: Benchmark Studio > Sources (InGage staff only).

## Workflow

| Step | How | Result |
|---|---|---|
| 1. Import the intern Source Register | `python manage.py import_source_register "<file>.xlsx"` (dry run), then `--commit` | Draft versions with review flags; watch feeds created disabled |
| 2. Store + verify files | `python manage.py ingest_source_files` (or "Fetch & verify file" in Studio) | File copied from Drive into `media/source_library/<sha256>`; checksum compared with the register |
| 3. Approve a version | Studio > Approve (note required; open flags must be acknowledged) | Version `active` and locked; previous active version `superseded` |
| 4. Draft requirements | Studio > "Draft requirements with AI" (Celery task; follows `AI_PROCESSING_MODE`) | Sections by page + AI drafts; drafts whose quote isn't in the source are dropped |
| 5. Review drafts | Studio > Review: edit / accept / reject | Accepted drafts become `Requirement`s (`<SOURCE>-R001`, page + exact quote kept) |

Re-run step 1 any time the sheet changes: drafts update in place, approved versions are never touched.

## The benchmark framework: InGage AI-QIF v1.0

AI-QIF is the framework the library is built on. It replaces the Source Pack catalogue below; that catalogue's 60
drafts are withdrawn, not deleted.

```
python manage.py import_aiqif "source_library_work/InGage_AI_READY_AI_QIF_Master_v1_0_AI_Criteria.xlsx"                    # dry run
python manage.py import_aiqif "source_library_work/InGage_AI_READY_AI_QIF_Master_v1_0_AI_Criteria.xlsx" --withdraw-others --commit
```

| Workbook sheet | Stored as |
|---|---|
| AI Benchmark Master: 9 criteria | `Pillar` `AIQIF-C1`..`C9`, with `weight` (out of 1000; they add up to 1000) |
| AI Benchmark Master: 36 key indicators | `Benchmark` `AIQIF-C1.1`..`C9.4` (draft, kind *proposed*, `weight` = KI weight, `framework` = `AIQIF-V1.0`) + `Capability` (what is benchmarked) |
| L3 / L2 / L1 columns | `MaturityDefinition`, `is_placeholder=True` (one template, only the KI name changes), so an expert confirms or rewrites each level in Studio > Levels |
| AI-QIF Maturity (6 dimensions) | each level's `observable_requirements` (e.g. "Strategy: AI intent/priority defined ...") |
| NAAC → AI-QIF Crosswalk | `Benchmark.naac_crosswalk` [{metric, requirement, relationship, shared_with}]; a metric mapped to "C3.1 / C3.2" is on both. 125 rows → 197 links; 9 KIs have none |
| Principles, Scoring Architecture, the rule columns (tests, evidence standard E0–E5, target / gap / transformation rules) | `Framework` `AIQIF-V1.0` `purpose` (authority `INGAGE`); Target Rule → each benchmark's `target_guidance` |

The import checks the weights (criteria = 1000, each criterion = sum of its KIs) and reports crosswalk rows naming
an unknown KI. Re-running updates drafts only and keeps expert-written levels and target guidance. Levels are
named as in AI-QIF: L3 Foundational, L2 Good / Recommended, L1 Advanced / Aspirational. Before release every
benchmark still needs, per the release checklist: real levels, an expert owner, evidence types, evidence rules
per level and applicability rules -- the workbook has none of these yet. Weights are stored and shown; CRI
scoring does not use them yet.

The catalogue list hides withdrawn benchmarks (`?status=all` shows them) and the pillar list hides pillars whose
benchmarks are all withdrawn.

## AI-written benchmark content (fully automatic)

Decided 2026-10-15 (experts: "use AI for all", fully automatic): the AI writes each draft AI-QIF indicator's
L3/L2/L1 (definition, measurement rule, observable requirements, minimum evidence, outcomes, non-examples),
3-9 evidence rules (a mandatory one on every level), 1-3 applicability rules, target guidance and owner -- and
that counts as the content, with no expert approval first.

```
python manage.py ai_draft_benchmarks                  # every AI-QIF draft still on template levels, one after another
python manage.py ai_draft_benchmarks --queue          # one background job per indicator, in parallel on the routers
python manage.py ai_draft_benchmarks AIQIF-C1.1       # one indicator; --redo to rewrite AI content again
```

Safeguards (`services/ai_drafting.py`):
- The answer must match a JSON schema whose choices are the real catalogues (EV-01..12, institution and
  programme types, statuses, approval bodies).
- It is saved through the same services as a person's edit, so the same checks apply: no template text, distinct
  levels, list and value limits, a mandatory rule per level.
- A draft that fails any check is not saved; the indicator stays exactly as it was.
- Every AI-written level and rule has `ai_model` (shown as an **AI-generated** badge in the Studio), is saved as
  the `ai.drafter@system.ingage.local` account (inactive, cannot sign in), and is audited (`benchmark.ai_drafted`
  with the model's rationale).
- A level or rule a person wrote is never overwritten. A person editing AI content clears its `ai_model`.
- Only drafts are written; creating and publishing a release is still a separate step.

Migration `0014_ai_drafting` also seeds the 12 evidence types (EV-01..12) on databases that never imported the
Source Pack.

## Benchmark catalogue (stage 3.1, replaced by AI-QIF)

```
python manage.py import_benchmark_catalogue "source_library_work/InGage_Benchmark_Source_Pack_v0_2_Expanded_Foundation.xlsx"            # dry run
python manage.py import_benchmark_catalogue "source_library_work/InGage_Benchmark_Source_Pack_v0_2_Expanded_Foundation.xlsx" --commit
```

Loads the Source Pack's pillars (Read Me), evidence types (Evidence Catalogue) and benchmarks with their
L3/L2/L1 text (Benchmark Catalogue) as drafts: tables `Pillar`, `EvidenceType`, `Capability` (one per
benchmark), `Benchmark`, `MaturityDefinition`, plus `BenchmarkRequirement` for stage 3.2. Benchmark kind comes
from the Benchmark Class column (mandatory / guidance / proposed). Level text shared word-for-word by 3+
benchmarks is the Source Pack's template and is stored with `is_placeholder=True` -- in v0.2 that is all 60.
Re-running updates drafts only. Studio > Catalogue shows it; API: `/api/v1/benchmarks/catalogue`,
`/catalogue/<code>`, `/pillars`, `/evidence-types`.

## Linking requirements to benchmarks (stage 3.2)

Studio > Requirements lists approved requirements (filter: not linked yet) with suggested benchmarks;
Studio > Catalogue > a benchmark shows its linked requirements and links one by code. Relationship:
`primary` | `supporting` | `crosswalk`. Links change only while the benchmark is a draft and never for a
requirement from a withdrawn source version; every change is audited (`benchmark.linked` / `link_changed` /
`unlinked`).

Suggestions (no AI call, so they cost nothing and work offline) are ranked and explained: +3 when the
benchmark's Source Pack source basis names the requirement's authority or the source title's acronym (e.g.
"DPDP"), +2 per source-title word in the source basis, +1 per shared term between the requirement and the
benchmark's title/capability. Already-linked benchmarks are left out. People decide; nothing is linked
automatically.

```
GET    /api/v1/benchmarks/catalogue/<code>/requirements
POST   /api/v1/benchmarks/catalogue/<code>/requirements   {requirement_code, relationship, note}
DELETE /api/v1/benchmarks/catalogue/<code>/requirements/<requirement_code>
GET    /api/v1/benchmarks/requirements?unlinked=1
GET    /api/v1/benchmarks/requirements/<code>/suggestions
```

## Writing L3/L2/L1 levels (stage 3.3)

Studio > Levels (or Catalogue > a benchmark > "Write L3 / L2 / L1"). Per level: definition, measurement rule,
observable requirements, minimum evidence, outcome expectations, non-examples (one per line), "requires manual
review". Per benchmark: expert owner, target guidance, release-readiness checklist, edit history.

Server rules: only draft benchmarks; a definition needs at least 40 characters, may not be the Source Pack
template text, and may not repeat another level of the same benchmark. Saving clears `is_placeholder`, records
who/when, and writes a `benchmark.level_saved` audit event with before/after. Re-importing the catalogue never
overwrites an expert-written level.

Readiness (`required` items must all pass before a benchmark can enter a release): all three levels written,
evidence types chosen, applicability stated, a primary requirement linked (recommended only for
InGage-proposed benchmarks), expert owner (required for proposed, recommended otherwise). Non-examples are
recommended. Evidence rules (3.4), structured applicability (3.5) and scoring rules show as `pending`.

```
PATCH /api/v1/benchmarks/catalogue/<code>                 {expert_owner, target_guidance}
PUT   /api/v1/benchmarks/catalogue/<code>/levels/<L3|L2|L1>
GET   /api/v1/benchmarks/catalogue/<code>/readiness
GET   /api/v1/benchmarks/catalogue/<code>/history
```

## Evidence rules (stage 3.4)

What evidence proves a benchmark level or a requirement. One table (`EvidenceRule`), exactly one target:
- a **benchmark** (optionally one level; blank = all levels) -- the manager prototype's per-level evidence
  requirements; written in Studio > Levels > Evidence rules (quick-start buttons pre-fill from the
  benchmark's evidence types; nothing is created until saved);
- a **requirement** -- the foundation schema's `requirement_evidence_rules` (one rule per requirement and
  evidence type).

Fields: evidence type (EV-xx), title, description, mandatory, minimum count, maximum age in months, scope,
validation method (manual / AI-assisted / automatic extraction / system integration), privacy class.
Benchmark rules change only while the benchmark is a draft; requirement rules only while every benchmark
linked to the requirement is a draft. A benchmark rule with a new evidence type adds it to the benchmark.
Everything is audited (`evidence_rule.created` / `updated` / `deleted`).

Readiness now requires at least one mandatory rule for each of L3, L2 and L1 (an all-levels rule counts for
all three) and recommends rules on every primary requirement.

```
GET/POST     /api/v1/benchmarks/catalogue/<code>/evidence-rules (see below for applicability)
GET/POST     /api/v1/benchmarks/requirements/<code>/evidence-rules
PATCH/DELETE /api/v1/benchmarks/evidence-rules/<id>
```

## Rules enforced in code

- Approved (active/superseded/withdrawn) versions: version, dates, file, checksum and links can't change; they
  can't be deleted; status only moves active -> superseded / withdrawn.
- A version can be approved only with a version label and either a stored, checksum-checked file or a
  link-only / licensed status.
- Files are stored once by content hash and never overwritten. A Drive file whose checksum differs from the
  register is not stored (`mismatch`). Unfinished downloads (`.crdownload`, ...) are refused.
- Licensed standards (ISO/IEC) are never downloaded or stored.
- The audit log (`SourceAuditEvent`) is append-only; every import, intake, approval and review is recorded.
- AI drafts are only candidates; only an expert's accept creates a requirement.

## Intake results

`verified` checksum matches the register - `computed` stored, register had no checksum - `mismatch` not
stored, wrong or changed file - `skipped` folder link / no link / licensed - `failed` Drive refused, network
error or incomplete download. Drive files must be shared "Anyone with the link - Viewer"
(`GOOGLE_DRIVE_API_KEY` in `.env`).

## API (InGage staff: super_admin, consultant)

```
GET  /api/v1/benchmarks/sources[?category=&authority=&role=&collection=&q=]
GET  /api/v1/benchmarks/sources/summary
GET  /api/v1/benchmarks/sources/<source_code>
POST /api/v1/benchmarks/versions/<id>/intake
POST /api/v1/benchmarks/versions/<id>/approve        {note, acknowledge_flags}
POST /api/v1/benchmarks/versions/<id>/withdraw       {note}
POST /api/v1/benchmarks/versions/<id>/draft-requirements
GET  /api/v1/benchmarks/versions/<id>/candidates[?status=pending]
POST /api/v1/benchmarks/candidates/<id>/review       {decision: accept|reject, statement?, kind?, note?}
GET  /api/v1/benchmarks/requirements[?source_code=&kind=]
```

## Applicability (stage 3.5)

Which benchmarks (or requirements) apply to an institution. Reference lists (seeded by migration 0008):
institution types (university, engineering, polytechnic, arts_science, iti, health_sciences), 11 programme
types, statuses (university / autonomous / affiliated / constituent / standalone) and approval bodies
(UGC, AICTE, NAAC, NBA, NIRF, DGT, NCVET, NMC, DCI, INC, PCI, State board).

`ApplicabilityRule` (schema: requirement_applicability, extended to benchmarks): result (applies /
does_not_apply / optional / requires_review), priority, and conditions -- institution types, statuses,
programmes offered (any of), approvals held (any of), jurisdiction. An empty condition matches everyone.
Rules run lowest priority first; the first whose conditions all match decides and gives the reason (its own
`reason`, or the matched conditions). Nothing matching -> does_not_apply, with what was needed. **No rules ->
requires_review, never applies.** Same edit guards and audit as evidence rules.

Note: in Source Pack v0.2 all 60 benchmarks carry the same applicability text (every institution type), so it
can't distinguish anything; it is shown for reference only and readiness requires real rules.

Studio > Levels > Applicability rules (per benchmark) and Studio > Applicability (describe a college, see every
benchmark's result and reason).

```
GET          /api/v1/benchmarks/applicability/reference
POST         /api/v1/benchmarks/applicability/preview        {institution_type, autonomous_status, programme_types[], approval_bodies[], jurisdiction}
GET/POST     /api/v1/benchmarks/catalogue/<code>/applicability-rules
GET/POST     /api/v1/benchmarks/requirements/<code>/applicability-rules
PATCH/DELETE /api/v1/benchmarks/applicability-rules/<id>
```

## Releases (stage 3.6)

Studio > Releases. A release is a complete, versioned set of benchmarks (schema: `benchmark_releases`,
`benchmark_release_items`; plus change type `unchanged` for items carried forward from the current release).

| Step | Rule |
|---|---|
| Create | One release in progress at a time; starts with every benchmark of the current release as `unchanged` |
| Add / retire | Draft benchmarks are `added` (or `updated` if published before); an active one can be `retired` |
| Submit (draft -> review) | Every added/updated benchmark must pass all `required` readiness checks; first release warns outside 20-30 benchmarks |
| Approve (review -> approved) | The approver must not be the submitter (four-eyes) |
| Publish (approved -> published) | Freezes each item's snapshot (levels, evidence rules, applicability, requirements + quotes) with a SHA-256, plus a release hash; benchmarks become `active` (or `withdrawn`); the previous release becomes `retired` but is never changed |
| Send back | review/approved -> draft, reason required |
| Reopen benchmark | active -> draft with a new version label (`v0.2` -> `v0.2.r1`) for the next release |

While a benchmark is in a release under review or approved, every edit to it (levels, evidence rules,
applicability, links) is refused -- what was approved is exactly what is published. Published items can never
change. `GET /releases/current` is the only release new scorecards may use.

```
GET/POST /api/v1/benchmarks/releases                         {release_label, release_notes}
GET      /api/v1/benchmarks/releases/current
GET      /api/v1/benchmarks/releases/<label>                  (+ problems, warnings)
POST     /api/v1/benchmarks/releases/<label>/items            {benchmark_code, retire, impact_summary}
DELETE   /api/v1/benchmarks/releases/<label>/items/<code>
POST     /api/v1/benchmarks/releases/<label>/submit | approve | publish | send-back   {note}
GET      /api/v1/benchmarks/releases/<label>/diff
POST     /api/v1/benchmarks/catalogue/<code>/reopen           {reason}
```


## Daily watcher (stage 4)

Studio > Watcher. Checks the official pages of the source feeds people have turned on, once a day, and lists
what changed for review (schema: `source_snapshots`, `source_change_events`, `watcher_runs`).

| Step | What happens |
|---|---|
| Turn a page on | Feeds are imported switched off. A person opens the address, confirms it is the official listing page, and clicks *Watch daily* (audited). Manual-upload sources have nothing to watch |
| Fetch | One request per page, honest User-Agent (`InGage-SourceWatcher/1.0`), robots.txt respected, 2 s pause per site, 30 s timeout, 20 MB limit |
| Compare | Document-index pages: the list of linked documents (title + address). Web pages: the visible text, minus dates, times, counters and bare numbers. Files: the bytes. So a changed date or visitor counter is not a change |
| First check | Saves a first copy (baseline); no change event |
| Same as last time | Records the check only |
| Different | Saves a copy (raw file in `media/source_snapshots/`) and creates change events: `new_document`, `withdrawal` (link removed, or page now 404/410), `new_version` (file changed), `content_change` (text), `access_change` (403/401 or robots.txt now blocks) |
| Importance | 0-100: more for new links whose title says regulation / amendment / notification / guideline / manual / SAR / SSR / norms / circular ..., and for bigger text changes |
| Impact | Approved requirements from that source, benchmarks linked to them, published releases containing those benchmarks |
| Review | A person marks each change *Looking into it*, *Accept*, *Reject* or *Ignore* (note required except for "looking into it"); audited |

The watcher never edits a source, requirement, benchmark or release, and never publishes. Accepting a change only
records the decision; a new source version or a benchmark edit then goes through the normal review and release
steps. A page that fails raises one event when it stops working, not one every day. Material changes also become
benchmark candidates (next section).

**Running it**

```
python manage.py run_source_watcher                                   # every enabled page, saves results
python manage.py run_source_watcher --codes UGC-001 --dry-run --include-disabled   # try a page; saves nothing
celery -A config beat -l info                                         # the daily schedule (needs WATCHER_ENABLED=true)
```

`WATCHER_ENABLED=false` by default so a development machine never contacts government sites on its own;
`WATCHER_HOUR_UTC=20` runs it at 20:30 UTC (02:00 IST). The Studio "Check now" button checks one page at once;
"Check all now" queues a run on the Celery worker.

```
GET  /api/v1/benchmarks/watcher/summary
GET  /api/v1/benchmarks/watcher/feeds?enabled=true|false&q=
POST /api/v1/benchmarks/watcher/feeds/<id>/enable              {enabled, note}
POST /api/v1/benchmarks/watcher/feeds/<id>/check
GET  /api/v1/benchmarks/watcher/runs        POST (queue a run now)
GET  /api/v1/benchmarks/watcher/events?status=open|all|triaged|under_review|accepted|rejected|ignored
POST /api/v1/benchmarks/watcher/events/<id>/review             {status, note}
```

## Benchmark candidates (stage 4b)

Studio > Candidates. Proposed changes to the library, kept apart from approved data until domain experts approve
them (schema: `benchmark_candidates`, `candidate_reviews`; code: `services/candidates.py`).

| Step | Rule |
|---|---|
| From the watcher | Every change event with importance >= 50 (new document, new version, content change, withdrawal) makes one **update benchmark** candidate per benchmark linked to the changed source, or one **review this source** candidate when nothing is linked yet. Starts in *review* |
| Filtered automatically | A low-authority source (intelligence signal, or feed trust score < 50) is created as *rejected*; a candidate that would duplicate an open one for the same benchmark / source is not created |
| By staff | New benchmark / update / retire / source review, from any watcher event ("Create a benchmark candidate") or from scratch. Starts in *research*; *Send to expert review* moves it on |
| Who approves | Regulatory / government sources: accreditation + legal. Accreditation bodies: accreditation + academic. Rankings / standards: academic (+ cybersecurity for CERT-In). AI benchmarks or InGage-proposed ones: + AI governance + academic. Editable until the first review |
| Decisions | Each required role reviewed by a **different person**; any reject rejects; "needs research" sends it back; all roles approve = approved. Reviews are append-only and audited |
| After approval | *Open a new draft* reopens the active benchmark as the next version (same as `reopen`); the candidate is marked **published** when a release that adds / updates / retires that benchmark is published. Nothing changes for colleges before that |

`WatcherRun.candidates_created` counts the candidates each run made.

```
GET/POST /api/v1/benchmarks/benchmark-candidates           ?status=open|all|research|review|approved|rejected|published
GET/PATCH /api/v1/benchmarks/benchmark-candidates/<id>
POST     /api/v1/benchmarks/benchmark-candidates/<id>/submit | review | open-revision
POST     /api/v1/benchmarks/watcher/events/<id>/propose
```
