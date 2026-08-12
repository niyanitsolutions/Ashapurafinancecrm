import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { login } from "@/features/auth/api";
import { ErrorBanner } from "@/features/auth/components/ErrorBanner";
import { FormField } from "@/features/auth/components/FormField";
import { PasswordField } from "@/features/auth/components/PasswordField";
import { SubmitButton } from "@/features/auth/components/SubmitButton";
import { getErrorMessage } from "@/features/auth/errors";
import { useAuth } from "@/features/auth/useAuth";
import { loginSchema, type LoginFormValues } from "@/features/auth/validation";

// `returnTo` rides in on a public, unauthenticated `?return=` query param — only ever
// follow it if it's a plain in-app path. A bare `/` prefix without a second leading slash
// rules out protocol-relative values (`//evil.com`) reaching `navigate()`.
function isSafeReturnPath(path: string): boolean {
  return /^\/(?!\/)/.test(path);
}

interface LoginFormProps {
  hidden: boolean;
  idPrefix: string;
  expectedRoles: readonly string[];
  wrongRoleMessage: string;
  returnTo: string | null;
  returnQuery: string;
  showCreateAccount?: boolean;
}

// One instance of this is mounted per tab (see LoginPage) and left in the DOM — hidden via
// CSS, never unmounted — so switching tabs preserves whatever the user already typed on the
// other tab. The backend has no notion of "login context"; `/auth/login` authenticates by
// mobile+password alone and returns whatever role that account actually has. Gating happens
// here, client-side, after a successful call: if the role that comes back isn't one this tab
// is for, the session is discarded (setSession is simply never called) and the user is told
// which tab to use instead — no backend change needed.
export function LoginForm({ hidden, idPrefix, expectedRoles, wrongRoleMessage, returnTo, returnQuery, showCreateAccount }: LoginFormProps) {
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const [apiError, setApiError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  const onSubmit = async (values: LoginFormValues) => {
    setApiError(null);
    try {
      const result = await login(values.mobile, values.password);
      if (!expectedRoles.includes(result.role)) {
        setApiError(wrongRoleMessage);
        return;
      }
      setSession({
        accessToken: result.access_token,
        refreshToken: result.refresh_token,
        role: result.role,
        userId: result.user_id,
        mustChangePassword: result.must_change_password,
      });
      navigate(returnTo && isSafeReturnPath(returnTo) ? returnTo : "/", { replace: true });
    } catch (err) {
      setApiError(getErrorMessage(err));
    }
  };

  return (
    <div className={hidden ? "hidden" : "animate-fade-in"}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <ErrorBanner message={apiError} />
        <FormField
          id={`${idPrefix}-mobile`}
          label="Mobile number"
          inputMode="numeric"
          maxLength={10}
          placeholder="10-digit mobile number"
          error={errors.mobile?.message}
          {...register("mobile")}
        />
        <PasswordField
          id={`${idPrefix}-password`}
          label="Password"
          error={errors.password?.message}
          {...register("password")}
        />
        <div className="flex justify-end mb-4 -mt-2">
          <Link to={`/forgot-password${returnQuery}`} className="text-sm text-primary hover:underline">
            Forgot password?
          </Link>
        </div>
        <SubmitButton isSubmitting={isSubmitting}>Log in</SubmitButton>
      </form>
      {showCreateAccount && (
        <p className="text-sm text-white/60 text-center mt-4">
          Don&apos;t have an account?{" "}
          <Link to={`/create-account${returnQuery}`} className="text-primary hover:underline">
            Create New Account
          </Link>
        </p>
      )}
    </div>
  );
}
