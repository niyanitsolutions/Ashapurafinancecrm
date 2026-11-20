import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { OpenLinkedFollowUp } from "./OpenLinkedFollowUp";
import { apiRequest } from "@/shared/api/client";
let allowed = true;
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ can: () => allowed }) }));
vi.mock("@/shared/api/client", () => ({ apiRequest: vi.fn() }));
beforeEach(() => { allowed = true; vi.mocked(apiRequest).mockReset(); });
it("opens the same server-linked workspace and reports a denied request", async () => {
  vi.mocked(apiRequest).mockRejectedValueOnce(new Error("Record is not assigned to you.")).mockResolvedValueOnce({ id: "working-id" });
  render(<MemoryRouter><Routes><Route path="/" element={<OpenLinkedFollowUp entity="lead" recordId="lead-id" />} /><Route path="/daily-operations/follow-ups" element={<p>Linked daily workspace</p>} /></Routes></MemoryRouter>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Open Daily Follow-up" }));
  expect(await screen.findByText("Record is not assigned to you.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Open Daily Follow-up" }));
  expect(await screen.findByText("Linked daily workspace")).toBeVisible();
  await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("/daily-operations/linked-follow-up", { method: "POST", body: JSON.stringify({ entity: "lead", record_id: "lead-id" }) }));
});
it("hides the action without existing permissions", () => {
  allowed = false; render(<MemoryRouter><OpenLinkedFollowUp entity="application" recordId="app-id" /></MemoryRouter>);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
