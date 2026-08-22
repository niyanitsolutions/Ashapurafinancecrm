import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UpdateLoanCaseModal } from "./UpdateLoanCaseModal";
import type { LoanCaseDetail } from "@/features/loan_management/api";

// Decision #130: the Update modal must render the form matching the case's CURRENT
// stage only — never more than one stage's form at a time, and never the wrong one.

vi.mock("@/features/loan_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/loan_management/api")>("@/features/loan_management/api");
  return {
    ...actual,
    listBankOffers: vi.fn(() => Promise.resolve([])),
  };
});

const baseDetails: LoanCaseDetail["loan_details"] = {
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

function renderModal(status: string, allowedNext: string[] = []) {
  return render(
    <UpdateLoanCaseModal
      caseId="case-1"
      loanCase={makeCase(status, allowedNext)}
      documentTypes={[]}
      canEdit
      canDisburse={false}
      onClose={() => {}}
      onUpdated={() => {}}
    />,
  );
}

describe("UpdateLoanCaseModal stage-specific form rendering", () => {
  it("New Customer: shows Document Verification only", async () => {
    renderModal("new_customer", ["credit_evaluation"]);
    expect(await screen.findByText("Document Verification")).toBeInTheDocument();
    expect(screen.queryByText("Bank / NBFC Offers")).not.toBeInTheDocument();
    expect(screen.queryByText("RV / OV / Ref")).not.toBeInTheDocument();
  });

  it("Credit Evaluation: shows Bank/NBFC Offers and Credit Score, not Document Verification", async () => {
    renderModal("credit_evaluation", ["offer_acceptance", "rejected", "re_eligible"]);
    expect(await screen.findByRole("heading", { name: "Bank / NBFC Offers" })).toBeInTheDocument();
    expect(screen.getByText("Credit Score (optional)")).toBeInTheDocument();
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
    expect(screen.queryByText("Document Verification")).not.toBeInTheDocument();
    expect(screen.queryByText("RV / OV / Ref")).not.toBeInTheDocument();
    expect(screen.queryByText("eSign / NACH / KYC Checklist")).not.toBeInTheDocument();
  });
});
