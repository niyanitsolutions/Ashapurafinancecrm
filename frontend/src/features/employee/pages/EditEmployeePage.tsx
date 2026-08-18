import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import {
  assignRole,
  createRole,
  getRole,
  getRolePermissions,
  listEmployeeRoles,
  listPermissions,
  setRolePermissions,
  type Permission,
} from "@/features/access_control/api";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { PermissionMatrixSection } from "@/features/employee/components/PermissionMatrixSection";
import { sanitizeGrantedActions } from "@/features/access_control/permissionHierarchy";
import {
  getEmployee,
  listBranches,
  listDepartments,
  listDesignations,
  updateEmployee,
  type BranchItem,
  type MasterDataItem,
} from "@/features/employee/api";
import { MATRIX_ACTIONS, PERMISSION_MATRIX_ROWS, buildMatrixGrants } from "@/features/employee/permissionMatrix";
import { getErrorMessage } from "@/features/employee/errors";
import { updateEmployeeSchema, type UpdateEmployeeFormValues } from "@/features/employee/validation";

// The role this employee's Business Modules section reads from / writes to — the one
// CreateEmployeePage.tsx auto-creates, identified by its description rather than by name
// (names are freeform, e.g. an Owner might rename it). Never shown to the Owner as
// "role" — purely an internal lookup key.
const AUTO_ROLE_DESCRIPTION = "Created automatically from Add Employee";

