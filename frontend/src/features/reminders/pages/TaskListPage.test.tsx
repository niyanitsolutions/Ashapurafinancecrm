import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { TaskListPage } from "./TaskListPage";
import userEvent from "@testing-library/user-event";

const { getTask, listTasks, resolveCallbackOwner } = vi.hoisted(() => ({ getTask: vi.fn(), listTasks: vi.fn(() => Promise.resolve({ data: [] as unknown[], pagination: null })), resolveCallbackOwner: vi.fn() }));
vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ role: "owner" }) }));
vi.mock("@/features/voice_assistant/callbackApi", () => ({ resolveCallbackOwner }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ can: () => false }) }));
vi.mock("@/features/reminders/api", () => ({ getTask, listTasks }));

it("loads a referenced task through the authorized detail API", async () => {
  getTask.mockResolvedValue({ id: "task1", title: "Call Vijay", description: "Follow up tomorrow", status: "pending", due_at: "2026-09-24T00:00:00Z" });
  render(<MemoryRouter initialEntries={["/tasks?task=task1"]}><TaskListPage /></MemoryRouter>);
  expect(await screen.findByRole("dialog", { name: "Call Vijay" })).toBeInTheDocument();
  expect(getTask).toHaveBeenCalledWith("task1");
});

it("shows a safe error when the referenced task is restricted", async () => {
  getTask.mockRejectedValue(new Error("Forbidden"));
  render(<MemoryRouter initialEntries={["/tasks?task=restricted"]}><TaskListPage /></MemoryRouter>);
  expect(await screen.findByText("This task is unavailable or you do not have access.")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("resolves a managed callback with an explicit reason and current version", async () => {
  const user = userEvent.setup();
  listTasks.mockResolvedValue({ data: [{ id: "callback-task", version: 4, title: "Managed callback", status: "pending", voice_callback_status: "confirmation_expired", due_at: "2026-09-24T00:00:00Z" }], pagination: null });
  resolveCallbackOwner.mockResolvedValue({ id: "callback-task", state: "cancelled", version: 5 });
  render(<MemoryRouter><TaskListPage /></MemoryRouter>);
  await user.click(await screen.findByRole("button", { name: "Resolve callback" }));
  const cancel = screen.getByRole("button", { name: "Cancel callback request" });
  expect(cancel).toBeDisabled();
  await user.type(screen.getByLabelText("Resolution reason"), "Parent unavailable; close request");
  await user.click(cancel);
  expect(resolveCallbackOwner).toHaveBeenCalledWith("callback-task", 4, "Parent unavailable; close request");
  expect(await screen.findByText("Callback cancelled; history retained.")).toBeInTheDocument();
});
