import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdvisorDetailsPage } from "./AdvisorDetailsPage";
import type { AdvisorDetail } from "@/features/recruitment/api";
import { ApiError } from "@/shared/api/client";

const getAdvisor = vi.fn();
const revealAdvisorPassword = vi.fn();
vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return {
    ...actual,
    getAdvisor: (...a: unknown[]) => getAdvisor(...(a as [])),
    revealAdvisorPassword: (...a: unknown[]) => revealAdvisorPassword(...(a as [])),
  };
});

let canValue = true;
vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ can: () => canValue }),
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
  beforeEach(() => {
    vi.clearAllMocks();
    canValue = true;
  });

  it("shows 'Not set' with no eye toggle when no password has ever been set", async () => {
    getAdvisor.mockResolvedValue(advisor({ has_password: false }));
    renderPage();
    await screen.findByText("Not set");
    expect(screen.queryByRole("button", { name: /password/i })).not.toBeInTheDocument();
    expect(revealAdvisorPassword).not.toHaveBeenCalled();
  });

  it("shows a masked placeholder; clicking the eye reveals the real saved password via the dedicated endpoint", async () => {
    getAdvisor.mockResolvedValue(advisor({ has_password: true }));
    revealAdvisorPassword.mockResolvedValue({ password: "Abc@123" });
    renderPage();

    expect(await screen.findByText("••••••••")).toBeInTheDocument();
    expect(revealAdvisorPassword).not.toHaveBeenCalled(); // nothing fetched until the click

    const toggle = screen.getByRole("button", { name: "Show password" });
    await userEvent.setup().click(toggle);

    await waitFor(() => expect(screen.getByText("Abc@123")).toBeInTheDocument());
    expect(revealAdvisorPassword).toHaveBeenCalledWith("a1");
    expect(screen.queryByText("••••••••")).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Hide password" }));
    expect(screen.getByText("••••••••")).toBeInTheDocument();
    expect(screen.queryByText("Abc@123")).not.toBeInTheDocument();
  });

  it("shows an error and no eye toggle disappearing when the reveal call fails", async () => {
    getAdvisor.mockResolvedValue(advisor({ has_password: true }));
    revealAdvisorPassword.mockRejectedValue(new ApiError("conflict", "This advisor has no password on file."));
    renderPage();
    await screen.findByText("••••••••");

    await userEvent.setup().click(screen.getByRole("button", { name: "Show password" }));
    await waitFor(() => expect(screen.getByText("This advisor has no password on file.")).toBeInTheDocument());
    expect(screen.queryByText(/\$2[aby]\$/)).not.toBeInTheDocument();
  });

  it("hides the eye toggle for a view-only user (no edit permission) — masked value only", async () => {
    canValue = false;
    getAdvisor.mockResolvedValue(advisor({ has_password: true }));
    renderPage();
    await screen.findByText("••••••••");
    expect(screen.queryByRole("button", { name: /password/i })).not.toBeInTheDocument();
    expect(revealAdvisorPassword).not.toHaveBeenCalled();
  });

  it("Edit Advisor's password field is unaffected — opens blank, unrelated to the masked display", async () => {
    getAdvisor.mockResolvedValue(advisor({ has_password: true }));
    renderPage();
    await screen.findByText("••••••••");

    await userEvent.setup().click(screen.getByRole("button", { name: "Edit" }));
    expect(await screen.findByLabelText("Password")).toHaveValue("");
  });
});
