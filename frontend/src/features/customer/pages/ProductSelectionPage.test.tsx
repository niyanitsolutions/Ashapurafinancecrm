import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProductSelectionPage } from "./ProductSelectionPage";
import type { NamedMasterData } from "@/features/system_settings/api";

const listPortalProducts = vi.fn();
const listPortalInsuranceCategories = vi.fn();
const listOwnApplications = vi.fn(() => Promise.resolve([]));

vi.mock("@/features/customer/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/customer/api")>("@/features/customer/api");
  return {
    ...actual,
    listPortalProducts: (...a: unknown[]) => listPortalProducts(...(a as [])),
    listPortalInsuranceCategories: (...a: unknown[]) => listPortalInsuranceCategories(...(a as [])),
    listOwnApplications: () => listOwnApplications(),
  };
});

const cat = (id: string, name: string): NamedMasterData => ({
  id,
  name,
  description: null,
  status: "active",
  created_at: "",
  updated_at: "",
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/portal/applications/new" element={<ProductSelectionPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProductSelectionPage", () => {
  beforeEach(() => {
    listPortalProducts.mockReset();
    listPortalInsuranceCategories.mockReset();
    listOwnApplications.mockReset().mockResolvedValue([]);
  });

  it("insurance is a two-step flow: category first, then category-scoped products", async () => {
    listPortalInsuranceCategories.mockResolvedValue([cat("c1", "Health Insurance"), cat("c2", "Life Insurance")]);
    listPortalProducts.mockResolvedValue([cat("p1", "Family Health Plus")]);
    const user = userEvent.setup();
    renderAt("/portal/applications/new?category=insurance");

    await screen.findByText("Choose an insurance category");
    expect(screen.getByText("Health Insurance")).toBeInTheDocument();
    expect(listPortalProducts).not.toHaveBeenCalled();

    await user.click(screen.getByText("Health Insurance"));
    await waitFor(() =>
      expect(listPortalProducts).toHaveBeenCalledWith("insurance", { insuranceCategoryId: "c1" }),
    );
    await screen.findByText("Family Health Plus");
  });

  it("loan stays a one-step flat product list", async () => {
    listPortalProducts.mockResolvedValue([cat("lp1", "Personal Loan")]);
    renderAt("/portal/applications/new?category=loan");

    await screen.findByText("Personal Loan");
    expect(listPortalProducts).toHaveBeenCalledWith("loan");
    expect(listPortalInsuranceCategories).not.toHaveBeenCalled();
    expect(screen.queryByText("Choose an insurance category")).not.toBeInTheDocument();
  });
});
