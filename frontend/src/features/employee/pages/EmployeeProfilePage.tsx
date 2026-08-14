import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getOwnProfile, updateOwnProfile, type EmployeeDetail } from "@/features/employee/api";
import { StatusBadge } from "@/features/employee/components/StatusBadge";
import { getErrorMessage } from "@/features/employee/errors";
import { selfUpdateEmployeeSchema, type SelfUpdateEmployeeFormValues } from "@/features/employee/validation";

export function EmployeeProfilePage() {
  const [employee, setEmployee] = useState<EmployeeDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<SelfUpdateEmployeeFormValues>({ resolver: zodResolver(selfUpdateEmployeeSchema) });

  useEffect(() => {
    getOwnProfile()
      .then((e) => {
        setEmployee(e);
        reset({
          first_name: e.first_name,
          last_name: e.last_name,
          display_name: e.display_name,
          blood_group: e.blood_group ?? undefined,
          alternative_mobile: e.alternative_mobile ?? undefined,
        });
      })
      .catch((err) => setLoadError(getErrorMessage(err)));
  }, [reset]);

  if (loadError) {
    return (
      <SimplePageLayout title="My Profile">
        <p className="text-sm text-danger">{loadError}</p>
      </SimplePageLayout>
    );
  }
  if (!employee) {
    return (
      <SimplePageLayout title="My Profile">
        <p className="text-sm text-text/50">Loading…</p>
      </SimplePageLayout>
    );
  }

  const onSubmit = async (values: SelfUpdateEmployeeFormValues) => {
    setApiError(null);
    setSuccessMessage(null);
    try {
      const updated = await updateOwnProfile(values);
      setEmployee(updated);
      setSuccessMessage("Profile updated.");
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout
      title="My Profile"
      actions={
        <>
          <Link to="/profile/sessions" className="text-sm text-primary hover:underline">
            My Sessions
          </Link>
          <Link to="/profile/login-history" className="text-sm text-primary hover:underline">
            Login History
          </Link>
        </>
      }
    >
      <div className="max-w-2xl bg-card border border-border rounded-card shadow-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-sm text-text/60">{employee.employee_code}</span>
          <StatusBadge status={employee.status} />
        </div>

        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <ErrorBanner message={apiError} />
          {successMessage && <p className="mb-4 text-sm text-success">{successMessage}</p>}

          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <FormField label="First name" error={errors.first_name?.message} {...register("first_name")} />
            <FormField label="Last name" error={errors.last_name?.message} {...register("last_name")} />
            <FormField label="Display name" error={errors.display_name?.message} {...register("display_name")} />
            <FormField label="Blood group" error={errors.blood_group?.message} {...register("blood_group")} />
            <FormField label="Alternative mobile" maxLength={10} error={errors.alternative_mobile?.message} {...register("alternative_mobile")} />
          </div>

          <p className="text-xs text-text/50 mt-2 mb-4">
            Department, designation, branch, and bank details can only be changed by the Owner.
          </p>

          <SubmitButton isSubmitting={isSubmitting}>Save Changes</SubmitButton>
        </form>
      </div>
    </SimplePageLayout>
  );
}
