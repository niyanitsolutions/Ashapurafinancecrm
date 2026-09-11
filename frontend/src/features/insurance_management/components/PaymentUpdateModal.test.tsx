import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PaymentUpdateModal } from "./PaymentUpdateModal";
import type { InsuranceCaseDetail } from "@/features/insurance_management/api";

function detail(over: Partial<InsuranceCaseDetail["insurance_details"]> = {}): InsuranceCaseDetail {
  return {
    id: "c1",
    case_code: "AFS-INS-000001",
    application_id: "app-1",
    customer_id: "cust-1",
    customer_name: "Test Customer",
    product_id: "prod-1",
    product_name: "Family Health Plus",
    assigned_to: null,
    assigned_to_name: null,
    assigned_to_channel: null,
    current_status: "payment",
    rejection_reason: null,
    next_follow_up_date: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    premium_amount: 20000,
    amount_paid: 0,
    payment_status: "not_paid",
    on_hold_reason: null,
    on_hold_other_reason: null,
    required_documents: { required_total: 1, verified_total: 1, all_required_verified: true },
    applicant: {
      age: null, profession: null, annual_income: null, alternate_mobile: null, height: null, weight: null,
      mother_name: null, father_name: null, education: null, company_name: null, designation: null,
      nominee_name: null, nominee_dob: null, nominee_relationship: null, remarks: null,
    },
    insurance_details: {
      sum_insured: null, premium_amount: 20000, ppt: 10, pt: 10, policy_login_remarks: null,
      policy_number: null, policy_issue_date: null, policy_issued_at: null,
      payment_status: "not_paid", amount_paid: 0, re_eligibility_choice: null,
      re_eligible_date: null, re_eligibility_auto_transitioned: false, ...over,
    },
  };
}

describe("PaymentUpdateModal", () => {
  it("shows the Premium plus the CURRENT Paid/Balance, and starts with a blank amount field", () => {
    render(<PaymentUpdateModal detail={detail({ amount_paid: 9000 })} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByText(/Premium ₹20,000/)).toBeInTheDocument();
    expect(screen.getByText("Current Paid")).toBeInTheDocument();
    expect(screen.getByText("₹9,000")).toBeInTheDocument();
    expect(screen.getByText("Current Balance")).toBeInTheDocument();
    expect(screen.getByText("₹11,000")).toBeInTheDocument();
    // The field is for the NEW amount only — never pre-filled with the existing total
    // (that would invite "replace the total" confusion, the exact production bug).
    expect(screen.getByLabelText("Add Payment Amount")).toHaveValue(null);
  });

  it("shows a live 'Total Paid after this payment' preview that ADDS to the current paid amount", () => {
    const detailWithExisting = detail({ amount_paid: 9000 });
    render(<PaymentUpdateModal detail={detailWithExisting} onCancel={vi.fn()} onConfirm={vi.fn()} />);

    const input = screen.getByLabelText("Add Payment Amount");
    fireEvent.change(input, { target: { value: "5000" } });

    expect(screen.getByText("Total Paid (after this payment)")).toBeInTheDocument();
    expect(screen.getByText("₹14,000")).toBeInTheDocument(); // 9000 + 5000, never just 5000
    expect(screen.getByText("₹6,000")).toBeInTheDocument(); // remaining balance 20000-14000
    expect(screen.getByText("Partially Paid")).toBeInTheDocument();
  });

  it("Save sends only the additional amount — never the total, never payment_status", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<PaymentUpdateModal detail={detail({ amount_paid: 9000 })} onCancel={vi.fn()} onConfirm={onConfirm} />);

    const input = screen.getByLabelText("Add Payment Amount");
    fireEvent.change(input, { target: { value: "5000" } });
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith({ amount: 5000 }));
  });

  it("blocks Save and shows an error when the added amount exceeds the remaining balance", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<PaymentUpdateModal detail={detail({ amount_paid: 9000 })} onCancel={vi.fn()} onConfirm={onConfirm} />);

    const input = screen.getByLabelText("Add Payment Amount");
    fireEvent.change(input, { target: { value: "20000" } }); // balance is only 11000

    expect(screen.getByText(/no more than the remaining balance/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("blocks Save for a zero or negative amount", () => {
    render(<PaymentUpdateModal detail={detail()} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    const input = screen.getByLabelText("Add Payment Amount");

    fireEvent.change(input, { target: { value: "0" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    fireEvent.change(input, { target: { value: "-5" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("shows Fully Paid in the preview when the added amount exactly clears the balance", () => {
    render(<PaymentUpdateModal detail={detail({ amount_paid: 15000 })} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Add Payment Amount"), { target: { value: "5000" } });
    expect(screen.getByText("Fully Paid")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });
});
