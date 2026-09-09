import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { InsuranceManagementLayout } from "./InsuranceManagementLayout";

vi.mock("@/components/layout/useNavKeys", () => ({
  useNavKeys: () => new Set(["insurance_cases", "recruitment_leads"]),
}));

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

    for (const label of ["Fresh Leads", "Policy Document", "Policy Login", "Policy Issued", "Re-Eligible", "Rejected", "Settings"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
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
});
