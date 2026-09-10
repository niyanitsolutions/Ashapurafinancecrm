import { render, screen } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AgencyCodeListPage } from "./AgencyCodeListPage";
import type { AdvisorListItem } from "@/features/recruitment/api";

const listAdvisors = vi.fn();
vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return { ...actual, listAdvisors: (...a: unknown[]) => listAdvisors(...(a as [])) };
});

vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ can: () => true }),
}));

const advisor: AdvisorListItem = {
  id: "a1",
  advisor_code: "AFS-ADV-000001",
  recruitment_lead_id: "r1",
  full_name: "Ravi Kumar",
  mobile: "9876543210",
  email: null,
  channel: "qr",
  agency_code: "AG-1001",
  agent_code: "AGT-9",
  profession: "salaried",
  other_profession: null,
  status: "active",
  is_employee: false,
  no_of_policies: 0,
  total_premium: 0,
  created_at: "2026-09-01T00:00:00Z",
  has_password: false,
};

describe("AgencyCodeListPage", () => {
  it("shows the agency code, agent code and QR / Non QR type columns", async () => {
    listAdvisors.mockResolvedValue({ data: [advisor], pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 } });
    render(
      <MemoryRouter>
        <Routes>
          <Route element={<Outlet context={{ refreshCounts: vi.fn() }} />}>
            <Route path="/" element={<AgencyCodeListPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("Ravi Kumar");
    expect(screen.getByText("AG-1001")).toBeInTheDocument();
    expect(screen.getByText("AGT-9")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Type" })).toBeInTheDocument();
    expect(screen.getByText("QR")).toBeInTheDocument();
  });
});
