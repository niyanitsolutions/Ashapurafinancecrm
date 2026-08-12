import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuthPageLayout } from "@/features/auth/components/AuthPageLayout";
import { ErrorBanner } from "@/features/auth/components/ErrorBanner";
import { FormField } from "@/features/auth/components/FormField";
import { SubmitButton } from "@/features/auth/components/SubmitButton";
import { getErrorMessage } from "@/features/auth/errors";
import { useAuth } from "@/features/auth/useAuth";
import { getRegistrationStatus, registerOwner } from "@/features/owner/api";
import { ownerRegisterSchema, type OwnerRegisterFormValues } from "@/features/owner/validation";

// The Login page's "Create New Account" always routes here first — this page decides,
// based on current system state, whether that means first-run Owner registration or
// handing off to the existing (unmodified) Customer self-registration flow at /register.
// No manual account-type selection is ever shown to the user (Rule 10).
export function CreateAccountPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setSession } = useAuth();
  const [ownerExists, setOwnerExists] = useState<boolean | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<OwnerRegisterFormValues>({ resolver: zodResolver(ownerRegisterSchema) });

  useEffect(() => {
    getRegistrationStatus()
      .then((status) => setOwnerExists(status.owner_exists))
      .catch((err) => setLoadError(getErrorMessage(err)));
  }, []);

  if (loadError) {
    return (
      <AuthPageLayout title="Create New Account">
        <ErrorBanner message={loadError} />
      </AuthPageLayout>
    );
  }

  if (ownerExists === null) {
    return (
      <AuthPageLayout title="Create New Account">
        <p className="text-sm text-white/50 text-center">Loading…</p>
      </AuthPageLayout>
    );
  }

  if (ownerExists) {
    // Preserves `?return=` (e.g. a secure link waiting to resume — see
    // SecureLinkLandingPage.tsx) through to /register's own OTP → password chain.
    return <Navigate to={`/register${location.search}`} replace />;
  }

  const onSubmit = async (values: OwnerRegisterFormValues) => {
    setApiError(null);
    try {
      const result = await registerOwner({
        company_name: values.company_name,
        owner_name: values.owner_name,
        mobile: values.mobile,
        email: values.email,
        password: values.password,
        accept_terms: values.accept_terms,
      });
      setSession({
        accessToken: result.access_token,
        refreshToken: result.refresh_token,
        role: result.role,
        userId: result.user_id,
        mustChangePassword: result.must_change_password,
      });
      navigate("/");
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  return (
    <AuthPageLayout title="Set up your organization" subtitle="Create the Owner account for your company">
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <ErrorBanner message={apiError} />
        <FormField label="Company Name" error={errors.company_name?.message} {...register("company_name")} />
        <FormField label="Owner Name" error={errors.owner_name?.message} {...register("owner_name")} />
        <FormField
          label="Mobile number"
          inputMode="numeric"
          maxLength={10}
          placeholder="10-digit mobile number"
          error={errors.mobile?.message}
          {...register("mobile")}
        />
        <FormField label="Email Address" type="email" error={errors.email?.message} {...register("email")} />
        <FormField label="Password" type="password" error={errors.password?.message} {...register("password")} />
        <FormField
          label="Confirm Password"
          type="password"
          error={errors.confirm_password?.message}
          {...register("confirm_password")}
        />
        <label className="mb-4 flex items-start gap-2 text-sm text-white/70">
          <input type="checkbox" className="mt-0.5" {...register("accept_terms")} />
          <span>I accept the Terms &amp; Conditions</span>
        </label>
        {errors.accept_terms && <p className="-mt-3 mb-4 text-sm text-red-300">{errors.accept_terms.message}</p>}
        <SubmitButton isSubmitting={isSubmitting}>Create Owner Account</SubmitButton>
      </form>
    </AuthPageLayout>
  );
}
