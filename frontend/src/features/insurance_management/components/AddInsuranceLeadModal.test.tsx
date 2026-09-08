import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AddInsuranceLeadModal } from "./AddInsuranceLeadModal";

const listPortalInsuranceCategories = vi.fn();
const listPortalProducts = vi.fn();
const createManualInsuranceCase = vi.fn();

vi.mock("@/features/customer/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/customer/api")>("@/features/customer/api");
  return {
    ...actual,
    listPortalInsuranceCategories: (...a: unknown[]) => listPortalInsuranceCategories(...(a as [])),
    listPortalProducts: (...a: unknown[]) => listPortalProducts(...(a as [])),
  };
});

vi.mock("@/features/insurance_management/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/insurance_management/api")>("@/features/insurance_management/api");
  return { ...actual, createManualInsuranceCase: (...a: unknown[]) => createManualInsuranceCase(...(a as [])) };
});

function renderModal() {
  return render(<AddInsuranceLeadModal onClose={vi.fn()} onCreated={vi.fn()} />);
}

async function fillCustomer(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Name"), "Ravi Kumar");
  await user.type(screen.getByLabelText("Mobile"), "9876543210");
  await user.type(screen.getByLabelText("Age"), "35");
}

describe("AddInsuranceLeadModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listPortalInsuranceCategories.mockResolvedValue([{ id: "cat-1", name: "Health Insurance" }]);
    listPortalProducts.mockResolvedValue([{ id: "prod-1", name: "Family Health Plus" }]);
  });

  it("loads products only after a category is chosen, scoped to that category", async () => {
    const user = userEvent.setup();
    renderModal();
    await screen.findByRole("option", { name: "Health Insurance" });

    expect(listPortalProducts).not.toHaveBeenCalled();
    await user.selectOptions(screen.getByLabelText("Insurance Category"), "cat-1");
    await waitFor(() => expect(listPortalProducts).toHaveBeenCalledWith("insurance", { insuranceCategoryId: "cat-1" }));
    await screen.findByRole("option", { name: "Family Health Plus" });
  });

  it("the Initial Stage dropdown offers only Fresh Lead / Policy Document / Re-Eligible / Rejected", async () => {
    renderModal();
    const select = await screen.findByLabelText("Initial Stage");
    const labels = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(labels).toEqual(["Fresh Lead", "Policy Document", "Re-Eligible", "Rejected"]);
  });

  it("reveals the 3 / 6 / 12 / Custom / No re-eligibility options (no 9-month) when Stage = Rejected", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.selectOptions(await screen.findByLabelText("Initial Stage"), "rejected");

    expect(screen.getByLabelText("3 Months")).toBeInTheDocument();
    expect(screen.getByLabelText("6 Months")).toBeInTheDocument();
    expect(screen.getByLabelText("12 Months")).toBeInTheDocument();
    expect(screen.queryByLabelText("9 Months")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Re-Eligible Date")).not.toBeInTheDocument();
    await user.click(screen.getByLabelText("Custom"));
    expect(screen.getByLabelText("Re-Eligible Date")).toBeInTheDocument();
  });

  it("submits a Fresh Lead payload", async () => {
    const user = userEvent.setup();
    createManualInsuranceCase.mockResolvedValue({ id: "c1" });
    renderModal();
    await fillCustomer(user);
    await user.selectOptions(screen.getByLabelText("Insurance Category"), "cat-1");
    await user.selectOptions(await screen.findByLabelText("Insurance Product"), "prod-1");
    await user.click(screen.getByRole("button", { name: "Create Insurance Lead" }));

    await waitFor(() => expect(createManualInsuranceCase).toHaveBeenCalled());
    expect(createManualInsuranceCase.mock.calls[0][0]).toMatchObject({
      full_name: "Ravi Kumar", mobile: "9876543210", age: 35,
      insurance_category_id: "cat-1", product_id: "prod-1", stage: "fresh_lead",
    });
  });
});
