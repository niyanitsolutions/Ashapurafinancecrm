import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AdvisorListPage } from "./AdvisorListPage";
import type { AdvisorListItem } from "@/features/recruitment/api";

const listAdvisors = vi.fn();

vi.mock("@/features/recruitment/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/recruitment/api")>("@/features/recruitment/api");
  return { ...actual, listAdvisors: (...a: unknown[]) => listAdvisors(...(a as [])) };
});

function advisor(over: Partial<AdvisorListItem> = {}): AdvisorListItem {
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
    no_of_policies: 3,
    total_premium: 150000,
    created_at: "2026-09-01T00:00:00Z",
    has_password: false,
    ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdvisorListPage />
    </MemoryRouter>,
  );
}

describe("AdvisorListPage", () => {
  it("shows Profession / Type columns and no Individual / Total Employees filters", async () => {
    listAdvisors.mockResolvedValue({ data: [advisor()], pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 } });
    renderPage();

    await screen.findByText("Ravi Kumar");
    expect(screen.getByText("₹1,50,000")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Profession" })).toBeInTheDocument();
    // Profession shown in the row (there is also a "Salaried" filter chip, hence the cell role).
    expect(screen.getByRole("cell", { name: "Salaried" })).toBeInTheDocument();

    // Profession chips are the five Fresh Leads values + All — never Individual / Total Employees.
    for (const label of ["All", "House Wife", "Retired", "Self Employed", "Salaried", "Other"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: /Individual/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Total Employees/ })).not.toBeInTheDocument();

    expect(listAdvisors).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      profession: undefined,
      channel: undefined,
      status: undefined,
    });
  });

  it("combines the Profession chip, Type dropdown and Status dropdown into one request", async () => {
    listAdvisors.mockResolvedValue({ data: [advisor()], pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 } });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Ravi Kumar");

    await user.click(screen.getByRole("button", { name: "Salaried" }));
    await user.selectOptions(screen.getByLabelText("Type"), "qr");
    await user.selectOptions(screen.getByLabelText("Status"), "active");

    await waitFor(() =>
      expect(listAdvisors).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 20,
        profession: "salaried",
        channel: "qr",
        status: "active",
      }),
    );

    // Back to "All" for each filter drops the restriction.
    await user.click(screen.getByRole("button", { name: "All" }));
    await user.selectOptions(screen.getByLabelText("Type"), "");
    await user.selectOptions(screen.getByLabelText("Status"), "");
    await waitFor(() =>
      expect(listAdvisors).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 20,
        profession: undefined,
        channel: undefined,
        status: undefined,
      }),
    );
  });

  it("renders '—' for an advisor with no profession", async () => {
    listAdvisors.mockResolvedValue({
      data: [advisor({ profession: null, other_profession: null })],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    renderPage();
    await screen.findByText("Ravi Kumar");
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
