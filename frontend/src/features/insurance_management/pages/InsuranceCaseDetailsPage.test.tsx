import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InsuranceCaseDetailsPage } from "./InsuranceCaseDetailsPage";
import type { InsuranceCaseDetail, InsuranceCaseDocument } from "@/features/insurance_management/api";

const getInsuranceCase = vi.fn();
const listInsuranceCaseDocuments = vi.fn();
const rejectInsuranceCase = vi.fn();
const moveToPolicyLogin = vi.fn();
const moveInsuranceCaseToStage = vi.fn();
const assignInsuranceCase = vi.fn();
const holdInsuranceCase = vi.fn();

vi.mock("@/features/insurance_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/insurance_management/api")>("@/features/insurance_management/api");
  return {
    ...actual,
    getInsuranceCase: (...a: unknown[]) => getInsuranceCase(...(a as [])),
    getInsuranceCaseTimeline: () => Promise.resolve([]),
    listInsuranceCaseDocuments: (...a: unknown[]) => listInsuranceCaseDocuments(...(a as [])),
    listOtherDocuments: () => Promise.resolve([]),
    rejectInsuranceCase: (...a: unknown[]) => rejectInsuranceCase(...(a as [])),
    moveToPolicyLogin: (...a: unknown[]) => moveToPolicyLogin(...(a as [])),
    moveInsuranceCaseToStage: (...a: unknown[]) => moveInsuranceCaseToStage(...(a as [])),
    assignInsuranceCase: (...a: unknown[]) => assignInsuranceCase(...(a as [])),
    holdInsuranceCase: (...a: unknown[]) => holdInsuranceCase(...(a as [])),
  };
});

const listAdvisors = vi.fn();
vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return { ...actual, listAdvisors: (...a: unknown[]) => listAdvisors(...(a as [])) };
});

const uploadApplicationDocument = vi.fn();
vi.mock("@/features/customer/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/customer/api")>("@/features/customer/api");
  return { ...actual, uploadApplicationDocument: (...a: unknown[]) => uploadApplicationDocument(...(a as [])) };
});

vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ isOwner: true, loading: false, can: () => true }),
}));

vi.mock("@/features/customer/useProductSchema", () => ({
  useProductSchema: () => ({
    data: {
      id: "form-1", product_category: "insurance", product_id: "prod-1", product_name: "Family Health Plus",
      insurance_category_id: "cat-1", insurance_category_name: "Health Insurance",
      fields: [], repeatable_groups: [], status: "active", version: 1, created_by: null, created_at: "", updated_at: "",
      required_documents: [{ document_type_id: "dt-pan", document_type_name: "PAN", section: null, note: null, required: true }],
    },
  }),
}));

const baseCase: InsuranceCaseDetail = {
  id: "c1",
  case_code: "AFS-INS-000001",
  application_id: "app-1",
  customer_id: "cust-1",
  customer_name: "Test Customer",
  product_id: "prod-1",
  product_name: "Family Health Plus",
  assigned_to: null,
  assigned_to_name: null,
  current_status: "policy_document",
  rejection_reason: null,
  next_follow_up_date: null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  insurance_details: {
    sum_insured: null, premium_amount: null, ppt: null, pt: null, policy_login_remarks: null,
    policy_number: null, policy_issued_at: null, re_eligibility_choice: null, re_eligible_date: null,
    re_eligibility_auto_transitioned: false,
  },
  required_documents: { required_total: 1, verified_total: 0, all_required_verified: false },
  on_hold_reason: null,
  on_hold_other_reason: null,
  applicant: {
    age: null, profession: null, annual_income: null, alternate_mobile: null, height: null, weight: null,
    mother_name: null, father_name: null, education: null, company_name: null, designation: null,
    nominee_name: null, nominee_dob: null, nominee_relationship: null, remarks: null,
  },
};

