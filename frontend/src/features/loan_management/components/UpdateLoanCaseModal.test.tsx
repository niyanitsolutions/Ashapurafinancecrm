import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UpdateLoanCaseModal } from "./UpdateLoanCaseModal";
import type { LoanCaseDetail } from "@/features/loan_management/api";

// Decision #130/#132, redesigned this round (New Customer bank/NBFC records + Additional
// Documents by name): the Update modal must render the form matching the case's CURRENT
// stage only — never more than one stage's form at a time, never the wrong one — and
// must never call a mutating API function until an explicit Save/Confirm click.

const updateLoanCaseStatus = vi.fn(() => Promise.resolve({ current_status: "re_eligible" }));
const moveToCreditEvaluation = vi.fn(() => Promise.resolve({ current_status: "credit_evaluation" }));
const moveLoanCaseBack = vi.fn(() => Promise.resolve({ current_status: "new_customer" }));
const disburseLoanCase = vi.fn((_id: string, _payload: Record<string, unknown>) => Promise.resolve({ current_status: "disbursed" }));
const getLoanCase = vi.fn((_id: string) =>
  Promise.resolve({ id: "case-1", case_code: "AFS-LOAN-000005", customer: null, loan_details: { disbursed_at: "2026-08-25T04:00:00.000Z" } }),
);
const listBankOffers = vi.fn(() => Promise.resolve([] as unknown[]));
const selectBankOffer = vi.fn((_caseId: string, _offerId: string) => Promise.resolve({ current_status: "offer_acceptance" }));
const overrideLoanCaseStage = vi.fn(() => Promise.resolve({ current_status: "disbursed" }));

vi.mock("@/features/loan_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/loan_management/api")>("@/features/loan_management/api");
  return {
    ...actual,
    listBankOffers: () => listBankOffers(),
    selectBankOffer: (caseId: string, offerId: string) => selectBankOffer(caseId, offerId),
    listAdditionalDocuments: vi.fn(() => Promise.resolve([])),
    updateLoanCaseStatus: (...args: unknown[]) => updateLoanCaseStatus(...(args as [])),
    moveToCreditEvaluation: (...args: unknown[]) => moveToCreditEvaluation(...(args as [])),
    moveLoanCaseBack: (...args: unknown[]) => moveLoanCaseBack(...(args as [])),
    disburseLoanCase: (id: string, payload: Record<string, unknown>) => disburseLoanCase(id, payload),
    overrideLoanCaseStage: (...args: unknown[]) => overrideLoanCaseStage(...(args as [])),
    getLoanCase: (id: string) => getLoanCase(id),
  };
});

