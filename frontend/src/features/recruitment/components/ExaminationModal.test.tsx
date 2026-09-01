import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ExaminationModal } from "./ExaminationModal";
import type { RecruitmentLeadDetail } from "@/features/recruitment/api";

const recordRecruitmentExamination = vi.fn(() => Promise.resolve({} as RecruitmentLeadDetail));
vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return {
    ...actual,
    recordRecruitmentExamination: (...args: unknown[]) => recordRecruitmentExamination(...(args as [])),
  };
});

const lead: RecruitmentLeadDetail = {
  id: "rec-1",
  recruitment_code: "AFS-RCT-000001",
  full_name: "Ravi Kumar",
  mobile: "9876543210",
  email: null,
  gender: "male",
  age: 32,
  source_id: "src-1",
  source_name: "Referral",
  profession: "salaried",
  other_profession: null,
  remarks: null,
  stage: "doc_collection_examination",
  assigned_to: null,
  assigned_to_name: null,
  latest_examination_result: null,
  documents_ready: true,
  advisor_id: null,
  rejected_reason: null,
  rejected_at: null,
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
  assigned_by: null,
  assigned_at: null,
  documents: null,
  examinations: [],
};

describe("ExaminationModal", () => {
  it("keeps Submit disabled for FAIL until remarks are entered", async () => {
    const user = userEvent.setup();
    render(<ExaminationModal lead={lead} onClose={vi.fn()} onSaved={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "FAIL" }));
    const submit = screen.getByRole("button", { name: /^submit$/i });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText("Remarks"), "did not clear");
    expect(submit).toBeEnabled();

    await user.click(submit);
    await waitFor(() =>
      expect(recordRecruitmentExamination).toHaveBeenCalledWith("rec-1", { result: "fail", remarks: "did not clear" }),
    );
  });

  it("allows a PASS submission with no remarks", async () => {
    const user = userEvent.setup();
    render(<ExaminationModal lead={lead} onClose={vi.fn()} onSaved={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "PASS" }));
    expect(screen.queryByLabelText("Remarks")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^submit$/i }));
    await waitFor(() =>
      expect(recordRecruitmentExamination).toHaveBeenCalledWith("rec-1", { result: "pass", remarks: undefined }),
    );
  });
});
