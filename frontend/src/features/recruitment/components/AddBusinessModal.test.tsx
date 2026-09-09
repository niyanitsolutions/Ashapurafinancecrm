import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AddBusinessModal } from "./AddBusinessModal";
import type { AdvisorBusinessRecord } from "@/features/recruitment/api";

const addAdvisorBusiness = vi.fn(() => Promise.resolve({} as AdvisorBusinessRecord));
vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return { ...actual, addAdvisorBusiness: (...a: unknown[]) => addAdvisorBusiness(...(a as [])) };
});

async function fill(user: ReturnType<typeof userEvent.setup>, category = "savings") {
  await user.selectOptions(screen.getByLabelText("Product Category"), category);
  if (category === "custom") await user.type(screen.getByLabelText("Custom Category"), "Micro Insurance");
  await user.type(screen.getByLabelText("Product Name"), "ABC Guaranteed Savings");
  await user.type(screen.getByLabelText("Premium"), "50000");
  await user.type(screen.getByLabelText("PPT (years)"), "10");
  await user.type(screen.getByLabelText("PT (years)"), "20");
  await user.type(screen.getByLabelText("Policy Issue Date"), "2026-09-01");
}

describe("AddBusinessModal", () => {
  it("shows the Custom Category field only for the Custom category, and requires it", async () => {
    const user = userEvent.setup();
    render(<AddBusinessModal advisorId="a1" onClose={vi.fn()} onSaved={vi.fn()} />);

    expect(screen.queryByLabelText("Custom Category")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Product Category"), "custom");
    expect(screen.getByLabelText("Custom Category")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Product Name"), "X");
    await user.type(screen.getByLabelText("Premium"), "100");
    await user.type(screen.getByLabelText("PPT (years)"), "5");
    await user.type(screen.getByLabelText("PT (years)"), "10");
    await user.type(screen.getByLabelText("Policy Issue Date"), "2026-09-01");
    // Still blocked — custom category is empty.
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
    await user.type(screen.getByLabelText("Custom Category"), "Micro");
    expect(screen.getByRole("button", { name: /^save$/i })).toBeEnabled();
  });

  it("saves with the right payload and resets the form afterwards", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const onClose = vi.fn();
    render(<AddBusinessModal advisorId="a1" onClose={onClose} onSaved={onSaved} />);
    await fill(user);

    await user.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() =>
      expect(addAdvisorBusiness).toHaveBeenCalledWith("a1", {
        product_category: "savings",
        product_name: "ABC Guaranteed Savings",
        premium: 50000,
        ppt: 10,
        pt: 20,
        policy_issue_date: "2026-09-01",
      }),
    );
    expect(onSaved).toHaveBeenCalled();
  });

  it("includes Customer Name / Customer Mobile / Policy Number in the payload", async () => {
    const user = userEvent.setup();
    render(<AddBusinessModal advisorId="a1" onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.type(screen.getByLabelText("Customer Name"), "Anita Rao");
    await user.type(screen.getByLabelText("Customer Mobile"), "9812345678");
    await user.type(screen.getByLabelText("Policy Number"), "POL-42");
    await fill(user);

    await user.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() =>
      expect(addAdvisorBusiness).toHaveBeenCalledWith("a1", {
        customer_name: "Anita Rao",
        customer_mobile: "9812345678",
        policy_number: "POL-42",
        product_category: "savings",
        product_name: "ABC Guaranteed Savings",
        premium: 50000,
        ppt: 10,
        pt: 20,
        policy_issue_date: "2026-09-01",
      }),
    );
  });
});
