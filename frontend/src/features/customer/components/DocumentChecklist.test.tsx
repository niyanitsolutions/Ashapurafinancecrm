import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DocumentChecklist, documentCompletionSummary } from "./DocumentChecklist";
import type { ApplicationDocument, RequiredDocument } from "@/features/customer/api";

// Bank Statement password support (optional field, associated with the document TYPE
// via `supports_password`, never hardcoded per product — see RequiredDocument's own
// docstring). Regression coverage for: the field only appears for a password-eligible
// document type, is masked, is never required, and the entered value (or its absence)
// reaches `onUpload` exactly as typed.

const BANK_STATEMENT_DOC: RequiredDocument = {
  document_type_id: "dt-bank",
  document_type_name: "Bank Statement",
  section: null,
  note: null,
  supports_password: true,
};

const PAN_DOC: RequiredDocument = {
  document_type_id: "dt-pan",
  document_type_name: "PAN Card",
  section: null,
  note: null,
  supports_password: false,
};

function makeFile(name = "statement.pdf") {
  return new File(["dummy"], name, { type: "application/pdf" });
}

describe("DocumentChecklist — Bank Statement password field", () => {
  it("does not render a password field for a document type without supports_password", () => {
    render(
      <DocumentChecklist requiredDocuments={[PAN_DOC]} uploadedDocuments={[]} onUpload={vi.fn()} uploadingFor={null} />,
    );
    expect(screen.queryByText(/Bank Statement Password/i)).not.toBeInTheDocument();
  });

  it("renders an optional, masked password field for a supports_password document type", () => {
    render(
      <DocumentChecklist requiredDocuments={[BANK_STATEMENT_DOC]} uploadedDocuments={[]} onUpload={vi.fn()} uploadingFor={null} />,
    );
    const input = screen.getByLabelText(/Bank Statement Password/i);
    expect(input).toHaveAttribute("type", "password");
    expect(input).not.toBeRequired();
    expect(
      screen.getByText(/Enter the password only if your bank statement is password protected/i),
    ).toBeInTheDocument();
  });

  it("uploads without a password when the field is left blank", async () => {
    const onUpload = vi.fn();
    const { container } = render(
      <DocumentChecklist requiredDocuments={[BANK_STATEMENT_DOC]} uploadedDocuments={[]} onUpload={onUpload} uploadingFor={null} />,
    );
    const user = userEvent.setup();
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, makeFile());

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload).toHaveBeenCalledWith("dt-bank", expect.any(File), undefined, undefined);
  });

  it("forwards the entered password to onUpload exactly as typed", async () => {
    const onUpload = vi.fn();
    const { container } = render(
      <DocumentChecklist requiredDocuments={[BANK_STATEMENT_DOC]} uploadedDocuments={[]} onUpload={onUpload} uploadingFor={null} />,
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/Bank Statement Password/i), "MyStatement@Pass1");
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, makeFile());

    expect(onUpload).toHaveBeenCalledWith("dt-bank", expect.any(File), "MyStatement@Pass1", undefined);
  });

  it("never sends a password for a document type that doesn't support one", async () => {
    const onUpload = vi.fn();
    const { container } = render(
      <DocumentChecklist requiredDocuments={[PAN_DOC]} uploadedDocuments={[]} onUpload={onUpload} uploadingFor={null} />,
    );
    const user = userEvent.setup();
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, makeFile("pan.pdf"));

    expect(onUpload).toHaveBeenCalledWith("dt-pan", expect.any(File), undefined, undefined);
  });

  it("still shows Preview/Download/Verify affordances for an uploaded, password-protected document", () => {
    const uploaded: ApplicationDocument = {
      id: "doc-1",
      application_id: "app-1",
      document_type_id: "dt-bank",
      document_type_name: "Bank Statement",
      file_name: "statement.pdf",
      content_type: "application/pdf",
      download_url: "https://example-signed-url.test/statement.pdf",
      attachment_url: "https://example-signed-url.test/statement.pdf?response-content-disposition=attachment",
      created_at: "2026-01-01T00:00:00Z",
      verification_status: "pending",
      verified_by_name: null,
      verified_at: null,
      rejection_reason: null,
      document_status: "uploaded",
      file_size_bytes: 1024,
      is_current: true,
      doc_version: 1,
      replaces_document_id: null,
      has_password: true,
    };
    render(
      <DocumentChecklist
        requiredDocuments={[BANK_STATEMENT_DOC]}
        uploadedDocuments={[uploaded]}
        onUpload={vi.fn()}
        uploadingFor={null}
        extraActions={(doc) => <button type="button">Show Password ({doc.has_password ? "yes" : "no"})</button>}
      />,
    );
    expect(screen.getByText("Preview")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("href", uploaded.attachment_url);
    expect(screen.getByText("Show Password (yes)")).toBeInTheDocument();
  });
});

// Front & Back upload (generic, config-driven — see RequiredDocument.front_back_upload).
// Deliberately uses a non-Aadhaar document type (Driving Licence) to prove the two-slot
// UI is driven purely by the schema flag, never a hardcoded document name.

