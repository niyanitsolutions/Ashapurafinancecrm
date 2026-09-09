import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AdvisorListPage } from "./AdvisorListPage";
import type { AdvisorCounts, AdvisorListItem } from "@/features/recruitment/api";

const listAdvisors = vi.fn();
const getAdvisorCounts = vi.fn();

vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return {
    ...actual,
    listAdvisors: (...a: unknown[]) => listAdvisors(...(a as [])),
    getAdvisorCounts: (...a: unknown[]) => getAdvisorCounts(...(a as [])),
  };
});

const advisor: AdvisorListItem = {
  id: "a1",
  advisor_code: "AFS-ADV-000001",
  recruitment_lead_id: "r1",
  full_name: "Ravi Kumar",
  mobile: "9876543210",
  email: null,
  channel: "non_qr",
  agency_code: null,
  agent_code: null,
  status: "active",
  is_employee: false,
  no_of_policies: 3,
  total_premium: 150000,
  created_at: "2026-09-01T00:00:00Z",
};

const counts: AdvisorCounts = {
  qr: 0,
  non_qr: 2,
  total: 2,
  individual: 1,
  total_employees: 1,
  active: 2,
  inactive: 0,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/insurance-management/advisors/non-qr"]}>
      <Routes>
        <Route element={<Outlet context={{ refreshCounts: vi.fn() }} />}>
          <Route path="/insurance-management/advisors/non-qr" element={<AdvisorListPage channel="non_qr" />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("AdvisorListPage", () => {
  it("renders the premium as an INR amount and filters by the chosen filter chip", async () => {
    listAdvisors.mockResolvedValue({ data: [advisor], pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 } });
    getAdvisorCounts.mockResolvedValue(counts);

    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Ravi Kumar");
    expect(screen.getByText("₹1,50,000")).toBeInTheDocument();
    expect(listAdvisors).toHaveBeenLastCalledWith({ channel: "non_qr", page: 1, page_size: 20, filter_key: undefined });

    await user.click(screen.getByRole("button", { name: /Total Employees/i }));
    await waitFor(() =>
      expect(listAdvisors).toHaveBeenLastCalledWith({
        channel: "non_qr",
        page: 1,
        page_size: 20,
        filter_key: "total_employees",
      }),
    );
  });
});