function makeBankOffer(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "offer-1", loan_case_id: "case-1", bank_name: "HDFC Bank", branch: null, loan_type: null, requested_amount: null,
    bank_application_id: null, reference_number: null, assigned_officer: null, decision: "pending", approved_amount: null,
    interest_rate: null, tenure_months: null, processing_fee: null, emi_per_month: null, remarks: null,
    is_selected: false, selected_at: null, selected_by: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const baseDetails: LoanCaseDetail["loan_details"] = {
  preferred_bank_name: null, preferred_branch: null, loan_type: null, requested_amount: null, preferred_remarks: null,
  credit_score: null, credit_remarks: null, bank_nbfc_name: null, bank_application_id: null, bank_reference_number: null,
  assigned_officer: null, bank_decision: null, bank_remarks: null, offered_amount: null, offered_tenure_months: null,
  offered_interest_rate: null, offer_decision: "pending", rv_ov_ref_type: null, rv_ov_ref_status: null, rv_ov_ref_date: null,
  rv_ov_ref_verified_by: null, rv_ov_ref_result: null, rv_ov_ref_remarks: null, esign_completed: false, nach_completed: false,
  kyc_completed: false, final_evaluation_remarks: null,
  re_eligibility_choice: null, re_eligible_date: null, re_eligibility_scheduled_at: null, re_eligibility_scheduled_by: null,
  re_eligibility_auto_transitioned: false,
  disbursed_amount: null, disbursed_at: null, disbursed_reference: null,
  top_up_period: null, top_up_eligibility_date: null, top_up_remarks: null, top_up_scheduled_at: null, top_up_scheduled_by: null,
};

function makeCase(status: string, allowedNext: string[] = [], allowedPrevious: string[] = []): LoanCaseDetail {
  return {
    id: "case-1", case_code: "AFS-LOAN-000005", application_id: "app-1", customer_id: "cust-1", customer_name: "Kamal Mandal",
    product_id: "prod-1", product_name: "Personal Loan", assigned_to: "emp-1", assigned_to_name: "Lucky Kumar",
    current_status: status, rejection_reason: null, allowed_next_statuses: allowedNext, selected_bank_name: null,
    approved_amount: null, disbursed_amount: null, disbursed_at: null, next_follow_up_date: null,
    created_at: "2026-01-01T00:00:00Z", pending_document_type_ids: [], loan_details: baseDetails,
    updated_at: "2026-01-01T00:00:00Z", allowed_previous_statuses: allowedPrevious, customer: null, application: null, bank_offers: [],
  };
}

function renderModal(status: string, allowedNext: string[] = [], onClose = () => {}, allowedPrevious: string[] = []) {
  return render(
    <UpdateLoanCaseModal caseId="case-1" loanCase={makeCase(status, allowedNext, allowedPrevious)} canEdit canDisburse={false} onClose={onClose} onUpdated={() => {}} />,
  );
}

describe("UpdateLoanCaseModal stage-specific form rendering", () => {
  it("New Customer: shows Bank/NBFC Offers and a Move to Credit Evaluation action, not RV/OV/Ref", async () => {
    renderModal("new_customer", ["credit_evaluation", "rejected"]);
    expect(await screen.findByRole("heading", { name: "Bank / NBFC Offers" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move to Credit Evaluation" })).toBeInTheDocument();
    expect(screen.queryByText("RV / OV / Ref")).not.toBeInTheDocument();
    expect(screen.queryByText("Document Verification")).not.toBeInTheDocument();
  });

  it("Credit Evaluation: shows Bank/NBFC Offers and Credit Score, not RV/OV/Ref or Additional Documents", async () => {
    renderModal("credit_evaluation", ["offer_acceptance", "rejected", "re_eligible"]);
    expect(await screen.findByRole("heading", { name: "Bank / NBFC Offers" })).toBeInTheDocument();
    expect(screen.getByText("Credit Score (optional)")).toBeInTheDocument();
    expect(screen.queryByText("RV / OV / Ref")).not.toBeInTheDocument();
    expect(screen.queryByText("Additional Documents")).not.toBeInTheDocument();
  });

  it("Credit Evaluation: with no approved offer yet, explains that approving + selecting an offer moves the case to Offer Acceptance", async () => {
    listBankOffers.mockResolvedValueOnce([makeBankOffer({ decision: "pending" })]);
    renderModal("credit_evaluation", ["offer_acceptance", "rejected", "re_eligible"]);
    const hint = await screen.findByText(/move this case to/i);
    expect(hint.textContent).toMatch(/Offer Acceptance/);
    expect(hint.textContent).toMatch(/Approved/);
    expect(hint.textContent).toMatch(/Select/);
    expect(screen.queryByRole("button", { name: "Select" })).not.toBeInTheDocument();
  });

  it("Credit Evaluation: an Approved, unselected offer shows Select; confirming it calls the existing selectBankOffer transition", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    listBankOffers.mockResolvedValueOnce([
      makeBankOffer({ decision: "approved", approved_amount: 500000, interest_rate: 10.5, tenure_months: 36, emi_per_month: 16000 }),
    ]);
    renderModal("credit_evaluation", ["offer_acceptance", "rejected", "re_eligible"], onClose);

    const selectButton = await screen.findByRole("button", { name: "Select" });
    // The explanatory hint is gone now that a selectable offer exists.
    expect(screen.queryByText(/move this case to/i)).not.toBeInTheDocument();

    await user.click(selectButton);
    await user.click(await screen.findByRole("button", { name: "Select Offer" }));

    expect(selectBankOffer).toHaveBeenCalledWith("case-1", "offer-1");
    // Same "onOfferSelected -> onUpdated + onClose" behavior the existing Offer
    // Acceptance hand-off already used before this fix.
    expect(onClose).toHaveBeenCalled();
  });

  it("Credit Evaluation: existing Reject/Mark Re-Eligible/Move back actions are unaffected by the hint text", async () => {
    listBankOffers.mockResolvedValueOnce([makeBankOffer({ decision: "pending" })]);
    renderModal("credit_evaluation", ["offer_acceptance", "rejected", "re_eligible"], () => {}, ["new_customer"]);
    await screen.findByText(/move this case to/i);
    expect(screen.getAllByRole("button", { name: "Reject" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Mark Re-Eligible")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move Back" })).toBeInTheDocument();
  });

  it("RV / OV / Ref: shows the RV/OV/Ref form only", async () => {
    renderModal("rv_ov_ref", ["esign_nach_kyc", "rejected"]);
    expect(await screen.findByText("RV / OV / Ref")).toBeInTheDocument();
    expect(screen.getByLabelText("Verification Type")).toBeInTheDocument();
    expect(screen.queryByText("Bank / NBFC Offers")).not.toBeInTheDocument();
    expect(screen.queryByText("eSign / NACH / KYC Checklist")).not.toBeInTheDocument();
  });

  it("eSign / NACH / KYC: shows its checklist only", async () => {
    renderModal("esign_nach_kyc", ["final_evaluation", "rejected"]);
    expect(await screen.findByRole("heading", { name: "eSign / NACH / KYC Checklist" })).toBeInTheDocument();
    expect(screen.queryByText("RV / OV / Ref")).not.toBeInTheDocument();
  });

  it("Top Up Loan (production add-on): a successful disbursement opens the Top Up scheduling popup automatically instead of just closing", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <UpdateLoanCaseModal
        caseId="case-1"
        loanCase={makeCase("send_for_disbursement", ["disbursed"])}
        canEdit
        canDisburse
        onClose={onClose}
        onUpdated={() => {}}
      />,
    );
    await screen.findByRole("heading", { name: "Disbursement" });

    await user.type(screen.getByRole("spinbutton"), "90000");
    await user.type(screen.getByRole("textbox"), "UTR12345");
    await user.click(screen.getByRole("button", { name: "Mark Disbursed" }));
    await user.click(await screen.findByRole("button", { name: "Confirm Disbursement" }));

    await screen.findByRole("heading", { name: "Top Up Loan" });
    expect(disburseLoanCase).toHaveBeenCalledWith("case-1", { disbursed_amount: 90000, disbursed_reference: "UTR12345" });
    // The Update modal's own onClose is deferred until the Top Up popup itself closes —
    // it must not have fired yet just because disbursement succeeded.
    expect(onClose).not.toHaveBeenCalled();
  });

  it("Disbursed (terminal): shows no stage-specific form and no available next status", async () => {
    renderModal("disbursed", []);
    expect(await screen.findByText(/no direct status update is available/i)).toBeInTheDocument();
    expect(screen.queryByText("Bank / NBFC Offers")).not.toBeInTheDocument();
    expect(screen.queryByText("RV / OV / Ref")).not.toBeInTheDocument();
    expect(screen.queryByText("eSign / NACH / KYC Checklist")).not.toBeInTheDocument();
  });

  it("Additional Documents: shows the named-document panel, not a fixed checklist", async () => {
    renderModal("additional_documents", ["rv_ov_ref", "rejected"]);
    expect(await screen.findByRole("heading", { name: "Additional Documents" })).toBeInTheDocument();
    expect(screen.getByLabelText("Document Name")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request Selected Documents" })).not.toBeInTheDocument();
  });

  it("shows a Move Back control only when the backend reports a configured previous status", async () => {
    renderModal("credit_evaluation", ["offer_acceptance", "rejected", "re_eligible"], () => {}, ["new_customer"]);
    expect(await screen.findByText(/Move back to/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move Back" })).toBeInTheDocument();
  });

  it("hides the Move Back control when no previous status is configured", async () => {
    renderModal("new_customer", ["credit_evaluation", "rejected"], () => {}, []);
    await screen.findByRole("heading", { name: "Bank / NBFC Offers" });
    expect(screen.queryByText(/Move back to/i)).not.toBeInTheDocument();
  });
});

describe("UpdateLoanCaseModal never mutates without an explicit Save/Confirm", () => {
  it("New Customer: adding a bank offer requires the Add form's own Save Bank click, not just typing", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderModal("new_customer", ["credit_evaluation", "rejected"], onClose);

    await user.click(await screen.findByRole("button", { name: "+ Add Other Bank" }));
    await user.type(await screen.findByLabelText("Bank / NBFC Name"), "HDFC Bank");
    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(onClose).toHaveBeenCalled();
    expect(moveToCreditEvaluation).not.toHaveBeenCalled();
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
    expect(updateLoanCaseStatus).toHaveBeenCalledWith("case-1", "re_eligible", undefined, undefined);
  });

  it("Move Back requires its own Confirm click", async () => {
    const user = userEvent.setup();
    renderModal("credit_evaluation", ["offer_acceptance", "rejected", "re_eligible"], () => {}, ["new_customer"]);

    await user.click(await screen.findByRole("button", { name: "Move Back" }));
    expect(moveLoanCaseBack).not.toHaveBeenCalled();

    await user.click(await screen.findByRole("button", { name: "Confirm Move Back" }));
    expect(moveLoanCaseBack).toHaveBeenCalledTimes(1);
  });

  it("Reject opens the Re-Eligibility scheduling popup and sends the chosen schedule + remarks", async () => {
    const user = userEvent.setup();
    updateLoanCaseStatus.mockClear();
    renderModal("new_customer", ["credit_evaluation", "rejected"]);

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    // Nothing fired yet — the scheduling popup opened.
    expect(updateLoanCaseStatus).not.toHaveBeenCalled();
    expect(await screen.findByText(/should this case become Re-Eligible/i)).toBeInTheDocument();

    // Confirm Reject is disabled until a choice + remarks are provided.
    const confirm = screen.getByRole("button", { name: "Confirm Reject" });
    expect(confirm).toBeDisabled();

    await user.click(screen.getByLabelText("6 Months"));
    await user.type(screen.getByLabelText(/Remarks/i), "Credit score too low");
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    expect(updateLoanCaseStatus).toHaveBeenCalledWith("case-1", "rejected", "Credit score too low", {
      re_eligibility: "6_months",
      re_eligible_date: undefined,
    });
  });

  it("Reject → No sends re_eligibility 'no' (never automatically Re-Eligible)", async () => {
    const user = userEvent.setup();
    updateLoanCaseStatus.mockClear();
    renderModal("new_customer", ["credit_evaluation", "rejected"]);

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    await user.click(await screen.findByLabelText("No"));
    await user.type(screen.getByLabelText(/Remarks/i), "Do not revisit");
    await user.click(screen.getByRole("button", { name: "Confirm Reject" }));

    expect(updateLoanCaseStatus).toHaveBeenCalledWith("case-1", "rejected", "Do not revisit", {
      re_eligibility: "no",
      re_eligible_date: undefined,
    });
  });
});

describe("UpdateLoanCaseModal — Staff Override — Skip Stage Validations", () => {
  it("is OFF by default: the checkbox is unchecked and the Move To Stage dropdown is hidden", async () => {
    renderModal("new_customer", ["credit_evaluation", "rejected"]);
    const checkbox = await screen.findByRole("checkbox", { name: /Staff Override — Skip Stage Validations/i });
    expect(checkbox).not.toBeChecked();
    expect(screen.queryByLabelText("Move To Stage")).not.toBeInTheDocument();
    // The normal Move-to-Next action is untouched and present.
    expect(screen.getByRole("button", { name: "Move to Credit Evaluation" })).toBeInTheDocument();
  });

  it("checking it reveals the stage dropdown (current stage + on_hold excluded); a non-adjacent stage moves via overrideLoanCaseStage after Confirm", async () => {
    const user = userEvent.setup();
    overrideLoanCaseStage.mockClear();
    overrideLoanCaseStage.mockResolvedValueOnce({ current_status: "esign_nach_kyc" });
    renderModal("new_customer", ["credit_evaluation", "rejected"]);

    await user.click(await screen.findByRole("checkbox", { name: /Staff Override/i }));
    const select = await screen.findByLabelText("Move To Stage");
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toContain("eSign / NACH / KYC");
    expect(options).not.toContain("New Customer"); // current stage excluded
    expect(options).not.toContain("On Hold"); // has its own Hold/Resume action

    await user.selectOptions(select, "esign_nach_kyc");
    await user.click(screen.getByRole("button", { name: "Move to Selected Stage" }));
    // Nothing fired yet — only the confirm step appeared.
    expect(overrideLoanCaseStage).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirm Override" }));
    expect(overrideLoanCaseStage).toHaveBeenCalledWith("case-1", "esign_nach_kyc", undefined);
  });

  it("passes the optional reason through", async () => {
    const user = userEvent.setup();
    overrideLoanCaseStage.mockClear();
    overrideLoanCaseStage.mockResolvedValueOnce({ current_status: "offer_acceptance" });
    renderModal("new_customer", ["credit_evaluation", "rejected"]);

    await user.click(await screen.findByRole("checkbox", { name: /Staff Override/i }));
    await user.selectOptions(await screen.findByLabelText("Move To Stage"), "offer_acceptance");
    await user.type(screen.getByLabelText("Reason (optional)"), "Management approved");
    await user.click(screen.getByRole("button", { name: "Move to Selected Stage" }));
    await user.click(screen.getByRole("button", { name: "Confirm Override" }));
    expect(overrideLoanCaseStage).toHaveBeenCalledWith("case-1", "offer_acceptance", "Management approved");
  });
});
