import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { UpdateStageModal } from "./UpdateStageModal";
import type { LeadDetail, LeadListItem } from "@/features/leads/api";

// Production fix "Reject Lead for Employees" — an employee who can already manage a
// lead (`leads:leads:edit`) must see and be able to use Reject Lead exactly like the
// Owner, without a separate `reject` permission grant. Backend enforcement (permission
// AND per-lead assignment scope) is covered in tests/api/test_leads.py; this file covers
// the frontend visibility/action wiring only.

let mockCan: (moduleResource: string, action: string) => boolean = () => true;
vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ isOwner: false, loading: false, can: (m: string, a: string) => mockCan(m, a) }),
}));

const rejectLead = vi.fn((_id: string, _reason: string) => Promise.resolve({} as LeadDetail));
vi.mock("@/features/leads/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/leads/api")>("@/features/leads/api");
  return {
    ...actual,
    getLead: () => Promise.resolve(leadDetail),
    rejectLead: (id: string, reason: string) => rejectLead(id, reason) as unknown as ReturnType<typeof actual.rejectLead>,
  };
});

const lead: LeadListItem = {
  id: "lead-1", lead_code: "AFS-LEAD-000006", full_name: "Ravi Kumar", mobile: "9611170001", email: null,
  source_id: "src-1", source_name: "Website", product_category: "loan", product_id: "prod-1", product_name: "Personal Loan",
  assigned_to: "emp-1", assigned_to_name: "Satyaa K", status: "assigned", stage: "assigned",
  salary_in_hand: null, next_follow_up_date: null, assigned_by: null, assigned_by_name: null, assigned_at: null,
  rejected_reason: null, rejected_by: null, rejected_by_name: null, rejected_at: null,
  application_id: null, application_status: null, is_potential_duplicate: false, created_at: "2026-08-20T10:00:00Z",
  is_lead_less: false,
};

const leadDetail: LeadDetail = {
  ...lead,
  remarks: null, city: null, preferred_amount: null, duplicate_of_lead_ids: [], updated_at: "2026-08-20T10:00:00Z",
  form_definition_id: null, product_form_data: null, financial_assessment: null, account_created: false,
  documents_required: 0, documents_verified: 0, documents_not_available: 0, all_documents_verified: false,
};

function renderModal() {
  return render(
    <MemoryRouter>
      <UpdateStageModal lead={lead} onClose={vi.fn()} onChanged={vi.fn()} />
    </MemoryRouter>,
  );
}

describe("UpdateStageModal — Reject Lead visibility (Owner vs Employee)", () => {
  it("Owner (isOwner short-circuits can() to true) sees Reject Lead", async () => {
    mockCan = () => true;
    renderModal();
    expect(await screen.findByRole("button", { name: /reject lead/i })).toBeInTheDocument();
  });

  it("Employee granted only 'edit' (no dedicated 'reject' grant) also sees Reject Lead", async () => {
    mockCan = (_m, action) => action === "edit";
    renderModal();
    expect(await screen.findByRole("button", { name: /reject lead/i })).toBeInTheDocument();
  });

  it("Employee granted only the dedicated 'reject' action (no edit) still sees Reject Lead — preserves prior behavior", async () => {
    mockCan = (_m, action) => action === "reject";
    renderModal();
    expect(await screen.findByRole("button", { name: /reject lead/i })).toBeInTheDocument();
  });

  it("Employee with neither 'edit' nor 'reject' does not see Reject Lead", async () => {
    mockCan = () => false;
    renderModal();
    await screen.findByText("Current Stage");
    expect(screen.queryByRole("button", { name: /reject lead/i })).not.toBeInTheDocument();
  });

  it("clicking Reject Lead opens the existing confirmation modal, and confirming calls the existing reject API", async () => {
    mockCan = (_m, action) => action === "edit";
    const user = userEvent.setup();
    renderModal();

    await user.click(await screen.findByRole("button", { name: /reject lead/i }));
    expect(await screen.findByRole("heading", { name: /reject lead/i })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/customer not interested/i), "Customer backed out");
    await user.click(screen.getByRole("button", { name: /^reject$/i }));

    await waitFor(() => expect(rejectLead).toHaveBeenCalledWith("lead-1", "Customer backed out"));
  });
});
