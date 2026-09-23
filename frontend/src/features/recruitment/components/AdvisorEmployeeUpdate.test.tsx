import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AuthContext, type AuthContextValue } from "@/features/auth/authContext";
import { AdvisorEmployeeUpdate } from "./AdvisorEmployeeUpdate";

const listEmployees = vi.fn();
vi.mock("@/features/employee/api", () => ({ listEmployees: (...args: unknown[]) => listEmployees(...args) }));

function renderAs(role: string) {
  return render(<AuthContext.Provider value={{ role } as AuthContextValue}><MemoryRouter><Routes>
    <Route path="/" element={<AdvisorEmployeeUpdate mobile="9876543210" isEmployee />} />
    <Route path="/employees/e1/edit" element={<span>Existing employee editor</span>} />
  </Routes></MemoryRouter></AuthContext.Provider>);
}

it("opens the existing Employee form for the Owner using an exact mobile match", async () => {
  listEmployees.mockResolvedValue({ data: [{ id: "e1", mobile: "9876543210" }] });
  renderAs("owner");
  await userEvent.click(screen.getByRole("button", { name: "Update Employee" }));
  expect(await screen.findByText("Existing employee editor")).toBeInTheDocument();
  expect(listEmployees).toHaveBeenCalledWith({ search: "9876543210", page_size: 100 });
});

it("hides employee update from roles the existing Employee API does not authorize", () => {
  renderAs("employee");
  expect(screen.queryByRole("button", { name: "Update Employee" })).not.toBeInTheDocument();
});
