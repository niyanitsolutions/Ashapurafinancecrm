import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Permission } from "@/features/access_control/api";
import { MODULE_ENABLED } from "@/features/employee/permissionMatrix";
import { PermissionMatrixSection } from "./PermissionMatrixSection";

const permissions: Permission[] = [
  { id: "root", module: "insurance_management", resource: "__module__", actions: ["view", "create", "edit"], label: "Insurance Management", node_type: "module", parent_resource: null },
  { id: "recruitment", module: "insurance_management", resource: "recruitment", actions: ["view", "create", "edit"], label: "Recruitment Leads", node_type: "page", parent_resource: "__module__" },
];

function Harness() {
  const [checked, setChecked] = useState<Record<string, Set<string>>>({
    root: new Set([MODULE_ENABLED, "view", "create", "edit"]),
  });
  return <PermissionMatrixSection permissions={permissions} checked={checked} onChange={setChecked} />;
}

function EmptyHarness() {
  const [checked, setChecked] = useState<Record<string, Set<string>>>({});
  return <PermissionMatrixSection permissions={permissions} checked={checked} onChange={setChecked} />;
}

describe("PermissionMatrixSection hierarchy", () => {
  it("renders an expandable tree and cycles a child from inherited to allow to deny", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getAllByText("Insurance Management")).toHaveLength(2);
    const inherited = screen.getByRole("button", { name: "Recruitment Leads Create: Inherited Yes" });
    await user.click(inherited);
    const allowed = screen.getByRole("button", { name: "Recruitment Leads Create: Override Yes" });
    await user.click(allowed);
    expect(screen.getByRole("button", { name: "Recruitment Leads Create: Override No" })).toBeInTheDocument();
  });

  it("enables the module and View when a module Create or Edit action is selected", async () => {
    const user = userEvent.setup();
    render(<EmptyHarness />);

    await user.click(screen.getByRole("checkbox", { name: "Insurance Management — Create" }));
    expect(screen.getByRole("checkbox", { name: "Insurance Management module enabled" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Insurance Management — View" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Recruitment Leads Create: Inherited Yes" })).toBeInTheDocument();
  });

  it("keeps an explicit child Create override valid when the module View default is cleared", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Recruitment Leads Create: Inherited Yes" }));
    await user.click(screen.getByRole("checkbox", { name: "Insurance Management — View" }));

    expect(screen.getByRole("button", { name: "Recruitment Leads View: Override Yes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recruitment Leads Create: Override Yes" })).toBeInTheDocument();
  });
});
