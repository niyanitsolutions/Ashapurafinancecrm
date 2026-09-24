import { describe, expect, it } from "vitest";
import type { Permission } from "@/features/access_control/api";
import { PERMISSION_MATRIX_ROWS, buildMatrixGrants } from "./permissionMatrix";

const recruitmentPermission: Permission = {
  id: "permission-recruitment",
  module: "insurance_management",
  resource: "recruitment",
  actions: ["view", "create", "edit", "assign", "approve"],
  label: "Recruitment Leads",
};

describe("employee permission matrix", () => {
  it("exposes the existing Recruitment and Advisor permission resource", () => {
    expect(PERMISSION_MATRIX_ROWS).toContainEqual({
      module: "insurance_management",
      resource: "recruitment",
      label: "Recruitment Leads",
    });
  });

  it("saves Recruitment view/create/edit grants through the normal Employee editor", () => {
    expect(
      buildMatrixGrants(
        [recruitmentPermission],
        { [recruitmentPermission.id]: new Set(["view", "create", "edit"]) },
      ),
    ).toEqual([
      {
        permission_id: recruitmentPermission.id,
        granted_actions: ["view", "create", "edit"],
      },
    ]);
  });
});
