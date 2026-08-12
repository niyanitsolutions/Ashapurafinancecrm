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
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { BusinessModulesSection } from "@/features/employee/components/BusinessModulesSection";
import {
  getEmployee,
  listBranches,
  listDepartments,
  listDesignations,
  updateEmployee,
  type BranchItem,
  type MasterDataItem,
} from "@/features/employee/api";
import { BUSINESS_MODULES, buildModuleGrants } from "@/features/employee/businessModules";
import { getErrorMessage } from "@/features/employee/errors";
import { updateEmployeeSchema, type UpdateEmployeeFormValues } from "@/features/employee/validation";
import { insuranceProductsApi, loanProductsApi, type NamedMasterData } from "@/features/system_settings/api";

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
  const [loanProducts, setLoanProducts] = useState<NamedMasterData[]>([]);
  const [insuranceProducts, setInsuranceProducts] = useState<NamedMasterData[]>([]);
  const [productIds, setProductIds] = useState<string[]>([]);

  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [personalRoleId, setPersonalRoleId] = useState<string | null>(null);
  const [hasExtraAccess, setHasExtraAccess] = useState(false);
  const [selectedModules, setSelectedModules] = useState<Set<string>>(new Set());
  const [capabilities, setCapabilities] = useState<Record<string, Set<string>>>({});

  const toggleProduct = (productId: string) => {
    setProductIds((prev) => (prev.includes(productId) ? prev.filter((id) => id !== productId) : [...prev, productId]));
  };

  const toggleModule = (key: string) => {
    setSelectedModules((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleCapability = (permissionId: string, action: string) => {
    setCapabilities((prev) => {
      const current = new Set(prev[permissionId] ?? []);
      if (current.has(action)) current.delete(action);
      else current.add(action);
      return { ...prev, [permissionId]: current };
    });
  };

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
    loanProductsApi.list().then(setLoanProducts).catch(() => setLoanProducts([]));
    insuranceProductsApi.list().then(setInsuranceProducts).catch(() => setInsuranceProducts([]));
    listPermissions().then(setPermissions).catch(() => setPermissions([]));
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
      setProductIds(e.product_ids);
      setIsLoaded(true);
    });
  }, [employeeId, reset]);

  // Finds this employee's personal auto-created role (if any) and pre-populates the
  // Business Modules section from its current grants — see AUTO_ROLE_DESCRIPTION above.
  useEffect(() => {
    if (!employeeId) return;
    listEmployeeRoles(employeeId).then(async (assignments) => {
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
      const nextModules = new Set<string>();
      const nextCapabilities: Record<string, Set<string>> = {};
      for (const grant of grants) {
        const module = BUSINESS_MODULES.find((m) => m.key === grant.module && m.resource === grant.resource);
        if (!module) continue; // a SHARED_RESOURCES (leads/tasks) grant, or something outside this simplified UI — no checkbox to set
        nextModules.add(module.key);
        nextCapabilities[grant.permission_id] = new Set(grant.granted_actions.filter((a) => a !== "view" && a !== "assign"));
      }
      setSelectedModules(nextModules);
      setCapabilities(nextCapabilities);
    });
  }, [employeeId]);

  if (!employeeId) return null;

  const onSubmit = async (values: UpdateEmployeeFormValues) => {
    setApiError(null);
    try {
      await updateEmployee(employeeId, { ...values, product_ids: productIds });

      // Business Modules — same convenience layer on top of Access Control (Module 3)
      // CreateEmployeePage.tsx uses, just reading from / writing to this employee's
      // existing personal role instead of always creating a new one.
      const activeGrants = buildModuleGrants(permissions, selectedModules, capabilities);
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
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="max-w-2xl space-y-6">
          <ErrorBanner message={apiError} />

          <div className="bg-card border border-border rounded-card shadow-card p-6">
            <h2 className="text-sm font-semibold text-text/70 mb-2">Personal</h2>
            <div className="grid grid-cols-2 gap-x-4">
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

            <h2 className="text-sm font-semibold text-text/70 mb-2 mt-4">Contact</h2>
            <div className="grid grid-cols-2 gap-x-4">
              <FormField label="Email" type="email" error={errors.email?.message} {...register("email")} />
              <FormField label="Alternative mobile" maxLength={10} error={errors.alternative_mobile?.message} {...register("alternative_mobile")} />
            </div>

            <h2 className="text-sm font-semibold text-text/70 mb-2 mt-4">Employment</h2>
            <div className="grid grid-cols-2 gap-x-4">
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

            <h2 className="text-sm font-semibold text-text/70 mb-2 mt-4">Products Handled</h2>
            <p className="text-xs text-text/50 mb-2">
              Operational metadata only — enriches the Lead Assignment picker. Grants no permission by itself.
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {[...loanProducts, ...insuranceProducts].map((p) => (
                <label key={p.id} className="flex items-center gap-1.5 text-sm text-text/80">
                  <input type="checkbox" checked={productIds.includes(p.id)} onChange={() => toggleProduct(p.id)} />
                  {p.name}
                </label>
              ))}
            </div>
          </div>

          <BusinessModulesSection
            permissions={permissions}
            selectedModules={selectedModules}
            onToggleModule={toggleModule}
            capabilities={capabilities}
            onToggleCapability={toggleCapability}
          />
          {hasExtraAccess && (
            <p className="text-xs text-text/50 -mt-4">
              This employee may have extra access configured separately — see Roles &amp; Permissions for details.
            </p>
          )}

          <div className="flex justify-end">
            <SubmitButton isSubmitting={isSubmitting}>Save Changes</SubmitButton>
          </div>
        </form>
      )}
    </SimplePageLayout>
  );
}
