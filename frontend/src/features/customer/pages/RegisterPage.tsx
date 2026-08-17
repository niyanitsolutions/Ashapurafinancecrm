import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router-dom";
import { verifyOtp } from "@/features/auth/api";
import { AuthPageLayout } from "@/features/auth/components/AuthPageLayout";
import { ErrorBanner } from "@/features/auth/components/ErrorBanner";
import { FormField } from "@/features/auth/components/FormField";
import { PasswordStrengthChecklist } from "@/features/auth/components/PasswordStrengthChecklist";
import { SubmitButton } from "@/features/auth/components/SubmitButton";
import { getErrorMessage as getAuthErrorMessage } from "@/features/auth/errors";
import { bypassVerifyRegistrationMobile, completeDirectRegistration, startDirectRegistration } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { directRegisterSchema, type DirectRegisterFormValues } from "@/features/customer/validation";

// Customer self-registration — the *only* self-registration path in the system. Owner,
// Employee, and Referral Partner accounts are always staff-created (Owner-invitation-
// only, see decision 011/053); there is no route to this page, or any equivalent, for
// those roles. One form (name/email/mobile/password/address), one OTP step, one
// "Create Account" action — no secure-link-specific variant (see SecureLinkLandingPage,
// which sends unauthenticated customers here with `?return=` and nowhere else).
type Stage = "form" | "otp" | "done";

export function RegisterPage() {
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("return");
  const loginPath = returnTo ? `/login?return=${encodeURIComponent(returnTo)}` : "/login";

  const [stage, setStage] = useState<Stage>("form");
  const [formValues, setFormValues] = useState<DirectRegisterFormValues | null>(null);
  const [otp, setOtp] = useState("");
  const [otpVerifiedToken, setOtpVerifiedToken] = useState<string | null>(null);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // TEMPORARY — MSG91 DLT approval testing bypass; see startDirectRegistration/
  // bypassVerifyRegistrationMobile in @/features/customer/api. Remove once DLT approval
  // lands and the backend's Settings.registration_otp_bypass is retired.
  const [bypassAvailable, setBypassAvailable] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<DirectRegisterFormValues>({ resolver: zodResolver(directRegisterSchema) });

  const onSendOtp = async (values: DirectRegisterFormValues) => {
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await startDirectRegistration(values.mobile);
      setBypassAvailable(result.bypass_available);
      setFormValues(values);
      setStage("otp");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const onVerifyOtp = async () => {
    if (!formValues) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await verifyOtp(formValues.mobile, otp, "signup");
      setOtpVerifiedToken(result.otp_verified_token);
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  // TEMPORARY — MSG91 DLT approval testing bypass. The backend independently re-verifies
  // the bypass is enabled (REGISTRATION_OTP_BYPASS=true); this button cannot itself mark
  // anything verified, it only requests that check.
  const onBypassVerifyMobile = async () => {
    if (!formValues) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await bypassVerifyRegistrationMobile(formValues.mobile);
      setOtpVerifiedToken(result.otp_verified_token);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const onResendOtp = () => {
    if (!formValues) return;
    setError(null);
    setResendMessage(null);
    startDirectRegistration(formValues.mobile)
      .then(() => setResendMessage("A new code has been sent."))
      .catch((err) => setError(getErrorMessage(err)));
  };

  const onCreateAccount = async () => {
    if (!formValues || !otpVerifiedToken) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await completeDirectRegistration({
        full_name: formValues.full_name,
        email: formValues.email,
        mobile: formValues.mobile,
        password: formValues.password,
        address_line1: formValues.address_line1,
        city: formValues.city,
        state: formValues.state,
        pincode: formValues.pincode,
        otp_verified_token: otpVerifiedToken,
      });
      setStage("done");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (stage === "done") {
    return (
      <AuthPageLayout title="Account Created Successfully">
        <p className="text-sm text-white/70 text-center mb-6">Your customer account is ready. Please log in to continue.</p>
        <Link to={loginPath} className="w-full block text-center rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-3 shadow-glass hover-lift">
          Go to Login
        </Link>
      </AuthPageLayout>
    );
  }

  if (stage === "otp" && formValues) {
    return (
      <AuthPageLayout
        title="Verify your mobile number"
        subtitle={bypassAvailable ? undefined : `We sent a 6-digit code to ${formValues.mobile}`}
      >
        <ErrorBanner message={error} />
        {otpVerifiedToken ? (
          <>
            <p className="text-sm text-success text-center mb-4">✓ Mobile number verified</p>
            <SubmitButton isSubmitting={isSubmitting} onClick={onCreateAccount}>
              Create Account
            </SubmitButton>
          </>
        ) : bypassAvailable ? (
          // TEMPORARY — MSG91 DLT approval testing bypass, shown for any valid mobile
          // while REGISTRATION_OTP_BYPASS=true on the backend. Remove this branch once
          // DLT approval lands.
          <>
            <p className="text-xs uppercase tracking-wide text-white/50 mb-1">Mobile Number</p>
            <p className="text-sm text-white/90 mb-4">{formValues.mobile}</p>
            <SubmitButton isSubmitting={isSubmitting} onClick={onBypassVerifyMobile}>
              Verify Mobile
            </SubmitButton>
          </>
        ) : (
          <>
            <FormField
              label="6-digit code"
              inputMode="numeric"
              maxLength={6}
              placeholder="123456"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
            />
            <SubmitButton isSubmitting={isSubmitting} onClick={onVerifyOtp} disabled={otp.length !== 6}>
              Verify OTP
            </SubmitButton>
            <p className="text-sm text-white/60 text-center mt-4">
              Didn't get a code?{" "}
              <button type="button" onClick={onResendOtp} className="text-primary hover:underline">
                Resend OTP
              </button>
            </p>
            {resendMessage && <p className="text-sm text-success text-center mt-2">{resendMessage}</p>}
          </>
        )}
      </AuthPageLayout>
    );
  }

  return (
    <AuthPageLayout title="Create Customer Account" subtitle="Apply for a loan or insurance product">
      <form onSubmit={handleSubmit(onSendOtp)} noValidate>
        <ErrorBanner message={error} />
        <FormField label="Full Name" error={errors.full_name?.message} {...register("full_name")} />
        <FormField label="Email Address" type="email" error={errors.email?.message} {...register("email")} />
        <FormField
          label="Mobile Number"
          inputMode="numeric"
          maxLength={10}
          placeholder="10-digit mobile number"
          error={errors.mobile?.message}
          {...register("mobile")}
        />
        <FormField label="Password" type="password" error={errors.password?.message} {...register("password")} />
        <PasswordStrengthChecklist password={watch("password") ?? ""} />
        <FormField
          label="Confirm Password"
          type="password"
          error={errors.confirm_password?.message}
          {...register("confirm_password")}
        />
        <FormField label="Address" error={errors.address_line1?.message} {...register("address_line1")} />
        <FormField label="City" error={errors.city?.message} {...register("city")} />
        <FormField label="State" error={errors.state?.message} {...register("state")} />
        <FormField label="PIN Code" inputMode="numeric" maxLength={6} error={errors.pincode?.message} {...register("pincode")} />
        <SubmitButton isSubmitting={isSubmitting}>Send OTP</SubmitButton>
      </form>
      <p className="text-sm text-white/60 text-center mt-4">
        Already have an account?{" "}
        <Link to={loginPath} className="text-primary hover:underline">
          Log in
        </Link>
      </p>
    </AuthPageLayout>
  );
}
