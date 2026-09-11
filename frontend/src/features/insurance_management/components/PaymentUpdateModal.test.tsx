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
  it("shows the Premium in the description and starts from the current Amount Paid", () => {
    render(<PaymentUpdateModal detail={detail({ amount_paid: 5000 })} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.getByText(/Premium ₹20,000/)).toBeInTheDocument();
    expect(screen.getByLabelText("Amount Paid")).toHaveValue(5000);
  });

  it("shows a live Balance / Payment Status preview that updates as you type — never submitted", async () => {
    const user = userEvent.setup();
    render(<PaymentUpdateModal detail={detail()} onCancel={vi.fn()} onConfirm={vi.fn()} />);

    const input = screen.getByLabelText("Amount Paid");
    await user.clear(input);
    await user.type(input, "12000");

    expect(screen.getByText("₹8,000")).toBeInTheDocument(); // Balance
    expect(screen.getByText("Partially Paid")).toBeInTheDocument();
  });

  it("Save sends only amount_paid — no payment_status field", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<PaymentUpdateModal detail={detail()} onCancel={vi.fn()} onConfirm={onConfirm} />);

    const input = screen.getByLabelText("Amount Paid");
    await user.clear(input);
    await user.type(input, "20000");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith({ amount_paid: 20000 }));
  });

  it("blocks Save and shows an error when Amount Paid exceeds the Premium", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<PaymentUpdateModal detail={detail()} onCancel={vi.fn()} onConfirm={onConfirm} />);

    const input = screen.getByLabelText("Amount Paid");
    fireEvent.change(input, { target: { value: "25000" } });

    expect(screen.getByText(/must be between ₹0 and the Premium Amount/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("blocks Save for a negative Amount Paid", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<PaymentUpdateModal detail={detail()} onCancel={vi.fn()} onConfirm={onConfirm} />);

    const input = screen.getByLabelText("Amount Paid");
    await user.clear(input);
    await user.type(input, "-5");

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });
});
