import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InsuranceManagementLayout } from "./InsuranceManagementLayout";

const getInsuranceCaseCounts = vi.fn();
let navKeys = new Set(["insurance_cases", "recruitment_leads"]);
let applicationsOnly = false;
vi.mock("@/features/insurance_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/insurance_management/api")>("@/features/insurance_management/api");
  return { ...actual, getInsuranceCaseCounts: (...a: unknown[]) => getInsuranceCaseCounts(...(a as [])) };
});

vi.mock("@/components/layout/useNavKeys", () => ({
  useNavKeys: () => navKeys,
}));
vi.mock("@/features/access_control/usePermissions", () => ({
  usePermissions: () => ({
    can: (resource: string) => !applicationsOnly || resource.startsWith("insurance_management:applications"),
    loading: false,
  }),
}));

beforeEach(() => {
  navKeys = new Set(["insurance_cases", "recruitment_leads"]);
  applicationsOnly = false;
  getInsuranceCaseCounts.mockReset();
  getInsuranceCaseCounts.mockRejectedValue(new Error("no counts"));
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/insurance-management" element={<InsuranceManagementLayout />}>
          <Route path="fresh-leads" element={<div>stage list</div>} />
          <Route path="recruitment" element={<div>recruitment list</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("InsuranceManagementLayout", () => {
  it("shows the Policy Leads pipeline sub-tabs (old underwriting/premium tabs gone) on a Policy Leads route", () => {
    renderAt("/insurance-management/fresh-leads");

    for (const label of ["Fresh Leads", "Policy Document", "Policy Login", "Policy Issued", "Re-Eligible", "Rejected", "On Hold", "Settings"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "On Hold" })).toHaveAttribute("href", "/insurance-management/on-hold");
    expect(screen.queryByRole("link", { name: "Underwriting" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Premium Acceptance/ })).not.toBeInTheDocument();

    // Settings links out to the category-aware Product Schema Engine.
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      "/settings/product-schemas?category=insurance",
    );
  });

  it("hides the Policy Leads sub-tabs on the Recruitment route", () => {
    renderAt("/insurance-management/recruitment");
    expect(screen.queryByRole("link", { name: "Policy Document" })).not.toBeInTheDocument();
  });

  it("shows a live server-computed count badge on every Policy Leads stage tab", async () => {
    getInsuranceCaseCounts.mockResolvedValue({
      fresh_lead: 5, policy_document: 3, policy_login: 2, policy_issued: 8, re_eligible: 1, rejected: 4, on_hold: 2,
    });
    renderAt("/insurance-management/fresh-leads");

    await waitFor(() => expect(screen.getByRole("link", { name: "Fresh Leads 5" })).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Policy Document 3" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "On Hold 2" })).toBeInTheDocument();
    // Settings has no count.
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  it("orders the top tabs Policy Leads, Recruitment Leads, Advisors", () => {
    renderAt("/insurance-management/recruitment");
    const top = ["Policy Leads", "Recruitment Leads", "Advisors"].map(
      (label) => screen.getByRole("link", { name: label }),
    );
    expect(top.map((el) => el.textContent)).toEqual(["Policy Leads", "Recruitment Leads", "Advisors"]);
    // DOM order matches.
    expect(top[0].compareDocumentPosition(top[1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(top[1].compareDocumentPosition(top[2]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("hides unrelated workflows from an employee with only Policy Leads access", async () => {
    navKeys = new Set(["insurance_cases"]);
    applicationsOnly = true;
    getInsuranceCaseCounts.mockResolvedValue({
      fresh_lead: 0, policy_document: 0, policy_login: 0, payment: 0,
      policy_issued: 0, re_eligible: 0, rejected: 0, on_hold: 0,
    });
    renderAt("/insurance-management/fresh-leads");

    for (const label of ["Policy Leads", "Fresh Leads 0", "Policy Document 0", "Policy Login 0", "Payment 0", "Policy Issued 0", "Re-Eligible 0", "Rejected 0", "On Hold 0", "Settings"]) {
      expect(await screen.findByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("link", { name: "Recruitment Leads" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Advisors" })).not.toBeInTheDocument();
  });
});
