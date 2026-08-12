import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuthPageLayout } from "@/features/auth/components/AuthPageLayout";
import { ErrorBanner } from "@/features/auth/components/ErrorBanner";
import { FormField } from "@/features/auth/components/FormField";
import { isPasswordStrong, PasswordStrengthChecklist } from "@/features/auth/components/PasswordStrengthChecklist";
import { SubmitButton } from "@/features/auth/components/SubmitButton";
import { changePassword } from "@/features/auth/api";
import { getErrorMessage } from "@/features/auth/errors";
import { useAuth } from "@/features/auth/useAuth";

// Reached only when the current account has must_change_password set (Employees created
// with an Owner-set temporary password — see RequireAuth.tsx). Uses the same, unmodified
// /auth/change-password endpoint as the self-service ChangePasswordPage — the temporary
// password the Employee already knows is entered as "current password". No back link:
// RequireAuth re-routes here on every navigation until this succeeds.
export function ForceChangePasswordPage() {
  const navigate = useNavigate();
  const { clearMustChangePassword } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!isPasswordStrong(newPassword)) {
      setError("New password doesn't meet the requirements below.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation don't match.");
      return;
    }
    setIsSubmitting(true);
    try {
      await changePassword(currentPassword, newPassword);
      clearMustChangePassword();
      navigate("/", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthPageLayout title="Set a new password" subtitle="You must change your temporary password before continuing">
      <form onSubmit={onSubmit} noValidate>
        <ErrorBanner message={error} />
        <FormField
          label="Temporary Password"
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          required
        />
        <FormField
          label="New Password"
          type="password"
          minLength={8}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
        />
        <PasswordStrengthChecklist password={newPassword} />
        <FormField
          label="Confirm New Password"
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          required
        />
        <SubmitButton isSubmitting={isSubmitting}>Set Password</SubmitButton>
      </form>
    </AuthPageLayout>
  );
}
