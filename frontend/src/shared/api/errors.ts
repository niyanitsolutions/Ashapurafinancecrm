// Centralized error-message parsing — the single source of truth for turning anything a
// try/catch might see (an ApiError from the backend's standard envelope, a network
// failure, or an unexpected JS error) into business-friendly, user-facing copy. Every
// feature's own `errors.ts` (auth, employee, customer, leads, ...) re-exports
// `getErrorMessage` from here rather than keeping its own copy of this logic — see those
// files' own comments. Full technical detail always goes to the console for developers;
// only the friendly string (or nothing) ever reaches the UI.
import { ApiError } from "@/shared/api/client";

export interface ValidationFieldError {
  loc: string[];
  type: string;
  msg: string;
}

// Backend error `code` -> friendly message. Covers every AppError subclass
// (backend/app/core/exceptions.py, feature-specific exceptions like
// AlreadyRegisteredError), the two new envelope-normalizing handlers
// (validation_error/internal_error, see core/exceptions.py), and the client-side-only
// codes client.ts assigns to network/parse failures. Where the backend already crafts a
// specific, human message for a given case (e.g. a ConflictError like "This mobile
// number is already registered."), that message is used as-is instead of being
// overridden here — see the default branch in `getErrorMessage`.
const CODE_MESSAGES: Record<string, string> = {
  network_error: "Unable to connect to the server. Please check your internet connection.",
  http_401: "Your session has expired. Please sign in again.",
  http_404: "The requested resource could not be found.",
  http_422: "Please check the highlighted fields.",
  http_429: "Too many requests. Please wait a moment and try again.",
  http_500: "An unexpected server error occurred. Please try again later.",
  unauthorized: "Your session has expired. Please sign in again.",
  not_found: "The requested resource could not be found.",
  rate_limited: "Too many requests. Please wait a moment and try again.",
  internal_error: "An unexpected server error occurred. Please try again later.",
  account_locked: "Too many failed attempts. Your account is temporarily locked — try again in 15 minutes.",
  login_geo_fence_denied: "Login is restricted to an authorized location. Please move to your permitted location or contact your administrator.",
  invalid_credentials: "Incorrect mobile number or password.",
  already_registered: "This mobile number is already registered. Please log in instead.",
  invalid_role_for_signup: "Self-signup is not available for this account type.",
  otp_not_found: "That code has expired. Request a new one.",
  otp_mismatch: "Incorrect code. Please try again.",
  otp_max_attempts_exceeded: "Too many incorrect attempts. Request a new code.",
  invalid_or_expired_ticket: "This session has expired. Please start again.",
  invalid_refresh_token: "Your session has expired. Please log in again.",
};

// Field-name (last segment of a Pydantic `loc` path) -> label, for building "{Label} ..."
// messages. Falls back to humanizing the raw field name when not listed here.
const FIELD_LABELS: Record<string, string> = {
  mobile: "Mobile number",
  alternative_mobile: "Alternative mobile number",
  email: "Email address",
  otp: "Verification code",
  password: "Password",
  new_password: "New password",
  current_password: "Current password",
  confirm_password: "Confirm password",
  full_name: "Full name",
  first_name: "First name",
  last_name: "Last name",
  owner_name: "Owner name",
  company_name: "Company name",
  pincode: "PIN code",
  ifsc_code: "IFSC code",
  gst: "GST number",
  pan_number: "PAN",
  aadhaar_number: "Aadhaar number",
  city: "City",
  preferred_amount: "Preferred loan amount",
};

// Field name -> "must be ..." format description, for the highest-traffic fields across
// the app's ~90 Pydantic `Field(pattern=...)` constraints (mobile/OTP/PIN/IFSC/GST
// specifically — see backend/app/features/*/schemas.py). Fields not listed here (mostly
// closed-set/enum fields like role, status, product_category) fall back to a generic,
// still non-leaking "{Label} is invalid." — the raw regex is never shown either way.
const FIELD_FORMAT_MESSAGES: Record<string, string> = {
  mobile: "must be a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9",
  alternative_mobile: "must be a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9",
  otp: "must be the 6-digit code we sent you",
  pincode: "must be a valid 6-digit PIN code",
  ifsc_code: "must be a valid IFSC code",
  gst: "must be a valid GST number",
};

function humanizeFieldName(name: string): string {
  return name
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function fieldLabel(fieldName: string): string {
  return FIELD_LABELS[fieldName] ?? humanizeFieldName(fieldName || "This field");
}

function friendlyValidationMessage(error: ValidationFieldError): string {
  const fieldName = error.loc[error.loc.length - 1] ?? "";
  const label = fieldLabel(fieldName);

  if (fieldName === "email" || error.msg.toLowerCase().includes("email")) {
    return "Please enter a valid email address.";
  }
  if (error.type === "missing") {
    return `${label} is required.`;
  }
  if (error.type === "string_too_short" || error.type === "string_too_long") {
    return `${label} length is invalid.`;
  }
  const formatMessage = FIELD_FORMAT_MESSAGES[fieldName];
  if (formatMessage) {
    return `${label} ${formatMessage}.`;
  }
  // Deliberately generic and never includes `error.msg`/`ctx` verbatim — FastAPI's raw
  // message for a pattern mismatch embeds the literal regex, which must never reach the
  // user (see docs/api/ERROR_CODES.md).
  return `${label} is invalid.`;
}

/** Field-name -> message map, for forms that want to highlight the specific input(s) in
 * error (e.g. via react-hook-form's `setError`). Returns null when the error carries no
 * per-field detail (anything other than a validation_error with structured `details`). */
export function getFieldErrors(error: unknown): Record<string, string> | null {
  if (!(error instanceof ApiError) || error.code !== "validation_error") return null;
  const details = error.details;
  if (!Array.isArray(details)) return null;

  const fieldErrors: Record<string, string> = {};
  for (const raw of details as ValidationFieldError[]) {
    const fieldName = raw.loc?.[raw.loc.length - 1];
    if (!fieldName) continue;
    fieldErrors[fieldName] = friendlyValidationMessage(raw);
  }
  return Object.keys(fieldErrors).length > 0 ? fieldErrors : null;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    // Technical detail stays in the console for developers, never in the UI (see file
    // docstring).
    console.error(`[API Error] ${error.code}: ${error.message}`, error.details);

    if (error.code === "validation_error" && Array.isArray(error.details) && error.details.length > 0) {
      return friendlyValidationMessage((error.details as ValidationFieldError[])[0]);
    }
    // Prefer the backend's own message when it's a code with no fixed mapping — service-
    // layer AppErrors (ConflictError, NotFoundError, ValidationError, ...) already carry
    // specific, human-written text (e.g. "This mobile number is already registered.",
    // "The selected product is not available.") that's more useful than a generic string.
    return CODE_MESSAGES[error.code] ?? error.message ?? "Something went wrong. Please try again.";
  }

  console.error("[Unexpected Error]", error);
  return "Something went wrong. Please try again.";
}
