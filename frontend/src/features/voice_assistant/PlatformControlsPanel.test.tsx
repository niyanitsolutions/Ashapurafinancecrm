import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PlatformControlsPanel } from "./PlatformControlsPanel";
import { ApiError } from "@/shared/api/client";
import { emergencyVoiceStop, getPlatform, getSpeechJobs, getSpeechProfiles, updateComponent, type PlatformState, type VoiceComponent } from "./platformApi";

const auth = vi.hoisted(() => ({ role: "owner" }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "platform-test-owner", role: auth.role }) }));
vi.mock("./platformApi", () => ({ emergencyVoiceStop: vi.fn(), getPlatform: vi.fn(), getSpeechJobs: vi.fn(), getSpeechProfiles: vi.fn(), getSpeechTestAudio: vi.fn(), setActivation: vi.fn(), startSpeechTest: vi.fn(), startPipelineTest: vi.fn(), updateComponent: vi.fn() }));
const components: VoiceComponent[] = ["telephony", "stt", "tts", "inference", "media", "workers", "recording", "transfer", "smartflo"];
function state(): PlatformState {
  return { environment: "test", version: 3, emergency_stopped: true, inbound: false, outbound: false, processing: false, production_eligible: false, live_implementation_available: false, evidence_token: "a".repeat(64), history: [], components: Object.fromEntries(components.map(key => [key, { enabled: false, profile_id: null, testing_supported: !["media", "recording", "transfer"].includes(key) }])) as PlatformState["components"], gates: [{ key: "native_control_media", passed: false, remediation: "Actual media acceptance is required." }] };
}
function mount() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><PlatformControlsPanel /></MemoryRouter></QueryClientProvider>); }

describe("Platform voice controls", () => {
  beforeEach(() => { vi.clearAllMocks(); auth.role = "owner"; vi.mocked(getPlatform).mockResolvedValue(state()); vi.mocked(getSpeechProfiles).mockResolvedValue({ profiles: [], message: "Operator installation required." }); vi.mocked(getSpeechJobs).mockResolvedValue({ items: [], total: 0 }); vi.mocked(emergencyVoiceStop).mockResolvedValue(state()); vi.mocked(updateComponent).mockResolvedValue(state()); });
  it("does not fetch or expose controls for employees", () => {
    auth.role = "employee"; mount();
    expect(screen.getByText(/restricted to the Owner/)).toBeInTheDocument();
    expect(getPlatform).not.toHaveBeenCalled(); expect(getSpeechJobs).not.toHaveBeenCalled();
  });
  it("keeps live activation and absent media engines blocked", async () => {
    mount();
    expect(await screen.findByText(/Actual media acceptance is required/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enable live inbound (blocked)" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Change reason/), "Review local controls");
    const media = screen.getByRole("region", { name: "Voice media" });
    expect(within(media).getByRole("button", { name: "Enable for testing Voice media" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run actual local STT test" })).toBeDisabled();
  });
  it("emergency stop calls the backend without an old UI version", async () => {
    mount();
    await screen.findByText(/Actual media acceptance is required/);
    await userEvent.type(screen.getByLabelText(/Change reason/), "Emergency test stop");
    await userEvent.click(screen.getByRole("button", { name: "Emergency disable test voice" }));
    await waitFor(() => expect(emergencyVoiceStop).toHaveBeenCalledWith("test", "Emergency test stop"));
  });
  it("emergency stop does not require typing a reason first", async () => {
    mount(); await screen.findByText(/Actual media acceptance is required/);
    await userEvent.click(screen.getByRole("button", { name: "Emergency disable test voice" }));
    await waitFor(() => expect(emergencyVoiceStop).toHaveBeenCalledWith("test", "Owner emergency disable"));
  });
  it("emergency stop stays usable while another action is pending", async () => {
    vi.mocked(updateComponent).mockImplementation(() => new Promise(() => {}));
    mount(); await screen.findByText(/Actual media acceptance is required/);
    await userEvent.type(screen.getByLabelText(/Change reason/), "Pending action emergency test");
    await userEvent.click(screen.getByRole("button", { name: "Enable for testing Voice verification workers" }));
    const emergency = screen.getByRole("button", { name: "Emergency disable test voice" });
    expect(emergency).toBeEnabled();
    await userEvent.click(emergency);
    await waitFor(() => expect(emergencyVoiceStop).toHaveBeenCalledWith("test", "Pending action emergency test"));
  });
  it("uses current control version for component changes", async () => {
    mount(); await screen.findByText(/Actual media acceptance is required/);
    await userEvent.type(screen.getByLabelText(/Change reason/), "Enable local worker testing");
    await userEvent.click(screen.getByRole("button", { name: "Enable for testing Voice verification workers" }));
    await waitFor(() => expect(updateComponent).toHaveBeenCalledWith("test", "workers", 3, true, null, "Enable local worker testing"));
  });
  it("fetches production state separately when the environment changes", async () => {
    mount(); await screen.findByText(/Actual media acceptance is required/);
    await userEvent.selectOptions(screen.getByLabelText("Voice environment"), "production");
    await waitFor(() => expect(getPlatform).toHaveBeenCalledWith("production"));
    expect(getSpeechJobs).toHaveBeenCalledWith("production", 1);
  });
  it("shows safe backend failures and a retry action", async () => {
    vi.mocked(getPlatform).mockRejectedValue(new ApiError("service_unavailable", "Service temporarily unavailable"));
    mount();
    expect(await screen.findByText("Service temporarily unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry platform status" })).toBeEnabled();
  });
});
