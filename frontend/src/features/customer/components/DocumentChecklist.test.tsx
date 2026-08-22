import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DocumentChecklist } from "./DocumentChecklist";
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
    expect(onUpload).toHaveBeenCalledWith("dt-bank", expect.any(File), undefined);
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

    expect(onUpload).toHaveBeenCalledWith("dt-bank", expect.any(File), "MyStatement@Pass1");
  });

  it("never sends a password for a document type that doesn't support one", async () => {
    const onUpload = vi.fn();
    const { container } = render(
      <DocumentChecklist requiredDocuments={[PAN_DOC]} uploadedDocuments={[]} onUpload={onUpload} uploadingFor={null} />,
    );
    const user = userEvent.setup();
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, makeFile("pan.pdf"));

    expect(onUpload).toHaveBeenCalledWith("dt-pan", expect.any(File), undefined);
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
    expect(screen.getByText("Show Password (yes)")).toBeInTheDocument();
  });
});
