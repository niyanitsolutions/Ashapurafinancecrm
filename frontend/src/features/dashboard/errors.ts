// Backed by the shared implementation (frontend/src/shared/api/errors.ts) — kept as a
// re-export here rather than moved, so every existing `@/features/dashboard/errors`
// import keeps working unchanged. See that file for the actual logic.
export { getErrorMessage } from "@/shared/api/errors";
