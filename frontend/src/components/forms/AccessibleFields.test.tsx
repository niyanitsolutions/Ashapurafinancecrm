import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FormField } from "./FormField";
import { SelectField } from "./SelectField";
import { TextareaField } from "./TextareaField";
import { ErrorBanner } from "./ErrorBanner";

describe("Shared accessible field contracts", () => {
  it("associates generated labels, errors and existing descriptions", () => {
    render(<><p id="hint">Existing help</p><FormField label="Reference" error="Reference is required" aria-describedby="hint" /></>);
    const input = screen.getByLabelText("Reference");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Existing help Reference is required");
  });
  it("keeps select and textarea errors accessible without caller IDs", () => {
    render(<><SelectField label="Purpose" error="Choose a purpose" options={[]} /><TextareaField label="Objective" error="Enter an objective" /></>);
    expect(screen.getByLabelText("Purpose")).toHaveAccessibleDescription("Choose a purpose");
    expect(screen.getByLabelText("Objective")).toHaveAccessibleDescription("Enter an objective");
  });
  it("announces a safe error banner", () => { render(<ErrorBanner message="Connection test failed" />); expect(screen.getByRole("alert")).toHaveTextContent("Connection test failed"); });
});
