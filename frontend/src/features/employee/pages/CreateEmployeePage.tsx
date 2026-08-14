import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { assignRole, createRole, listPermissions, setRolePermissions, type Permission } from "@/features/access_control/api";
import { Button } from "@/components/buttons/Button";
import { CheckboxField } from "@/components/forms/CheckboxField";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { PermissionMatrixSection } from "@/features/employee/components/PermissionMatrixSection";
import {
  createEmployee,
  listBranches,
  listDepartments,
  listDesignations,
  listEmployees,
  type BranchItem,
  type EmployeeListItem,
  type MasterDataItem,
} from "@/features/employee/api";
import { buildMatrixGrants } from "@/features/employee/permissionMatrix";
import { getErrorMessage } from "@/features/employee/errors";
import { simpleCreateEmployeeSchema, type SimpleCreateEmployeeFormValues } from "@/features/employee/validation";
import { insuranceProductsApi, loanProductsApi, type NamedMasterData } from "@/features/system_settings/api";

// Defaults for the two backend-required fields this simplified form doesn't ask about —
// editable afterward via Edit / the Employee Profile's Employment tab.
const DEFAULT_EMPLOYMENT_TYPE = "full_time";
const todayIso = () => new Date().toISOString().slice(0, 10);

export function CreateEmployeePage() {
  const navigate = useNavigate();
  const [apiError, setApiError] = useState<string | null>(null);
  const [departments, setDepartments] = useState<MasterDataItem[]>([]);
  const [designations, setDesignations] = useState<MasterDataItem[]>([]);
  const [branches, setBranches] = useState<BranchItem[]>([]);
  const [managers, setManagers] = useState<EmployeeListItem[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [checkedPermissions, setCheckedPermissions] = useState<Record<string, Set<string>>>({});
  const [loanProducts, setLoanProducts] = useState<NamedMasterData[]>([]);
  const [insuranceProducts, setInsuranceProducts] = useState<NamedMasterData[]>([]);
  const [productIds, setProductIds] = useState<string[]>([]);

  useEffect(() => {
    listDepartments().then(setDepartments).catch(() => setDepartments([]));
    listDesignations().then(setDesignations).catch(() => setDesignations([]));
    listBranches().then(setBranches).catch(() => setBranches([]));
    listEmployees({ page: 1, page_size: 100 }).then((res) => setManagers(res.data)).catch(() => setManagers([]));
    listPermissions().then(setPermissions).catch(() => setPermissions([]));
    loanProductsApi.list().then(setLoanProducts).catch(() => setLoanProducts([]));
    insuranceProductsApi.list().then(setInsuranceProducts).catch(() => setInsuranceProducts([]));
  }, []);

  const toggleProduct = (productId: string) => {
    setProductIds((prev) => (prev.includes(productId) ? prev.filter((id) => id !== productId) : [...prev, productId]));
  };

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SimpleCreateEmployeeFormValues>({ resolver: zodResolver(simpleCreateEmployeeSchema) });

  const onSubmit = async (values: SimpleCreateEmployeeFormValues) => {
    setApiError(null);
    try {
      const employee = await createEmployee({
        ...values,
        joining_date: todayIso(),
        employment_type: DEFAULT_EMPLOYMENT_TYPE,
        reporting_manager_id: values.reporting_manager_id || undefined,
        product_ids: productIds,
      });

      // The Permissions matrix is a convenience layer on top of Access Control (Module
      // 3) — orchestrates its existing endpoints (create a role scoped to this
      // employee, grant it whatever's checked, assign it), rather than a new backend
      // capability. Skipped entirely if nothing was checked — an Owner can always
      // configure access later from Roles & Permissions.
      const activeGrants = buildMatrixGrants(permissions, checkedPermissions);
      if (activeGrants.length > 0) {
        const role = await createRole(`${values.first_name} ${values.last_name}`, "Created automatically from Add Employee");
        await setRolePermissions(role.id, activeGrants);
        await assignRole(role.id, employee.id);
      }

      navigate(`/employees/${employee.id}`);
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Add Employee" subtitle="Just the essentials — detailed HR information can be added later from their profile." backTo="/employees">
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="max-w-4xl mx-auto space-y-6">
        <ErrorBanner message={apiError} />

        <div className="bg-card border border-border rounded-card shadow-card p-6">
          <h2 className="text-sm font-semibold text-text mb-1">Basic Information</h2>
          <p className="text-xs text-text/50 mb-4">Who they are and how they'll log in.</p>
          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <FormField label="First name" error={errors.first_name?.message} {...register("first_name")} />
            <FormField label="Last name" error={errors.last_name?.message} {...register("last_name")} />
            <FormField label="Email" type="email" error={errors.email?.message} {...register("email")} />
            <FormField label="Mobile number" maxLength={10} error={errors.mobile?.message} {...register("mobile")} />
            <FormField label="Password" type="password" error={errors.initial_password?.message} {...register("initial_password")} />
          </div>
        </div>

        <div className="bg-card border border-border rounded-card shadow-card p-6">
          <h2 className="text-sm font-semibold text-text mb-1">Organization</h2>
          <p className="text-xs text-text/50 mb-4">Where they sit in your company.</p>
          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <SelectField
              label="Department"
              placeholder="Select department"
              options={departments.map((d) => ({ value: d.id, label: d.name }))}
              error={errors.department_id?.message}
              {...register("department_id")}
            />
            <SelectField
              label="Designation"
              placeholder="Select designation"
              options={designations.map((d) => ({ value: d.id, label: d.name }))}
              error={errors.designation_id?.message}
              {...register("designation_id")}
            />
            <SelectField
              label="Branch"
              placeholder="Select branch"
              options={branches.map((b) => ({ value: b.id, label: b.name }))}
              error={errors.branch_id?.message}
              {...register("branch_id")}
            />
            <SelectField
              label="Reporting Manager (optional)"
              placeholder="None"
              options={managers.map((m) => ({ value: m.id, label: m.display_name }))}
              error={errors.reporting_manager_id?.message}
              {...register("reporting_manager_id")}
            />
          </div>
        </div>

        <div className="bg-card border border-border rounded-card shadow-card p-6">
          <h2 className="text-sm font-semibold text-text mb-1">Product Specialization</h2>
          <p className="text-xs text-text/50 mb-4">
            Select products this employee is experienced with. Used only to improve Lead assignment
            recommendations — it does not grant or remove access to Leads or any other module.
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5">
            {[...loanProducts, ...insuranceProducts].map((p) => (
              <CheckboxField
                key={p.id} label={p.name}
                checked={productIds.includes(p.id)} onChange={() => toggleProduct(p.id)}
              />
            ))}
            {loanProducts.length === 0 && insuranceProducts.length === 0 && <p className="text-sm text-text/40">Loading…</p>}
          </div>
        </div>

        <PermissionMatrixSection permissions={permissions} checked={checkedPermissions} onChange={setCheckedPermissions} />

        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={() => navigate("/employees")}>
            Cancel
          </Button>
          <SubmitButton isSubmitting={isSubmitting}>Save Employee</SubmitButton>
        </div>
      </form>
    </SimplePageLayout>
  );
}
