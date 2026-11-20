import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { OperationsMonitor } from "./OperationsMonitor";
import { apiRequest } from "@/shared/api/client";
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ isOwner: false, can: () => true }) }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "employee-user" }) }));
vi.mock("@/features/dashboard/DashboardFiltersContext", () => ({ useDashboardFilters: () => ({ filters: { range: "this_month", productCategory: "loan" } }) }));
vi.mock("@/shared/api/client", () => ({ apiRequest: vi.fn() }));
it("preserves employee scope and links priorities to the original records", async () => {
  vi.mocked(apiRequest).mockResolvedValue({ tabs: { fresh: 2 }, cohort_leads: 2, definition: "Actual scoped lead counts",
    followups: { overdue: 1, today: 0, upcoming: 0 }, priorities: [{ id: "lead-id", name: "Ramesh", reference: "LEAD-1", due_at: "2026-11-19T00:00:00Z", route: "/leads/lead-id" }], workload: [], workload_total: 0 });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><OperationsMonitor /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole("link", { name: "Ramesh · LEAD-1" })).toHaveAttribute("href", "/leads/lead-id");
  expect(screen.getByRole("link", { name: "fresh 2" })).toHaveAttribute("href", "/leads");
  expect(screen.queryByRole("link", { name: "Auto Assignment Settings" })).not.toBeInTheDocument();
  expect(apiRequest).toHaveBeenCalledWith("/dashboard/operations?range=this_month&page=1&product_category=loan");
});
