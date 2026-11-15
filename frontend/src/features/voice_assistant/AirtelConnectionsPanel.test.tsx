import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AirtelConnectionsPanel } from "./AirtelConnectionsPanel";
import { getAirtelVoice, saveAirtelVoice, validateAirtelVoice, type AirtelVoiceConnection } from "./airtelApi";

const auth = vi.hoisted(() => ({ owner: true }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "owner-fixture" }) }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ isOwner: auth.owner }) }));
vi.mock("./airtelApi", () => ({ getAirtelVoice: vi.fn(), saveAirtelVoice: vi.fn(), validateAirtelVoice: vi.fn() }));

const initial: AirtelVoiceConnection = {
  version: 1, public_origin: null, account_sid: null, caller_id: null, call_flow_id: null,
  requested_concurrency: 500, credentials_configured: false, connection_status: "not_configured",
  provider_authentication: "not_verified", webhook_status: "blocked_pending_authentication_and_correlation_contract",
  audio_status: "offline_protocol_only", capacity_status: "not_measured", recording_api_origin: "https://openapi.airtel.in",
  c2c_path: "/gateway/airtel-xchange/v2/adv/ob-click-to-call", recording_path: "/gateway/airtel-xchange/callv2/recording",
  media_url: null, events_url: null, cdr_url: null, blockers: ["AI services are unverified."], last_test: null,
};
function mount() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><AirtelConnectionsPanel /></QueryClientProvider>);
}
describe("Airtel VoiceBOT settings", () => {
  beforeEach(() => { vi.clearAllMocks(); auth.owner = true; vi.mocked(getAirtelVoice).mockResolvedValue(initial); });
  it("does not fetch configuration for employees", () => {
    auth.owner = false; mount();
    expect(screen.getByText(/restricted to the Owner/)).toBeInTheDocument();
    expect(getAirtelVoice).not.toHaveBeenCalled();
  });
  it("shows actual blockers and does not claim 500-call capacity", async () => {
    mount(); await screen.findByText(/Live calling: disabled/);
    expect(screen.getByLabelText(/Requested concurrency/)).toHaveValue(500);
    expect(screen.getByText(/Capacity: not_measured/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate saved signing and offline codec" })).toBeDisabled();
    expect(screen.getByLabelText("App ID (write-only)")).toHaveValue("");
  });
  it("requires a credential pair and clears secrets after saving", async () => {
    vi.mocked(saveAirtelVoice).mockResolvedValue({ ...initial, version: 2, credentials_configured: true });
    mount(); await screen.findByText(/Live calling: disabled/);
    await userEvent.type(screen.getByLabelText("App ID (write-only)"), "fixture-app");
    expect(screen.getByRole("button", { name: "Save Airtel VoiceBOT settings" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("API key (write-only)"), "fixture-key");
    await userEvent.click(screen.getByRole("button", { name: "Save Airtel VoiceBOT settings" }));
    await waitFor(() => expect(saveAirtelVoice).toHaveBeenCalledWith(expect.objectContaining({ app_id: "fixture-app", api_key: "fixture-key" })));
    await waitFor(() => expect(screen.getByLabelText("API key (write-only)")).toHaveValue(""));
  });
  it("prevents validation of dirty credentials and labels offline validation honestly", async () => {
    vi.mocked(getAirtelVoice).mockResolvedValue({ ...initial, credentials_configured: true });
    vi.mocked(validateAirtelVoice).mockResolvedValue({ status: "local_contract_passed", scope: "offline_signing_and_codec_only", message: "No network request was sent.", provider_verified: false, calls_placed: 0 });
    mount(); await screen.findByText(/Live calling: disabled/);
    const button = screen.getByRole("button", { name: "Validate saved signing and offline codec" });
    await userEvent.click(button);
    expect(await screen.findByText("No network request was sent.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("App ID (write-only)"), "replacement");
    expect(button).toBeDisabled();
    expect(validateAirtelVoice).toHaveBeenCalledTimes(1);
  });
});
