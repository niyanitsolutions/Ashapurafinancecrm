import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PolicyLoginUpdateModal } from "./PolicyLoginUpdateModal";
import type { InsuranceCaseDetail } from "@/features/insurance_management/api";

const listPortalProducts = vi.fn();
vi.mock("@/features/customer/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/customer/api")>("@/features/customer/api");
  return { ...actual, listPortalProducts: (...a: unknown[]) => listPortalProducts(...(a as [])) };
});

function detail(over: Partial<InsuranceCaseDetail["insurance_details"]> = {}): InsuranceCaseDetail {
  return {
    id: "c1",
    case_code: "AFS-INS-000001",
    application_id: "app-1",
    customer_id: "cust-1",
    customer_name: "Test Customer",
    product_id: "prod-1",
    product_name: "ManipalCigna Prime Senior",
    assigned_to: null,
    assigned_to_name: null,
    assigned_to_channel: null,
    current_status: "policy_login",
    rejection_reason: null,
    next_follow_up_date: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    on_hold_reason: null,
    on_hold_other_reason: null,
    required_documents: { required_total: 1, verified_total: 1, all_required_verified: true },
    applicant: {
      age: null, profession: null, annual_income: null, alternate_mobile: null, height: null, weight: null,
      mother_name: null, father_name: null, education: null, company_name: null, designation: null,
      nominee_name: null, nominee_dob: null, nominee_relationship: null, remarks: null,
    },
    insurance_details: {
      sum_insured: null, premium_amount: null, ppt: null, pt: null, policy_login_remarks: null,
      policy_number: null, policy_issue_date: null, policy_issued_at: null, re_eligibility_choice: null,
      re_eligible_date: null, re_eligibility_auto_transitioned: false, ...over,
    },
  };
}

describe("PolicyLoginUpdateModal", () => {
  beforeEach(() => {
    listPortalProducts.mockReset();
    listPortalProducts.mockResolvedValue([]);
  });

  it("shows an Issue Date field near Policy Number", async () => {
    render(<PolicyLoginUpdateModal detail={detail()} onCancel={vi.fn()} onConfirm={vi.fn()} />);
    await screen.findByLabelText("Product");
    expect(screen.getByLabelText("Issue Date")).toBeInTheDocument();
    expect(screen.getByLabelText("Issue Date")).toHaveAttribute("type", "date");
  });

  it("loads an existing saved Issue Date into the form", async () => {
    render(
      <PolicyLoginUpdateModal
        detail={detail({ policy_issue_date: "2026-09-09T18:30:00+00:00", policy_number: "POL123456789" })}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    await screen.findByLabelText("Product");
    expect(screen.getByLabelText("Issue Date")).toHaveValue("2026-09-10");
    expect(screen.getByLabelText("Policy Number")).toHaveValue("POL123456789");
  });

  it("sends the entered Issue Date on Save", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<PolicyLoginUpdateModal detail={detail()} onCancel={vi.fn()} onConfirm={onConfirm} />);
    await screen.findByLabelText("Product");

    await user.type(screen.getByLabelText("Premium Amount"), "20000");
    await user.type(screen.getByLabelText("PPT (years)"), "10");
    await user.type(screen.getByLabelText("PT (years)"), "10");
    await user.type(screen.getByLabelText("Policy Number"), "POL123456789");
    await user.type(screen.getByLabelText("Issue Date"), "2026-09-10");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(onConfirm).toHaveBeenCalledWith(
        expect.objectContaining({
          premium_amount: 20000, ppt: 10, pt: 10, policy_number: "POL123456789", policy_issue_date: "2026-09-10",
        }),
      ),
    );
  });

  it("omits policy_issue_date when left blank", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<PolicyLoginUpdateModal detail={detail()} onCancel={vi.fn()} onConfirm={onConfirm} />);
    await screen.findByLabelText("Product");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
    expect(onConfirm.mock.calls[0][0].policy_issue_date).toBeUndefined();
  });
});
