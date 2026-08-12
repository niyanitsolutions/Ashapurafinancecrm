import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { forgotPassword, verifyOtp } from "@/features/auth/api";
import { AuthPageLayout } from "@/features/auth/components/AuthPageLayout";
import { ErrorBanner } from "@/features/auth/components/ErrorBanner";
import { FormField } from "@/features/auth/components/FormField";
import { SubmitButton } from "@/features/auth/components/SubmitButton";
import { getErrorMessage } from "@/features/auth/errors";
import { otpVerificationSchema, type OtpVerificationFormValues } from "@/features/auth/validation";

// Forgot Password's OTP step (see ForgotPasswordPage.tsx). Customer self-registration
// has its own inline OTP step (RegisterPage.tsx) — Auth's own signup-invitation OTP
// (`purpose: "signup"`) is only ever used by the staff-invitation flow, which has no UI
// of its own to reach this page from, so this page only ever handles "forgot_password".
interface LocationState {
  mobile: string;
  returnTo?: string | null; // threaded through to ResetPasswordPage's "Go to login" link
}

export function OtpVerificationPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as LocationState | undefined;
  const [apiError, setApiError] = useState<string | null>(null);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<OtpVerificationFormValues>({ resolver: zodResolver(otpVerificationSchema) });

  if (!state?.mobile) {
    // Direct navigation without going through Forgot Password first — nothing to verify.
    return <Navigate to="/login" replace />;
  }

  const onSubmit = async (values: OtpVerificationFormValues) => {
    setApiError(null);
    try {
      const result = await verifyOtp(state.mobile, values.otp, "forgot_password");
      navigate("/reset-password", {
        state: { otpVerifiedToken: result.otp_verified_token, isNewUser: result.is_new_user, returnTo: state.returnTo },
      });
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  const onResend = async () => {
    setApiError(null);
    setResendMessage(null);
    try {
      await forgotPassword(state.mobile);
      setResendMessage("A new code has been sent.");
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  return (
    <AuthPageLayout title="Enter verification code" subtitle={`We sent a 6-digit code to ${state.mobile}`}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <ErrorBanner message={apiError} />
        {resendMessage && <p className="mb-4 text-sm text-success">{resendMessage}</p>}
        <FormField
          label="6-digit code"
          inputMode="numeric"
          maxLength={6}
          placeholder="123456"
          error={errors.otp?.message}
          {...register("otp")}
        />
        <SubmitButton isSubmitting={isSubmitting}>Verify</SubmitButton>
        <p className="text-sm text-text/60 text-center mt-4">
          Didn't get a code?{" "}
          <button type="button" onClick={onResend} className="text-primary hover:underline">
            Resend
          </button>
        </p>
      </form>
    </AuthPageLayout>
  );
}
