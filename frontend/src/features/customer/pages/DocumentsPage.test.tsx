import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentsPage } from "./DocumentsPage";
import type { ApplicationDocument, ApplicationListItem, FormDefinition, RequiredDocument } from "@/features/customer/api";

// Regression test for a real bug: this page's own `onUpload` used to drop the
// `password`/`side` arguments `DocumentChecklist` passes it, so a password typed on the
// Customer Portal's "Document Center" page never reached the backend (the equivalent
// Application-page flow was never affected — only this call site was broken).

const mockApplication: ApplicationListItem = {
  id: "app-1",
  application_code: "AFS-APP-000020",
  customer_id: "cust-1",
  customer_name: "Test Customer",
  lead_id: null,
  product_category: "loan",
  product_id: "prod-1",
  product_name: "Personal Loan",
  assigned_to: null,
  assigned_to_name: null,
  status: "draft",
  created_at: "2026-01-01T00:00:00Z",
  submitted_at: null,
  progress_percent: 40,
  case_id: null,
  case_type: null,
  case_code: null,
  case_status: null,
  case_status_label: null,
};

const bankStatementDoc: RequiredDocument = {
  document_type_id: "dt-bank",
  document_type_name: "Bank Statement",
  section: null,
  note: null,
  supports_password: true,
};

const mockFormDef: FormDefinition = {
  id: "form-1",
  product_category: "loan",
  product_id: "prod-1",
  product_name: "Personal Loan",
  fields: [],
  required_documents: [bankStatementDoc],
  repeatable_groups: [],
  status: "active",
  version: 1,
  created_by: null,
  created_at: "",
  updated_at: "",
  is_locked: false,
  frozen_at: null,
  frozen_by: null,
  schema_version: 1,
  source_schema_version: null,
};

const mockDocuments: ApplicationDocument[] = [];

const { uploadApplicationDocument } = vi.hoisted(() => ({ uploadApplicationDocument: vi.fn(() => Promise.resolve({})) }));

vi.mock("@/features/customer/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/customer/api")>("@/features/customer/api");
  return {
    ...actual,
    listOwnApplications: vi.fn(() => Promise.resolve([mockApplication])),
    getFormDefinition: vi.fn(() => Promise.resolve(mockFormDef)),
    listDocuments: vi.fn(() => Promise.resolve(mockDocuments)),
    uploadApplicationDocument,
  };
});

function makeFile(name = "statement.pdf") {
  return new File(["dummy"], name, { type: "application/pdf" });
}

describe("DocumentsPage — password forwarding regression", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("forwards a typed password through to uploadApplicationDocument, not dropped", async () => {
    render(
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>,
    );

    await screen.findByText("Bank Statement");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/Bank Statement Password/i), "PortalTypedPass1");

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, makeFile());

    expect(uploadApplicationDocument).toHaveBeenCalledWith("app-1", "dt-bank", expect.any(File), "PortalTypedPass1", undefined);
  });

  it("uploads with no password when the field is left blank", async () => {
    render(
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>,
    );

    await screen.findByText("Bank Statement");
    const user = userEvent.setup();
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, makeFile());

    expect(uploadApplicationDocument).toHaveBeenCalledWith("app-1", "dt-bank", expect.any(File), undefined, undefined);
  });
});
