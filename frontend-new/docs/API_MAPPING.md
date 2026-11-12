# Maturity Roadmap frontend: screens, backend APIs and dummies

Design reference: `AIFRC_Maturity_Roadmap_Developer_Handoff_v1.zip` (Option 4, Maturity Roadmap).
Backend: this checkout (branch A1); contract in `backend/docs/API_CONTRACT.md`. Every path below is relative to
`VITE_API_BASE_URL` (default `/api/v1`). Service functions live in `src/services/*.ts`. The backend is not changed.

Rule used throughout: **everything the backend supports is wired to its real API; everything it does not
support is a dummy** — the prototype's sample content inside a block marked "Sample data" (`Dummy` in
`src/components/ui.tsx`), so sample figures are never read as real ones. All menus and screens exist.

## Authentication

JWT as the existing frontend: `POST /auth/login` → `access_token` + `refresh_token`, bearer on every request,
silent `POST /auth/refresh` on a 401, `POST /auth/logout`, `GET /auth/me`, `POST /auth/password-reset`.
Tokens live in this app's own localStorage keys (`aircampus_*`).

## Shell (every screen)

| Element | Endpoint |
|---|---|
| Sprint / institution switcher | `GET /sprints` |
| Data-requests and notifications badges | `GET /evidence-requests/summary` |
| Journey strip, "Next step" | derived from `sprint.status` |

## Evidence-based capability assessment (A1 only)

`src/services/capability.ts`, `src/hooks/useCapability.ts`, `src/components/Capability.tsx`:

| Use | Endpoint |
|---|---|
| Run history (+ `enabled` flag) | `GET /sprints/{id}/capability-runs` (polled while a run is queued/running) |
| Latest completed run: score bounds, conditions, citations, tiers, pathways | `GET /sprints/{id}/capability-runs/{run}` |
| Start a run (button + confirmation; uses model credits; `Idempotency-Key`) | `POST /sprints/{id}/capability-runs` with `{scope_mode: "default"}` |
| Cancel a running run | `POST /sprints/{id}/capability-runs/{run}/cancel` |
| Latest completed recommendation (foundation plan: goals, routes) | `GET .../{run}/recommendations`, `GET .../{run}/recommendations/{id}` |
| Leadership / evidence report, PDF · HTML · JSON | `GET .../{run}/report?file=&audience=&recommendation_id=` |

Not used (left to the existing frontend): starting recommendations, plan evaluations, action-state updates,
custom-scope refinement runs, source-identity confirmation.

## Screens

| Screen (route) | Real data | Dummy (sample) parts |
|---|---|---|
| Executive overview (`/`) | `/sprints/{id}/overview`, capability run (tier, score), assessment cycles | — |
| Institution onboarding (`/onboarding`) | `GET/POST /institutions`, `POST /sprints`, `PATCH /sprints/{id}`, coordinator resend | — |
| Institution profile (`/profile`) | `/institutions/{id}` (+ departments, systems), `/assessments/institutions/{id}/profile`, applicability preview (staff), `PATCH /institutions/{id}` | Investment appetite and constraints |
| Sprint setup (`/sprint`) | overview, `/work-summary`, `PATCH /sprints/{id}` | — |
| Data requests (`/requests`) | `GET /evidence-requests?sprint=`, `POST /evidence-requests/{id}/submit` | Reminder and escalation status |
| Upload & processing (`/uploads`) | documents, upload-file, extraction jobs (start / stop / poll), download | — |
| Evidence intelligence (`/evidence`) | facts page + facets | — |
| Evidence review (`/review`) | facts `?status=extracted`; confirm / reject / correct / request-evidence | — |
| AI readiness assessment (`/assessment`) | capability runs (start, cancel, indicators with conditions and citations); audit CRI: `POST /sprints/{id}/score`, `/scoring/config` | — |
| Benchmark comparison (`/benchmark`) | `/assessments/cycles` (+ create, staff) | — |
| Gap analysis (`/gaps`) | gaps page + facets, resolve / unavailable / skip, benchmark plan gaps | — |
| CRI & maturity standing (`/cri`) | capability standing (bounds, coverage, Silver/Gold/Platinum eligibility with threshold, pillar floor, gates); audit CRI; benchmark component averages | — |
| Level pathway (`/pathway`) | capability tiers + pathways (requirements remaining, projected minimum), benchmark levels, foundation-plan routes | Progression timeline, only until a recommendation exists |
| Transformation plan (`/plan`) | foundation-plan routes and goals, benchmark improvement plan (+ generate, staff), audit recommendations (+ generate) | Routes (only until a recommendation exists); route approval |
| Goals & tasks (`/goals`) | benchmark plan initiatives and tasks (status, add task) | — |
| Progress & reassessment (`/progress`) | `/score/history`, overview, plan; reassess = `POST /score` | Projected CRI, next reassessment, stage-gate readiness |
| Reports & exports (`/reports`) | capability report (PDF/HTML/JSON × leadership/evidence); audit reports (generate, poll, PDF/DOCX, JSON) | Evidence register, roadmap, board presentation exports |
| AI advisor (`/copilot`) | `POST /sprints/{id}/evidence-search` (cited passages) | Written conversational answer |
| Compliance mapping (`/compliance`) | cycle benchmarks by source class; staff: source library | — |
| People & roles (`/team`) | `/users` (users.manage), `/auth/access-matrix` | — |
| Notifications (`/notifications`) | evidence-request summary and overdue list | Notification preferences |
| Benchmark Studio (`/benchmarkstudio`, staff) | `/benchmarks/sources/summary`, `/benchmarks/pillars` | — |
| Platform settings (`/admin`) | `/health`, `/scoring/config`, `POST /auth/change-password` | Organisation, integrations, data governance, audit settings |
| Help (`/help`) | — (static guide links) | — |

