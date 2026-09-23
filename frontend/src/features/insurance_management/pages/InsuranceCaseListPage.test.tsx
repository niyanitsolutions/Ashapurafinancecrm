import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { InsuranceCaseListPage } from "./InsuranceCaseListPage";

let canEdit = true;
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ can: () => canEdit }) }));
vi.mock("@/components/pages/CaseListPage", () => ({ CaseListPage: () => <div>Existing list</div> }));

it("opens the shared Insurance bulk upload on Fresh Leads", async () => {
  canEdit = true;
  render(<MemoryRouter><InsuranceCaseListPage fixedStatus="fresh_lead" /></MemoryRouter>);
  await userEvent.setup().click(screen.getByRole("button", { name: "Bulk Upload" }));
  expect(screen.getByRole("dialog", { name: "Bulk Upload Insurance Leads" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Download Sample Excel" })).toBeInTheDocument();
});

it("hides import and creation from an unauthorized employee", () => {
  canEdit = false;
  render(<MemoryRouter><InsuranceCaseListPage fixedStatus="fresh_lead" /></MemoryRouter>);
  expect(screen.queryByRole("button", { name: "Bulk Upload" })).not.toBeInTheDocument();
});