export function EditEmployeePage() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const navigate = useNavigate();
  const [apiError, setApiError] = useState<string | null>(null);
  const [departments, setDepartments] = useState<MasterDataItem[]>([]);
  const [designations, setDesignations] = useState<MasterDataItem[]>([]);
  const [branches, setBranches] = useState<BranchItem[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);

  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [permissionsLoadFailed, setPermissionsLoadFailed] = useState(false);
  const [personalRoleId, setPersonalRoleId] = useState<string | null>(null);
  const [hasExtraAccess, setHasExtraAccess] = useState(false);
  const [checkedPermissions, setCheckedPermissions] = useState<Record<string, Set<string>>>({});

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<UpdateEmployeeFormValues>({ resolver: zodResolver(updateEmployeeSchema) });

  useEffect(() => {
    listDepartments().then(setDepartments).catch(() => setDepartments([]));
    listDesignations().then(setDesignations).catch(() => setDesignations([]));
    listBranches().then(setBranches).catch(() => setBranches([]));
    // Distinguish "catalog genuinely fetched, nothing in it" from "fetch failed" — the
    // latter must never be treated as "grant nothing" by onSubmit's full-replace call to
    // setRolePermissions (see permissionsLoadFailed below).
    listPermissions()
      .then((data) => {
        setPermissions(data);
        setPermissionsLoadFailed(false);
      })
      .catch(() => {
        setPermissions([]);
        setPermissionsLoadFailed(true);
      });
  }, []);

  useEffect(() => {
    if (!employeeId) return;
    getEmployee(employeeId).then((e) => {
      reset({
        first_name: e.first_name,
        last_name: e.last_name,
        display_name: e.display_name,
        gender: (e.gender as UpdateEmployeeFormValues["gender"]) ?? undefined,
        date_of_birth: e.date_of_birth?.slice(0, 10),
        blood_group: e.blood_group ?? undefined,
        email: e.email,
        alternative_mobile: e.alternative_mobile ?? undefined,
        department_id: e.department_id,
        designation_id: e.designation_id,
        branch_id: e.branch_id,
        joining_date: e.joining_date?.slice(0, 10),
        employment_type: e.employment_type as UpdateEmployeeFormValues["employment_type"],
        status: e.status as UpdateEmployeeFormValues["status"],
      });
      setIsLoaded(true);
    });
  }, [employeeId, reset]);

  // Finds this employee's personal auto-created role (if any) and pre-populates the
  // Permissions matrix from its current grants — see AUTO_ROLE_DESCRIPTION above.
  useEffect(() => {
    if (!employeeId) return;
    listEmployeeRoles(employeeId)
      .then(async (assignments) => {
        let personal: string | null = null;
        for (const assignment of assignments) {
          const role = await getRole(assignment.role_id);
          if (role.description === AUTO_ROLE_DESCRIPTION) {
            personal = assignment.role_id;
            break;
          }
        }
        setPersonalRoleId(personal);
        setHasExtraAccess(assignments.some((a) => a.role_id !== personal));
        if (!personal) return;

        const grants = await getRolePermissions(personal);
        const nextChecked: Record<string, Set<string>> = {};
        for (const grant of grants) {
          const row = PERMISSION_MATRIX_ROWS.find((r) => r.module === grant.module && r.resource === grant.resource);
          if (!row) continue; // a grant outside this simplified 8-row matrix — no checkbox to set
          const relevant = grant.granted_actions.filter((a) => a === "view" || a === "create" || a === "edit");
          nextChecked[grant.permission_id] = sanitizeGrantedActions(relevant, MATRIX_ACTIONS);
        }
        setCheckedPermissions(nextChecked);
      })
      .catch(() => {
        // One bad/orphaned role reference (e.g. a stale EmployeeRole pointing at a
        // deleted role) must not silently leave the Permissions section looking empty
        // with no explanation — surface it instead of failing invisibly.
        setApiError("Couldn't load this employee's current permissions. Please refresh and try again before saving.");
      });
  }, [employeeId]);

  if (!employeeId) return null;

  const onSubmit = async (values: UpdateEmployeeFormValues) => {
    setApiError(null);

    // The Permissions save below is a full replace (setRolePermissions soft-deletes every
    // existing grant on the role and inserts only what buildMatrixGrants returns) — if the
    // permission catalog failed to load, buildMatrixGrants can't resolve any row and would
    // silently return an empty grant list regardless of what's actually checked, wiping
    // this employee's real permissions with no error shown. Block the save instead.
    if (permissionsLoadFailed) {
      setApiError("Permissions couldn't be loaded, so saving now would erase this employee's existing access. Please refresh the page and try again.");
      return;
    }

    try {
      // product_ids is intentionally omitted here — this form no longer edits Product
      // Specialization; omitting the field (rather than sending []) preserves whatever
      // value this employee already has, per UpdateEmployeeRequest's "omitted = don't
      // touch" contract.
      await updateEmployee(employeeId, values);

      // Permissions matrix — same convenience layer on top of Access Control (Module 3)
      // CreateEmployeePage.tsx uses, just reading from / writing to this employee's
      // existing personal role instead of always creating a new one.
      const activeGrants = buildMatrixGrants(permissions, checkedPermissions);
      if (personalRoleId) {
        await setRolePermissions(personalRoleId, activeGrants);
      } else if (activeGrants.length > 0) {
        const role = await createRole(`${values.first_name} ${values.last_name}`, "Created automatically from Add Employee");
        await setRolePermissions(role.id, activeGrants);
        await assignRole(role.id, employeeId);
      }

      navigate(`/employees/${employeeId}`);
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Edit Employee" backTo={`/employees/${employeeId}`}>
      {!isLoaded ? (
        <p className="text-sm text-text/50">Loading…</p>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="max-w-4xl mx-auto space-y-6">
          <ErrorBanner message={apiError} />

          <div className="bg-card border border-border rounded-card shadow-card p-6">
            <h2 className="text-sm font-semibold text-text mb-1">Personal</h2>
            <p className="text-xs text-text/50 mb-4">Who they are.</p>
            <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
              <FormField label="First name" error={errors.first_name?.message} {...register("first_name")} />
              <FormField label="Last name" error={errors.last_name?.message} {...register("last_name")} />
              <FormField label="Display name" error={errors.display_name?.message} {...register("display_name")} />
              <SelectField
                label="Gender"
                placeholder="Select"
                options={[{ value: "male", label: "Male" }, { value: "female", label: "Female" }, { value: "other", label: "Other" }]}
                error={errors.gender?.message}
                {...register("gender")}
              />
              <FormField label="Date of birth" type="date" error={errors.date_of_birth?.message} {...register("date_of_birth")} />
              <FormField label="Blood group" error={errors.blood_group?.message} {...register("blood_group")} />
            </div>
          </div>

          <div className="bg-card border border-border rounded-card shadow-card p-6">
            <h2 className="text-sm font-semibold text-text mb-1">Contact</h2>
            <p className="text-xs text-text/50 mb-4">How to reach them.</p>
            <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
              <FormField label="Email" type="email" error={errors.email?.message} {...register("email")} />
              <FormField label="Alternative mobile" maxLength={10} error={errors.alternative_mobile?.message} {...register("alternative_mobile")} />
            </div>
          </div>

          <div className="bg-card border border-border rounded-card shadow-card p-6">
            <h2 className="text-sm font-semibold text-text mb-1">Employment</h2>
            <p className="text-xs text-text/50 mb-4">Where they sit in your company.</p>
            <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
              <SelectField
                label="Department"
                options={departments.map((d) => ({ value: d.id, label: d.name }))}
                error={errors.department_id?.message}
                {...register("department_id")}
              />
              <SelectField
                label="Designation"
                options={designations.map((d) => ({ value: d.id, label: d.name }))}
                error={errors.designation_id?.message}
                {...register("designation_id")}
              />
              <SelectField
                label="Branch"
                options={branches.map((b) => ({ value: b.id, label: b.name }))}
                error={errors.branch_id?.message}
                {...register("branch_id")}
              />
              <SelectField
                label="Employment type"
                options={[
                  { value: "full_time", label: "Full-time" },
                  { value: "part_time", label: "Part-time" },
                  { value: "contract", label: "Contract" },
                  { value: "intern", label: "Intern" },
                ]}
                error={errors.employment_type?.message}
                {...register("employment_type")}
              />
              <FormField label="Joining date" type="date" error={errors.joining_date?.message} {...register("joining_date")} />
              <SelectField
                label="Status"
                options={[
                  { value: "active", label: "Active" },
                  { value: "inactive", label: "Inactive" },
                  { value: "suspended", label: "Suspended" },
                  { value: "on_leave", label: "On Leave" },
                  { value: "resigned", label: "Resigned" },
                ]}
                error={errors.status?.message}
                {...register("status")}
              />
            </div>
          </div>

          <PermissionMatrixSection permissions={permissions} checked={checkedPermissions} onChange={setCheckedPermissions} />
          {permissionsLoadFailed && (
            <p className="text-xs text-danger -mt-4">
              Couldn't load the permission catalog — saving is disabled until this page is refreshed, to avoid
              accidentally clearing this employee's existing access.
            </p>
          )}
          {hasExtraAccess && (
            <p className="text-xs text-text/50 -mt-4">
              This employee may have extra access configured separately — see Roles &amp; Permissions for details.
            </p>
          )}

          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => navigate(`/employees/${employeeId}`)}>
              Cancel
            </Button>
            <SubmitButton isSubmitting={isSubmitting}>Save Changes</SubmitButton>
          </div>
        </form>
      )}
    </SimplePageLayout>
  );
}