## Access rules

`src/utils/access.ts` copies `frontend/src/utils/access.ts` (same roles and action keys); each roadmap screen is
mapped to the existing menu rule it corresponds to. The server stays the authority.

## Decisions and assumptions

- **Maturity tier**: from the capability run's `tiers` (highest `demonstrated` one) when a completed run exists;
  otherwise benchmark levels L3 / L2 / L1 read as Silver / Gold / Platinum (lowest scored benchmark level). Never
  inferred from an upper bound; `badge_policy: not_calibrated` awards none.
- Unknown or contradictory conditions stay unknown — shown as such, never as a pass or a fail.
- `GET /sprints/{id}/baseline` and `GET /sprints/{id}/score` are not called: both create records on first
  read. The audit CRI is read from `/overview`.
- Starting a capability run spends model credits, so it needs an explicit click plus a confirmation.

## Full API audit (5 Nov 2026)

Every A1 backend route (214) was compared with the frontend. The UI flow is fixed, so only existing screens were
connected; no menus or screens were added.

- **Service layer:** every endpoint now has a typed function in `src/services/*` (accounts, users, institutions
  and their departments / systems / leaders, sprints, documents, Drive import, extraction jobs, AI usage, facts,
  verification, corrections, AI-QIF tags and expert queue, profile suggestion, guided review batch, evidence
  requests, gaps, baseline, recommendations, vector index, capability runs / advice / plan evaluations,
  assessment cycles, templates, score rules, and the read-only benchmark library).
- **Newly connected on existing screens:**
  - `/reset-password` (link in the reset email): `POST /auth/password-reset/confirm`
  - `/activate-account` (link in the coordinator invitation): `POST /auth/invitation`, `POST /auth/invitation/accept`
  - Progress → CRI projection: next undemonstrated capability pathway's `projected_minimum`
  - Reports → Evidence register (CSV): all pages of `GET /sprints/{id}/facts` plus missing-document gaps
  - Settings → AI and processing (InGage staff): `GET /extraction-jobs/usage-report`
- **Still sample / not supported by the backend:** the numbered list for the backend developer (BR-01 to BR-31)
  is published at https://claude.ai/artifact/6js64rjhCUqq8J1F5gxcRt.

## A2 architecture pass (12 Nov 2026)

Branch A2 = A1 + part-credit judging + the depth follow-up skeleton. Theme and every existing menu are unchanged;
new screens are added to the existing sidebar groups (rules in `src/utils/access.ts`, menus in `src/navigation.ts`).

- **One headline score (A2 part credit):** `Result.score`, `documented` (per readiness area and indicator) and per-condition
  `credit` / `parts` / `cause` are read in `src/types/capability.ts`; `scoreLabel` prefers `score`, earlier runs keep bounds.
  Shown in `Capability.tsx` (nine readiness areas, part findings, why conditions are unknown).
