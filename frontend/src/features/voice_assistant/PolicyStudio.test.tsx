import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { PolicyStudio } from "./PolicyStudio";
import { policyReports, runPolicyReport } from "./api";
const state = vi.hoisted(() => ({ owner: true }));
vi.mock("@/features/access_control/usePermissions", () => ({ usePermissions: () => ({ isOwner: state.owner }) }));
vi.mock("./api", () => ({ policyReports: vi.fn(), runPolicyReport: vi.fn() }));
beforeEach(() => { vi.clearAllMocks(); state.owner = true; vi.mocked(policyReports).mockResolvedValue({ items: [], total: 0, suite_version: "test-suite" }); });
it("hides Owner studio from staff without fetching reports", () => {
  state.owner = false; render(<PolicyStudio />); expect(screen.queryByText("Synthetic policy regression")).not.toBeInTheDocument(); expect(policyReports).not.toHaveBeenCalled();
});
it("loads reports lazily and requires explicit suite execution", async () => {
  render(<PolicyStudio />); expect(policyReports).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Load policy test reports" })); await screen.findByText("No policy reports yet.");
  expect(runPolicyReport).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Run synthetic policy suite" }));
  expect(runPolicyReport).toHaveBeenCalledWith("test-suite", expect.any(String));
  expect(screen.getByText(/Passing does not approve a release/)).toBeInTheDocument();
});
