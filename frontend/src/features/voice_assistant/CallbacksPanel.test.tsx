import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CallbacksPanel } from "./CallbacksPanel";
import { changeCallback, createCallback, getCallbackHistory, getCallbacks, type CallbackList, type CallbackRow } from "./callbackApi";
import { getContactPolicies, saveContactSuppression } from "./api";
import { ApiError } from "@/shared/api/client";

const permissions = vi.hoisted(() => ({ allowed: true, owner: true }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ isOwner: permissions.owner, can: () => permissions.allowed }) }));
vi.mock("@/components/forms/EmployeeSelect", () => ({ EmployeeSelect: ({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) => <label>{label}<input value={value} onChange={e => onChange(e.target.value)} /></label> }));
vi.mock("./callbackApi", () => ({ changeCallback: vi.fn(), createCallback: vi.fn(), getCallbacks: vi.fn(), getCallbackHistory: vi.fn() }));
vi.mock("./api", () => ({ getContactPolicies: vi.fn(), saveContactSuppression: vi.fn() }));
const row: CallbackRow = { id: "aaaaaaaaaaaaaaaaaaaaaaaa", version: 2, state: "awaiting_confirmation", due_at: "2026-10-17T05:30:00Z", requested_local: "2026-10-17T11:00:00", timezone: "Asia/Kolkata", environment: "test", entity_type: "lead", entity_id: "bbbbbbbbbbbbbbbbbbbbbbbb", customer_id: "cccccccccccccccccccccccc", customer_request: "Call at the requested time.", provenance: "staff_attested", source_call_id: null, confirmed_at: null, blockers: [], calls_placed: 0, history_count: 1 };
function list(items = [row]): CallbackList { return { items, total: items.length, live_dispatch: "blocked", capabilities: { create: true, edit: true, current_employee_id: "dddddddddddddddddddddddd" } }; }
async function open() { render(<CallbacksPanel entityType="lead" entityId={row.entity_id} />); await userEvent.click(screen.getByRole("button", { name: "Schedule or review AI callbacks" })); await screen.findByText(/Staff-attested request/); }

describe("CRM callback controls", () => {
  beforeEach(() => { vi.clearAllMocks(); permissions.allowed = true; permissions.owner = true; vi.mocked(getCallbacks).mockResolvedValue(list()); vi.mocked(changeCallback).mockResolvedValue(row); vi.mocked(createCallback).mockResolvedValue(row); vi.mocked(getCallbackHistory).mockResolvedValue({ items: [{ event: "requested", at: "2026-10-16T00:00:00Z", request: "Original customer time preference" }], total: 1 }); vi.stubGlobal("crypto", { randomUUID: () => "12345678-1234-1234-1234-123456789012" }); });
  afterEach(() => vi.unstubAllGlobals());
  it("hides ungranted actions and performs no callback lookup", () => {
    permissions.allowed = false; permissions.owner = false;
    render(<CallbacksPanel entityType="lead" entityId={row.entity_id} />);
    expect(screen.queryByText("AI callbacks")).not.toBeInTheDocument(); expect(getCallbacks).not.toHaveBeenCalled();
  });
  it("loads only when the callback manager is opened", async () => {
    render(<CallbacksPanel entityType="lead" entityId={row.entity_id} />);
    expect(getCallbacks).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Schedule or review AI callbacks" }));
    await waitFor(() => expect(getCallbacks).toHaveBeenCalledWith("lead", row.entity_id, "test", 1));
  });
  it("requires explicit customer-time attestation before confirming", async () => {
    await open(); const confirm = screen.getByRole("button", { name: "Confirm customer time" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Callback action reason"), "Customer confirmed exact time");
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /confirmed this exact date/ }));
    await userEvent.click(confirm);
    await waitFor(() => expect(changeCallback).toHaveBeenCalledWith(row, { action: "confirm", reason: "Customer confirmed exact time" }));
  });
  it("keeps fetched append-only history visible without reloading rows", async () => {
    await open(); await userEvent.click(screen.getByRole("button", { name: "View callback history (1)" }));
    expect(await screen.findByText("Original customer time preference")).toBeInTheDocument();
    expect(getCallbacks).toHaveBeenCalledTimes(1);
  });
  it("reuses the idempotency key when retrying the unchanged request", async () => {
    vi.mocked(createCallback).mockRejectedValueOnce(new ApiError("network_error", "Connection interrupted"));
    await open();
    await userEvent.type(screen.getByLabelText("Callback supervisor"), "dddddddddddddddddddddddd");
    await userEvent.type(screen.getByLabelText("Customer callback preference"), "Please call at the chosen time");
    await userEvent.type(screen.getByLabelText("Requested local callback time"), "2026-10-18T11:00");
    await userEvent.click(screen.getByRole("button", { name: "Save callback request" }));
    await waitFor(() => expect(createCallback).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save callback request" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Save callback request" }));
    await waitFor(() => expect(createCallback).toHaveBeenCalledTimes(2));
    expect(vi.mocked(createCallback).mock.calls[0][0].idempotency_key).toBe(vi.mocked(createCallback).mock.calls[1][0].idempotency_key);
  });
  it("writes global suppression through the existing policy API before cancellation", async () => {
    vi.mocked(getContactPolicies).mockResolvedValue({ consents: [], suppressions: [{ id: "policy", version: 4, scope: "global", suppressed: false }] });
    await open(); await userEvent.type(screen.getByLabelText("Callback action reason"), "Customer requested no more calls");
    await userEvent.click(screen.getByRole("button", { name: "Mark global voice do-not-call" }));
    await waitFor(() => expect(saveContactSuppression).toHaveBeenCalledWith({ customer_id: row.customer_id, version: 4, suppressed: true, reason: "Customer requested no more calls" }));
    expect(vi.mocked(saveContactSuppression).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(changeCallback).mock.invocationCallOrder[0]);
  });
});
