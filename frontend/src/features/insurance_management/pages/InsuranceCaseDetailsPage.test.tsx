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
  };
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
