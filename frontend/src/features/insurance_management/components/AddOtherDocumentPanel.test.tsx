import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AddOtherDocumentPanel } from "./AddOtherDocumentPanel";
import type { OtherDocument } from "@/features/insurance_management/api";

const listOtherDocuments = vi.fn();
const addOtherDocument = vi.fn();
const uploadOtherDocument = vi.fn();
const rejectOtherDocument = vi.fn();
const getOtherDocumentHistory = vi.fn();

vi.mock("@/features/insurance_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/insurance_management/api")>("@/features/insurance_management/api");
  return {
    ...actual,
    listOtherDocuments: (...a: unknown[]) => listOtherDocuments(...(a as [])),
    addOtherDocument: (...a: unknown[]) => addOtherDocument(...(a as [])),
    uploadOtherDocument: (...a: unknown[]) => uploadOtherDocument(...(a as [])),
    verifyOtherDocument: vi.fn(),
    rejectOtherDocument: (...a: unknown[]) => rejectOtherDocument(...(a as [])),
    getOtherDocumentHistory: (...a: unknown[]) => getOtherDocumentHistory(...(a as [])),
  };
});

function doc(over: Partial<OtherDocument> = {}): OtherDocument {
  return {
    id: "od-1",
    insurance_case_id: "c1",
    name: "Medical Prescription",
    document_status: "requested",
    verification_status: "pending",
    rejection_reason: null,
    file_name: null,
    download_url: null,
    attachment_url: null,
    uploaded_at: null,
    verified_at: null,
    created_at: "2026-09-01T00:00:00Z",
    is_current: true,
    doc_version: 1,
    ...over,
  };
}

describe("AddOtherDocumentPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows an Upload control after a document is added (name only)", async () => {
    listOtherDocuments.mockResolvedValue([doc()]);
    uploadOtherDocument.mockResolvedValue(doc({ document_status: "uploaded", file_name: "prescription.pdf" }));
    const { container } = render(<AddOtherDocumentPanel caseId="c1" canEdit />);

    await screen.findByText("Medical Prescription");
    expect(screen.getByText("Pending Upload")).toBeInTheDocument();
    const uploadBtn = screen.getByRole("button", { name: "Upload" });
    expect(uploadBtn).toBeInTheDocument();

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.setup().upload(input, new File(["x"], "prescription.pdf", { type: "application/pdf" }));
    await waitFor(() =>
      expect(uploadOtherDocument).toHaveBeenCalledWith("c1", "od-1", expect.any(File)),
    );
  });

  it("shows Preview / Download / Verify / Reject once uploaded", async () => {
    listOtherDocuments.mockResolvedValue([
      doc({ document_status: "uploaded", file_name: "prescription.pdf", download_url: "http://x/p", attachment_url: "http://x/a" }),
    ]);
    render(<AddOtherDocumentPanel caseId="c1" canEdit />);
    await screen.findByText("prescription.pdf");
    expect(screen.getByRole("button", { name: "Preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verify" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("offers a Re-upload control for a rejected document (old version kept in history)", async () => {
    listOtherDocuments.mockResolvedValue([
      doc({
        id: "od-2", document_status: "uploaded", verification_status: "rejected",
        rejection_reason: "Document not clear", file_name: "prescription_new.pdf", doc_version: 2,
      }),
    ]);
    getOtherDocumentHistory.mockResolvedValue([
      doc({ id: "od-1", doc_version: 1, file_name: "prescription_old.pdf", verification_status: "rejected", document_status: "uploaded" }),
      doc({ id: "od-2", doc_version: 2, file_name: "prescription_new.pdf", document_status: "uploaded" }),
    ]);
    uploadOtherDocument.mockResolvedValue(doc({ id: "od-3", doc_version: 3, document_status: "uploaded" }));
    const user = userEvent.setup();
    const { container } = render(<AddOtherDocumentPanel caseId="c1" canEdit />);

    await screen.findByText(/Document not clear/);
    expect(screen.getByRole("button", { name: "Re-upload" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /History/ }));
    await screen.findByText("prescription_old.pdf");

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["y"], "prescription_newer.pdf", { type: "application/pdf" }));
    await waitFor(() => expect(uploadOtherDocument).toHaveBeenCalledWith("c1", "od-2", expect.any(File)));
  });
});
