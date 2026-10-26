/**
 * True only on the local Vite dev server (`npm run dev`); false in every production build. Used to show
 * development-only helpers (e.g. Baseline Approval's "Start demo revision") that must never reach production.
 * Kept in its own module so tests can stub it.
 */
export const isLocalDev: boolean = import.meta.env.DEV;
