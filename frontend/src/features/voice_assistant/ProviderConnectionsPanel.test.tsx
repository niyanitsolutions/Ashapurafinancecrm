import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProviderConnectionsPanel } from "./ProviderConnectionsPanel";
import { getSmartfloConnection, getSmartfloEvents, saveSmartfloConnection, testSmartflo, type SmartfloConnection } from "./api";

const auth = vi.hoisted(() => ({ owner: true }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "owner-test" }) }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ isOwner: auth.owner }) }));
vi.mock("./api", () => ({ getSmartfloConnection: vi.fn(), getSmartfloEvents: vi.fn(), saveSmartfloConnection: vi.fn(), testSmartflo: vi.fn() }));

const connection: SmartfloConnection = {
  version: 1, api_base_url: "https://api-smartflo.tatateleservices.com", public_origin: null,
  api_token_configured: false, callback_token_configured: false, token_expires_at: null, token_expired: false,
  callback_mode: "disabled", connection_status: "not_configured", last_test: null,
  sandbox: "pending_provider_verification", audio_status: "blocked_missing_speech_engine", url_verification: "not_externally_verified",
  incoming_webhook_url: null, answered_webhook_url: null, call_status_webhook_url: null,
  dynamic_endpoint_url: null, audio_websocket_url: null, warnings: [],
};
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProviderConnectionsPanel /></QueryClientProvider>);
}
describe("Smartflo provider connection controls", () => {
  beforeEach(() => {
    vi.clearAllMocks(); auth.owner = true;
    vi.mocked(getSmartfloConnection).mockResolvedValue(connection);
    vi.mocked(getSmartfloEvents).mockResolvedValue({ items: [], total: 0 });
  });
  it("does not fetch credentials or events for employees", () => {
    auth.owner = false; mount();
    expect(screen.getByText(/restricted to the Owner/)).toBeInTheDocument();
    expect(getSmartfloConnection).not.toHaveBeenCalled(); expect(getSmartfloEvents).not.toHaveBeenCalled();
  });
  it("shows pending capabilities and disables unavailable credential tests", async () => {
    mount(); await screen.findByText("No provider events received.");
    expect(screen.getByRole("button", { name: "Test API connection (read-only)" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Test local webhook pipeline" })).toBeDisabled();
    expect(screen.getByText(/Live calling: disabled/)).toBeInTheDocument();
    expect(screen.getByLabelText("API token (write-only)")).toHaveValue("");
    expect(screen.getByLabelText("API base URL")).toHaveAttribute("readonly");
  });
  it("prevents testing a replacement token before saving it", async () => {
    vi.mocked(getSmartfloConnection).mockResolvedValue({ ...connection, api_token_configured: true });
    mount(); await screen.findByText("No provider events received.");
    await userEvent.type(screen.getByLabelText("API token (write-only)"), "test-only-replacement-token-value");
    expect(screen.getByRole("button", { name: "Test API connection (read-only)" })).toBeDisabled();
    expect(testSmartflo).not.toHaveBeenCalled();
  });
  it("clears entered secrets after a successful save", async () => {
    vi.mocked(saveSmartfloConnection).mockResolvedValue({ ...connection, version: 2, api_token_configured: true });
    mount(); await screen.findByText("No provider events received.");
    await userEvent.type(screen.getByLabelText("API token (write-only)"), "test-only-replacement-token-value");
    await userEvent.click(screen.getByRole("button", { name: "Save connection settings" }));
    await waitFor(() => expect(saveSmartfloConnection).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByLabelText("API token (write-only)")).toHaveValue(""));
  });
  it("labels offline audio results without claiming a live connection", async () => {
    vi.mocked(testSmartflo).mockResolvedValue({ status: "offline_protocol_passed", message: "Local protocol check only." });
    mount(); await screen.findByText("No provider events received.");
    await userEvent.click(screen.getByRole("button", { name: "Test offline audio protocol" }));
    expect(await screen.findByText("offline_protocol_passed: Local protocol check only.")).toBeInTheDocument();
    expect(testSmartflo).toHaveBeenCalledWith("audio");
    expect(screen.getByText(/Live calling: disabled/)).toBeInTheDocument();
  });
});
