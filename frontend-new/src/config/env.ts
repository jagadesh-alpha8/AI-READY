/**
 * Runtime configuration, read once from Vite's build-time environment (see .env.example).
 * Nothing secret may live here: every VITE_* value ends up in the browser bundle.
 */
// import.meta.env exists only under Vite; the unit tests run these modules in plain Node, where it is undefined.
const env: Partial<ImportMetaEnv> = import.meta.env ?? {};

/**
 * Demo build: hides the "Sample data" sections, the Backend status screen and Review mode, so a college sees only
 * what the backend serves. On by default in production builds (the live site); VITE_DEMO_MODE=true or =false at
 * build time overrides it. Off in the dev server unless VITE_DEMO_MODE=true.
 */
export const DEMO_MODE: boolean = env.VITE_DEMO_MODE ? env.VITE_DEMO_MODE === 'true' : !!env.PROD;

export const API_BASE_URL: string = (env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '');

/** localStorage keys for this frontend's session, kept apart from the existing frontend's keys. */
export const ACCESS_TOKEN_KEY = 'aircampus_access_token';
export const REFRESH_TOKEN_KEY = 'aircampus_refresh_token';
export const SELECTED_SPRINT_KEY = 'aircampus_selected_sprint';
