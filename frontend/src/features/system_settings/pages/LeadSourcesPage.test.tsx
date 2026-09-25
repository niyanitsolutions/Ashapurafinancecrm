import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LeadSourcesPage } from "./LeadSourcesPage";

const listLeadSources = vi.fn();
const listRoutes = vi.fn();
const saveRoute = vi.fn();
const syncRoutes = vi.fn();
const setStatus = vi.fn();
const listLoans = vi.fn();
const listInsurance = vi.fn();
const listCategories = vi.fn();

vi.mock("@/features/lead_capture/api", () => ({
  listMetaLeadRoutings: (...a: unknown[]) => listRoutes(...a),
  saveMetaLeadRouting: (...a: unknown[]) => saveRoute(...a),
  syncMetaLeadRoutings: (...a: unknown[]) => syncRoutes(...a),
  setMetaLeadRoutingStatus: (...a: unknown[]) => setStatus(...a),
}));
vi.mock("@/features/system_settings/api", () => ({
  leadSourcesApi: { list: (...a: unknown[]) => listLeadSources(...a), create: vi.fn(), update: vi.fn(), activate: vi.fn(), deactivate: vi.fn() },
  loanProductsApi: { list: (...a: unknown[]) => listLoans(...a) },
  insuranceProductsApi: { list: (...a: unknown[]) => listInsurance(...a) },
  insuranceCategoriesApi: { list: (...a: unknown[]) => listCategories(...a) },
}));

const source = { id: "meta-source", name: "Meta", status: "active", description: null, created_at: "2026-01-01", updated_at: "2026-01-01" };
const baseRoute = {
  id: "route-1", meta_form_id: "FORM-1", form_name: "All Loans", category: "loan", product_mode: "customer_answer",
  default_product_id: null, destination_module: "leads", destination_type: "fresh_leads", product_question_key: "loan_type",
  product_question_label: null, answer_mappings: { "Personal Loan": "loan-1" }, discovered_questions: ["loan_type"],
  priority: 0, status: "active", created_at: "2026-01-01", updated_at: "2026-01-01",
};

beforeEach(() => {
  vi.clearAllMocks();
  listLeadSources.mockResolvedValue([source]);
  listRoutes.mockResolvedValue([baseRoute]);
  listLoans.mockResolvedValue([{ id: "loan-1", name: "Personal Loan", status: "active" }, { id: "loan-off", name: "Inactive Loan", status: "inactive" }]);
  listCategories.mockResolvedValue([{ id: "cat-1", name: "Health", status: "active" }]);
  listInsurance.mockResolvedValue([{ id: "ins-1", name: "Health Plan", status: "active", category_id: "cat-1" }, { id: "ins-off", name: "Retired", status: "inactive", category_id: "cat-1" }]);
  saveRoute.mockResolvedValue(baseRoute);
  syncRoutes.mockResolvedValue([baseRoute]);
  setStatus.mockResolvedValue({ ...baseRoute, status: "inactive" });
});

async function openRouting() {
  render(<LeadSourcesPage />);
  await userEvent.setup().click(await screen.findByRole("button", { name: "Edit" }));
  return userEvent.setup();
}

describe("Meta Lead Routing settings", () => {
  it("loads form routing, preserves immutable ID, filters products, and saves answer mappings", async () => {
    const user = await openRouting();
    expect(await screen.findByText("Form ID: FORM-1")).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Inactive Loan" })).not.toBeInTheDocument();
    await user.clear(screen.getByRole("textbox", { name: "Answer 1" }));
    await user.type(screen.getByRole("textbox", { name: "Answer 1" }), "Business Loan");
    await user.click(screen.getByRole("button", { name: "Save Routing" }));
    await waitFor(() => expect(saveRoute).toHaveBeenCalledWith("FORM-1", expect.objectContaining({
      category: "loan", product_mode: "customer_answer", destination_module: "leads",
      answer_mappings: { "Business Loan": "loan-1" },
    })));
  });

  it("clears incompatible mappings when category changes and exposes only active insurance products", async () => {
    const user = await openRouting();
    await user.selectOptions(await screen.findByRole("combobox", { name: "All Loans Category" }), "insurance");
    expect(screen.getByDisplayValue("Insurance -> Policy Leads -> Fresh Leads")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Health Plan" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Retired" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Mapped product 1" })).toHaveValue("");
  });

  it("syncs forms without assigning a default and can deactivate an active route", async () => {
    const user = await openRouting();
    await user.click(await screen.findByRole("button", { name: "Sync Forms" }));
    await waitFor(() => expect(syncRoutes).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(setStatus).toHaveBeenCalledWith("FORM-1", false));
  });
});
