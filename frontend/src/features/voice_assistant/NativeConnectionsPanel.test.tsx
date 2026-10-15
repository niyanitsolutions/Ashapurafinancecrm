import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NativeConnectionsPanel } from "./NativeConnectionsPanel";
import { getNativeConnections, getTelephoneNumbers, saveNativeConnection, type NativeConnection } from "./api";

const auth = vi.hoisted(() => ({ role: "owner" }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "test-native-owner", role: auth.role }) }));
vi.mock("./api", () => ({ getNativeConnections: vi.fn(), getTelephoneNumbers: vi.fn(), saveNativeConnection: vi.fn(), testNativeConnection: vi.fn(), getNativeConnectionEvents: vi.fn().mockResolvedValue({ items: [], total: 0 }), saveTelephoneNumber: vi.fn(), telephoneNumberAction: vi.fn() }));
function mount() { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><NativeConnectionsPanel /></QueryClientProvider>); }
describe("Native telephone administration", () => {
  beforeEach(() => { vi.clearAllMocks(); auth.role = "owner"; vi.mocked(getNativeConnections).mockResolvedValue({ items: [], total: 0, origin_allowlist_configured: false }); vi.mocked(getTelephoneNumbers).mockResolvedValue({ items: [], total: 0 }); });
  it("does not load Owner connection records for employees", () => { auth.role = "employee"; mount(); expect(screen.getByText(/restricted to the Owner/)).toBeInTheDocument(); expect(getNativeConnections).not.toHaveBeenCalled(); expect(getTelephoneNumbers).not.toHaveBeenCalled(); });
  it("shows missing allowlist and keeps live status disabled", async () => { mount(); await screen.findByText("No native PBX connections registered."); expect(screen.getByText(/VOICE_NATIVE_ALLOWED_ORIGINS/)).toBeInTheDocument(); expect(screen.getByText("Live calling disabled")).toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Activate" })).not.toBeInTheDocument(); });
  it("saves credentials through the API and clears write-only fields", async () => {
    const data: NativeConnection = { id: "aaaaaaaaaaaaaaaaaaaaaaaa", version: 1, name: "Staging PBX", adapter: "asterisk_ari", api_origin: "https://pbx.example.internal:8089", endpoint_name: "test-trunk", state: "configuration_incomplete", credentials_configured: true, live_calling: false, last_test: null };
    vi.mocked(saveNativeConnection).mockResolvedValue(data); mount();
    await userEvent.type(screen.getByLabelText("Connection name"), data.name);
    await userEvent.type(screen.getByLabelText("PBX API origin"), data.api_origin);
    await userEvent.type(screen.getByLabelText("Configured PJSIP endpoint name"), data.endpoint_name);
    await userEvent.type(screen.getByLabelText("ARI username (write-only)"), "test-user");
    await userEvent.type(screen.getByLabelText("ARI password (write-only)"), "test-password-only");
    await userEvent.click(screen.getByRole("button", { name: "Save native connection" }));
    await waitFor(() => expect(saveNativeConnection).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByLabelText("ARI password (write-only)")).toHaveValue(""));
    expect(screen.getByLabelText("ARI username (write-only)")).toHaveValue("");
    expect(JSON.stringify(localStorage)).not.toContain("test-password-only");
  });
  it("shows backend blockers and disables activation for registered drafts", async () => {
    vi.mocked(getTelephoneNumbers).mockResolvedValue({ total: 1, items: [{ id: "bbbbbbbbbbbbbbbbbbbbbbbb", version: 1, number: "+919000000100", label: "Draft number", purpose: "bidirectional", connection_id: null, authorization_reference: null, compliance_reference: null, timezone: "Asia/Kolkata", calling_start: "09:00", calling_end: "18:00", inbound_route: "dynamic_ai", state: "draft", live_calling: false, activation_eligible: false, activation_checks: [{ key: "media", passed: false, description: "Media acceptance is outstanding." }] }] });
    mount(); expect(await screen.findByText(/Media acceptance is outstanding/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Activate (requirements outstanding)" })).toBeDisabled();
  });
});
