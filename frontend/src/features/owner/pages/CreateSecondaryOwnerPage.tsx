import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { createSecondaryOwner } from "@/features/owner/api";
import { createSecondaryOwnerSchema, type CreateSecondaryOwnerFormValues } from "@/features/owner/validation";
import { getErrorMessage } from "@/shared/api/errors";

export function CreateSecondaryOwnerPage() {
  const navigate = useNavigate();
  const [apiError, setApiError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CreateSecondaryOwnerFormValues>({ resolver: zodResolver(createSecondaryOwnerSchema) });

  const onSubmit = async (values: CreateSecondaryOwnerFormValues) => {
    setApiError(null);
    try {
      await createSecondaryOwner(values);
      navigate("/owner-accounts");
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Add Secondary Owner" subtitle="Secondary Owners can manage Employees and Referral Partners, but not other Owner accounts." backTo="/owner-accounts">
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="max-w-2xl space-y-6">
        <ErrorBanner message={apiError} />

        <div className="bg-card border border-border rounded-card shadow-card p-6">
          <h2 className="text-sm font-semibold text-text mb-1">Account Details</h2>
          <p className="text-xs text-text/50 mb-4">
            They'll be asked to change this password the first time they log in.
          </p>
          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <FormField label="Full name" error={errors.full_name?.message} {...register("full_name")} />
            <FormField label="Email" type="email" error={errors.email?.message} {...register("email")} />
            <FormField label="Mobile number" maxLength={10} error={errors.mobile?.message} {...register("mobile")} />
            <FormField label="Initial password" type="password" error={errors.initial_password?.message} {...register("initial_password")} />
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => navigate("/owner-accounts")}>
            Cancel
          </Button>
          <SubmitButton isSubmitting={isSubmitting}>Create Secondary Owner</SubmitButton>
        </div>
      </form>
    </SimplePageLayout>
  );
}
