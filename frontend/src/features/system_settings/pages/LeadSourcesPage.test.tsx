import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LeadSourcesPage } from "./LeadSourcesPage";

const listLeadSources = vi.fn();
const listCaptureSources = vi.fn();
const updateCaptureSource = vi.fn();
const listLoanProducts = vi.fn();
const listInsuranceProducts = vi.fn();
const listInsuranceCategories = vi.fn();

vi.mock("@/features/lead_capture/api", () => ({
  listCaptureSources: (...args: unknown[]) => listCaptureSources(...args),
  updateCaptureSource: (...args: unknown[]) => updateCaptureSource(...args),
}));

vi.mock("@/features/system_settings/api", () => ({
  leadSourcesApi: {
    list: (...args: unknown[]) => listLeadSources(...args),
    create: vi.fn(),
    update: vi.fn(),
    activate: vi.fn(),
    deactivate: vi.fn(),
  },
  loanProductsApi: { list: (...args: unknown[]) => listLoanProducts(...args) },
  insuranceProductsApi: { list: (...args: unknown[]) => listInsuranceProducts(...args) },
  insuranceCategoriesApi: { list: (...args: unknown[]) => listInsuranceCategories(...args) },
}));

const metaLeadSource = {
  id: "lead-source-meta",
  name: "Meta",
  description: null,
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  listLeadSources.mockResolvedValue([metaLeadSource]);
  listCaptureSources.mockResolvedValue([
    {
      id: "capture-meta",
      key: "meta_lead_ads",
      label: "Meta Lead Ads",
      lead_source_id: metaLeadSource.id,
      default_product_category: "loan",
      default_product_id: "loan-active",
    },
  ]);
  listLoanProducts.mockResolvedValue([
    { id: "loan-active", name: "Personal Loan", status: "active" },
    { id: "loan-inactive", name: "Inactive Loan", status: "inactive" },
  ]);
  listInsuranceCategories.mockResolvedValue([
    { id: "category-active", name: "Health", status: "active" },
    { id: "category-inactive", name: "Retired", status: "inactive" },
  ]);
  listInsuranceProducts.mockResolvedValue([
    { id: "insurance-active", name: "Health Protect", status: "active", category_id: "category-active" },
    { id: "insurance-inactive", name: "Inactive Policy", status: "inactive", category_id: "category-active" },
    { id: "insurance-retired-category", name: "Retired Category Policy", status: "active", category_id: "category-inactive" },
  ]);
  updateCaptureSource.mockImplementation(async (key: string, payload: Record<string, string>) => ({
    id: "capture-meta",
    key,
    label: "Meta Lead Ads",
    lead_source_id: metaLeadSource.id,
    ...payload,
  }));
});

describe("LeadSourcesPage Meta product mapping", () => {
  it("loads persisted mapping, resets product on category change, filters inactive options, and saves IDs", async () => {
    const user = userEvent.setup();
    render(<LeadSourcesPage />);

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const category = await screen.findByRole("combobox", { name: "Meta Product Category" });
    const product = screen.getByRole("combobox", { name: "Meta Product" });

    await waitFor(() => expect(category).toHaveValue("loan"));
    expect(product).toHaveValue("loan-active");
    expect(screen.getByRole("option", { name: "Personal Loan" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Inactive Loan" })).not.toBeInTheDocument();

    await user.selectOptions(category, "insurance");
    expect(product).toHaveValue("");
    expect(screen.getByRole("option", { name: "Health Protect" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Inactive Policy" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Retired Category Policy" })).not.toBeInTheDocument();

    await user.selectOptions(product, "insurance-active");
    await user.click(screen.getByRole("button", { name: "Save Meta Mapping" }));

    await waitFor(() => expect(updateCaptureSource).toHaveBeenCalledWith("meta_lead_ads", {
      default_product_category: "insurance",
      default_product_id: "insurance-active",
    }));
    expect(await screen.findByText("Meta Lead Ads product mapping saved.")).toBeInTheDocument();
  });

  it("warns when the Meta mapping is unconfigured", async () => {
    listCaptureSources.mockResolvedValue([
      {
        id: "capture-meta",
        key: "meta_lead_ads",
        label: "Meta Lead Ads",
        lead_source_id: metaLeadSource.id,
        default_product_category: null,
        default_product_id: null,
      },
    ]);
    const user = userEvent.setup();
    render(<LeadSourcesPage />);
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Meta imports are blocked");
    expect(screen.getByRole("button", { name: "Save Meta Mapping" })).toBeDisabled();
  });
});
