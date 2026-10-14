import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecordingsPanel } from "./RecordingsPanel";
import { ApiError } from "@/shared/api/client";
import { deleteRecording, getRecordingAudio, getRecordings, getTranscript } from "./api";

const permissions = vi.hoisted(() => ({ view: true, download: false }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ userId: "operator" }) }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ can: (_resource: string, action: string) => action === "view" ? permissions.view : action === "download" ? permissions.download : true }) }));
vi.mock("./api", () => ({ getRecordings: vi.fn(), getRecordingAudio: vi.fn(), getTranscript: vi.fn(), deleteRecording: vi.fn(), importRecording: vi.fn(), saveTranscript: vi.fn(), recoverRecording: vi.fn() }));
const record = { id: "111111111111111111111111", call_id: "222222222222222222222222", version: 2, direction: "incoming", status: "completed", origin: "imported_artifact", call_provider: "mock", duration_seconds: 1, size_bytes: 16044, sample_rate: 8000, channels: 1, created_at: "2026-10-14T00:00:00Z", expires_at: "2026-11-14T00:00:00Z", transcript_status: "imported_unverified_recognition" };
function mount() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RecordingsPanel /></QueryClientProvider>); }
describe("Private imported recording library", () => {
  beforeEach(() => {
    vi.clearAllMocks(); permissions.view = true; permissions.download = false;
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:test-artifact"), revokeObjectURL: vi.fn() }));
    vi.mocked(getRecordings).mockResolvedValue({ items: [record], total: 1, page: 1, storage: "configured_not_externally_verified", live_capture: "blocked", transcription_engine: "not_approved" });
    vi.mocked(getRecordingAudio).mockResolvedValue(new Blob(["test-only-WAV-fixture"], { type: "audio/wav" }));
    vi.mocked(getTranscript).mockResolvedValue({ language: "en", recognizer_label: "Test recognizer", provenance: "operator_supplied_recognition_not_independently_verified", summary: null, summary_status: "not_generated", segments: [{ speaker: "caller", start_seconds: 0.4, end_seconds: 0.8, text: "Actual test recognition fixture" }] });
  });
  it("does not fetch artifacts without dedicated View permission", () => {
    permissions.view = false; mount(); expect(screen.getByText(/recordings View permission/)).toBeInTheDocument(); expect(getRecordings).not.toHaveBeenCalled();
  });
  it("blocks upload until storage is configured and shows honest empty state", async () => {
    vi.mocked(getRecordings).mockResolvedValue({ items: [], total: 0, page: 1, storage: "not_configured", live_capture: "blocked", transcription_engine: "not_approved" });
    mount(); expect(await screen.findByText(/No recording artifacts/)).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Import and verify artifact" })).toBeDisabled(); expect(screen.getByText(/Live capture and automatic transcription remain blocked/)).toBeInTheDocument();
  });
  it("loads authorized audio only on request, labels transcript provenance, seeks and revokes URL", async () => {
    const view = mount(); fireEvent.click(await screen.findByRole("button", { name: "Open audio and transcript" })); expect(getRecordingAudio).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Load authorized audio" }));
    const audio = await screen.findByLabelText("Authorized recording playback") as HTMLAudioElement;
    expect(getRecordingAudio).toHaveBeenCalledWith(record.id); expect(audio.src).toContain("blob:test-artifact");
    fireEvent.click(screen.getByRole("button", { name: "Load recognized transcript" }));
    expect(await screen.findByText("Actual test recognition fixture")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Seek to 0.4s" })); expect(audio.currentTime).toBe(0.4);
    expect(screen.getByText(/operator supplied recognition not independently verified/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download" })).not.toBeInTheDocument(); view.unmount(); expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-artifact");
  });
  it("shows playback failures instead of fake audio", async () => {
    vi.mocked(getRecordingAudio).mockRejectedValue(new ApiError("artifact_unavailable", "Artifact unavailable")); mount(); fireEvent.click(await screen.findByRole("button", { name: "Open audio and transcript" })); fireEvent.click(screen.getByRole("button", { name: "Load authorized audio" }));
    expect(await screen.findByText("Artifact unavailable")).toBeInTheDocument(); expect(screen.queryByLabelText("Authorized recording playback")).not.toBeInTheDocument();
  });
  it("requires explicit deletion confirmation", async () => {
    vi.mocked(deleteRecording).mockResolvedValue({ status: "deleted" }); mount(); fireEvent.click(await screen.findByRole("button", { name: "Delete artifact and transcript" }));
    expect(deleteRecording).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole("button", { name: "Delete permanently" })); await waitFor(() => expect(deleteRecording).toHaveBeenCalledWith(record));
  });
  it("applies UTC import-date filters with an exclusive next-day end", async () => {
    mount(); await screen.findByRole("button", { name: "Open audio and transcript" });
    fireEvent.change(screen.getByLabelText("Imported from (UTC)"), { target: { value: "2026-10-14" } });
    fireEvent.change(screen.getByLabelText("Imported through (UTC)"), { target: { value: "2026-10-14" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filter" }));
    await waitFor(() => expect(getRecordings).toHaveBeenLastCalledWith(1, "", "", "2026-10-14T00:00:00Z", "2026-10-15T00:00:00.000Z"));
  });
});
