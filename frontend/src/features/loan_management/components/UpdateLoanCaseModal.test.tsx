import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UpdateLoanCaseModal } from "./UpdateLoanCaseModal";
import type { LoanCaseDetail } from "@/features/loan_management/api";

// Decision #130/#132: the Update modal must render the form matching the case's CURRENT
// stage only — never more than one stage's form at a time, never the wrong one — and
// must never call a mutating API function until an explicit Save/Confirm click.

const updateLoanCaseStatus = vi.fn(() => Promise.resolve({ current_status: "re_eligible" }));
const recordNewCustomerDetails = vi.fn(() => Promise.resolve({ current_status: "credit_evaluation" }));

vi.mock("@/features/loan_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/loan_management/api")>("@/features/loan_management/api");
  return {
    ...actual,
    listBankOffers: vi.fn(() => Promise.resolve([])),
    updateLoanCaseStatus: (...args: unknown[]) => updateLoanCaseStatus(...(args as [])),
    recordNewCustomerDetails: (...args: unknown[]) => recordNewCustomerDetails(...(args as [])),
  };
});

vi.mock("@/features/customer/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/customer/api")>("@/features/customer/api");
  return {
    ...actual,
    getFormDefinition: vi.fn(() =>
      Promise.resolve({
        required_documents: [
          { document_type_id: "doc-1", document_type_name: "Salary Slip", section: null, note: null, required: true },
          { document_type_id: "doc-2", document_type_name: "GST Certificate", section: null, note: null, required: false },
          { document_type_id: "doc-3", document_type_name: "Hidden Doc", section: null, note: null, required: true, hidden: true },
        ],
      }),
    ),
  };
});

const baseDetails: LoanCaseDetail["loan_details"] = {
  preferred_bank_name: null, preferred_branch: null, loan_type: null, requested_amount: null, preferred_remarks: null,
  credit_score: null, credit_remarks: null, bank_nbfc_name: null, bank_application_id: null, bank_reference_number: null,
  assigned_officer: null, bank_decision: null, bank_remarks: null, offered_amount: null, offered_tenure_months: null,
  offered_interest_rate: null, offer_decision: "pending", rv_ov_ref_type: null, rv_ov_ref_status: null, rv_ov_ref_date: null,
  rv_ov_ref_verified_by: null, rv_ov_ref_result: null, rv_ov_ref_remarks: null, esign_completed: false, nach_completed: false,
  kyc_completed: false, final_evaluation_remarks: null, disbursed_amount: null, disbursed_at: null, disbursed_reference: null,
};

