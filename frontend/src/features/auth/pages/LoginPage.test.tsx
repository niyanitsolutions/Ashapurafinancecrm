import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";

vi.mock("@/features/auth/useAuth", () => ({ useAuth: () => ({ setSession: vi.fn() }) }));
vi.mock("@/features/auth/api", () => ({ login: vi.fn() }));

function renderPage(entry = "/login") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe("LoginPage default tab", () => {
  it("opens with the Customer tab selected and the Customer login form visible", () => {
    renderPage();
    expect(screen.getByRole("tab", { name: "Customer" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Employee / Partner" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("heading", { name: "Customer Login" })).toBeInTheDocument();
  });

  it("still opens on Customer even for a returning secure-application link", () => {
    renderPage("/login?return=%2Fapply%2Fabc123");
    expect(screen.getByRole("tab", { name: "Customer" })).toHaveAttribute("aria-selected", "true");
  });

  it("switching to Employee / Partner still works", async () => {
    renderPage();
    await userEvent.setup().click(screen.getByRole("tab", { name: "Employee / Partner" }));
    expect(screen.getByRole("tab", { name: "Employee / Partner" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Employee / Partner Login" })).toBeInTheDocument();
  });
});
