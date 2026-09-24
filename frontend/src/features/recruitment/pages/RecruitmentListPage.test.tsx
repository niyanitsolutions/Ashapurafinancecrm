import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecruitmentListPage } from "./RecruitmentListPage";

const mocks = vi.hoisted(() => ({
  canCreate: false,
  listRecruitmentLeads: vi.fn(),
  refreshCounts: vi.fn(),
}));

vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({
    can: (resource: string, action: string) =>
      resource === "insurance_management:recruitment.fresh" &&
      (action === "view" || (action === "create" && mocks.canCreate)),
    loading: false,
  }),
}));
vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return { ...actual, listRecruitmentLeads: mocks.listRecruitmentLeads };
});
vi.mock("@/features/bin/useListDelete", () => ({
  useListDelete: () => ({ enabled: false, dialog: null, error: null, requestDelete: vi.fn() }),
}));
vi.mock("@/features/recruitment/components/RecruitmentLeadModal", () => ({
  RecruitmentLeadModal: ({ onSaved }: { onSaved: () => void }) => (
    <div role="dialog" aria-label="Add Recruitment Lead">
      Existing recruitment form
      <button onClick={onSaved}>Complete save</button>
    </div>
  ),
}));

function TestLayout() {
  return <Outlet context={{ refreshCounts: mocks.refreshCounts }} />;
}

function renderFreshList() {
  return render(
    <MemoryRouter initialEntries={["/insurance-management/recruitment/fresh"]}>
      <Routes>
        <Route path="/insurance-management/recruitment" element={<TestLayout />}>
          <Route path="fresh" element={<RecruitmentListPage variant="fresh" />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("RecruitmentListPage add access", () => {
  beforeEach(() => {
    mocks.canCreate = false;
    mocks.listRecruitmentLeads.mockReset().mockResolvedValue({ data: [], pagination: { total: 0 } });
    mocks.refreshCounts.mockReset();
  });

  it("shows Add Lead only with the existing recruitment create permission", async () => {
    const denied = renderFreshList();
    await screen.findByText(/No fresh recruitment leads/i);
    expect(screen.queryByRole("button", { name: /add lead/i })).not.toBeInTheDocument();
    denied.unmount();

    mocks.canCreate = true;
    renderFreshList();
    expect(await screen.findByRole("button", { name: /add lead/i })).toBeInTheDocument();
  });

  it("opens the existing modal and refreshes the list and counts after save", async () => {
    mocks.canCreate = true;
    const user = userEvent.setup();
    renderFreshList();

    await user.click(await screen.findByRole("button", { name: /add lead/i }));
    expect(screen.getByRole("dialog", { name: /add recruitment lead/i })).toHaveTextContent("Existing recruitment form");
    await user.click(screen.getByRole("button", { name: /complete save/i }));

    await waitFor(() => expect(mocks.listRecruitmentLeads).toHaveBeenCalledTimes(2));
    expect(mocks.refreshCounts).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Recruitment lead saved.")).toBeInTheDocument();
  });
});
