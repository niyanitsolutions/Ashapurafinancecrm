import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecruitmentLayout } from "./RecruitmentLayout";

const getRecruitmentCounts = vi.fn();

vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return { ...actual, getRecruitmentCounts: (...args: unknown[]) => getRecruitmentCounts(...(args as [])) };
});

vi.mock("@/components/layout/useNavKeys", () => ({
  useNavKeys: () => new Set(["insurance_cases"]),
}));
vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ can: () => true, loading: false }),
}));

beforeEach(() => getRecruitmentCounts.mockReset());

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/insurance-management/recruitment" element={<RecruitmentLayout />}>
          <Route path="fresh" element={<div>recruitment list</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("RecruitmentLayout", () => {
  it("keeps every stage tab visible with employee-scoped zero counts", async () => {
    getRecruitmentCounts.mockResolvedValue({
      fresh: 0, bop: 0, doc_collection: 0, exam_fee_status: 0,
      examination: 0, re_examination: 0, agency_code: 0, rejected: 0,
    });
    renderAt("/insurance-management/recruitment/fresh");

    await waitFor(() => expect(screen.getByRole("link", { name: "Fresh Leads 0" })).toBeInTheDocument());
    for (const label of ["BOP 0", "Doc Collection 0", "Exam Fee Status 0", "Examination 0", "Re-Examination 0", "Agency Code 0", "Rejected 0"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });
});
