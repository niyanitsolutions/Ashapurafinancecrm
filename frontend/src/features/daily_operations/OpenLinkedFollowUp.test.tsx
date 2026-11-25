import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { OpenLinkedFollowUp } from "./OpenLinkedFollowUp";
import { apiRequest } from "@/shared/api/client";
vi.mock("./RecordForm",()=>({RecordForm:({onSaved,onCancel}:{onSaved:()=>void;onCancel:()=>void})=><div><button onClick={onSaved}>Save test form</button><button onClick={onCancel}>Close test form</button></div>}));
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

it("opens the existing linked form in a modal without changing routes and closes only on saved callback",async()=>{
 vi.mocked(apiRequest).mockResolvedValue({id:"working-id",customer_name:"Verified Customer",customer_number:"9000000000",date:"2026-11-25",status:"DISBURSE",remarks_date:"2026-11-25",banks:[]});
 const saved=vi.fn();
 render(<MemoryRouter><OpenLinkedFollowUp entity="application" recordId="app-id" mode="modal" onSaved={saved}/></MemoryRouter>);
 await userEvent.click(screen.getByRole("button",{name:"Open Daily Follow-up"}));
 expect(await screen.findByRole("dialog",{name:"Daily Follow-up"})).toBeVisible();expect(screen.queryByText("Linked daily workspace")).not.toBeInTheDocument();
 await userEvent.click(screen.getByRole("button",{name:"Close test form"}));expect(screen.queryByRole("dialog")).not.toBeInTheDocument();expect(saved).not.toHaveBeenCalled();
 await userEvent.click(screen.getByRole("button",{name:"Open Daily Follow-up"}));await screen.findByRole("dialog");await userEvent.click(screen.getByRole("button",{name:"Save test form"}));expect(saved).toHaveBeenCalledTimes(1);expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
