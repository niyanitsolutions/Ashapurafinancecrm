import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/layout/Sidebar";
import { DailyUpdateLayout } from "./DailyUpdateLayout";
import { DailyOperationsPage } from "./DailyOperationsPage";
import { TransferCentre } from "./TransferCentre";
import { areas, type Area } from "./api";

const mocks = vi.hoisted(() => ({
  owner: true, loading: false,
  keys: new Set(["dashboard", "leads", "loan_cases", "insurance_cases", "daily_follow-ups", "daily_progress", "daily_sessions", "daily_issues"]),
  can: vi.fn((_resource: string, _action: string) => true),
  list: vi.fn(), getLookups: vi.fn(),
}));
vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ can: mocks.can, isOwner: mocks.owner, loading: mocks.loading }),
}));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ role: mocks.owner ? "owner" : "employee", userId: "synthetic-user" }) }));
vi.mock("@/features/auth/useProfile", () => ({ useProfile: () => ({ data: { name: "Synthetic User", mobile: "" } }) }));
vi.mock("@/features/owner/useOwnOwnerAccount", () => ({ useOwnOwnerAccount: () => ({ data: null }) }));
vi.mock("@/components/layout/useNavKeys", () => ({ useNavKeys: () => mocks.keys }));
vi.mock("./api", async importOriginal => ({ ...await importOriginal<typeof import("./api")>(), listRecords: mocks.list, getLookups: mocks.getLookups }));

function mount(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Sidebar isOpen isCollapsed={false} onClose={vi.fn()} onToggleCollapsed={vi.fn()} />
        <header>Existing greeting</header>
        <Routes>
          <Route path="/" element={<p>Existing dashboard</p>} />
          <Route path="/daily-operations" element={<DailyUpdateLayout />}>
            {Object.keys(areas).map(area => <Route key={area} path={area} element={<DailyOperationsPage key={area} area={area as Area} />} />)}
            <Route path="transfers" element={<TransferCentre />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks(); mocks.owner = true; mocks.loading = false;
  mocks.can.mockImplementation(() => true);
  mocks.keys = new Set(["dashboard", "leads", "loan_cases", "insurance_cases", "daily_follow-ups", "daily_progress", "daily_sessions", "daily_issues"]);
  mocks.list.mockResolvedValue({ items: [], total: 0 }); mocks.getLookups.mockResolvedValue({ self_id: "synthetic-user", employees: [], leads: [], cases: [] });
});

