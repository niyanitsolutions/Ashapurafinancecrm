import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { CaseListPage, type CaseListItem, type CaseListResponse } from "./CaseListPage";

// Decision #130: `onUpdate` is an additive, opt-in prop — Insurance Management's own
// wrapper never passes it, so its rendered list must show exactly the pre-existing
// single View button per row, byte-identical to before this change. Loan Management's
// wrapper passes it, adding a distinct Update action beside View.

vi.mock("@/features/auth/useAuth", () => ({
  useAuth: () => ({ role: "employee" }),
}));

const items: CaseListItem[] = [
  { id: "case-1", case_code: "AFS-LOAN-000001", customer_name: "Kamal Mandal", product_name: "Personal Loan", assigned_to_name: "Lucky Kumar", current_status: "new_customer" },
  { id: "case-2", case_code: "AFS-LOAN-000002", customer_name: "Test Customer", product_name: "Personal Loan", assigned_to_name: null, current_status: "disbursed" },
];

function listFn(): Promise<CaseListResponse<CaseListItem>> {
  return Promise.resolve({ data: items, pagination: { total: items.length } });
}

const baseProps = {
  icon: "loan" as const,
  entityLabel: "Loan",
  detailBasePath: "/loan-cases",
  itemLabel: "loan case",
  statusLabels: { new_customer: "New Customer", disbursed: "Disbursed" },
  listFn,
  defaultDescription: "Every loan application moving through underwriting to disbursement.",
  reEligibleDescription: "Rejected loan cases that become eligible to reapply after their cooldown period.",
  emptyStateDescription: "A loan case appears here once explicitly moved from Document Collection into Loan Management.",
};

function renderList(extraProps: Record<string, unknown> = {}) {
  return render(
    <MemoryRouter>
      <CaseListPage {...baseProps} {...extraProps} />
    </MemoryRouter>,
  );
}

describe("CaseListPage row actions", () => {
  it("without onUpdate (Insurance's usage): renders only a View action per row, no Update button", async () => {
    renderList();
    await screen.findByText("AFS-LOAN-000001");

    expect(screen.getAllByRole("link", { name: /view/i })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /update/i })).not.toBeInTheDocument();
  });

  it("with onUpdate (Loan Management's usage): renders both View and Update, and Update invokes the callback with the row", async () => {
    const onUpdate = vi.fn();
    const user = userEvent.setup();
    renderList({ onUpdate });
    await screen.findByText("AFS-LOAN-000001");

    const updateButtons = screen.getAllByRole("button", { name: /update/i });
    expect(updateButtons).toHaveLength(2);

    await user.click(updateButtons[0]);
    expect(onUpdate).toHaveBeenCalledWith(items[0]);
  });

  it("canUpdateRow hides Update for rows it excludes (e.g. a terminal Disbursed case)", async () => {
    const onUpdate = vi.fn();
    renderList({ onUpdate, canUpdateRow: (item: CaseListItem) => item.current_status !== "disbursed" });
    await screen.findByText("AFS-LOAN-000001");

    // Row 1 (new_customer) keeps Update; row 2 (disbursed) does not.
    expect(screen.getAllByRole("button", { name: /update/i })).toHaveLength(1);
    expect(screen.getAllByRole("link", { name: /view/i })).toHaveLength(2);
  });
});
