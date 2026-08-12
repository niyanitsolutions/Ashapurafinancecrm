import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { forgotPassword } from "@/features/auth/api";
import { AuthPageLayout } from "@/features/auth/components/AuthPageLayout";
import { ErrorBanner } from "@/features/auth/components/ErrorBanner";
import { FormField } from "@/features/auth/components/FormField";
import { SubmitButton } from "@/features/auth/components/SubmitButton";
import { getErrorMessage } from "@/features/auth/errors";
import { forgotPasswordSchema, type ForgotPasswordFormValues } from "@/features/auth/validation";

export function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("return");
  const backToLoginPath = returnTo ? `/login?return=${encodeURIComponent(returnTo)}` : "/login";
  const [apiError, setApiError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordFormValues>({ resolver: zodResolver(forgotPasswordSchema) });

  const onSubmit = async (values: ForgotPasswordFormValues) => {
    setApiError(null);
    try {
      await forgotPassword(values.mobile);
      // Response is deliberately generic (see docs/SECURITY.md) — always proceed to the
      // OTP step regardless of whether the account actually exists. `returnTo` rides
      // along so "Go to login" at the end of this detour can still resume wherever it
      // started from (e.g. a secure link).
      navigate("/verify-otp", { state: { mobile: values.mobile, returnTo } });
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  return (
    <AuthPageLayout title="Forgot password" subtitle="We'll send a one-time code to your mobile number">
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <ErrorBanner message={apiError} />
        <FormField
          label="Mobile number"
          inputMode="numeric"
          maxLength={10}
          placeholder="10-digit mobile number"
          error={errors.mobile?.message}
          {...register("mobile")}
        />
        <SubmitButton isSubmitting={isSubmitting}>Send OTP</SubmitButton>
        <p className="text-sm text-text/60 text-center mt-4">
          <Link to={backToLoginPath} className="text-primary hover:underline">
            Back to login
          </Link>
        </p>
      </form>
    </AuthPageLayout>
  );
}
