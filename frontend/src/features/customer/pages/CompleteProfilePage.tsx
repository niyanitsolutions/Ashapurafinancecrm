import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { completeOwnProfile, getOwnDashboard } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";

// Unified onboarding — the one shared profile-completion step every customer goes
// through right after authentication, Flow 1 (secure link) and Flow 2 (direct portal)
// alike (see docs/decisions/DECISIONS.md #047's supersession note — it used to be Flow
// 2 only, with Flow 1 collecting the same fields inline inside the application form).
// The backend links any pending Flow-1 application to the new Customer immediately
// (`CustomerService.complete_profile`), so once saved we just ask the dashboard whether
// there's an application to resume.
export function CompleteProfilePage() {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [panNumber, setPanNumber] = useState("");
  const [aadhaarNumber, setAadhaarNumber] = useState("");
  const [line1, setLine1] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [pincode, setPincode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await completeOwnProfile({
        full_name: fullName,
        email: email || undefined,
        date_of_birth: dateOfBirth || undefined,
        pan_number: panNumber || undefined,
        aadhaar_number: aadhaarNumber || undefined,
        address: line1 ? { line1, city, state, pincode } : undefined,
      });
      const dashboard = await getOwnDashboard();
      navigate(dashboard.has_application && dashboard.application_id ? `/portal/applications/${dashboard.application_id}` : "/portal");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-xl">
      <h1 className="text-xl font-semibold text-text mb-4">Complete your profile</h1>
      <form onSubmit={onSubmit} noValidate className="bg-card border border-border rounded-card shadow-card p-6">
        <ErrorBanner message={error} />
        <FormField label="Full Name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
        <FormField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <FormField label="Date of Birth" type="date" value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} />
        <FormField label="PAN Number" value={panNumber} onChange={(e) => setPanNumber(e.target.value)} />
        <FormField label="Aadhaar Number" value={aadhaarNumber} onChange={(e) => setAadhaarNumber(e.target.value)} />
        <FormField label="Address Line 1" value={line1} onChange={(e) => setLine1(e.target.value)} />
        <div className="grid grid-cols-3 gap-3">
          <FormField label="City" value={city} onChange={(e) => setCity(e.target.value)} />
          <FormField label="State" value={state} onChange={(e) => setState(e.target.value)} />
          <FormField label="Pincode" value={pincode} onChange={(e) => setPincode(e.target.value)} />
        </div>
        <SubmitButton isSubmitting={isSubmitting}>Save Profile</SubmitButton>
      </form>
    </div>
  );
}
