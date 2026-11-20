import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { BulkAssignmentModal } from "./BulkAssignmentModal";
import { apiRequest } from "@/shared/api/client";

vi.mock("@/shared/api/client", () => ({ apiRequest: vi.fn() }));
const api = vi.mocked(apiRequest);
beforeEach(() => api.mockReset());

it("previews before confirming and returns partial per-record results", async () => {
  const done = vi.fn();
  const preview = { preview: true, preview_id: "preview", total: 2, eligible: 1, assigned: 0, skipped: 1, failed: 0,
    results: [{ id: "two", collection: "applications", status: "skipped", reason: "Existing assignment preserved" }] };
  api.mockResolvedValueOnce([{ id: "employee", name: "Lucky" }]).mockResolvedValueOnce(preview).mockResolvedValueOnce({ ...preview, preview: false, assigned: 1, eligible: 0 });
  render(<BulkAssignmentModal collection="applications" ids={["one", "two"]} onClose={vi.fn()} onDone={done} />);
  const user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText("Select Employee"), "employee");
  await user.click(screen.getByRole("button", { name: "Review assignments" }));
  expect(done).not.toHaveBeenCalled();
  expect(await screen.findByText(/Existing assignment preserved/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Assign 1 Applications" }));
  await waitFor(() => expect(done).toHaveBeenCalledWith(expect.objectContaining({ assigned: 1, skipped: 1 })));
  expect(api).toHaveBeenLastCalledWith("/applications/bulk-assign", expect.objectContaining({ body: JSON.stringify({ ids: ["one", "two"], employee_id: "employee", allow_reassignment: false, preview_id: "preview" }) }));
});

it("requires a fresh preview after changing explicit reassignment consent", async () => {
  api.mockResolvedValueOnce([{ id: "employee", name: "Pavan" }]).mockResolvedValueOnce({ preview: true, preview_id: "p", eligible: 1, skipped: 0, failed: 0, results: [] });
  render(<BulkAssignmentModal collection="leads" ids={["one"]} onClose={vi.fn()} onDone={vi.fn()} />);
  const user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText("Select Employee"), "employee");
  await user.click(screen.getByRole("button", { name: "Review assignments" }));
  await screen.findByRole("button", { name: "Assign 1 Leads" });
  await user.click(screen.getByRole("checkbox"));
  expect(screen.getByRole("button", { name: "Review assignments" })).toBeVisible();
});

it("keeps the selection open on a request error and permits cancellation", async () => {
  const close = vi.fn();
  api.mockResolvedValueOnce([{ id: "employee", name: "Bharath" }]).mockRejectedValueOnce(new Error("Preview expired"));
  render(<BulkAssignmentModal collection="leads" ids={["one"]} onClose={close} onDone={vi.fn()} />);
  const user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText("Select Employee"), "employee");
  await user.click(screen.getByRole("button", { name: "Review assignments" }));
  expect(await screen.findByText("Preview expired")).toBeVisible();
  expect(screen.getByLabelText("Select Employee")).toHaveValue("employee");
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(close).toHaveBeenCalled();
});