const DRIVING_LICENCE_DOC: RequiredDocument = {
  document_type_id: "dt-dl",
  document_type_name: "Driving Licence",
  section: null,
  note: null,
  supports_password: false,
  front_back_upload: true,
};

function makeUploadedDoc(overrides: Partial<ApplicationDocument>): ApplicationDocument {
  return {
    id: "doc-x",
    application_id: "app-1",
    document_type_id: "dt-dl",
    document_type_name: "Driving Licence",
    file_name: "dl.jpg",
    content_type: "image/jpeg",
    download_url: "https://example-signed-url.test/dl.jpg",
    attachment_url: "https://example-signed-url.test/dl.jpg?disposition=attachment",
    created_at: "2026-01-01T00:00:00Z",
    verification_status: "pending",
    verified_by_name: null,
    verified_at: null,
    rejection_reason: null,
    document_status: "uploaded",
    file_size_bytes: 2048,
    is_current: true,
    doc_version: 1,
    replaces_document_id: null,
    has_password: false,
    side: null,
    ...overrides,
  };
}

describe("DocumentChecklist — Front & Back upload (generic, not Aadhaar-specific)", () => {
  it("renders two independent Front Side / Back Side slots for any front_back_upload document", () => {
    render(
      <DocumentChecklist requiredDocuments={[DRIVING_LICENCE_DOC]} uploadedDocuments={[]} onUpload={vi.fn()} uploadingFor={null} />,
    );
    expect(screen.getByText("Front Side")).toBeInTheDocument();
    expect(screen.getByText("Back Side")).toBeInTheDocument();
  });

  it("shows each side's own uploaded document in its own slot, not mixed together", () => {
    const front = makeUploadedDoc({ id: "doc-front", file_name: "dl_front.jpg", side: "front" });
    const back = makeUploadedDoc({ id: "doc-back", file_name: "dl_back.jpg", side: "back" });
    render(
      <DocumentChecklist
        requiredDocuments={[DRIVING_LICENCE_DOC]}
        uploadedDocuments={[front, back]}
        onUpload={vi.fn()}
        uploadingFor={null}
      />,
    );
    expect(screen.getByText("dl_front.jpg")).toBeInTheDocument();
    expect(screen.getByText("dl_back.jpg")).toBeInTheDocument();
  });

  it("forwards the correct side to onUpload when uploading into the Front vs Back slot", async () => {
    const onUpload = vi.fn();
    const { container } = render(
      <DocumentChecklist requiredDocuments={[DRIVING_LICENCE_DOC]} uploadedDocuments={[]} onUpload={onUpload} uploadingFor={null} />,
    );
    const user = userEvent.setup();
    const fileInputs = container.querySelectorAll('input[type="file"]');
    expect(fileInputs).toHaveLength(2);
    await user.upload(fileInputs[0] as HTMLInputElement, makeFile("dl_front.jpg"));
    expect(onUpload).toHaveBeenCalledWith("dt-dl", expect.any(File), undefined, "front");

    await user.upload(fileInputs[1] as HTMLInputElement, makeFile("dl_back.jpg"));
    expect(onUpload).toHaveBeenCalledWith("dt-dl", expect.any(File), undefined, "back");
  });

  it("never offers 'I don't have this document' for a Front & Back document", () => {
    render(
      <DocumentChecklist
        requiredDocuments={[{ ...DRIVING_LICENCE_DOC, required: false }]}
        uploadedDocuments={[]}
        onUpload={vi.fn()}
        onMarkNotAvailable={vi.fn()}
        canMarkNotAvailable
        uploadingFor={null}
      />,
    );
    expect(screen.queryByText(/I don't have this document/i)).not.toBeInTheDocument();
  });
});

describe("documentCompletionSummary — Front & Back counts as one requirement, both sides required", () => {
  it("does not count a front_back_upload document as completed with only one side uploaded", () => {
    const front = makeUploadedDoc({ id: "doc-front", side: "front" });
    const summary = documentCompletionSummary([DRIVING_LICENCE_DOC], [front]);
    expect(summary.total).toBe(1);
    expect(summary.completed).toBe(0);
    expect(summary.missing).toEqual([DRIVING_LICENCE_DOC]);
  });

  it("counts a front_back_upload document as completed once both sides are uploaded", () => {
    const front = makeUploadedDoc({ id: "doc-front", side: "front" });
    const back = makeUploadedDoc({ id: "doc-back", side: "back" });
    const summary = documentCompletionSummary([DRIVING_LICENCE_DOC], [front, back]);
    expect(summary.total).toBe(1);
    expect(summary.completed).toBe(1);
    expect(summary.missing).toEqual([]);
  });

  it("still counts an ordinary (non-front-back) document as completed with a single upload", () => {
    const uploaded = makeUploadedDoc({ id: "doc-1", document_type_id: "dt-pan", side: null });
    const summary = documentCompletionSummary([PAN_DOC], [uploaded]);
    expect(summary.completed).toBe(1);
  });
});
