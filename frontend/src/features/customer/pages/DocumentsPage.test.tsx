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
  insurance_category_id: null,
  insurance_category_name: null,
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

let applicationsToReturn: ApplicationListItem[] = [mockApplication];
let documentsToReturn: ApplicationDocument[] = mockDocuments;
let formDefToReturn: FormDefinition = mockFormDef;

const { uploadApplicationDocument } = vi.hoisted(() => ({ uploadApplicationDocument: vi.fn(() => Promise.resolve({})) }));

vi.mock("@/features/customer/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/customer/api")>("@/features/customer/api");
  return {
    ...actual,
    listOwnApplications: vi.fn(() => Promise.resolve(applicationsToReturn)),
    getFormDefinition: vi.fn(() => Promise.resolve(formDefToReturn)),
    listDocuments: vi.fn(() => Promise.resolve(documentsToReturn)),
    uploadApplicationDocument,
  };
});

function makeFile(name = "statement.pdf") {
  return new File(["dummy"], name, { type: "application/pdf" });
}

describe("DocumentsPage — password forwarding regression", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    applicationsToReturn = [mockApplication];
    documentsToReturn = mockDocuments;
    formDefToReturn = mockFormDef;
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

// Real production bug: Staff could always see "Re-upload" for a rejected document (their
// own page never disables DocumentChecklist), but the Customer Portal's Document Center
// blanket-disabled the ENTIRE checklist once `application.status === "submitted"` — and
// rejection only ever happens AFTER a customer submits, so in practice a customer could
// never actually re-upload a rejected document from this page. The backend's own
// `confirm_document` has no submission-status gate at all (re-upload after submission is
// exactly how staff review is supposed to work), so this was a frontend-only
// overcorrection, not a real business rule.

const panDoc: RequiredDocument = {
  document_type_id: "dt-pan", document_type_name: "PAN Card", section: null, note: null, supports_password: false,
};

const submittedApplication: ApplicationListItem = { ...mockApplication, status: "submitted" };

const rejectedPanDocument: ApplicationDocument = {
  id: "doc-1", application_id: "app-1", document_type_id: "dt-pan", document_type_name: "PAN Card",
  file_name: "pan_old.jpg", content_type: "image/jpeg", download_url: "https://example.test/pan_old.jpg",
  attachment_url: "https://example.test/pan_old.jpg?disposition=attachment", created_at: "2026-01-01T00:00:00Z",
  verification_status: "rejected", verified_by_name: null, verified_at: null, rejection_reason: "Blurry scan.",
  document_status: "uploaded", file_size_bytes: 1024, is_current: true, doc_version: 1, replaces_document_id: null,
  has_password: false, side: null,
};

describe("DocumentsPage — Re-upload must stay available for a rejected document after submission", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    applicationsToReturn = [submittedApplication];
    documentsToReturn = [rejectedPanDocument];
    formDefToReturn = { ...mockFormDef, required_documents: [panDoc] };
  });

  it("shows a Re-upload control for a rejected document even though the application is already submitted", async () => {
    render(
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>,
    );

    await screen.findByText("PAN Card");
    expect(screen.getByText(/Rejected — Blurry scan\./i)).toBeInTheDocument();
    expect(screen.getByText("Re-upload")).toBeInTheDocument();
  });

  it("re-uploading via that control actually calls uploadApplicationDocument", async () => {
    const { container } = render(
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>,
    );
    await screen.findByText("PAN Card");

    const user = userEvent.setup();
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, makeFile("pan_new.jpg"));

    expect(uploadApplicationDocument).toHaveBeenCalledWith("app-1", "dt-pan", expect.any(File), undefined, undefined);
  });

  it("Front/Back on a submitted application: only the rejected side offers Re-upload", async () => {
    const aadhaarDoc: RequiredDocument = {
      document_type_id: "dt-aadhaar", document_type_name: "Aadhaar Card", section: null, note: null,
      supports_password: false, front_back_upload: true,
    };
    const rejectedFront: ApplicationDocument = {
      ...rejectedPanDocument, id: "doc-front", document_type_id: "dt-aadhaar", document_type_name: "Aadhaar Card",
      file_name: "aadhaar_front.jpg", side: "front",
    };
    const verifiedBack: ApplicationDocument = {
      ...rejectedPanDocument, id: "doc-back", document_type_id: "dt-aadhaar", document_type_name: "Aadhaar Card",
      file_name: "aadhaar_back.jpg", side: "back", verification_status: "verified", rejection_reason: null,
    };
    applicationsToReturn = [submittedApplication];
    documentsToReturn = [rejectedFront, verifiedBack];
    formDefToReturn = { ...mockFormDef, required_documents: [aadhaarDoc] };

    render(
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>,
    );

    await screen.findByText("Aadhaar Card");
    expect(screen.getByText("Re-upload Front")).toBeInTheDocument();
    expect(screen.queryByText("Re-upload Back")).not.toBeInTheDocument();
  });
});
