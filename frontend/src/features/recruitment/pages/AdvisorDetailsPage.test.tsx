import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdvisorDetailsPage } from "./AdvisorDetailsPage";
import type { AdvisorDetail } from "@/features/recruitment/api";

const getAdvisor = vi.fn();
vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return { ...actual, getAdvisor: (...a: unknown[]) => getAdvisor(...(a as [])) };
});

vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ can: () => true }),
}));

function advisor(over: Partial<AdvisorDetail> = {}): AdvisorDetail {
  return {
    id: "a1",
    advisor_code: "AFS-ADV-000001",
    recruitment_lead_id: "r1",
    full_name: "Ravi Kumar",
    mobile: "9876543210",
    email: null,
    channel: "qr",
    agency_code: null,
    agent_code: null,
    profession: "salaried",
    other_profession: null,
    status: "active",
    is_employee: false,
    no_of_policies: 0,
    total_premium: 0,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    recruitment: null,
    businesses: [],
    has_password: false,
    ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/insurance-management/advisors/a1"]}>
      <Routes>
        <Route path="/insurance-management/advisors/:advisorId" element={<AdvisorDetailsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AdvisorDetailsPage — password display", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows 'Not set' with no eye toggle when no password has ever been set", async () => {
    getAdvisor.mockResolvedValue(advisor({ has_password: false }));
    renderPage();
    await screen.findByText("Not set");
    expect(screen.queryByRole("button", { name: /password state/i })).not.toBeInTheDocument();
  });

  it("shows a masked placeholder with an eye toggle when a password is set — never the real value", async () => {
    getAdvisor.mockResolvedValue(advisor({ has_password: true }));
    renderPage();

    expect(await screen.findByText("••••••••")).toBeInTheDocument();
    // The raw response body never contains a secret; confirm nothing resembling one renders.
    expect(screen.queryByText(/\$2[aby]\$/)).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Show password state" });
    await userEvent.setup().click(toggle);
    expect(screen.getByText("Password set")).toBeInTheDocument();
    expect(screen.queryByText("••••••••")).not.toBeInTheDocument();
    // Still never a real credential — just the fixed, safe label.
    expect(screen.getByText("Password set")).not.toHaveTextContent(/\$2[aby]\$/);

    await userEvent.setup().click(screen.getByRole("button", { name: "Hide password state" }));
    expect(screen.getByText("••••••••")).toBeInTheDocument();
  });

  it("Edit Advisor's password field is unaffected — opens blank, unrelated to the masked display", async () => {
    getAdvisor.mockResolvedValue(advisor({ has_password: true }));
    renderPage();
    await screen.findByText("••••••••");

    await userEvent.setup().click(screen.getByRole("button", { name: "Edit" }));
    expect(await screen.findByLabelText("Password")).toHaveValue("");
  });
});
