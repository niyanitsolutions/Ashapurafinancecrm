import { describe, expect, it } from "vitest";
import { validateField } from "./fieldValidation";
import type { FormField } from "@/features/customer/api";

// Production fix — "Gender must be a dropdown in ALL Product Schemas." Mirrors the
// backend's own static-options membership check (field_validation.py). Also a
// regression guard on a real bug caught while writing the backend test for this: an
// earlier version of both the frontend and backend checks was placed AFTER an
// early-return that fires whenever the field has no `validation` block at all — which
// is exactly the Gender field's real-world shape (no min/max/format/pattern, just
// options) — so the check silently never ran. This test would have caught it.

function selectField(overrides: Partial<FormField> = {}): FormField {
  return {
    key: "gender", label: "Gender", field_type: "select", required: true, options: ["Male", "Female", "Other"],
    section: null, options_source: "static", ...overrides,
  };
}

describe("validateField — static Select options membership", () => {
  it("accepts every declared option", () => {
    expect(validateField(selectField(), "Male")).toBeNull();
    expect(validateField(selectField(), "Female")).toBeNull();
    expect(validateField(selectField(), "Other")).toBeNull();
  });

  it("rejects a value outside the declared options — even with no `validation` block set", () => {
    // The Gender field, as constructed by the backend's own model_validator, never has
    // a `validation` block — this must not skip the options check.
    expect(selectField().validation).toBeUndefined();
    expect(validateField(selectField(), "unknown-value")).toBe("Gender must be one of: Male, Female, Other.");
  });

  it("does not apply the options check to an API-sourced Select (real options live elsewhere)", () => {
    expect(validateField(selectField({ options_source: "api", options: null }), "anything")).toBeNull();
  });

  it("does not apply the options check to a non-Select field", () => {
    expect(validateField({ key: "notes", label: "Notes", field_type: "textarea", required: false, options: null, section: null }, "anything")).toBeNull();
  });

  it("required-but-empty still short-circuits before the options check", () => {
    expect(validateField(selectField(), "")).toBe("Gender is required.");
  });
});
