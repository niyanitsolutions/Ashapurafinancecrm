import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation } from "react-router-dom";
import { resetPassword } from "@/features/auth/api";
import { AuthPageLayout } from "@/features/auth/components/AuthPageLayout";
import { ErrorBanner } from "@/features/auth/components/ErrorBanner";
import { FormField } from "@/features/auth/components/FormField";
import { PasswordStrengthChecklist } from "@/features/auth/components/PasswordStrengthChecklist";
import { SubmitButton } from "@/features/auth/components/SubmitButton";
import { getErrorMessage } from "@/features/auth/errors";
import { resetPasswordSchema, type ResetPasswordFormValues } from "@/features/auth/validation";

interface LocationState {
  otpVerifiedToken: string;
  isNewUser: boolean;
  returnTo?: string | null; // threaded from RegisterPage/ForgotPasswordPage via OtpVerificationPage
}

export function ResetPasswordPage() {
  const location = useLocation();
  const state = location.state as LocationState | undefined;
  const [apiError, setApiError] = useState<string | null>(null);
  const [isDone, setIsDone] = useState(false);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordFormValues>({ resolver: zodResolver(resetPasswordSchema) });

  if (!state?.otpVerifiedToken) {
    return <Navigate to="/login" replace />;
  }

  const title = state.isNewUser ? "Create your password" : "Reset your password";
  const loginPath = state.returnTo ? `/login?return=${encodeURIComponent(state.returnTo)}` : "/login";

  if (isDone) {
    return (
      <AuthPageLayout title={title}>
        <p className="text-sm text-text mb-4">
          {state.isNewUser ? "Your account is ready." : "Your password has been updated."}
        </p>
        <Link to={loginPath} className="text-sm text-primary hover:underline">
          Go to login
        </Link>
      </AuthPageLayout>
    );
  }

  const onSubmit = async (values: ResetPasswordFormValues) => {
    setApiError(null);
    try {
      await resetPassword(state.otpVerifiedToken, values.newPassword);
      setIsDone(true);
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  return (
    <AuthPageLayout title={title}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <ErrorBanner message={apiError} />
        <FormField label="New password" type="password" error={errors.newPassword?.message} {...register("newPassword")} />
        <PasswordStrengthChecklist password={watch("newPassword") ?? ""} />
        <FormField
          label="Confirm password"
          type="password"
          error={errors.confirmPassword?.message}
          {...register("confirmPassword")}
        />
        <SubmitButton isSubmitting={isSubmitting}>{state.isNewUser ? "Create account" : "Reset password"}</SubmitButton>
      </form>
    </AuthPageLayout>
  );
}
