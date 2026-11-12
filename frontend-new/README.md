# AI Ready Campus: Maturity Roadmap frontend

A separate React + TypeScript frontend for the existing Django/DRF backend, following the AIFRC
"Maturity Roadmap" (Option 4) handoff: one journey from onboarding through audit sprint, readiness,
transformation and outputs. It reuses the backend's APIs and JWT authentication and has no mock data.
`frontend/` and `backend/` are untouched.

## Run

Requires Node 20+ (tested on Node 24) and the backend on `http://localhost:8000`.

```bash
cd frontend-new
cp .env.example .env        # optional: defaults work for local development
npm install                 # .npmrc sets legacy-peer-deps=false
npm run dev                 # http://localhost:5173, /api proxied to the backend
```

Sign in with an existing backend account.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Vite dev server with the `/api` proxy |
| `npm run typecheck` | `tsc -b` |
| `npm run lint` | ESLint (typescript-eslint + react-hooks) |
| `npm test` | Node test runner over `src/**/*.test.ts` (pure utilities) |
| `npm run build` | Type check + production build to `dist/` |

## Configuration (`.env.example`)

- `VITE_API_BASE_URL`: API base the browser calls. Default `/api/v1` (through the dev proxy, or a reverse proxy
  in production). For a backend on another origin, set the full URL and add this app's origin to the
  backend's `CORS_ALLOWED_ORIGINS`.
- `VITE_DEV_API_PROXY_TARGET`: dev proxy target (default `http://localhost:8000`).
- `VITE_DEV_PORT`: dev port (default 5173, already in the backend's default CORS list).

No secrets belong in these files: every `VITE_*` value is compiled into the public bundle.

## Structure

```
src/
  config/env.ts          environment + storage keys
  services/              the API layer: one module per backend area (http.ts = axios client, JWT refresh)
  types/api.ts           response shapes used here
  context/               AuthContext (session), SprintContext (selected audit sprint)
  hooks/                 useResource (load + stale-response guard), usePolling, useCycle, useAccess
  components/            Shell (sidebar, header, journey strip), ui (states, tables, dialog), RequireSprint
  pages/                 one file per screen of the handoff
  utils/                 access rules, maturity mapping, formatting, errors (+ utils.test.ts)
  navigation.ts          sidebar groups, page headings, routes
docs/API_MAPPING.md      screen → endpoint map, assumptions, missing backend support
```

See `docs/API_MAPPING.md` for which endpoints each screen uses and what is not connected yet.
