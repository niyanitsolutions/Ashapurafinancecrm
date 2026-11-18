import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CustomerDocumentChecklist } from "./CustomerDocumentChecklist";
import type { ApplicationDocument } from "../api";

vi.mock("./DocumentChecklist", () => ({ DocumentChecklist: () => <div>Existing shared checklist</div> }));

describe("Customer camera upload eligibility", () => {
  it.each(["pending", "verified", "rejected"] as const)("respects existing single-document replacement rules for %s", status => {
    const current = { id: "fixture", document_type_id: "pan", is_current: true, document_status: "uploaded", verification_status: status } as ApplicationDocument;
    render(<CustomerDocumentChecklist applicationId="application" requiredDocuments={[{ document_type_id: "pan", document_type_name: "PAN", section: null, note: null, allowed_types: ["image/jpeg"] }]}
      uploadedDocuments={[current]} onUpload={vi.fn()} uploadingFor={null} />);
    const camera = screen.queryByLabelText("Camera upload PAN");
    if (status === "rejected") expect(camera).toHaveAttribute("capture", "environment");
    else expect(camera).not.toBeInTheDocument();
  });
});
