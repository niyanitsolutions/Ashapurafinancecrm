import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NewSchemaModal } from "./NewSchemaModal";
import type { CreatableProduct, FormDefinition } from "@/features/customer/api";

const listCreatableProducts = vi.fn();
const createProductSchema = vi.fn(() => Promise.resolve({ id: "schema-99" } as FormDefinition));

vi.mock("@/features/customer/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/customer/api")>("@/features/customer/api");
  return {
    ...actual,
    listCreatableProducts: (...a: unknown[]) => listCreatableProducts(...(a as [])),
    createProductSchema: (...a: unknown[]) => createProductSchema(...(a as [])),
  };
});

const insuranceProducts: CreatableProduct[] = [
  { id: "p1", name: "Family Health Plus", product_category: "insurance", category_id: "c1", category_name: "Health Insurance" },
];
const loanProducts: CreatableProduct[] = [
  { id: "lp1", name: "Personal Loan", product_category: "loan", category_id: null, category_name: null },
];

describe("NewSchemaModal", () => {
  it("loads creatable products for the chosen category and creates a schema", async () => {
    listCreatableProducts.mockImplementation((cat: string) =>
      Promise.resolve(cat === "insurance" ? insuranceProducts : loanProducts),
    );
    const onCreated = vi.fn();
    const user = userEvent.setup();
    render(<NewSchemaModal onClose={vi.fn()} onCreated={onCreated} />);

    // Insurance is the default; product option shows its category.
    await screen.findByRole("option", { name: "Family Health Plus — Health Insurance" });

    // Switch to Loan → reloads.
    await user.selectOptions(screen.getByLabelText("Product Category"), "loan");
    await waitFor(() => expect(listCreatableProducts).toHaveBeenLastCalledWith("loan"));
    await screen.findByRole("option", { name: "Personal Loan" });

    await user.selectOptions(screen.getByLabelText("Product Category"), "insurance");
    await screen.findByRole("option", { name: "Family Health Plus — Health Insurance" });
    await user.selectOptions(screen.getByLabelText("Product"), "p1");
    await user.click(screen.getByRole("button", { name: /create & configure/i }));

    await waitFor(() =>
      expect(createProductSchema).toHaveBeenCalledWith({
        product_category: "insurance",
        product_id: "p1",
        fields: [],
        required_documents: [],
      }),
    );
    expect(onCreated).toHaveBeenCalledWith("schema-99");
  });

  it("shows a message when every product already has a schema", async () => {
    listCreatableProducts.mockResolvedValue([]);
    render(<NewSchemaModal onClose={vi.fn()} onCreated={vi.fn()} />);
    expect(await screen.findByText(/already has a schema/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create & configure/i })).toBeDisabled();
  });
});
