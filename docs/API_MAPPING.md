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
