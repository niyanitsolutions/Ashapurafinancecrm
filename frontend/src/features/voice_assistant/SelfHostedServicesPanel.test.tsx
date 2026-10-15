import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SelfHostedServicesPanel } from "./SelfHostedServicesPanel";
import { getSelfHostedHealth, testSelfHostedText, type SelfHostedHealth } from "./api";

const auth = vi.hoisted(() => ({ role: "owner" }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ role: auth.role, userId: "test-owner" }) }));
vi.mock("./api", () => ({ getSelfHostedHealth: vi.fn(), testSelfHostedText: vi.fn() }));
const disabled: SelfHostedHealth = { text_inference: "disabled", model: null, configured: false, evidence_fresh: false, speech_to_text: "not_installed", text_to_speech: "not_installed", live_calling: false, message: "Text checks do not verify speech or live calling.", last_test: null };
function mount() { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SelfHostedServicesPanel /></QueryClientProvider>); }
describe("Self-hosted readiness evidence", () => {
  beforeEach(() => { vi.clearAllMocks(); auth.role = "owner"; vi.mocked(getSelfHostedHealth).mockResolvedValue(disabled); });
  it("never requests Owner health data for employees", () => { auth.role = "employee"; mount(); expect(getSelfHostedHealth).not.toHaveBeenCalled(); });
  it("keeps tests disabled until an operator configures inference", async () => { mount(); await screen.findByText("No model configured"); expect(screen.getByRole("button", { name: "Test representative text request" })).toBeDisabled(); });
  it("reports actual test failure without calling it healthy", async () => {
    vi.mocked(getSelfHostedHealth).mockResolvedValue({ ...disabled, configured: true, model: "test-model", text_inference: "unverified_or_unavailable" });
    vi.mocked(testSelfHostedText).mockResolvedValue({ ...disabled, configured: true, text_inference: "unverified_or_unavailable", last_test: { status: "functional_request_failed", latency_ms: 42, checked_at: "2026-10-15T00:00:00Z", scope: "synthetic_text" } });
    mount(); await userEvent.click(await screen.findByRole("button", { name: "Test representative text request" }));
    expect(await screen.findByText(/functional_request_failed/)).toBeInTheDocument();
    expect(screen.getByText("Text checks do not verify speech or live calling.")).toBeInTheDocument();
  });
});
