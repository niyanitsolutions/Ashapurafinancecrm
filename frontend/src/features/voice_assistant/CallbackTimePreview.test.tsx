import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { CallbackTimePreview } from "./CallbackTimePreview";
import { previewCallbackTime } from "./callbackApi";
vi.mock("./callbackApi", () => ({ previewCallbackTime: vi.fn() }));
beforeEach(() => vi.clearAllMocks());
it("never applies or schedules an ambiguous request", async () => {
  vi.mocked(previewCallbackTime).mockResolvedValue({ status: "clarification_required", requested_local: null, timezone: "UTC", clarification: "Which exact time?", requires_confirmation: true, persisted: false });
  const apply = vi.fn(); render(<CallbackTimePreview request="Call tomorrow" timezone="UTC" disabled={false} apply={apply} />);
  await userEvent.click(screen.getByRole("button", { name: "Preview requested time" }));
  expect(await screen.findByText("Which exact time?")).toBeInTheDocument(); expect(apply).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Use proposed time in form" })).not.toBeInTheDocument();
});
it("requires explicit application and hides a stale preview after request edits", async () => {
  vi.mocked(previewCallbackTime).mockResolvedValue({ status: "proposed", requested_local: "2026-10-19T11:00:00", timezone: "UTC", clarification: "Confirm time", requires_confirmation: true, persisted: false });
  const apply = vi.fn(); const view = render(<CallbackTimePreview request="tomorrow at 11 AM" timezone="UTC" disabled={false} apply={apply} />);
  await userEvent.click(screen.getByRole("button", { name: "Preview requested time" }));
  await screen.findByText("Confirm time"); expect(apply).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Use proposed time in form" })); expect(apply).toHaveBeenCalledWith("2026-10-19T11:00");
  view.rerender(<CallbackTimePreview request="after 11 AM" timezone="UTC" disabled={false} apply={apply} />);
  expect(screen.queryByText("Confirm time")).not.toBeInTheDocument();
});
