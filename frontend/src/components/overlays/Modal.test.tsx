import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "./Modal";

// Regression test for the "Update Lead modal loses focus while typing" bug.
//
// Root cause: Modal's focus-on-open and Escape/Tab-trap logic used to live in one
// useEffect keyed on [open, onClose]. Any caller passing an inline onClose (a fresh
// function identity every render — the common React pattern, e.g.
// `onClose={() => setX(null)}`) would cause that effect to re-fire, and its
// `dialogRef.current?.focus()` call would yank focus out of whatever input the user was
// actively typing in, back onto the dialog wrapper. In production this was triggered by
// LeadListPage's own 15s polling re-render, which recreated UpdateStageModal's onClose
// prop on every tick — this test reproduces that exact shape directly against Modal,
// the shared component, so the bug class can't reappear in any future modal.
function renderModal(onClose: () => void) {
  return (
    <Modal open onClose={onClose} title="Test Modal">
      <input aria-label="Company Location" />
    </Modal>
  );
}

describe("Modal focus retention", () => {
  it("does not steal focus from an active input when re-rendered with a new onClose identity", async () => {
    const user = userEvent.setup();
    const { rerender } = render(renderModal(() => {}));

    const input = screen.getByLabelText("Company Location");
    await user.click(input);
    await user.type(input, "Pune");
    expect(input).toHaveFocus();

    // A brand-new arrow function every call — exactly what an inline
    // `onClose={() => setX(null)}` caller produces on every parent re-render (e.g. a
    // polling list refresh), without the modal's `open`/identity actually changing.
    rerender(renderModal(() => {}));
    rerender(renderModal(() => {}));

    expect(input).toHaveFocus();

    await user.type(input, " Office");
    expect(input).toHaveValue("Pune Office");
  });

  it("still closes on Escape after being re-rendered with a new onClose", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { rerender } = render(renderModal(onClose));
    await user.click(screen.getByLabelText("Company Location"));

    // Re-render with a different onClose reference, then verify the LATEST one fires —
    // proves the Escape/Tab-trap effect still legitimately re-subscribes on identity
    // change (only the focus-stealing behavior was un-coupled from it).
    const latestOnClose = vi.fn();
    rerender(renderModal(latestOnClose));
    await user.keyboard("{Escape}");

    expect(onClose).not.toHaveBeenCalled();
    expect(latestOnClose).toHaveBeenCalledTimes(1);
  });
});
