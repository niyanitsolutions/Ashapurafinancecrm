import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AdditionalDocumentsPanel } from "./AdditionalDocumentsPanel";
import type { AdditionalDocument } from "@/features/loan_management/api";

// Requirements 12/16: staff requests a document by free-text NAME (no fixed checklist),
// and Verify/Reject are real, explicit actions — Reject specifically requires a reason
// before it fires, never a bare click.

const listAdditionalDocuments = vi.fn();
const addAdditionalDocument = vi.fn(() => Promise.resolve({}));
const verifyAdditionalDocument = vi.fn(() => Promise.resolve({}));
const rejectAdditionalDocument = vi.fn(() => Promise.resolve({}));

vi.mock("@/features/loan_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/loan_management/api")>("@/features/loan_management/api");
  return {
    ...actual,
    listAdditionalDocuments: (...args: unknown[]) => listAdditionalDocuments(...(args as [])),
    addAdditionalDocument: (...args: unknown[]) => addAdditionalDocument(...(args as [])),
    verifyAdditionalDocument: (...args: unknown[]) => verifyAdditionalDocument(...(args as [])),
    rejectAdditionalDocument: (...args: unknown[]) => rejectAdditionalDocument(...(args as [])),
  };
});

const uploadedDoc: AdditionalDocument = {
  id: "doc-1", loan_case_id: "case-1", name: "Salary Revision Letter", document_status: "uploaded", verification_status: "pending",
  rejection_reason: null, file_name: "letter.pdf", download_url: "https://s3/preview", attachment_url: "https://s3/download",
  uploaded_at: "2026-08-25T10:00:00Z", verified_by_name: null, verified_at: null, created_at: "2026-08-25T09:00:00Z",
};

describe("AdditionalDocumentsPanel", () => {
  it("adding a document requires the Add Document click, not just typing a name", async () => {
    listAdditionalDocuments.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<AdditionalDocumentsPanel caseId="case-1" canEdit />);

    await user.type(await screen.findByLabelText("Document Name"), "Salary Revision Letter");
    expect(addAdditionalDocument).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "+ Add Document" }));
    expect(addAdditionalDocument).toHaveBeenCalledWith("case-1", "Salary Revision Letter");
  });

  it("shows the exact requested name and Verify/Reject actions once uploaded", async () => {
    listAdditionalDocuments.mockResolvedValue([uploadedDoc]);
    render(<AdditionalDocumentsPanel caseId="case-1" canEdit />);

    expect(await screen.findByText("Salary Revision Letter")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verify" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Preview" })).toHaveAttribute("href", "https://s3/preview");
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("href", "https://s3/download");
  });

  it("Reject requires a reason before Confirm Reject can fire", async () => {
    listAdditionalDocuments.mockResolvedValue([uploadedDoc]);
    const user = userEvent.setup();
    render(<AdditionalDocumentsPanel caseId="case-1" canEdit />);

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    const confirmButton = screen.getByRole("button", { name: "Confirm Reject" });
    expect(confirmButton).toBeDisabled();

    await user.type(screen.getByLabelText("Reason (mandatory)"), "Document is not clear.");
    expect(confirmButton).toBeEnabled();

    await user.click(confirmButton);
    await waitFor(() => expect(rejectAdditionalDocument).toHaveBeenCalledWith("case-1", "doc-1", "Document is not clear."));
  });

  it("Verify calls the API directly (no reason required)", async () => {
    listAdditionalDocuments.mockResolvedValue([uploadedDoc]);
    const user = userEvent.setup();
    render(<AdditionalDocumentsPanel caseId="case-1" canEdit />);

    await user.click(await screen.findByRole("button", { name: "Verify" }));
    await waitFor(() => expect(verifyAdditionalDocument).toHaveBeenCalledWith("case-1", "doc-1"));
  });
});
