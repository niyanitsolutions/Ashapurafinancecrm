import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SignaturePad, type SignatureValue } from "./SignaturePad";

describe("SignaturePad", () => {
  it("stores a typed signature and clears it when switching method", async () => {
    const user = userEvent.setup();
    let current: SignatureValue | null = null;
    const onChange = vi.fn((v: SignatureValue | null) => {
      current = v;
    });
    const { rerender } = render(<SignaturePad value={current} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Type" }));
    rerender(<SignaturePad value={current} onChange={onChange} />);
    await user.type(screen.getByLabelText("Typed signature"), "Ravi Kumar");
    expect(current).toEqual({ method: "type", text: "Ravi Kumar" });

    // Switching to Upload drops the typed value — only one active representation.
    await user.click(screen.getByRole("button", { name: "Upload" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("only offers one method's input at a time", async () => {
    const user = userEvent.setup();
    render(<SignaturePad value={null} onChange={vi.fn()} />);

    // Draw is the default.
    expect(screen.getByLabelText("Signature drawing area")).toBeInTheDocument();
    expect(screen.queryByLabelText("Typed signature")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Upload" }));
    expect(screen.getByLabelText("Upload signature image")).toBeInTheDocument();
    expect(screen.queryByLabelText("Signature drawing area")).not.toBeInTheDocument();
  });
});
