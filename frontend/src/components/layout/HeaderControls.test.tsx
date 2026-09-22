import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { DashboardFiltersProvider, useDashboardFilters } from "@/features/dashboard/DashboardFiltersContext";
import { DateScopePill, FiltersButton } from "./HeaderControls";

function CurrentFilters() {
  const { filters } = useDashboardFilters();
  return <output data-testid="filters">{JSON.stringify(filters)}</output>;
}

function setup() {
  render(<DashboardFiltersProvider><DateScopePill /><FiltersButton /><CurrentFilters /></DashboardFiltersProvider>);
  return userEvent.setup();
}

describe("Dashboard header filters", () => {
  it("opens and validates a custom range before applying inclusive dates", async () => {
    const user = setup();
    await user.click(screen.getByRole("button", { name: "This Month" }));
    await user.click(screen.getByRole("button", { name: "Custom" }));
    const apply = screen.getByRole("button", { name: "Apply custom range" });
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Start Date"), { target: { value: "2026-09-22" } });
    fireEvent.change(screen.getByLabelText("End Date"), { target: { value: "2026-09-21" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Start Date cannot be after End Date");
    expect(apply).toBeDisabled();
    expect(screen.getByTestId("filters")).toHaveTextContent('"range":"this_month"');
    fireEvent.change(screen.getByLabelText("End Date"), { target: { value: "2026-09-22" } });
    await user.click(apply);
    expect(JSON.parse(screen.getByTestId("filters").textContent!)).toEqual({ range: "custom", startDate: "2026-09-22", endDate: "2026-09-22" });
    expect(screen.queryByLabelText("Start Date")).not.toBeInTheDocument();
  });

  it("applies product filters only on Apply and clears them without resetting the period", async () => {
    const user = setup();
    await user.click(screen.getByRole("button", { name: "This Month" }));
    await user.click(screen.getByRole("button", { name: "Last Week" }));
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.selectOptions(screen.getByLabelText("Product"), "insurance");
    expect(screen.getByTestId("filters")).not.toHaveTextContent("insurance");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(JSON.parse(screen.getByTestId("filters").textContent!)).toEqual({ range: "last_week", productCategory: "insurance" });
    await user.click(screen.getByRole("button", { name: "Filters (1)" }));
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(JSON.parse(screen.getByTestId("filters").textContent!)).toEqual({ range: "last_week" });
  });

  it("dismisses drafts on Escape and restores applied values on reopening", async () => {
    const user = setup();
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.selectOptions(screen.getByLabelText("Product"), "loan");
    await user.keyboard("{Escape}");
    expect(screen.queryByLabelText("Product")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByLabelText("Product")).toHaveValue("");
  });
});
