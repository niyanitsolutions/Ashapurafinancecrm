import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InsuranceAnalyticsPage } from "./InsuranceAnalyticsPage";

const getAnalyticsOverview = vi.fn();
const listAdvisorAnalytics = vi.fn();
const listProductAnalytics = vi.fn();
const getAdvisorWork = vi.fn();
const getProductWork = vi.fn();
vi.mock("@/features/insurance_management/analyticsApi", () => ({
  getAnalyticsOverview: (...args: unknown[]) => getAnalyticsOverview(...args),
  listAdvisorAnalytics: (...args: unknown[]) => listAdvisorAnalytics(...args),
  listProductAnalytics: (...args: unknown[]) => listProductAnalytics(...args),
  getAdvisorWork: (...args: unknown[]) => getAdvisorWork(...args),
  getProductWork: (...args: unknown[]) => getProductWork(...args),
}));

const overview = {
  capabilities: { advisor_business: true, policy_pipeline: true },
  summary: { total_advisors: 1, total_business: 2, business_premium: 135000, total_policy_leads: 2, total_policy_issued: 1, policy_premium: 119000 },
  pipeline: [{ stage: "fresh_lead", count: 1 }, { stage: "policy_issued", count: 1 }],
  stages: ["fresh_lead", "policy_issued"],
  advisors: [{ id: "a1", label: "Kishan" }], products: [{ id: "p1", label: "Smart Term" }],
};

beforeEach(() => {
  getAnalyticsOverview.mockReset().mockResolvedValue(overview);
  listAdvisorAnalytics.mockReset().mockResolvedValue({ data: [{ advisor_id: "a1", advisor_code: "AFS-ADV-1", advisor_name: "Kishan", businesses: 2, total_premium: 135000, products: 2 }], pagination: { page: 1, page_size: 10, total: 1, total_pages: 1 } });
  listProductAnalytics.mockReset().mockResolvedValue({ data: [{ product_id: "p1", product_name: "Smart Term", leads: 2, issued: 1, premium: 119000 }], pagination: { page: 1, page_size: 10, total: 1, total_pages: 1 } });
  getAdvisorWork.mockReset().mockResolvedValue({ data: { advisor: { advisor_id: "a1", advisor_code: "AFS-ADV-1", advisor_name: "Kishan", businesses: 2, total_premium: 135000, products: 2 }, products: [{ product_name: "Smart Term", businesses: 2 }], businesses: [{ id: "b1", customer_name: "Chandra", product_name: "Smart Term", premium: 80000 }] }, pagination: null });
  getProductWork.mockReset().mockResolvedValue({ data: { product: { product_id: "p1", product_name: "Smart Term", leads: 2, issued: 1, premium: 119000 }, leads: [{ id: "c1", case_code: "AFS-INS-1", customer_id: "u1", customer_name: "Chandra", advisor_name: "Kishan", stage: "policy_issued" }] }, pagination: null });
});

function renderPage() {
  return render(<MemoryRouter initialEntries={["/insurance-management/analytics"]}><Routes><Route path="/insurance-management/analytics" element={<InsuranceAnalyticsPage />} /><Route path="/insurance-management/policy-issued" element={<div>Issued list</div>} /></Routes></MemoryRouter>);
}

describe("InsuranceAnalyticsPage", () => {
  it("renders separate summaries, advisor work, pipeline navigation and product drill-down", async () => {
    const user = userEvent.setup(); renderPage();
    expect(screen.getByLabelText("Loading insurance analytics")).toBeInTheDocument();
    expect(await screen.findByText("Advisor Business Analytics")).toBeInTheDocument();
    expect(screen.getByText("Policy Pipeline Analytics")).toBeInTheDocument();
    expect(screen.getByText("Product Analytics")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View Work" }));
    expect(await screen.findByRole("dialog", { name: "Kishan" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: "Smart Term" }));
    expect(await screen.findByText("AFS-INS-1")).toBeInTheDocument();
  });

  it("applies filters and opens the existing stage list", async () => {
    const user = userEvent.setup(); renderPage();
    await screen.findByText("Policy Pipeline Analytics");
    await user.selectOptions(screen.getByLabelText("Advisor"), "a1");
    await waitFor(() => expect(getAnalyticsOverview).toHaveBeenLastCalledWith(expect.objectContaining({ advisor_id: "a1" })));
    await user.click(screen.getByRole("button", { name: /Policy Issued 1/ }));
    expect(await screen.findByText("Issued list")).toBeInTheDocument();
  });

  it("distinguishes an API failure from an empty result and offers retry", async () => {
    getAnalyticsOverview.mockRejectedValueOnce(new Error("analytics unavailable"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Please try again.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("renders successful empty states without treating them as an error", async () => {
    getAnalyticsOverview.mockResolvedValue({
      ...overview,
      summary: { total_advisors: 0, total_business: 0, business_premium: 0, total_policy_leads: 0, total_policy_issued: 0, policy_premium: 0 },
      pipeline: [],
      advisors: [],
      products: [],
    });
    listAdvisorAnalytics.mockResolvedValue({ data: [], pagination: { page: 1, page_size: 10, total: 0, total_pages: 0 } });
    listProductAnalytics.mockResolvedValue({ data: [], pagination: { page: 1, page_size: 10, total: 0, total_pages: 0 } });
    renderPage();
    expect(await screen.findByText("No advisor business records found for the selected filters.")).toBeInTheDocument();
    expect(screen.getByText("No policy leads found for the selected filters.")).toBeInTheDocument();
    expect(screen.getByText("No product activity found for the selected filters.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not render advisor analytics when the backend capability is absent", async () => {
    getAnalyticsOverview.mockResolvedValue({
      ...overview,
      capabilities: { advisor_business: false, policy_pipeline: true },
      summary: { ...overview.summary, total_advisors: null, total_business: null, business_premium: null },
      advisors: [],
    });
    renderPage();
    await screen.findByText("Policy Pipeline Analytics");
    expect(screen.queryByText("Advisor Business Analytics")).not.toBeInTheDocument();
    expect(listAdvisorAnalytics).not.toHaveBeenCalled();
  });
});
