import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FormField } from "./FormField";
import { SubmitButton } from "./SubmitButton";
import { ErrorBanner } from "./ErrorBanner";
import { useAuth } from "../useAuth";
import { finishPin, loginPin, pinPolicy, startPin, verifyPinOtp, type Challenge, type Purpose } from "../pinApi";
import type { LoginResponse } from "../api";
import { ApiError } from "@/shared/api/client";
import { getErrorMessage } from "../errors";
export function PinAuthPanel({ returnTo, onLegacy }: {
  returnTo: string | null;
  onLegacy: () => void;
}) {
  const { setSession } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "start" | "verify" | "set" | "success">("login");
  const [policy, setPolicy] = useState<string | null>(null);
  const [mobile, setMobile] = useState("");
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [otp, setOtp] = useState("");
  const [purpose, setPurpose] = useState<Purpose>("FIRST_TIME_LOGIN");
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [authorization, setAuthorization] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [resendAt, setResendAt] = useState(0);
  const [expiresAt, setExpiresAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { pinPolicy().then(row => setPolicy(row.mode)).catch(() => setError("Unable to load sign-in policy. Refresh before continuing.")); }, []);
  useEffect(() => {
    if(mode !== "verify")
      return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [mode]);
  function authenticated(result: LoginResponse) {
    setSession({ accessToken: result.access_token, refreshToken: result.refresh_token, role: result.role, userId: result.user_id, mustChangePassword: result.must_change_password });
    navigate(returnTo && /^\/(?!\/)/.test(returnTo) && !returnTo.includes("\\") ? returnTo : "/", { replace: true });
  }
  async function issue() {
    const row = await startPin(mobile, purpose);
    setChallenge(row);
    setResendAt(Date.now() + row.resend_after * 1000);
    setExpiresAt(Date.now() + row.expires_in * 1000);
    setNow(Date.now());
    setOtp("");
    setMode("verify");
  }
  async function act(action: () => Promise<void>) {
    if(lock.current)
      return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      await action();
    }
    catch(e) {
      setError(e instanceof ApiError && ["unauthorized", "invalid_credentials"].includes(e.code) ? e.message : getErrorMessage(e));
    }
    finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function submit() {
    await act(async () => {
      if(mode === "login") {
        authenticated(await loginPin(mobile, pin, null));
        setPin("");
      }
      else if(mode === "start")
        await issue();
      else if(mode === "verify" && challenge) {
        const proof = await verifyPinOtp(mobile, purpose, challenge.challenge_id, otp);
        setAuthorization(proof.authorization);
        setOtp("");
        setPin("");
        setMode("set");
      }
      else if(mode === "set") {
        if(pin !== confirm) {
          setError("PIN confirmation does not match.");
          return;
        }
        const result = await finishPin(authorization, pin, confirm, null);
        setAuthorization("");
        setPin("");
        setConfirm("");
        if("access_token" in result)
          authenticated(result);
        else
          setMode("success");
      }
    });
  }
  function start(p: Purpose) {
    setPurpose(p);
    setMode("start");
    setError(null);
    setPin("");
    setConfirm("");
    setOtp("");
  }
  const title = mode === "login" ? "Sign in with PIN"
    : mode === "success" ? "PIN reset successful"
    : mode === "set" ? (purpose === "FIRST_TIME_LOGIN" ? "Create 4-digit PIN" : "Create new PIN")
    : mode === "verify" ? "Verify your mobile"
    : purpose === "FIRST_TIME_LOGIN" ? "First-time verification" : "Forgot PIN";
  function backToLogin() {
    setMode("login");
    setAuthorization("");
    setPin("");
    setConfirm("");
    setOtp("");
    setError(null);
  }
  return (
    <div className="text-white">
      <h2 className="mb-5 text-lg font-semibold">{title}</h2>
      <ErrorBanner message={error} />
      {mode === "success" ? <>
        <p className="mb-4">Your previous PIN is no longer valid. Log in with your new PIN.</p>
        <button type="button" className="text-primary" onClick={backToLogin}>Return to login</button>
      </> : (
        <form onSubmit={e => { e.preventDefault(); void submit(); }}>
          {(mode === "login" || mode === "start") && (
            <FormField id="pin-mobile" label="Registered mobile number" required inputMode="numeric"
              pattern="[6-9][0-9]{9}" maxLength={10} autoComplete="tel-national" disabled={busy}
              value={mobile} onChange={e => setMobile(e.target.value)} />
          )}
          {mode === "verify" && <>
            <p className="mb-3 text-sm">Code for {challenge?.masked_mobile}. {challenge?.message}</p>
            <FormField id="pin-otp" label="4-digit OTP" type="password" required inputMode="numeric"
              pattern="[0-9]{4}" maxLength={4} autoComplete="one-time-code" disabled={busy}
              value={otp} onChange={e => setOtp(e.target.value)} />
            <p className="mb-3 text-sm">
              {now >= expiresAt ? "Code expired. Request a new code."
                : `Code expires in ${Math.max(0, Math.ceil((expiresAt - now) / 60000))} minutes.`}
            </p>
            <button type="button" className="mb-4 text-primary disabled:opacity-50"
              disabled={busy || now < resendAt} onClick={() => void act(issue)}>
              {now < resendAt ? `Resend in ${Math.ceil((resendAt - now) / 1000)}s` : "Resend OTP"}
            </button>
          </>}
          {(mode === "login" || mode === "set") && (
            <FormField id="login-pin" label={mode === "set" ? "New 4-digit PIN" : "4-digit PIN"}
              type="password" required inputMode="numeric" pattern="[0-9]{4}" maxLength={4} disabled={busy}
              autoComplete={mode === "set" ? "new-password" : "current-password"}
              value={pin} onChange={e => setPin(e.target.value)} />
          )}
          {mode === "set" && (
            <FormField id="confirm-pin" label="Confirm PIN" type="password" required inputMode="numeric"
              pattern="[0-9]{4}" maxLength={4} autoComplete="new-password" disabled={busy}
              value={confirm} onChange={e => setConfirm(e.target.value)} />
          )}
          <SubmitButton isSubmitting={busy} disabled={mode === "verify" && now >= expiresAt}>
            {mode === "login" ? "Log in" : mode === "start" ? "Send verification code"
              : mode === "verify" ? "Verify OTP" : "Save PIN"}
          </SubmitButton>
        </form>
      )}
      {mode === "login" ? (
        <div className="mt-4 grid gap-3 text-sm">
          <button type="button" className="text-primary" disabled={busy} onClick={() => start("FORGOT_PIN")}>Forgot PIN</button>
          <button type="button" className="text-primary" disabled={busy} onClick={() => start("FIRST_TIME_LOGIN")}>First-time verification / Create PIN</button>
          {policy === "enrollment" && <button type="button" className="text-white/70" disabled={busy} onClick={onLegacy}>
            Existing account migration: password sign-in
          </button>}
        </div>
      ) : mode !== "success" && (
        <button type="button" className="mt-4 text-primary" disabled={busy} onClick={backToLogin}>Back to login</button>
      )}
    </div>
  );
}
