import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DocumentChecklist, documentCompletionSummary } from "./DocumentChecklist";
import type { ApplicationDocument, RequiredDocument } from "@/features/customer/api";

const pan: RequiredDocument = { document_type_id: "pan", document_type_name: "PAN Card", section: null, note: null, supports_password: true, front_back_optional: true };
const bank: RequiredDocument[] = ["Bank Statement", "Cancelled Cheque"].map((name, index) => ({ ...pan, document_type_id: String(index), document_type_name: name, required: false, requirement_group: "bank" }));
const uploaded = (type: string, side?: "front" | "back"): ApplicationDocument => ({
  id: type + side, application_id: "app", document_type_id: type, document_type_name: type,
  file_name: "file.pdf", content_type: "application/pdf", download_url: "/preview", attachment_url: "/download",
  created_at: "2026-09-01T00:00:00Z", verification_status: "pending", verified_by_name: null,
  verified_at: null, rejection_reason: null, document_status: "uploaded", file_size_bytes: 10,
  is_current: true, doc_version: 1, replaces_document_id: null, side,
});

describe("Insurance documents", () => {
  it("collects both sides before upload and uses one password for the pair", async () => {
    const onUpload = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    const { container } = render(<DocumentChecklist requiredDocuments={[pan]} uploadedDocuments={[]} onUpload={onUpload} uploadingFor={null} />);
    await user.type(screen.getByLabelText("Document Password (Optional)"), "paired-secret");
    await user.click(screen.getByRole("checkbox", { name: "Document has Front & Back" }));
    const uploadButton = screen.getByRole("button", { name: "Upload Front & Back" });
    expect(uploadButton).toBeDisabled();
    const inputs = container.querySelectorAll<HTMLInputElement>('input[type="file"]');
    const front = new File(["front"], "front.pdf", { type: "application/pdf" });
    const back = new File(["back"], "back.pdf", { type: "application/pdf" });
    await user.upload(inputs[0], front);
    expect(uploadButton).toBeDisabled();
    expect(onUpload).not.toHaveBeenCalled();
    await user.upload(inputs[1], back);
    await user.click(uploadButton);
    await waitFor(() => expect(onUpload).toHaveBeenCalledTimes(2));
    expect(onUpload).toHaveBeenNthCalledWith(1, "pan", front, "paired-secret", "front");
    expect(onUpload).toHaveBeenNthCalledWith(2, "pan", back, "paired-secret", "back");
    expect(screen.getByLabelText("Document Password (Optional)")).toHaveValue("");
  });

  it("shows one bank requirement and keeps both upload options", () => {
    render(<DocumentChecklist requiredDocuments={bank} uploadedDocuments={[]} onUpload={vi.fn()} uploadingFor={null} />);
    expect(screen.getByRole("heading", { name: /Bank Statement or Cancelled Cheque/ })).toBeInTheDocument();
    expect(screen.getByText("Bank Statement")).toBeInTheDocument();
    expect(screen.getByText("Cancelled Cheque")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Document Password (Optional)")).toHaveLength(2);
  });

  it.each([[[], 0], [["0"], 1], [["1"], 1], [["0", "1"], 1]] as [string[], number][])("counts bank alternatives %j", (types, completed) => {
    expect(documentCompletionSummary(bank, types.map((type) => uploaded(type)))).toMatchObject({ total: 1, completed });
  });

  it("does not count a single side as complete, and accepts legacy single files", () => {
    expect(documentCompletionSummary([pan], [uploaded("pan", "front")]).completed).toBe(0);
    expect(documentCompletionSummary([pan], [uploaded("pan", "front"), uploaded("pan", "back")]).completed).toBe(1);
    expect(documentCompletionSummary([pan], [uploaded("pan")]).completed).toBe(1);
  });
});
