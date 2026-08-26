import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LeadListPage } from "./LeadListPage";
import type { LeadListItem } from "@/features/leads/api";

// Production fix "DC vs LM" — the Document Collection tab now renders a mix of real
// Lead rows and synthesized Lead-less rows (`is_lead_less: true`, no Lead ever created).
// A Lead-less row has no Lead to view/edit/generate-a-link-for/follow-up-on — its Code
// links straight to the Application, and its only action is "Update", which opens
// `MoveApplicationToLoanManagementModal` instead of `UpdateStageModal`.

vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ isOwner: true, loading: false, can: () => true }),
}));

vi.mock("@/features/system_settings/api", () => ({
  leadSourcesApi: { list: vi.fn(() => Promise.resolve([])) },
}));

const leadLessRow: LeadListItem = {
  id: "app-1", lead_code: "AFS-APP-000001", full_name: "Direct Applicant", mobile: "9611170001", email: null,
  source_id: "", source_name: "Direct", product_category: "loan", product_id: "prod-1", product_name: "Personal Loan",
  assigned_to: null, assigned_to_name: null, status: "pending", stage: "document_collection",
  salary_in_hand: null, next_follow_up_date: null, assigned_by: null, assigned_by_name: null, assigned_at: null,
  rejected_reason: null, rejected_by: null, rejected_by_name: null, rejected_at: null,
  application_id: "app-1", application_status: "submitted", is_potential_duplicate: false, created_at: "2026-08-20T10:00:00Z",
  is_lead_less: true,
};

const leadRow: LeadListItem = {
  ...leadLessRow, id: "lead-2", lead_code: "AFS-LEAD-000002", full_name: "Ravi Kumar", mobile: "9611170002",
  source_name: "Website", application_id: "app-2", is_lead_less: false,
};

const listLeads = vi.fn(() => Promise.resolve({ data: [leadLessRow, leadRow], pagination: { total: 2 } }));
const getLeadLessApplicationSummary = vi.fn(() =>
  Promise.resolve({ application_id: "app-1", application_status: "submitted", documents_required: 1, documents_verified: 1, all_documents_verified: true }),
);
const moveLeadLessApplicationToLoanManagement = vi.fn((_id: string) => Promise.resolve(null));

vi.mock("@/features/leads/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/leads/api")>("@/features/leads/api");
  return {
    ...actual,
    listLeads: () => listLeads(),
    getLeadLessApplicationSummary: () => getLeadLessApplicationSummary(),
    moveLeadLessApplicationToLoanManagement: (id: string) => moveLeadLessApplicationToLoanManagement(id),
  };
});

function renderDocumentCollectionTab() {
  return render(
    <MemoryRouter initialEntries={["/leads/document-collection"]}>
      <Routes>
        <Route element={<Outlet context={{ refreshCounts: vi.fn() }} />}>
          <Route path="/leads/document-collection" element={<LeadListPage tab="document_collection" />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("LeadListPage — Document Collection tab, Lead-less rows", () => {
  it("Lead-less row's Code links to its Application, not a Lead page", async () => {
    renderDocumentCollectionTab();
    await screen.findByText("AFS-APP-000001");

    const link = screen.getByRole("link", { name: "AFS-APP-000001" });
    expect(link).toHaveAttribute("href", "/applications/app-1?from=document-collection");

    const leadLink = screen.getByRole("link", { name: "AFS-LEAD-000002" });
    expect(leadLink).toHaveAttribute("href", "/leads/lead-2");
  });

  it("Lead-less row hides Generate Link and Edit actions; the real Lead row keeps them", async () => {
    renderDocumentCollectionTab();
    await screen.findByText("AFS-APP-000001");

    const rows = screen.getAllByRole("row");
    const leadLessRowEl = rows[1];
    const leadRowEl = rows[2];

    expect(within(leadLessRowEl).queryByRole("button", { name: /generate link/i })).not.toBeInTheDocument();
    expect(within(leadLessRowEl).queryByRole("link", { name: /^edit$/i })).not.toBeInTheDocument();

    expect(within(leadRowEl).getByRole("button", { name: /generate link/i })).toBeInTheDocument();
    expect(within(leadRowEl).getByRole("link", { name: /^edit$/i })).toBeInTheDocument();
  });

  it("Lead-less row's Update action opens MoveApplicationToLoanManagementModal, not UpdateStageModal", async () => {
    const user = userEvent.setup();
    renderDocumentCollectionTab();
    await screen.findByText("AFS-APP-000001");

    const rows = screen.getAllByRole("row");
    const updateButton = within(rows[1]).getByRole("button", { name: /update/i });
    await user.click(updateButton);

    expect(await screen.findByRole("heading", { name: /move to loan management/i })).toBeInTheDocument();
    await waitFor(() => expect(getLeadLessApplicationSummary).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: /move to loan management/i })).toBeEnabled();
  });
});