function makeCase(status: string, allowedNext: string[] = []): LoanCaseDetail {
  return {
    id: "case-1", case_code: "AFS-LOAN-000005", application_id: "app-1", customer_id: "cust-1", customer_name: "Kamal Mandal",
    product_id: "prod-1", product_name: "Personal Loan", assigned_to: "emp-1", assigned_to_name: "Lucky Kumar",
    current_status: status, rejection_reason: null, allowed_next_statuses: allowedNext, selected_bank_name: null,
    approved_amount: null, created_at: "2026-01-01T00:00:00Z", pending_document_type_ids: [], loan_details: baseDetails,
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function renderModal(status: string, allowedNext: string[] = [], onClose = () => {}) {
  return render(
    <UpdateLoanCaseModal caseId="case-1" loanCase={makeCase(status, allowedNext)} canEdit canDisburse={false} onClose={onClose} onUpdated={() => {}} />,
  );
}

describe("UpdateLoanCaseModal stage-specific form rendering", () => {
  it("New Customer: shows the New Customer Details form (and Document Verification), not Bank/NBFC Offers or RV/OV/Ref", async () => {
    renderModal("new_customer", ["credit_evaluation"]);
    expect(await screen.findByRole("heading", { name: "New Customer Details" })).toBeInTheDocument();
    expect(screen.getByText("Document Verification")).toBeInTheDocument();
    expect(screen.queryByText("Bank / NBFC Offers")).not.toBeInTheDocument();
    expect(screen.queryByText("RV / OV / Ref")).not.toBeInTheDocument();
  });

  it("Credit Evaluation: shows Bank/NBFC Offers and Credit Score, not New Customer Details or Document Verification", async () => {
    renderModal("credit_evaluation", ["offer_acceptance", "rejected", "re_eligible"]);
    expect(await screen.findByRole("heading", { name: "Bank / NBFC Offers" })).toBeInTheDocument();
    expect(screen.getByText("Credit Score (optional)")).toBeInTheDocument();
    expect(screen.queryByText("New Customer Details")).not.toBeInTheDocument();
    expect(screen.queryByText("Document Verification")).not.toBeInTheDocument();
    expect(screen.queryByText("RV / OV / Ref")).not.toBeInTheDocument();
  });

  it("RV / OV / Ref: shows the RV/OV/Ref form only", async () => {
    renderModal("rv_ov_ref", ["esign_nach_kyc"]);
    expect(await screen.findByText("RV / OV / Ref")).toBeInTheDocument();
    expect(screen.getByLabelText("Verification Type")).toBeInTheDocument();
    expect(screen.queryByText("Bank / NBFC Offers")).not.toBeInTheDocument();
    expect(screen.queryByText("eSign / NACH / KYC Checklist")).not.toBeInTheDocument();
  });

  it("eSign / NACH / KYC: shows its checklist only", async () => {
    renderModal("esign_nach_kyc", ["final_evaluation"]);
    expect(await screen.findByRole("heading", { name: "eSign / NACH / KYC Checklist" })).toBeInTheDocument();
    expect(screen.queryByText("RV / OV / Ref")).not.toBeInTheDocument();
  });

  it("Disbursed (terminal): shows no stage-specific form and no available next status", async () => {
    renderModal("disbursed", []);
    expect(await screen.findByText(/no direct status update is available/i)).toBeInTheDocument();
    expect(screen.queryByText("Bank / NBFC Offers")).not.toBeInTheDocument();
    expect(screen.queryByText("New Customer Details")).not.toBeInTheDocument();
    expect(screen.queryByText("RV / OV / Ref")).not.toBeInTheDocument();
    expect(screen.queryByText("eSign / NACH / KYC Checklist")).not.toBeInTheDocument();
  });

  it("Additional Documents: renders only the product's scoped required documents, not a full catalog", async () => {
    renderModal("additional_documents", ["rv_ov_ref"]);
    expect(await screen.findByText("Salary Slip")).toBeInTheDocument();
    // Both a non-required document type and a hidden one are excluded from the
    // checklist — only the product's actual required, visible documents show.
    expect(screen.queryByText("GST Certificate")).not.toBeInTheDocument();
    expect(screen.queryByText("Hidden Doc")).not.toBeInTheDocument();
  });
});

describe("UpdateLoanCaseModal never mutates without an explicit Save/Confirm", () => {
  it("filling the New Customer Details form and closing the modal (X) calls nothing", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderModal("new_customer", ["credit_evaluation"], onClose);

    await user.type(await screen.findByLabelText("Bank / NBFC Name"), "HDFC Bank");
    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(onClose).toHaveBeenCalled();
    expect(recordNewCustomerDetails).not.toHaveBeenCalled();
    expect(updateLoanCaseStatus).not.toHaveBeenCalled();
  });

  it("clicking a simple action's button only reveals the confirm panel — Cancel makes zero calls, Confirm makes exactly one", async () => {
    const user = userEvent.setup();
    renderModal("credit_evaluation", ["offer_acceptance", "rejected", "re_eligible"]);

    const findUpdateButton = () => screen.getByText("Mark Re-Eligible").closest("div")!.querySelector("button")!;
    await user.click(findUpdateButton());

    // No call fired merely by clicking — only the confirm panel appeared.
    expect(updateLoanCaseStatus).not.toHaveBeenCalled();
    expect(await screen.findByText("Remarks (optional)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(updateLoanCaseStatus).not.toHaveBeenCalled();
    expect(screen.queryByText("Remarks (optional)")).not.toBeInTheDocument();

    // Re-open (fresh DOM node after Cancel's re-render) and actually confirm this time.
    await user.click(findUpdateButton());
    await user.click(await screen.findByRole("button", { name: "Confirm" }));
    expect(updateLoanCaseStatus).toHaveBeenCalledTimes(1);
    expect(updateLoanCaseStatus).toHaveBeenCalledWith("case-1", "re_eligible", undefined);
  });
});
