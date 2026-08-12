// Backed by the shared implementation (frontend/src/shared/api/errors.ts) — kept as a
// re-export here rather than moved, so every existing `@/features/customer/errors`
// import (including the several other features that import this one as a de facto
// shared helper) keeps working unchanged. See that file for the actual logic.
export { getErrorMessage } from "@/shared/api/errors";