- **New screens:** Setup guide (`/auth/guide-*`, menu tours), Processing control (Drive import, processing summary,
  extraction jobs, search index, sprint AI usage), Verification & corrections (guided review batch, verification summary,
  shadow report, re-verify, correction approve/reject/withdraw, bulk confirm), AI-QIF tagging (tag review/add/edit/reopen,
  fact kind, expert queue + auto-check, profile suggestion), Baseline approval (approve / provisional / return / revise,
  409 handling), Assessment runs (history, any run's result, frozen run evidence, cancel), Depth follow-up (derived from
  the latest run; responses and judgments are sample data: the backend has no depth API yet), Benchmark cycles (cycle
  actions, scope and target, evidence submit / review / download, assessor input, scorecard), Recommended actions
  (start / cancel grounded advice, action owner / feasibility / status, audit recommendation edit and status),
  Plan comparison (plan evaluations, cancel, HTML / JSON), Institutions (portfolio dashboard, coordinator, departments,
  systems, leaders, archive, deletion preview and delete), Assessment setup (templates, score rules, college profiles),
  Benchmark library (catalogue detail, requirements and suggestions, sources and versions, releases and diff, watcher,
  candidates, AI jobs, reference; read-only).
- **Added to existing screens:** People & roles (create, edit, deactivate / reactivate, deletion preview and permanent
  delete), Data requests (full request view: assign, comment, review, retry AI check), Gap analysis (assign, upload
  evidence, choose a contradiction's value, plan-gap update and validate), Upload & processing (edit, confirm category,
  delete, retry / stop / clear job, re-run incomplete), Sprint setup (archive, delete), full-fact view (verification
  detail, proposed corrections, assign, propose correction).
- **Deliberately not called:** `GET /sprints/{id}/score` (creates a first score on read; recalculation uses POST),
  `GET /sprints/{id}` and `GET /sprints/{id}/evidence-requests` (the list endpoints already return the same data).

### Menu merges (2B, 12 Nov 2026)

Overlapping menus were merged into the original roadmap menus; no endpoint was dropped:
- **Assessment runs** → AI readiness assessment (`components/RunHistory.tsx`: run history, any run's result, frozen evidence).
- **Benchmark cycles** → Benchmark comparison (`components/CycleWorkspace.tsx`: cycle actions, per-benchmark dialog, scorecard).
- **Benchmark library** → Benchmark Studio (library tabs plus the former Studio summary).
- **Audit recommendations** are edited only in Transformation plan (`components/AuditRecommendations.tsx`); Recommended
  actions keeps the assessment advice.

Menus that still show sample data (Level pathway, Progress & reassessment, Notifications, the sample blocks and the
Silver/Gold/Platinum visuals) are unchanged while their APIs are requested from the backend team.

### New flow and second layer (12 Nov 2026, after Siddharth's reply)

- **Flow:** menus grouped as Start · 1 Initial evidence · 2 Assessment · 3 Report & recommendations; the journey strip
  follows it (Set up, Initial evidence, Assessment, Report & recommendations). Benchmark comparison, Gap analysis and
  CRI & maturity standing sit in the report step.
- **Questionnaire** (`src/pages/Questionnaire.tsx`, replaces Depth follow-up), one item at a time with answer box,
  prominent upload and Skip:
  - line 1, before the assessment: guided review cases (`/sprints/{id}/review-batch`), Skip only moves on;
  - line 2, after the provisional score: `GET .../capability-runs/{run}/questions` (a follow-up first),
    `POST .../questions/{q}/responses`, `POST .../responses/{r}/follow-up`, `GET .../responses/{r}` polled while
    "pending"; at most one follow-up; files are uploaded through the document API first and processed, then
    referenced by id;
  - additional evidence: `GET/POST .../additional-evidence` with at least one area, key indicator or requirement.
- **Removed after the reply:** R-02 and R-06 samples (score history now on CRI & maturity standing), R-08
  (Notifications menu), R-09 sample, the AI advisor sample (renamed Evidence search), the three fixed paces (D-03).
- **Report step:** each indicator, requirement and area has room for "how this score was reached"
  (`ScoreExplanation` in `src/types/capability.ts`), shown when the backend sends it.
- Open items are tracked in `src/utils/apiStatus.ts` (Backend status screen, Review mode).
