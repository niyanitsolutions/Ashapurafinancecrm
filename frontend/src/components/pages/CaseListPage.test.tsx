import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { CaseListPage, type CaseListItem, type CaseListParams, type CaseListResponse } from "./CaseListPage";

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

  it("View targets whatever detailBasePath the caller passes — Loan Management's real usage points at the canonical /loan-management/cases route, not the legacy /loan-cases alias (decision #132)", async () => {
    renderList({ detailBasePath: "/loan-management/cases" });
    await screen.findByText("AFS-LOAN-000001");

    const viewLinks = screen.getAllByRole("link", { name: /view/i });
    expect(viewLinks[0]).toHaveAttribute("href", "/loan-management/cases/case-1");
    expect(viewLinks[0]).not.toHaveAttribute("href", expect.stringContaining("/loan-cases/"));
  });

  it("Top Up Loan (production add-on): rowActions renders per-row custom actions alongside View, and titleOverride/descriptionOverride replace the computed title/description", async () => {
    renderList({
      fixedStatus: "disbursed",
      titleOverride: "Top Up Loan",
      descriptionOverride: "Custom description",
      rowActions: (item: CaseListItem) => <button type="button">Custom Action {item.id}</button>,
    });
    await screen.findByText("AFS-LOAN-000001");

    expect(screen.getByRole("heading", { name: "Top Up Loan" })).toBeInTheDocument();
    expect(screen.getByText("Custom description")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Custom Action case-1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Custom Action case-2" })).toBeInTheDocument();
    // Every existing caller (none of which pass rowActions) is unaffected — View still
    // renders regardless.
    expect(screen.getAllByRole("link", { name: /view/i })).toHaveLength(2);
  });
});

// Production bug: Loan Management's tab badges (Credit Evaluation, Offer Acceptance,
// ...) showed real counts, but clicking a tab rendered "No cases match your filters" /
// 0 of 0 — for every tab except whichever one was opened first. Root cause: every tab
// route (/loan-management/cases, /loan-management/credit-evaluation, ...) renders the
// SAME <CaseListPage> component type at the SAME position under the shared layout's
// <Outlet/>, just with a different `fixedStatus` prop. React Router does not remount a
// component across sibling routes like this — it reuses the instance and only updates
// props — but `status` was seeded from `fixedStatus` via a `useState` LAZY INITIALIZER,
// which only runs on the very first mount. Clicking from tab A to tab B (client-side
// <Link> navigation, exactly what ModuleTabs uses) left the internal `status` state
// frozen at tab A's value forever, so every subsequent tab's list query silently kept
// filtering on the FIRST tab ever visited — while the tab badges (a separate component,
// LoanManagementLayout, fetched independently via GET /loan-cases/counts) correctly
// showed each tab's real count. This reproduces the exact symptom with the real
// react-router-dom nested-route/Outlet mechanics, not a simplified mock — and locks in
// the fix: an explicit, distinct `key` per tab route (applied in app/router.tsx), which
// forces React to remount rather than reuse the instance across a tab switch.

function TabbedLayout({ tabsTo }: { tabsTo: string[] }) {
  return (
    <div>
      {tabsTo.map((to) => (
        <Link key={to} to={to}>
          {to}
        </Link>
      ))}
      <Outlet />
    </div>
  );
}

describe("CaseListPage tab-to-tab navigation (shared Outlet position, no remount)", () => {
  it("re-queries with the NEWLY navigated tab's fixedStatus, not the first tab ever mounted", async () => {
    const calls: CaseListParams[] = [];
    const spyListFn = (params: CaseListParams): Promise<CaseListResponse<CaseListItem>> => {
      calls.push(params);
      return Promise.resolve({ data: [], pagination: { total: 0 } });
    };

    render(
      <MemoryRouter initialEntries={["/loan-management/cases"]}>
        <Routes>
          <Route element={<TabbedLayout tabsTo={["/loan-management/cases", "/loan-management/credit-evaluation"]} />}>
            <Route
              path="/loan-management/cases"
              element={<CaseListPage key="new_customer" {...baseProps} listFn={spyListFn} fixedStatus="new_customer" />}
            />
            <Route
              path="/loan-management/credit-evaluation"
              element={<CaseListPage key="credit_evaluation" {...baseProps} listFn={spyListFn} fixedStatus="credit_evaluation" />}
            />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(calls.at(-1)?.status).toBe("new_customer");

    const user = userEvent.setup();
    await user.click(screen.getByRole("link", { name: "/loan-management/credit-evaluation" }));

    await waitFor(() => expect(calls.at(-1)?.status).toBe("credit_evaluation"));
    // Page must also reset — a stale page number left over from a previous tab (e.g.
    // page 3 of a long New Customer list) must not silently produce an out-of-range,
    // artificially-empty result on a tab with real data on page 1.
    expect(calls.at(-1)?.page).toBe(1);
  }, 10000);
});
