import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";

vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ setSession: vi.fn() }) }));
vi.mock("@/features/auth/pinApi", () => ({pinPolicy: async () => ({mode: "enrollment"})}));
vi.mock("@/features/auth/api", () => ({ login: vi.fn() }));

function renderPage(entry = "/login") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe("LoginPage default tab", () => {
  it("opens with the Customer tab selected and the Customer login form visible", async () => {
    await act(async () => { renderPage(); });
    expect(screen.getByRole("tab", { name: "Customer" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Employee / Partner" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("heading", { name: "Customer Login" })).toBeInTheDocument();
  });

  it("still opens on Customer even for a returning secure-application link", async () => {
    await act(async () => { renderPage("/login?return=%2Fapply%2Fabc123"); });
    expect(screen.getByRole("tab", { name: "Customer" })).toHaveAttribute("aria-selected", "true");
  });

  it("orders the customer links, preserves the registration return path and opens migration", async () => {
    await act(async () => { renderPage("/login?return=%2Fapply%2Fabc123"); });
    const forgot = screen.getByRole("button", { name: "Forgot PIN" });
    const create = within(forgot.closest(".customer-pin-panel") as HTMLElement).getByRole("link", { name: "Create New Account" });
    const migration = screen.getByRole("button", { name: "Existing account migration: password sign-in" });
    expect(screen.queryByText("First-time verification / Create PIN")).not.toBeInTheDocument();
    expect(forgot.compareDocumentPosition(create) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(create.compareDocumentPosition(migration) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(create).toHaveAttribute("href", "/create-account?return=%2Fapply%2Fabc123");
    await userEvent.setup().click(migration);
    expect(document.getElementById("customer-password")).toBeVisible();
    await userEvent.setup().click(screen.getByRole("button", { name: "Use customer PIN sign-in" }));
    expect(screen.getByLabelText("4-digit PIN")).toBeVisible();
  });

  it("switching to Employee / Partner still works", async () => {
    renderPage();
    await userEvent.setup().click(screen.getByRole("tab", { name: "Employee / Partner" }));
    expect(screen.getByRole("tab", { name: "Employee / Partner" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Employee / Partner Login" })).toBeInTheDocument();
    expect(document.getElementById("internal-password")).toBeVisible();
    expect(screen.getByLabelText("4-digit PIN")).not.toBeVisible();
    expect(screen.queryByRole("button", { name: "Forgot PIN" })).not.toBeInTheDocument();
  });
});
