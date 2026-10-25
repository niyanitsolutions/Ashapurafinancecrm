import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DailyOperationsPage } from "./DailyOperationsPage";

const mocks = vi.hoisted(() => ({
  owner: false, list: vi.fn(), lookup: vi.fn(), save: vi.fn(), detail: vi.fn(), remove: vi.fn(), request: vi.fn(),
}));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "synthetic-user", role: mocks.owner ? "owner" : "employee" }) }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ can: () => true, isOwner: mocks.owner, loading: false }) }));
vi.mock("@/shared/api/client", async original => ({ ...await original<typeof import("@/shared/api/client")>(), apiRequest: mocks.request }));
vi.mock("./api", async original => ({ ...await original<typeof import("./api")>(), listRecords: mocks.list, getLookups: mocks.lookup, getRecord: mocks.detail, saveRecord: mocks.save, deleteRecord: mocks.remove }));

function mount(area: "follow-ups" | "progress" | "issues" | "sessions") {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><DailyOperationsPage area={area} /></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks(); mocks.owner = false;
  mocks.list.mockResolvedValue({ items: [], total: 0 });
  mocks.lookup.mockResolvedValue({ self_id: "synthetic-user", employees: [{ id: "synthetic-user", name: "Synthetic Employee" }], leads: [], cases: [] });
  mocks.save.mockResolvedValue({ id: "synthetic-row", version: 1 }); mocks.remove.mockResolvedValue({ deleted: true });
});

describe("simple daily entry", () => {
  it("shows only quick filters initially and replaces the employee ID filter with a name combobox", async () => {
    mount("follow-ups");
    expect(screen.getByLabelText("Search")).toBeVisible();
    expect(screen.getByLabelText("Employee name")).toHaveAttribute("list");
    expect(screen.queryByLabelText(/Employee CRM ID/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("From date")).not.toBeVisible();
    expect(await screen.findByRole("button", { name: /Add record/ })).toBeVisible();
    fireEvent.click(screen.getByText("More filters"));
    expect(screen.getByLabelText("From date")).toBeVisible();
  });

  it("adds a manual follow-up with a typed employee name and no CRM IDs", async () => {
    mount("follow-ups"); fireEvent.click(screen.getByRole("button", { name: /Add record/ }));
    const dialog = within(screen.getByRole("dialog"));
    await waitFor(() => expect(dialog.getByLabelText("Employee name")).toHaveValue("Synthetic Employee"));
    fireEvent.change(dialog.getByLabelText("Employee name"), { target: { value: "Synthetic manual label" } });
    for (const [label, value] of [["Customer name", "Synthetic Customer"], ["Customer number", "9000000000"], ["Bank / NBFC", "Synthetic Bank"], ["Today's case status / remarks", "Call tomorrow"]]) {
      fireEvent.change(dialog.getByLabelText(label), { target: { value } });
    }
    expect(dialog.queryByLabelText(/CRM ID|LEAD ID|Employee ID/)).not.toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "Save record" }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith("follow-ups", expect.objectContaining({ lead_id: null, customer_name: "Synthetic Customer", employee_name: "Synthetic manual label", assigned_to: "synthetic-user", next_action: "Call tomorrow" }), undefined));
  });

  it("provides Add record and individual Edit for loan progress", async () => {
    const row = { id: "synthetic-progress", version: 1, source: "manual", date: "2026-10-25", customer_name: "Synthetic Customer", customer_number: "9000000000", bank: "Synthetic Bank", status: "Application login", employee_name: "Synthetic Employee" };
    mocks.list.mockResolvedValue({ items: [row], total: 1 }); mocks.detail.mockResolvedValue(row);
    mount("progress");
    expect(screen.getByRole("button", { name: /Add record/ })).toBeVisible();
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = within(await screen.findByRole("dialog"));
    fireEvent.change(dialog.getByLabelText("Today's case stage"), { target: { value: "Waiting for documents" } });
    fireEvent.click(dialog.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith("progress", expect.objectContaining({ status: "Waiting for documents", version: 1 }), row.id));
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("allows only the Owner to see Delete and requires confirmation before removal", async () => {
    mocks.owner = true;
    const row = { id: "synthetic-row", version: 1, date: "2026-10-25", inquiry: "Synthetic issue", status: "OPEN" };
    mocks.list.mockResolvedValue({ items: [row], total: 1 });
    mount("issues");
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(mocks.remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Delete record" }));
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith("issues", row));
  });

  it("keeps automatic session editing protected and lets an employee request a correction", async () => {
    mocks.list.mockResolvedValue({ items: [{ id: "synthetic-family", date: "2026-10-25", login_at: "2026-10-25T04:00:00Z", logout_at: null }], total: 1 });
    mocks.request.mockResolvedValue({ id: "synthetic-issue" });
    mount("sessions");
    fireEvent.click(await screen.findByRole("button", { name: "Request correction" }));
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("What needs correcting?"), { target: { value: "Synthetic missing logout request" } });
    fireEvent.click(screen.getByRole("button", { name: "Send request" }));
    await waitFor(() => expect(mocks.request).toHaveBeenCalledWith("/daily-operations/issues", expect.objectContaining({ method: "POST" })));
  });
});
