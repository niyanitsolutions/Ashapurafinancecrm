import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { TaskListPage } from "./TaskListPage";

const { getTask } = vi.hoisted(() => ({ getTask: vi.fn() }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ can: () => false }) }));
vi.mock("@/features/reminders/api", () => ({ getTask, listTasks: () => Promise.resolve({ data: [], pagination: null }) }));

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
