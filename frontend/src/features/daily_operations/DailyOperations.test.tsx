import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DailyOperationsPage } from "./DailyOperationsPage";
import { RecordForm } from "./RecordForm";
import { TransferCentre } from "./TransferCentre";
import { NAV_SECTIONS } from "@/components/layout/navConfig";

const mocks = vi.hoisted(() => ({ list: vi.fn(), save: vi.fn(), getLookups: vi.fn(), request: vi.fn(), can: vi.fn(() => true) }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "isolated-test-user" }) }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ can: mocks.can, isOwner: true, loading: false }) }));
vi.mock("@/shared/api/client", async importOriginal => ({ ...await importOriginal<typeof import("@/shared/api/client")>(), apiRequest: mocks.request }));
vi.mock("./api", async importOriginal => ({ ...await importOriginal<typeof import("./api")>(), listRecords: mocks.list, saveRecord: mocks.save, getLookups: mocks.getLookups }));

function mount(component: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{component}</MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { vi.clearAllMocks(); mocks.can.mockReturnValue(true); mocks.list.mockResolvedValue({ items: [], total: 0 }); mocks.getLookups.mockResolvedValue({ self_id: "synthetic-user", employees: [], leads: [], cases: [] }); });

describe("daily operations", () => {
  it.each([
    ["FOLLOW UP PENDING", "!bg-red-50"], ["NEXT FOLLOW UP", "!bg-blue-50"],
    ["DISBURSE", "!bg-green-50"], ["REJECTED WITH REASON", "!bg-yellow-50"],
  ])("colors the whole %s row and retains its label", async (status, color) => {
    mocks.list.mockResolvedValue({ items: [{ id: "row", status, customer_name: "Synthetic Customer" }], total: 1 });
    mount(<DailyOperationsPage area="follow-ups" />);
    const row = (await screen.findByText("Synthetic Customer")).closest("tr")!;
    expect(row).toHaveClass(color);
    expect(within(row).getByText(status)).toBeInTheDocument();
  });
  it("opens separate session history from a daily summary", async () => {
    mocks.list.mockResolvedValue({ items: [{ id: "user:2026-10-26", recorded_seconds: 9000, status: "active", sessions: [{ id: "family1", recorded_seconds: 3600, status: "logged_out", end_reason: "manual_logout" }] }], total: 1 });
    mount(<DailyOperationsPage area="sessions" />);
    expect(await screen.findByText("2h 30m")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Session history" }));
    expect(await screen.findByText(/Manual Logout/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Correct session" })).toBeInTheDocument();
  });
  it("adds one Daily Update navigation entry and preserves CRM sections", () => {
    const daily = NAV_SECTIONS.flatMap(section => section.items).filter(item => item.to.startsWith("/daily-operations"));
    expect(daily).toHaveLength(1);
    expect(daily[0].label).toBe("Daily Update");
    expect(NAV_SECTIONS.flatMap(section => section.items).some(item => item.label === "Leads")).toBe(true);
  });
  it("renders empty state and sends search and date filters", async () => {
    mount(<DailyOperationsPage area="follow-ups" />);
    expect(await screen.findByText(/No records match these filters/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "document" } });
    fireEvent.change(screen.getByLabelText("From date"), { target: { value: "2026-10-01" } });
    await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith("follow-ups", expect.stringContaining("date_from=2026-10-01")));
  });
  it("shows permission denial and does not request records", async () => {
    mocks.can.mockReturnValue(false); mount(<DailyOperationsPage area="issues" />);
    expect(screen.getByRole("alert")).toHaveTextContent("permission"); expect(mocks.list).not.toHaveBeenCalled();
  });
  it("shows loading and safe server error with retry", async () => {
    mocks.list.mockRejectedValue(new Error("Service unavailable")); mount(<DailyOperationsPage area="issues" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
  it("requires rejection reasons and due dates in status-dependent forms", () => {
    mount(<RecordForm area="follow-ups" onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByLabelText("Next follow-up date")).toBeRequired();
    fireEvent.change(screen.getByLabelText("Follow-up status"), { target: { value: "REJECTED WITH REASON" } });
    expect(screen.getByLabelText("Rejection reason")).toBeRequired();
    expect(screen.queryByLabelText("Next follow-up date")).not.toBeInTheDocument();
  });
  it("shows issue resolution validation and handles save errors", async () => {
    mocks.save.mockRejectedValue(new Error("Concurrent update"));
    mount(<RecordForm area="issues" record={{ id: "synthetic-record", version: 1, status: "OPEN", priority: "medium" }} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Inquiry or issue"), { target: { value: "Internal test" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "RESOLVED" } });
    expect(screen.getByLabelText("Resolution notes")).toBeRequired();
    fireEvent.change(screen.getByLabelText("Resolution notes"), { target: { value: "Resolved in test" } });
    fireEvent.submit(screen.getByRole("button", { name: "Save changes" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Concurrent update");
  });
  it("previews row errors and requires confirmation before committing", async () => {
    mocks.request.mockResolvedValueOnce({ id: "isolated-preview", policy: "Atomic rows", rows: [{ row: 2, values: { date: "2026-10-25" }, errors: [] }, { row: 3, values: {}, errors: [{ column: "FOLLOW PENDING", message: "Required" }] }] }).mockResolvedValueOnce({ inserted: 1, updated: 0, skipped: 0, rejected: 1, errors: [] });
    mount(<TransferCentre />);
    fireEvent.change(screen.getByLabelText("Upload CSV or XLSX"), { target: { files: [new File(["DATE"], "test.csv", { type: "text/csv" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Validate & preview" }));
    expect(await screen.findByText("FOLLOW PENDING: Required")).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "Confirm import" }); expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /I reviewed these rows/ })); expect(confirm).toBeEnabled(); fireEvent.click(confirm);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Inserted: 1"));
  });
});
