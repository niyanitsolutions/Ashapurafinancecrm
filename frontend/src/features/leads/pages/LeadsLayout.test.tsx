import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LeadsLayout } from "./LeadsLayout";

// Production spec "Move Top Up Loan Tab from Loan Management to Leads Only" — the tab
// now lives here, gated on the SAME loan_management:applications:view permission its
// underlying API already enforces (not a new permission), with its badge count reused
// verbatim from Loan Management's own existing counts endpoint.

vi.mock("@/components/layout/useNavKeys", () => ({
  useNavKeys: () => new Set(["leads"]),
}));

let mockCan: (moduleResource: string, action: string) => boolean = () => true;
vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ isOwner: false, loading: false, can: (m: string, a: string) => mockCan(m, a) }),
}));

const getLeadCounts = vi.fn(() =>
  Promise.resolve({ fresh: 1, my_leads: 2, document_collection: 3, rejected: 4, assigned: 5 }),
);
const getLoanCaseCounts = vi.fn(() =>
  Promise.resolve({
    new_customer: 0, credit_evaluation: 0, offer_acceptance: 0, additional_documents: 0, rv_ov_ref: 0, esign_nach_kyc: 0,
    final_evaluation: 0, send_for_disbursement: 0, disbursed: 0, on_hold: 0, re_eligible: 9, rejected: 0, top_up_eligible: 7,
  }),
);

vi.mock("@/features/leads/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/leads/api")>("@/features/leads/api");
  return { ...actual, getLeadCounts: () => getLeadCounts() };
});

vi.mock("@/features/loan_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/loan_management/api")>("@/features/loan_management/api");
  return { ...actual, getLoanCaseCounts: () => getLoanCaseCounts() };
});

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={["/leads"]}>
      <Routes>
        <Route path="/leads" element={<LeadsLayout />}>
          <Route index element={<div>Fresh Leads Page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("LeadsLayout — Top Up Loan tab", () => {
  it("shows Top Up Loan (with its badge count from Loan Management's existing counts endpoint) when the user can view loan_management:applications", async () => {
    mockCan = () => true;
    renderLayout();
    const tab = await screen.findByRole("link", { name: /top up loan/i });
    expect(tab).toHaveAttribute("href", "/leads/top-up");
    await waitFor(() => expect(screen.getByRole("link", { name: /top up loan/i }).textContent).toContain("7"));
  });

  it("hides Top Up Loan and Re-Eligible for a user without loan_management:applications view access", async () => {
    mockCan = () => false;
    renderLayout();
    await screen.findByText("Fresh Leads Page");
    expect(screen.queryByRole("link", { name: /top up loan/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /re-eligible/i })).not.toBeInTheDocument();
  });

  it("shows Re-Eligible (moved here from Loan Management) with its Loan Management count, gated on the same permission", async () => {
    mockCan = () => true;
    renderLayout();
    const tab = await screen.findByRole("link", { name: /re-eligible/i });
    expect(tab).toHaveAttribute("href", "/leads/re-eligible");
    await waitFor(() => expect(screen.getByRole("link", { name: /re-eligible/i }).textContent).toContain("9"));
  });

  it("existing Leads tabs (Fresh/My/Document Collection/Rejected/Assigned) are unaffected", async () => {
    mockCan = () => true;
    renderLayout();
    await screen.findByRole("link", { name: /top up loan/i });
    for (const label of ["Fresh Leads", "My Leads", "Document Collection", "Rejected", "Assigned"]) {
      expect(screen.getByRole("link", { name: new RegExp(`^${label}`) })).toBeInTheDocument();
    }
  });
});
