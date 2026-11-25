import { Modal } from "@/components/overlays/Modal";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { CustomerAuthLayout as AuthPageLayout } from "@/features/customer/components/CustomerAuthLayout";
import { ErrorBanner } from "@/features/auth/components/ErrorBanner";
import { FormField } from "@/features/auth/components/FormField";
import { SubmitButton } from "@/features/auth/components/SubmitButton";
import { loginPin, verifyPinOtp, type Challenge } from "@/features/auth/pinApi";
import { useAuth } from "@/features/auth/useAuth";
import { completeDirectRegistration, startDirectRegistration } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { directRegisterSchema, type DirectRegisterFormValues } from "@/features/customer/validation";

export function RegisterPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const returnTo = params.get("return");
  const loginPath = returnTo ? `/login?return=${encodeURIComponent(returnTo)}` : "/login";
  const [details, setDetails] = useState<DirectRegisterFormValues | null>(null);
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [accountNotFound,setAccountNotFound] = useState(false);
  const [authorization, setAuthorization] = useState("");
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [resendAt, setResendAt] = useState(0);
  const [expiresAt, setExpiresAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const { register, handleSubmit, reset, formState: { errors } } = useForm<DirectRegisterFormValues>({ resolver: zodResolver(directRegisterSchema), defaultValues: { mobile: /^[0-9]{10}$/.test(params.get("mobile") || "") ? params.get("mobile")! : "", terms_accepted: false } });
  useEffect(() => {
    if (!challenge) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [challenge]);
  async function act(action: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(null);
    try { await action(); } catch (e) { setError(getErrorMessage(e)); }
    finally { lock.current = false; setBusy(false); }
  }
  async function send(values: DirectRegisterFormValues) {
    const result = await startDirectRegistration({ ...values, email: values.email || null });
    setDetails(values); setChallenge(result); setOtp(""); setAuthorization("");
    setNow(Date.now()); setResendAt(Date.now() + result.resend_after * 1000);
    setExpiresAt(Date.now() + result.expires_in * 1000); reset();
  }
  return <AuthPageLayout title={challenge ? "Verify your mobile number" : "Create Customer Account"} subtitle="Use your mobile number and a 4-digit login PIN">
    <ErrorBanner message={error} />
    {accountNotFound && <Modal open title="Customer Account Not Found" onClose={()=>navigate(loginPath)}>
      <p className="mb-4 text-sm">Your mobile ownership is verified. This number is not registered yet. Continue to create your customer account.</p>
      <button type="button" className="text-primary" onClick={()=>setAccountNotFound(false)}>Create New Account</button>
      <button type="button" className="ml-4" onClick={()=>navigate(loginPath)}>Cancel</button>
    </Modal>}
    {!challenge ? <form onSubmit={handleSubmit(values => act(() => send(values)))} noValidate>
      <FormField label="Mobile Number" inputMode="numeric" autoComplete="tel-national" maxLength={10} disabled={busy} error={errors.mobile?.message} {...register("mobile")} />
      <FormField label="Full Name" autoComplete="name" disabled={busy} error={errors.full_name?.message} {...register("full_name")} />
      <FormField label="Email Address (optional)" type="email" autoComplete="email" disabled={busy} error={errors.email?.message} {...register("email")} />
      <FormField label="Create 4-Digit PIN" type="password" inputMode="numeric" maxLength={4} autoComplete="new-password" disabled={busy} error={errors.pin?.message} {...register("pin")} />
      <FormField label="Confirm 4-Digit PIN" type="password" inputMode="numeric" maxLength={4} autoComplete="new-password" disabled={busy} error={errors.confirm_pin?.message} {...register("confirm_pin")} />
      <p className="mb-4 text-sm text-white/70">Your login PIN is separate from the SMS verification code.</p>
      <label className="mb-4 flex items-start gap-2 text-sm text-white/80"><input type="checkbox" disabled={busy} {...register("terms_accepted")} />I accept the applicable terms and privacy policy.</label>
      {errors.terms_accepted && <p role="alert" className="mb-3 text-sm text-red-300">{errors.terms_accepted.message}</p>}
      <SubmitButton isSubmitting={busy}>Send OTP</SubmitButton>
    </form> : <>
      <p role="status" className="mb-4 text-sm text-white/80">{authorization ? "Customer Account Not Found. Your mobile is verified. Complete registration to create your account." : `${challenge.message} Recipient: ${challenge.masked_mobile}`}</p>
      {authorization ? <SubmitButton isSubmitting={busy} onClick={() => void act(async () => {
        if (!details) return;
        await completeDirectRegistration({ ...details, email: details.email || null, authorization });
        setDetails(null); setAuthorization(""); reset();
        try {
          const result = await loginPin(details.mobile, details.pin, null);
          setSession({ accessToken: result.access_token, refreshToken: result.refresh_token, role: result.role,
            userId: result.user_id, mustChangePassword: result.must_change_password });
          const target = returnTo && /^\/(?!\/)/.test(returnTo) && !returnTo.includes("\\") ? returnTo : "/portal";
          navigate(target, { replace: true });
        } catch {
          navigate(loginPath, { replace: true, state: { message: "Registration successful. Please log in with your mobile number and PIN." } });
        }
      })}>Complete Registration</SubmitButton> : <form onSubmit={e => { e.preventDefault(); void act(async () => {
        if (!details) return;
        const proof = await verifyPinOtp(details.mobile, "REGISTRATION", challenge.challenge_id, otp);
        if (proof.next_action === "login") { setOtp(""); setError("This verified mobile already has an account. Log in or use Forgot PIN."); return; }
        setAuthorization(proof.authorization); setAccountNotFound(true); setOtp("");
      }); }}>
        <FormField id="registration-otp" label="4-digit SMS OTP" type="password" inputMode="numeric" pattern="[0-9]{4}" required maxLength={4} autoComplete="one-time-code" value={otp} disabled={busy} onChange={e => setOtp(e.target.value)} />
        <p className="mb-3 text-sm text-white/70">{now >= expiresAt ? "Code expired. Request a new code." : "Code valid for 10 minutes."}</p>
        <SubmitButton isSubmitting={busy} disabled={!/^[0-9]{4}$/.test(otp) || now >= expiresAt}>Verify OTP</SubmitButton>
        <button type="button" className="mt-4 text-primary disabled:opacity-50" disabled={busy || now < resendAt} onClick={() => details && void act(() => send(details))}>
          {now < resendAt ? `Resend OTP in ${Math.ceil((resendAt - now) / 1000)}s` : "Resend OTP"}
        </button>
      </form>}
    </>}
    <p className="mt-4 text-center text-sm text-white/70">Already have an account? <Link className="text-primary" to={loginPath}>Log in</Link></p>
  </AuthPageLayout>;
}
