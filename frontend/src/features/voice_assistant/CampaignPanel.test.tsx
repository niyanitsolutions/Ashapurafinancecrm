import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CampaignPanel } from "./CampaignPanel";
import { createCampaign, getCampaigns, previewCampaign } from "./api";

const access = vi.hoisted(() => ({ allowed: true }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "owner-fixture", role: "owner" }) }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ loading: false, can: () => access.allowed }) }));
vi.mock("./api", () => ({ getCampaigns: vi.fn(), createCampaign: vi.fn(), campaignAction: vi.fn(), importCampaignAudience: vi.fn(), previewCampaign: vi.fn(), stopCampaigns: vi.fn() }));
function mount() { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><CampaignPanel /></QueryClientProvider>); }
describe("Persisted campaign controls", () => {
  beforeEach(() => { vi.clearAllMocks(); access.allowed = true; vi.mocked(getCampaigns).mockResolvedValue({ items: [], total: 0 }); });
  it("does not fetch campaigns without view permission", () => { access.allowed = false; mount(); expect(screen.getByText("Campaign View permission is required.")).toBeInTheDocument(); expect(getCampaigns).not.toHaveBeenCalled(); });
  it("creates a dry run through the API and labels live blocking", async () => {
    mount(); await userEvent.type(screen.getByLabelText("Name"), "Callback review");
    await userEvent.type(screen.getByLabelText("Objective"), "Review consent for callbacks");
    await userEvent.click(screen.getByRole("button", { name: "Create dry-run campaign" }));
    await waitFor(() => expect(createCampaign).toHaveBeenCalledWith("Callback review", "service_callback", "Review consent for callbacks", "Asia/Kolkata"));
    expect(screen.getByText(/No calls are placed/)).toBeInTheDocument();
  });
  it("shows server eligibility results without claiming calls", async () => {
    vi.mocked(getCampaigns).mockResolvedValue({ total: 1, items: [{ id: "campaign-fixture", version: 1, name: "Review", purpose: "service_callback", objective: "Fixture review", timezone: "Asia/Kolkata", status: "draft", mode: "dry_run", processing_counts: { pending: 1 } }] });
    vi.mocked(previewCampaign).mockResolvedValue({ items: [{ customer_id: "customer-fixture", eligible: false, reason: "missing_or_expired_consent" }], calls_placed: 0, production_dispatch: "blocked" });
    mount(); await userEvent.click(await screen.findByRole("button", { name: "Review" }));
    await userEvent.click(screen.getByRole("button", { name: "Preview eligibility (first 25)" }));
    expect(await screen.findByText("Calls placed: 0. Production: blocked.")).toBeInTheDocument();
    expect(screen.getByText(/missing or expired consent/)).toBeInTheDocument();
  });
});
