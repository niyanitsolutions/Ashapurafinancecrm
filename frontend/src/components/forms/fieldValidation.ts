import type { FormField } from "@/features/customer/api";

// Phase 3.1 — the frontend mirror of backend/app/features/customer/field_validation.py.
// This is UX only (inline errors, progress %) — the backend re-validates independently
// on submit/create, so drift here can never let bad data through, only produce a worse
// error message shown a step later than it could have been.

const FORMAT_PATTERNS: Record<string, RegExp> = {
  email: /^[^@\s]+@[^@\s]+\.[^@\s]+$/,
  mobile: /^[6-9]\d{9}$/,
  pan: /^[A-Z]{5}\d{4}[A-Z]$/,
  aadhaar: /^\d{12}$/,
  ifsc: /^[A-Z]{4}0[A-Z0-9]{6}$/,
  gst: /^\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z]{1}[A-Z\d]{1}$/,
  pincode: /^\d{6}$/,
};

const FORMAT_LABELS: Record<string, string> = {
  email: "a valid email address",
  mobile: "a valid 10-digit mobile number",
  pan: "a valid PAN (e.g. ABCDE1234F)",
  aadhaar: "a valid 12-digit Aadhaar number",
  ifsc: "a valid IFSC code",
  gst: "a valid GST number",
  pincode: "a valid 6-digit PIN code",
};

function isBlank(value: unknown): boolean {
  return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
}

export function isFieldVisible(field: FormField, values: Record<string, unknown>): boolean {
  const condition = field.visible_when;
  if (!condition) return true;
  const current = values[condition.field_key];
  if (condition.operator === "equals") return current === condition.value;
  if (condition.operator === "not_equals") return current !== condition.value;
  if (condition.operator === "in") return Array.isArray(condition.value) && condition.value.includes(current);
  return true;
}

// Governance round — `trim`/`auto_uppercase` are applied before validating (and before
// the value is stored), mirroring backend `field_validation.normalize_field_value`.
// Non-string values pass through unchanged.
export function normalizeFieldValue(field: FormField, value: unknown): unknown {
  const validation = field.validation;
  if (!validation || typeof value !== "string") return value;
  let next = value;
  if (validation.trim) next = next.trim();
  if (validation.auto_uppercase) next = next.toUpperCase();
  return next;
}

export function validateField(field: FormField, value: unknown): string | null {
  if (isBlank(value)) {
    return field.required ? `${field.label} is required.` : null;
  }
  const validation = field.validation;
  if (!validation) return null;

  const text = String(value);
  if (validation.min_length != null && text.length < validation.min_length) {
    return `${field.label} must be at least ${validation.min_length} characters.`;
  }
  if (validation.max_length != null && text.length > validation.max_length) {
    return `${field.label} must be at most ${validation.max_length} characters.`;
  }
  if (validation.format) {
    const pattern = FORMAT_PATTERNS[validation.format];
    if (pattern && !pattern.test(text)) {
      return `${field.label} must be ${FORMAT_LABELS[validation.format] ?? "in the correct format"}.`;
    }
  }
  if (validation.pattern && !new RegExp(validation.pattern).test(text)) {
    return `${field.label} is not in the correct format.`;
  }
  if (field.field_type === "number") {
    const number = Number(value);
    if (!Number.isNaN(number)) {
      if (validation.min_value != null && number < validation.min_value) {
        return `${field.label} must be at least ${validation.min_value}.`;
      }
      if (validation.max_value != null && number > validation.max_value) {
        return `${field.label} must be at most ${validation.max_value}.`;
      }
    }
  }
  if (field.field_type === "date") {
    if (validation.min_date != null && text < validation.min_date) {
      return `${field.label} must be on or after ${validation.min_date}.`;
    }
    if (validation.max_date != null && text > validation.max_date) {
      return `${field.label} must be on or before ${validation.max_date}.`;
    }
  }
  return null;
}

/** Errors keyed by field `key`, considering only currently-visible fields. */
export function validateFormData(fields: FormField[], values: Record<string, unknown>): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const field of fields) {
    if (!isFieldVisible(field, values)) continue;
    const error = validateField(field, values[field.key]);
    if (error) errors[field.key] = error;
  }
  return errors;
}

/** % of currently-visible required fields that have a value — a display indicator only. */
export function computeProgress(fields: FormField[], values: Record<string, unknown>): number {
  const requiredVisible = fields.filter((f) => f.required && isFieldVisible(f, values));
  if (requiredVisible.length === 0) return 100;
  const filled = requiredVisible.filter((f) => !isBlank(values[f.key])).length;
  return Math.round((filled / requiredVisible.length) * 100);
}
