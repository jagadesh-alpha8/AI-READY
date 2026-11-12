/**
 * Runtime configuration, read once from Vite's build-time environment (see .env.example).
 * Nothing secret may live here: every VITE_* value ends up in the browser bundle.
 */
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '');

/** localStorage keys for this frontend's session, kept apart from the existing frontend's keys. */
export const ACCESS_TOKEN_KEY = 'aircampus_access_token';
export const REFRESH_TOKEN_KEY = 'aircampus_refresh_token';
export const SELECTED_SPRINT_KEY = 'aircampus_selected_sprint';
