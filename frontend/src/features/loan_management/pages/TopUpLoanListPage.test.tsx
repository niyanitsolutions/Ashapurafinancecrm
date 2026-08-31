import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { TopUpLoanListPage } from "./TopUpLoanListPage";

// Top Up Loan (production add-on) — the tab reuses the SAME list/table component and
// column shape the Disbursed list uses (CaseListPage + LoanCaseListItem), filtered to
// top_up_eligible cases, with two row actions: "Rejected" (opens the same scheduling
// popup, for a reschedule) and "Move to Document Collection" (the existing Leads pipeline).

vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ isOwner: true, loading: false, can: () => true }),
}));

vi.mock("@/features/auth/useAuth", () => ({
  useAuth: () => ({ role: "owner" }),
}));

const item = {
  id: "case-1", case_code: "AFS-LOAN-000015", application_id: "app-1", customer_id: "cust-1", customer_name: "dummy lead",
  product_id: "prod-1", product_name: "Personal Loan", assigned_to: null, assigned_to_name: null, current_status: "disbursed",
  rejection_reason: null, allowed_next_statuses: [], selected_bank_name: "HDFC Bank", approved_amount: 250000,
  disbursed_amount: 250000, disbursed_at: "2026-08-25T04:00:00.000Z", created_at: "2026-05-01T00:00:00.000Z",
};

const listLoanCases = vi.fn((_params?: Record<string, unknown>) => Promise.resolve({ data: [item], pagination: { total: 1 } }));
const moveTopUpToDocumentCollection = vi.fn((_id: string) => Promise.resolve({}));
const getLoanCase = vi.fn((_id: string) =>
  Promise.resolve({ id: "case-1", case_code: "AFS-LOAN-000015", customer: { full_name: "dummy lead" }, loan_details: { disbursed_at: "2026-08-25T04:00:00.000Z" } }),
);

vi.mock("@/features/loan_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/loan_management/api")>("@/features/loan_management/api");
  return {
    ...actual,
    listLoanCases: (params?: Record<string, unknown>) => listLoanCases(params),
    moveTopUpToDocumentCollection: (id: string) => moveTopUpToDocumentCollection(id),
    getLoanCase: (id: string) => getLoanCase(id),
  };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <TopUpLoanListPage />
    </MemoryRouter>,
  );
}

describe("TopUpLoanListPage", () => {
  it("lists top-up-eligible cases with the same Approved/Disbursed Amount/Date columns as the Disbursed list", async () => {
    renderPage();
    await screen.findByText("AFS-LOAN-000015");
    expect(screen.getByText("dummy lead")).toBeInTheDocument();
    // Approved Amount and Disbursed Amount are both ₹2,50,000 in this fixture.
    expect(screen.getAllByText("₹2,50,000").length).toBe(2);

    const call = listLoanCases.mock.calls[0][0] as Record<string, unknown>;
    expect(call.top_up_eligible).toBe(true);
  });

  it("shows Rejected and Move to Document Collection actions per row", async () => {
    renderPage();
    await screen.findByText("AFS-LOAN-000015");
    expect(screen.getByRole("button", { name: "Rejected" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move to Document Collection" })).toBeInTheDocument();
  });

  it("clicking Rejected opens the same Top Up scheduling popup for that case", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("AFS-LOAN-000015");

    await user.click(screen.getByRole("button", { name: "Rejected" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Top Up Loan" })).toBeInTheDocument();
    await waitFor(() => expect(getLoanCase).toHaveBeenCalledWith("case-1"));
  });

  it("clicking Move to Document Collection calls the existing hand-off action and refreshes the list", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("AFS-LOAN-000015");
    listLoanCases.mockClear();

    await user.click(screen.getByRole("button", { name: "Move to Document Collection" }));

    await waitFor(() => expect(moveTopUpToDocumentCollection).toHaveBeenCalledWith("case-1"));
    await waitFor(() => expect(listLoanCases).toHaveBeenCalled());
  });
});
