import { useState } from "react";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { changePassword } from "@/features/auth/api";
import { isPasswordStrong, PasswordStrengthChecklist } from "@/features/auth/components/PasswordStrengthChecklist";
import { getErrorMessage } from "@/features/dashboard/errors";

// Uses Auth's existing POST /auth/change-password (Module 1, frozen) — the endpoint
// always existed, it just had no frontend page until this UI-navigation pass.
export function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setMessage(null);
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
      setMessage("Password updated.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SimplePageLayout title="Change Password" backTo="/profile">
      <div className="max-w-sm bg-card border border-border rounded-card shadow-card p-6">
        <form onSubmit={onSubmit} className="space-y-4">
          <ErrorBanner message={error} />
          {message && <p className="text-sm text-success">{message}</p>}
          <FormField label="Current Password" type="password" required value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
          <FormField label="New Password" type="password" required minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          <PasswordStrengthChecklist password={newPassword} />
          <FormField
            label="Confirm New Password" type="password" required value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
          <SubmitButton isSubmitting={isSubmitting}>Update Password</SubmitButton>
        </form>
      </div>
    </SimplePageLayout>
  );
}
