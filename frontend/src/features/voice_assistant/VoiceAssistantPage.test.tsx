import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { VoiceAssistantPage } from "./VoiceAssistantPage";
import { getDashboard, getSettings } from "./api";

const auth = vi.hoisted(() => ({ owner: true }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "test-user" }) }));
vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({ isOwner: auth.owner, can: () => auth.owner, loading: false }),
}));
vi.mock("./api", () => ({ getDashboard: vi.fn(), getSettings: vi.fn() }));

function mount(section: string) {
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={query}><MemoryRouter initialEntries={[`/voice-assistant/${section}`]}><Routes><Route path="/voice-assistant/:section" element={<VoiceAssistantPage />} /></Routes></MemoryRouter></QueryClientProvider>);
}

describe("Voice assistant readiness and permissions", () => {
  beforeEach(() => {
    vi.clearAllMocks(); auth.owner = true;
    vi.mocked(getDashboard).mockResolvedValue({
      metrics: { incoming: 0, active: 0 }, data_mode: "mock_only", estimated_cost: null,
      provider: { telephony: "not_configured", conversation_ai: "not_configured", blockers: ["Provider setup outstanding."], validated_languages: [] },
      worker: "unknown_or_stale", worker_heartbeat_at: null, recent: [],
    });
  });
  it("shows empty backend data without pretending calls are operational", async () => {
    mount("dashboard");
    expect(screen.getByText(/Live calling disabled/)).toBeInTheDocument();
    expect(await screen.findByText("No call activity yet.")).toBeInTheDocument();
    expect(screen.getByText(/unknown_or_stale/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /activate/i })).not.toBeInTheDocument();
  });
  it("does not fetch Owner settings for an employee", async () => {
    auth.owner = false; mount("settings");
    expect(screen.getByText("Voice settings are restricted to the Owner.")).toBeInTheDocument();
    await screen.findByText(/Live calling disabled/);
    expect(getSettings).not.toHaveBeenCalled();
  });
  it("clearly labels unimplemented voice uploads", async () => {
    mount("studio");
    expect(screen.getByText(/No voice provider is connected/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/upload/i)).not.toBeInTheDocument();
  });
});
