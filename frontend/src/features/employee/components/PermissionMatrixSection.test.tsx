import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Permission } from "@/features/access_control/api";
import { DENY_PREFIX, MODULE_ENABLED } from "@/features/employee/permissionMatrix";
import { PermissionMatrixSection } from "./PermissionMatrixSection";

const permissions: Permission[] = [
  { id: "root", module: "insurance_management", resource: "__module__", actions: ["view", "create", "edit"], label: "Insurance Management", node_type: "module", parent_resource: null },
  { id: "recruitment", module: "insurance_management", resource: "recruitment", actions: ["view", "create", "edit"], label: "Recruitment Leads", node_type: "page", parent_resource: "__module__" },
  { id: "documents", module: "insurance_management", resource: "documents", actions: ["view"], label: "Documents", node_type: "page", parent_resource: "__module__" },
];

type Snapshot = Record<string, Set<string>>;

function Harness({ initial = { root: new Set([MODULE_ENABLED, "view", "create", "edit"]) }, onSnapshot }: { initial?: Snapshot; onSnapshot?: (next: Snapshot) => void }) {
  const [checked, setChecked] = useState<Snapshot>(initial);
  const handleChange = (next: Snapshot) => {
    setChecked(next);
    onSnapshot?.(next);
  };
  return <PermissionMatrixSection permissions={permissions} checked={checked} onChange={handleChange} />;
}

describe("PermissionMatrixSection hierarchy", () => {
  it("renders the accessible hierarchy without exposing implementation terminology", () => {
    render(<Harness />);

    expect(screen.getByRole("columnheader", { name: /view/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /create/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /edit/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collapse Insurance Management" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Recruitment Leads")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Can add Recruitment Leads" })).toBeChecked();
    expect(screen.getByLabelText("Create not available for Documents")).toHaveTextContent("—");
    expect(screen.queryByText(/Inherited|Explicit Allow|Explicit Deny|parent_resource|node_type/i)).not.toBeInTheDocument();
  });

  it("collapses from the module header and expands again", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Collapse Insurance Management" }));
    expect(screen.queryByText("Recruitment Leads")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Expand Insurance Management" }));
    expect(screen.getByText("Recruitment Leads")).toBeInTheDocument();
  });

  it("filters child rows while retaining their module context", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByRole("textbox", { name: "Search permissions" }), "recruitment");
    expect(screen.getByText("Insurance Management")).toBeInTheDocument();
    expect(screen.getByText("Recruitment Leads")).toBeInTheDocument();
    expect(screen.queryByText("Documents")).not.toBeInTheDocument();
  });

  it("preserves module action dependencies in the underlying selection state", async () => {
    const user = userEvent.setup();
    let latest: Snapshot = {};
    render(<Harness initial={{}} onSnapshot={(next) => { latest = next; }} />);

    await user.click(screen.getByRole("checkbox", { name: "Can add Insurance Management" }));
    expect(latest.root).toEqual(new Set([MODULE_ENABLED, "create", "view"]));
    expect(screen.getByRole("checkbox", { name: "Enable Insurance Management" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Can view Insurance Management" })).toBeChecked();
  });

  it("keeps the existing inherited-to-allow-to-deny child state cycle", async () => {
    const user = userEvent.setup();
    let latest: Snapshot = {};
    render(<Harness onSnapshot={(next) => { latest = next; }} />);
    const row = screen.getByText("Recruitment Leads").closest(".grid");
    expect(row).not.toBeNull();
    const create = within(row as HTMLElement).getByRole("checkbox", { name: "Can add Recruitment Leads" });

    await user.click(create);
    expect(latest.recruitment).toEqual(new Set(["create"]));
    expect(create).toBeChecked();

    await user.click(create);
    expect(latest.recruitment).toEqual(new Set([`${DENY_PREFIX}create`]));
    expect(create).not.toBeChecked();
  });
});
