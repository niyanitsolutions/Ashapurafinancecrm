import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getOwnerAccount, updateSecondaryOwner, type OwnerAccountDetail } from "@/features/owner/api";
import { updateSecondaryOwnerSchema, type UpdateSecondaryOwnerFormValues } from "@/features/owner/validation";
import { getErrorMessage } from "@/shared/api/errors";

export function EditSecondaryOwnerPage() {
  const { ownerId } = useParams<{ ownerId: string }>();
  const navigate = useNavigate();
  const [owner, setOwner] = useState<OwnerAccountDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<UpdateSecondaryOwnerFormValues>({ resolver: zodResolver(updateSecondaryOwnerSchema) });

  useEffect(() => {
    if (!ownerId) return;
    getOwnerAccount(ownerId)
      .then((detail) => {
        setOwner(detail);
        reset({ full_name: detail.full_name, email: detail.email });
      })
      .catch((err) => setLoadError(getErrorMessage(err)));
  }, [ownerId, reset]);

  const onSubmit = async (values: UpdateSecondaryOwnerFormValues) => {
    if (!ownerId) return;
    setApiError(null);
    try {
      await updateSecondaryOwner(ownerId, values);
      navigate("/owner-accounts");
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  if (loadError) {
    return (
      <SimplePageLayout title="Edit Secondary Owner" backTo="/owner-accounts">
        <p className="text-sm text-danger">{loadError}</p>
      </SimplePageLayout>
    );
  }

  if (!owner) {
    return (
      <SimplePageLayout title="Edit Secondary Owner" backTo="/owner-accounts">
        <p className="text-sm text-text/50">Loading…</p>
      </SimplePageLayout>
    );
  }

  return (
    <SimplePageLayout title="Edit Secondary Owner" subtitle={owner.mobile} backTo="/owner-accounts">
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="max-w-2xl space-y-6">
        <ErrorBanner message={apiError} />

        <div className="bg-card border border-border rounded-card shadow-card p-6">
          <h2 className="text-sm font-semibold text-text mb-1">Account Details</h2>
          <p className="text-xs text-text/50 mb-4">
            Mobile number can't be changed here. Use the Owner list to deactivate/reactivate this account, or Change
            Password (from their own Profile) to update their password.
          </p>
          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <FormField label="Full name" error={errors.full_name?.message} {...register("full_name")} />
            <FormField label="Email" type="email" error={errors.email?.message} {...register("email")} />
            <FormField label="Mobile number" value={owner.mobile} disabled readOnly />
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => navigate("/owner-accounts")}>
            Cancel
          </Button>
          <SubmitButton isSubmitting={isSubmitting}>Save Changes</SubmitButton>
        </div>
      </form>
    </SimplePageLayout>
  );
}
