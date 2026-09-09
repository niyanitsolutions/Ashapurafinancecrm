import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ExamFeeModal } from "./ExamFeeModal";
import type { RecruitmentLeadDetail } from "@/features/recruitment/api";

const recordRecruitmentExamFee = vi.fn(() => Promise.resolve({} as RecruitmentLeadDetail));
vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return { ...actual, recordRecruitmentExamFee: (...a: unknown[]) => recordRecruitmentExamFee(...(a as [])) };
});

const lead = {
  id: "rec-1",
  recruitment_code: "AFS-RCT-000001",
  full_name: "Ravi Kumar",
  exam_fee_reference: null,
} as unknown as RecruitmentLeadDetail;

describe("ExamFeeModal", () => {
  it("records the exam fee with an optional reference", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    render(<ExamFeeModal lead={lead} onClose={vi.fn()} onSaved={onSaved} />);

    await user.type(screen.getByLabelText(/Payment reference/i), "UTR-77");
    await user.click(screen.getByRole("button", { name: /Mark Fee Paid/i }));

    await waitFor(() => expect(recordRecruitmentExamFee).toHaveBeenCalledWith("rec-1", { reference: "UTR-77" }));
    expect(onSaved).toHaveBeenCalled();
  });
});