const pendingDoc: InsuranceCaseDocument = {
  id: "doc-1",
  application_id: "app-1",
  document_type_id: "dt-pan",
  document_type_name: "PAN",
  file_name: "pan.jpg",
  content_type: "image/jpeg",
  download_url: null,
  attachment_url: null,
  created_at: "2026-09-01T00:00:00Z",
  verification_status: "pending",
  verified_by_name: null,
  verified_at: null,
  rejection_reason: null,
  document_status: "uploaded",
  file_size_bytes: 1024,
  is_current: true,
  doc_version: 1,
  replaces_document_id: null,
  has_password: false,
  side: null,
  is_in_schema: true,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/insurance-cases/c1"]}>
      <Routes>
        <Route path="/insurance-cases/:caseId" element={<InsuranceCaseDetailsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("InsuranceCaseDetailsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listInsuranceCaseDocuments.mockResolvedValue([pendingDoc]);
    listAdvisors.mockResolvedValue({
      data: [
        { id: "adv-1", full_name: "Ravi Kumar", channel: "qr", status: "active" },
        { id: "adv-2", full_name: "Suresh", channel: "non_qr", status: "active" },
      ],
      pagination: null,
    });
  });

  it("assigns the case to an ACTIVE advisor (QR / Non QR shown), never a bare employee list", async () => {
    getInsuranceCase.mockResolvedValue(baseCase);
    assignInsuranceCase.mockResolvedValue(baseCase);
    renderPage();

    const select = await screen.findByLabelText("Advisor");
    await waitFor(() => expect(listAdvisors).toHaveBeenCalledWith(expect.objectContaining({ status: "active" })));
    const labels = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(labels).toEqual(expect.arrayContaining(["Ravi Kumar — QR", "Suresh — Non QR"]));

    await userEvent.setup().selectOptions(select, "adv-1");
    await userEvent.setup().click(screen.getByRole("button", { name: "Assign" }));
    await waitFor(() => expect(assignInsuranceCase).toHaveBeenCalledWith("c1", "adv-1"));
  });

  it("hold form uses the insurance reasons and requires 'Other Hold Reason' when Other is picked", async () => {
    getInsuranceCase.mockResolvedValue(baseCase);
    holdInsuranceCase.mockResolvedValue(baseCase);
    const user = userEvent.setup();
    renderPage();

    const reason = await screen.findByLabelText("Hold Reason");
    const options = Array.from(reason.querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toEqual(["Underwriting Issues", "Medical Pending", "Document Not Clear", "Payment Pending", "Document Pending", "Other"]);

    await user.selectOptions(reason, "other");
    const placeOnHold = screen.getByRole("button", { name: "Place On Hold" });
    expect(placeOnHold).toBeDisabled();

    await user.type(screen.getByLabelText("Other Hold Reason"), "Customer requested callback tomorrow");
    expect(placeOnHold).toBeEnabled();
    await user.click(placeOnHold);
    await waitFor(() =>
      expect(holdInsuranceCase).toHaveBeenCalledWith("c1", {
        reason: "other",
        other_reason: "Customer requested callback tomorrow",
        remarks: undefined,
      }),
    );
  });

  it("shows the hold reason (incl. the Other free text) while a case is on hold", async () => {
    getInsuranceCase.mockResolvedValue({
      ...baseCase,
      current_status: "on_hold",
      on_hold_reason: "other",
      on_hold_other_reason: "Customer requested callback tomorrow",
    });
    renderPage();
    expect(await screen.findByText(/Other — Customer requested callback tomorrow/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume" })).toBeInTheDocument();
  });

  it("renders the extended applicant details, dashes for missing values", async () => {
    getInsuranceCase.mockResolvedValue({
      ...baseCase,
      applicant: { ...baseCase.applicant, height: 172, mother_name: "Lakshmi", nominee_name: "Priya Kumar" },
    });
    renderPage();
    await screen.findByText("Applicant Details");
    expect(screen.getByText("172")).toBeInTheDocument();
    expect(screen.getByText("Lakshmi")).toBeInTheDocument();
    expect(screen.getByText("Priya Kumar")).toBeInTheDocument();
  });

  it("keeps Move to Policy Login disabled until every required document is verified", async () => {
    getInsuranceCase.mockResolvedValue(baseCase);
    renderPage();

    const moveBtn = await screen.findByRole("button", { name: "Move to Policy Login" });
    expect(moveBtn).toBeDisabled();
    expect(screen.getByText("0 / 1 required documents verified.")).toBeInTheDocument();
  });

  it("enables Move to Policy Login once all required documents are verified", async () => {
    getInsuranceCase.mockResolvedValue({
      ...baseCase,
      required_documents: { required_total: 1, verified_total: 1, all_required_verified: true },
    });
    moveToPolicyLogin.mockResolvedValue(baseCase);
    renderPage();

    const moveBtn = await screen.findByRole("button", { name: "Move to Policy Login" });
    expect(moveBtn).toBeEnabled();
    await userEvent.setup().click(moveBtn);
    await waitFor(() => expect(moveToPolicyLogin).toHaveBeenCalledWith("c1"));
  });

  it("opens the reject modal with insurance's 3 / 6 / 12 / Custom / No options (no 9-month)", async () => {
    getInsuranceCase.mockResolvedValue(baseCase);
    renderPage();

    const rejectBtn = await screen.findByRole("button", { name: "Reject Case" });
    await userEvent.setup().click(rejectBtn);

    expect(await screen.findByText("Reject Insurance Case")).toBeInTheDocument();
    expect(screen.getByLabelText("3 Months")).toBeInTheDocument();
    expect(screen.getByLabelText("6 Months")).toBeInTheDocument();
    expect(screen.getByLabelText("12 Months")).toBeInTheDocument();
    expect(screen.queryByLabelText("9 Months")).not.toBeInTheDocument();
  });

  it("the Move To Stage control offers the other stages and moves the case", async () => {
    getInsuranceCase.mockResolvedValue(baseCase);
    moveInsuranceCaseToStage.mockResolvedValue(baseCase);
    renderPage();

    const select = await screen.findByLabelText("Target stage");
    const labels = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(labels).toContain("Policy Login");
    expect(labels).not.toContain("Policy Document"); // current stage is excluded

    await userEvent.setup().selectOptions(select, "policy_login");
    await userEvent.setup().click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(moveInsuranceCaseToStage).toHaveBeenCalledWith("c1", { target: "policy_login" }));
  });

  it("picking Rejected in Move To Stage opens the reject modal", async () => {
    getInsuranceCase.mockResolvedValue(baseCase);
    renderPage();

    await userEvent.setup().selectOptions(await screen.findByLabelText("Target stage"), "rejected");
    await userEvent.setup().click(screen.getByRole("button", { name: "Move" }));
    expect(await screen.findByText("Reject Insurance Case")).toBeInTheDocument();
    expect(moveInsuranceCaseToStage).not.toHaveBeenCalled();
  });

  it("at Policy Document, an un-uploaded required document shows an upload control wired to the staff upload endpoint", async () => {
    getInsuranceCase.mockResolvedValue(baseCase);
    listInsuranceCaseDocuments.mockResolvedValue([]); // nothing uploaded yet
    uploadApplicationDocument.mockResolvedValue({ id: "d1" });
    const { container } = renderPage();
    await screen.findByRole("button", { name: "Move to Policy Login" });

    expect(screen.getByText(/choose a file/i)).toBeInTheDocument();

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.setup().upload(input, new File(["x"], "pan.pdf", { type: "application/pdf" }));
    await waitFor(() =>
      expect(uploadApplicationDocument).toHaveBeenCalledWith("app-1", "dt-pan", expect.any(File), undefined, undefined),
    );
  });

  it("at Policy Document, a rejected required document shows its reason and a re-upload control", async () => {
    getInsuranceCase.mockResolvedValue(baseCase);
    listInsuranceCaseDocuments.mockResolvedValue([
      { ...pendingDoc, verification_status: "rejected", rejection_reason: "Blurry scan" },
    ]);
    const { container } = renderPage();
    await screen.findByRole("button", { name: "Move to Policy Login" });

    expect(screen.getByText(/Blurry scan/)).toBeInTheDocument();
    // A rejected doc keeps a re-upload dropzone even though a version already exists.
    expect(container.querySelector('input[type="file"]')).not.toBeNull();
  });

  it("at Policy Issued the checklist is read-only (no upload control)", async () => {
    getInsuranceCase.mockResolvedValue({ ...baseCase, current_status: "policy_issued" });
    listInsuranceCaseDocuments.mockResolvedValue([]);
    const { container } = renderPage();
    await screen.findByText("Policy");
    expect(container.querySelector('input[type="file"]')).toBeNull();
  });
});
