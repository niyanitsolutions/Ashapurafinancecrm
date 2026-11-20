import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AutoAssignmentPage } from "./AutoAssignmentPage";
import { apiRequest } from "@/shared/api/client";

let owner = true;
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ isOwner: owner }) }));
vi.mock("@/shared/api/client", () => ({ apiRequest: vi.fn() }));
const api = vi.mocked(apiRequest);
function mount() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><AutoAssignmentPage /></MemoryRouter></QueryClientProvider>); }
beforeEach(() => {
  owner = true; api.mockReset();
  api.mockImplementation(async (path) => path.endsWith("auto-assignment") ? {
    enabled: false, employee_ids: [], version: 4, sequence: 0,
    employees: [{ id: "one", name: "Rahul", active: true }, { id: "two", name: "Priya", active: true }],
  } : { items: [], total: 0 });
});
describe("Owner auto assignment controls", () => {
  it("saves the selected employee order with the loaded settings version", async () => {
    mount(); const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "Priya" }));
    await user.click(screen.getByRole("checkbox", { name: "Rahul" }));
    await user.click(screen.getByRole("checkbox", { name: "Enable automatic assignment" }));
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("/leads/auto-assignment", { method: "PUT", body: JSON.stringify({ enabled: true, employee_ids: ["two", "one"], version: 4 }) }));
    expect(await screen.findByText("Assignment settings saved.")).toBeVisible();
  });
  it("does not load company assignment controls for an employee", () => {
    owner = false; mount();
    expect(screen.getByText("Only an Owner can manage automatic assignment.")).toBeVisible();
    expect(api).not.toHaveBeenCalled();
  });
});
