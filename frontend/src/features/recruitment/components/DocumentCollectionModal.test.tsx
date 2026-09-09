import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DocumentCollectionModal } from "./DocumentCollectionModal";
import type { RecruitmentDocuments, RecruitmentLeadDetail } from "@/features/recruitment/api";

vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return { ...actual, saveRecruitmentDocuments: vi.fn(), uploadRecruitmentFile: vi.fn() };
});

const baseLead: RecruitmentLeadDetail = {
  id: "rec-1",
  recruitment_code: "AFS-RCT-000001",
  full_name: "Ravi Kumar",
  mobile: "9876543210",
  email: null,
  gender: "male",
  age: 32,
  source_id: "s1",
  source_name: "Referral",
  profession: "salaried",
  other_profession: null,
  remarks: null,
  stage: "doc_collection",
  assigned_to: null,
  assigned_to_name: null,
  latest_examination_result: null,
  documents_ready: false,
  advisor_id: null,
  rejected_reason: null,
  rejected_at: null,
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
  assigned_by: null,
  assigned_at: null,
  exam_fee_paid: false,
  exam_fee_paid_at: null,
  exam_fee_reference: null,
  documents: null,
  examinations: [],
};

const file = (name: string) => ({ file_name: name, uploaded_at: "2026-09-01T10:00:00Z", download_url: null });

const fullDocs: RecruitmentDocuments = {
  pan: file("pan.jpg"),
  aadhaar: file("aadhaar.jpg"),
  bank_proof: file("passbook.jpg"),
  bank_proof_type: "passbook",
  cheque_name_confirmed: false,
  qualification: file("degree.pdf"),
  photo: file("photo.jpg"),
  email: null,
  mobile: "9876543210",
  alternate_number: null,
  nominee: null,
  signature: { method: "type", value: "Ravi Kumar", file_name: null },
};

describe("DocumentCollectionModal", () => {
  it("disables Save and explains why when required documents are missing", () => {
    render(<DocumentCollectionModal lead={baseLead} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
    expect(screen.getByText(/Please upload all required documents before saving/i)).toBeInTheDocument();
  });

  it("enables Save once every required document is already stored", () => {
    render(
      <DocumentCollectionModal lead={{ ...baseLead, documents: fullDocs }} onClose={vi.fn()} onSaved={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /^save$/i })).toBeEnabled();
    expect(screen.queryByText(/Please upload all required documents before saving/i)).not.toBeInTheDocument();
  });
});
