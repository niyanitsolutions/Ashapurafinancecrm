import {
  activateDepartment,
  createDepartment,
  deactivateDepartment,
  listDepartments,
  updateDepartment,
} from "@/features/system_settings/api";
import { NamedMasterDataPage } from "@/features/system_settings/pages/NamedMasterDataPage";

// Departments already had list/create in Module 2 (no frontend page yet — full
// management UI was deferred here, decision 019); edit/activate/deactivate are Module 4's.
const api = {
  list: listDepartments,
  create: createDepartment,
  update: updateDepartment,
  activate: activateDepartment,
  deactivate: deactivateDepartment,
};

export function DepartmentsPage() {
  return <NamedMasterDataPage title="Departments" createPlaceholder="e.g. Loan" api={api} />;
}