describe("Daily Update navigation", () => {
  it("opens the module from a single sidebar entry and keeps all five tabs outside the sidebar", async () => {
    mount("/");
    const sidebar = document.querySelector("aside")!;
    expect(within(sidebar).getAllByRole("link", { name: "Daily Update" })).toHaveLength(1);
    expect(within(sidebar).queryByRole("link", { name: "Daily Follow-up Data" })).not.toBeInTheDocument();
    fireEvent.click(within(sidebar).getByRole("link", { name: "Daily Update" }));
    const bar = await screen.findByRole("navigation", { name: "Daily Update tabs" });
    expect(within(bar).getAllByRole("link")).toHaveLength(5);
    expect(sidebar.contains(bar)).toBe(false);
    expect(bar).toHaveClass("overflow-x-auto");
    expect(screen.getByText("Existing greeting")).toBeInTheDocument();
    expect(within(sidebar).getByRole("link", { name: "Daily Update" })).toHaveClass("bg-primary");
    for (const name of ["Dashboard", "Leads", "Loan Management", "Insurance Management"]) {
      expect(within(sidebar).getByRole("link", { name })).toBeInTheDocument();
    }
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith("follow-ups", expect.any(String)));
    expect(new Set(mocks.list.mock.calls.map(call => call[0]))).toEqual(new Set(["follow-ups"]));
  });

  it.each([
    ["follow-ups", "Daily Follow-up Data"], ["progress", "Loan Progress Tracking"],
    ["sessions", "Employee Login & Logout"], ["issues", "Inquiry or Issue"],
    ["transfers", "Import & Export Centre"],
  ])("direct URL /%s renders its existing functional page and active tab", async (path, label) => {
    mount(`/daily-operations/${path}`);
    const bar = screen.getByRole("navigation", { name: "Daily Update tabs" });
    const active = within(bar).getByRole("link", { name: label });
    expect(active).toHaveAttribute("aria-current", "page");
    expect(active).toHaveClass("border-primary", "text-primary");
    expect(screen.getByRole("heading", { name: label })).toBeInTheDocument();
    if (path === "transfers") expect(screen.getByLabelText("Upload CSV or XLSX")).toBeInTheDocument();
    else await waitFor(() => expect(mocks.list).toHaveBeenCalledWith(path, expect.any(String)));
  });

  it("switches functional pages with keyboard navigation without fetching inactive work areas", async () => {
    const user = userEvent.setup(); mount("/daily-operations/follow-ups");
    await screen.findByText(/No records match these filters/); mocks.list.mockClear();
    const bar = screen.getByRole("navigation", { name: "Daily Update tabs" });
    const target = within(bar).getByRole("link", { name: "Inquiry or Issue" });
    target.focus(); await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { name: "Inquiry or Issue" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Daily Update tabs" })).toBe(bar);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith("issues", expect.any(String)));
    expect(new Set(mocks.list.mock.calls.map(call => call[0]))).toEqual(new Set(["issues"]));
  });

  it("defaults an employee to their first permitted tab and hides unauthorized transfer controls", async () => {
    mocks.owner = false; mocks.keys = new Set(["daily_issues"]);
    mocks.can.mockImplementation((resource, action) => resource === "daily_operations:issues" && action === "view");
    mount("/daily-operations");
    expect(await screen.findByRole("heading", { name: "Inquiry or Issue" })).toBeInTheDocument();
    const bar = screen.getByRole("navigation", { name: "Daily Update tabs" });
    expect(within(bar).getAllByRole("link")).toHaveLength(1);
    expect(screen.queryByRole("link", { name: "Import & Export Centre" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add record/ })).not.toBeInTheDocument();
  });

  it.each(["follow-ups", "progress", "sessions", "transfers"])("rejects an employee's unauthorized direct /%s route before mounting its page", path => {
    mocks.owner = false;
    mocks.can.mockImplementation((resource, action) => resource === "daily_operations:issues" && action === "view");
    mount(`/daily-operations/${path}`);
    expect(screen.getByRole("alert")).toHaveTextContent("do not have permission");
    expect(mocks.list).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Upload CSV or XLSX")).not.toBeInTheDocument();
  });

  it("waits for permissions without fetching data", () => {
    mocks.loading = true; mount("/daily-operations");
    expect(screen.getByRole("status")).toHaveTextContent("Loading Daily Update permissions");
    expect(mocks.list).not.toHaveBeenCalled();
  });

  it("preserves query filters and pagination across direct navigation and a fresh mount", async () => {
    const path = "/daily-operations/issues?search=Internal&status=OPEN&date_from=2026-10-01&page=2";
    const first = mount(path);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith("issues", expect.stringContaining("page=2")));
    expect(screen.getByLabelText("Search")).toHaveValue("Internal");
    expect(screen.getByLabelText("From date")).toHaveValue("2026-10-01");
    first.unmount(); mocks.list.mockClear(); mount(path);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith("issues", expect.stringContaining("status=OPEN")));
    expect(screen.getByLabelText("Search")).toHaveValue("Internal");
    expect(within(screen.getByRole("navigation", { name: "Daily Update tabs" })).getByRole("link", { name: "Inquiry or Issue" })).toHaveAttribute("aria-current", "page");
  });

  it("offers only authorized transfer destinations and defaults to the employee's permitted area", () => {
    mocks.owner = false;
    mocks.can.mockImplementation((resource, action) => resource === "daily_operations:issues" && ["view", "export"].includes(action));
    mount("/daily-operations/transfers");
    const destination = screen.getByLabelText("Destination work area");
    expect(destination).toHaveValue("issues");
    expect(within(destination).getAllByRole("option")).toHaveLength(1);
    expect(screen.getByRole("link", { name: /Open Inquiry or Issue to filter and export/ })).toHaveAttribute("href", "/daily-operations/issues");
    expect(screen.queryByLabelText("Upload CSV or XLSX")).not.toBeInTheDocument();
  });
});
