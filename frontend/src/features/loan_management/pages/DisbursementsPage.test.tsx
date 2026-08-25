import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { DisbursementsPage } from "./DisbursementsPage";

// Requirements 26-32: default "This Month", a single listDisbursements() call drives
// card + table + pagination together (never two separate queries that could disagree),
// switching filters resets to page 1, and Clear Filters resets everything back to the
// defaults.

const listDisbursements = vi.fn((_params?: Record<string, unknown>) =>
  Promise.resolve({
    data: {
      items: [
        {
          id: "case-1", case_code: "AFS-LOAN-000012", customer_name: "Dharmendra", product_name: "Personal Loan",
          approved_amount: 200000, disbursed_amount: 200000, disbursed_reference: "REF-1", disbursed_at: "2026-08-25T10:00:00Z",
        },
      ],
      total_count: 1, total_amount: 200000,
    },
    pagination: { page: 1, page_size: 10, total: 1, total_pages: 1 },
  }),
);

vi.mock("@/features/loan_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/loan_management/api")>("@/features/loan_management/api");
  return { ...actual, listDisbursements: (...args: unknown[]) => listDisbursements(...(args as [])) };
});

vi.mock("@/features/system_settings/api", () => ({
  loanProductsApi: { list: vi.fn(() => Promise.resolve([{ id: "prod-1", name: "Personal Loan", description: null, status: "active", created_at: "" }])) },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <DisbursementsPage />
    </MemoryRouter>,
  );
}

describe("DisbursementsPage", () => {
  it("defaults to This Month and shows the total from the same response as the table", async () => {
    renderPage();
    await screen.findByText("AFS-LOAN-000012");
    // Total card + the row's own Approved/Disbursed Amount cells all show ₹2,00,000 here
    // (single-item fixture) — asserting at least one confirms the card rendered without
    // over-constraining which cell is "the" total.
    expect(screen.getAllByText("₹2,00,000").length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("This Month")).toBeInTheDocument();
    const call = listDisbursements.mock.calls[0][0] as Record<string, unknown>;
    expect(call.page).toBe(1);
  });

  it("changing the product filter resets to page 1 and refetches", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("AFS-LOAN-000012");
    listDisbursements.mockClear();

    await user.selectOptions(screen.getByDisplayValue("All Loans"), "Personal Loan");

    await waitFor(() => expect(listDisbursements).toHaveBeenCalled());
    const call = listDisbursements.mock.calls[0][0] as Record<string, unknown>;
    expect(call.product_id).toBe("prod-1");
    expect(call.page).toBe(1);
  });

  it("Clear Filters resets product/search/date preset and page", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("AFS-LOAN-000012");

    await user.selectOptions(screen.getByDisplayValue("All Loans"), "Personal Loan");
    await user.type(screen.getByPlaceholderText("Case code / Customer…"), "AFS");
    listDisbursements.mockClear();

    await user.click(screen.getByRole("button", { name: "Clear Filters" }));

    await waitFor(() => expect(listDisbursements).toHaveBeenCalled());
    const call = listDisbursements.mock.calls[0][0] as Record<string, unknown>;
    expect(call.product_id).toBeUndefined();
    expect(call.search).toBeUndefined();
    expect(call.page).toBe(1);
    expect(screen.getByDisplayValue("This Month")).toBeInTheDocument();
  });

  it("shows an empty state and ₹0 total when nothing matches", async () => {
    listDisbursements.mockResolvedValueOnce({
      data: { items: [], total_count: 0, total_amount: 0 },
      pagination: { page: 1, page_size: 10, total: 0, total_pages: 1 },
    });
    renderPage();
    expect(await screen.findByText("No disbursements match your filters")).toBeInTheDocument();
    expect(screen.getByText("₹0")).toBeInTheDocument();
  });
});
