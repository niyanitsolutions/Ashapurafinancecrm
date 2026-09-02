import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CaseTimelineEntry, LoanCaseDetail } from "@/features/loan_management/api";
import { ReEligibleUpdateModal } from "./ReEligibleUpdateModal";

const updateLoanCaseStatus = vi.fn(() => Promise.resolve({ current_status: "credit_evaluation" }));
const addLoanFollowUp = vi.fn(() => Promise.resolve({ current_status: "re_eligible" }));
const holdLoanCase = vi.fn(() => Promise.resolve({ current_status: "on_hold" }));
const getLoanCaseTimeline = vi.fn(() => Promise.resolve([] as CaseTimelineEntry[]));
const getLoanCase = vi.fn(() => Promise.resolve({} as LoanCaseDetail));

vi.mock("@/features/loan_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/loan_management/api")>("@/features/loan_management/api");
  return {
    ...actual,
    updateLoanCaseStatus: (...a: unknown[]) => updateLoanCaseStatus(...(a as [])),
    addLoanFollowUp: (...a: unknown[]) => addLoanFollowUp(...(a as [])),
    holdLoanCase: (...a: unknown[]) => holdLoanCase(...(a as [])),
    getLoanCaseTimeline: () => getLoanCaseTimeline(),
    getLoanCase: () => getLoanCase(),
  };
});

const loanCase = {
  id: "case-1", case_code: "AFS-LOAN-000002", application_id: "app-1", customer_id: "c1", customer_name: "Lucky Kumar",
  product_id: "p1", product_name: "Personal Loan", assigned_to: null, assigned_to_name: null,
  current_status: "re_eligible", rejection_reason: null,
  allowed_next_statuses: ["new_customer", "credit_evaluation", "rejected", "on_hold"],
  selected_bank_name: null, approved_amount: null, disbursed_amount: null, disbursed_at: null, next_follow_up_date: null,
  created_at: "2026-01-01T00:00:00Z", pending_document_type_ids: [], loan_details: {} as LoanCaseDetail["loan_details"],
  updated_at: "2026-01-01T00:00:00Z", allowed_previous_statuses: [], customer: null, application: null, bank_offers: [],
} as unknown as LoanCaseDetail;

function renderModal(props: Partial<Parameters<typeof ReEligibleUpdateModal>[0]> = {}) {
  return render(
    <ReEligibleUpdateModal loanCase={loanCase} canEdit onClose={() => {}} onUpdated={() => {}} {...props} />,
  );
}

describe("ReEligibleUpdateModal", () => {
  it("the Move Case To dropdown offers exactly the case's allowed_next_statuses (restart-safe only)", async () => {
    renderModal();
    const select = await screen.findByLabelText("Move Case To");
    const options = [...select.querySelectorAll("option")].map((o) => o.textContent).filter((t) => t && t !== "Select Status");
    expect(options).toEqual(["New Customer", "Credit Evaluation", "Rejected", "On Hold"]);
    // Document Collection is a Leads-module concept — never a Loan Management destination.
    expect(options).not.toContain("Document Collection");
  });

  it("selecting a plain stage and clicking Update Status calls updateLoanCaseStatus", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.selectOptions(await screen.findByLabelText("Move Case To"), "credit_evaluation");
    await user.click(screen.getByRole("button", { name: "Update Status" }));
    expect(updateLoanCaseStatus).toHaveBeenCalledWith("case-1", "credit_evaluation");
  });

  it("selecting Rejected opens the Re-Eligibility scheduling popup instead of transitioning directly", async () => {
    const user = userEvent.setup();
    updateLoanCaseStatus.mockClear();
    renderModal();
    await user.selectOptions(await screen.findByLabelText("Move Case To"), "rejected");
    await user.click(screen.getByRole("button", { name: "Update Status" }));
    expect(updateLoanCaseStatus).not.toHaveBeenCalled();
    expect(await screen.findByText(/should this case become Re-Eligible/i)).toBeInTheDocument();
  });

  it("selecting On Hold reveals a hold-reason select and routes through holdLoanCase", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.selectOptions(await screen.findByLabelText("Move Case To"), "on_hold");
    expect(screen.getByLabelText("Hold Reason")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Update Status" }));
    expect(holdLoanCase).toHaveBeenCalledWith("case-1", expect.any(String));
  });

  it("Add Comment calls addLoanFollowUp with the comment + follow-up date and never touches status", async () => {
    const user = userEvent.setup();
    updateLoanCaseStatus.mockClear();
    renderModal();
    await screen.findByLabelText("Move Case To");
    await user.type(screen.getByLabelText("Add Comment"), "Customer confirmed interest");
    await user.type(screen.getByLabelText("Next Follow-up"), "2026-09-05");
    await user.click(screen.getByRole("button", { name: "Add Comment" }));
    expect(addLoanFollowUp).toHaveBeenCalledWith("case-1", { comment: "Customer confirmed interest", follow_up_date: "2026-09-05" });
    expect(updateLoanCaseStatus).not.toHaveBeenCalled();
  });

  it("hides the status + comment controls when canEdit is false", async () => {
    renderModal({ canEdit: false });
    await screen.findByText(/Follow-up & Comment History/i);
    expect(screen.queryByLabelText("Move Case To")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Comment" })).not.toBeInTheDocument();
  });
});
